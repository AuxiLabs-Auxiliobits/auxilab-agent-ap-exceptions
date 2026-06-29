"""Ingest node — deterministic. Parses + validates the exception queue.

Two-tier validation:
  - File-level failures (empty, unparseable, duplicate columns, missing required
    columns) FAIL the whole run.
  - Row-level failures (bad types, negative amount, missing value, duplicate
    invoice_id, future date) QUARANTINE that row and continue.

Header aliasing, coercion, and the reason taxonomy live in app.upload_format so
the API (template / format spec / rejection download) can't drift from ingest.
"""
from __future__ import annotations

import hashlib
import io
import logging
from datetime import UTC
from decimal import InvalidOperation

import pandas as pd
from pydantic import ValidationError

from app.audit.logger import make_event
from app.graph.state import RunState
from app.schemas import (
    AuditEventType,
    ExceptionRow,
    NodeError,
    QuarantinedRow,
    RunStatus,
)
from app.upload_format import (
    CORE_REQUIRED,
    DATE_COLUMNS,
    RowReject,
    find_duplicate_columns,
    friendly_reason,
    prepare_model_row,
    raw_csv_headers,
    resolve_columns,
    sniff_delimiter,
)

log = logging.getLogger("ap_agent.ingest")


def _read_table(content: bytes, filename: str) -> pd.DataFrame:
    bio = io.BytesIO(content)
    name = filename.lower()
    if name.endswith(".json"):
        return pd.read_json(bio, dtype=False)
    # Auto-detect the delimiter (, ; tab |) and strip a UTF-8 BOM.
    return pd.read_csv(
        bio,
        dtype=str,
        keep_default_na=False,
        sep=sniff_delimiter(content),
        encoding="utf-8-sig",
        engine="python",
    )


def _utcnow():
    from datetime import datetime
    return datetime.now(UTC)


def _jsonable(raw: dict) -> dict:
    """Stringify a record so it round-trips through JSON (rejection report / API)."""
    return {str(k): ("" if v is None else str(v)) for k, v in raw.items()}


def _fail(state: RunState, audit: list, errors: list, error_class: str, message: str) -> RunState:
    errors.append(
        NodeError(
            node_name="ingest_node",
            error_class=error_class,
            message=message,
            timestamp=_utcnow(),
        )
    )
    state["errors"] = errors
    state["status"] = RunStatus.FAILED
    state["audit_events"] = audit
    log.warning("ingest: file rejected (%s): %s", error_class, message)
    return state


def ingest_from_bytes(
    state: RunState,
    *,
    content: bytes,
    filename: str,
) -> RunState:
    """Pure function. Mutates a copy of state and returns it."""
    state = dict(state)  # shallow copy
    state["current_node"] = "ingest_node"
    state["status"] = RunStatus.RUNNING

    audit = list(state.get("audit_events", []))
    errors = list(state.get("errors", []))

    file_hash = hashlib.sha256(content).hexdigest()
    state["source_file_hash"] = file_hash
    state["source_filename"] = filename

    audit.append(
        make_event(
            run_id=state["run_id"],
            node_name="ingest_node",
            event_type=AuditEventType.NODE_START,
            metadata={"filename": filename, "file_hash": file_hash},
        )
    )

    # ---- File-level gate 1: empty -----------------------------------------
    if not content or not content.strip():
        return _fail(state, audit, errors, "EmptyFile", "The uploaded file is empty.")

    # ---- File-level gate 2: duplicate columns (CSV literal headers) -------
    if filename.lower().endswith(".csv"):
        dups = find_duplicate_columns(raw_csv_headers(content))
        if dups:
            return _fail(
                state, audit, errors, "DuplicateColumn",
                f"Duplicate column(s) detected: {dups}. Keep exactly one of each.",
            )

    # ---- File-level gate 3: parse -----------------------------------------
    try:
        df = _read_table(content, filename)
    except Exception as e:  # noqa: BLE001
        return _fail(state, audit, errors, type(e).__name__, f"Could not parse file: {e}")

    if df is None or df.shape[1] == 0:
        return _fail(
            state, audit, errors, "ParseError",
            "No columns were found — check the file format / delimiter.",
        )

    # ---- Smart column mapping (alias detection) ---------------------------
    rename_map, unknown_cols, dup_canon = resolve_columns([str(c) for c in df.columns])
    if dup_canon:
        return _fail(
            state, audit, errors, "DuplicateColumn",
            f"Multiple columns map to the same field: {dup_canon}. Keep one of each.",
        )
    if rename_map:
        df = df.rename(columns=rename_map)
        log.info("ingest: auto-mapped columns %s", rename_map)

    # ---- File-level gate 4: required columns ------------------------------
    present = {str(c) for c in df.columns}
    missing = CORE_REQUIRED - present
    if missing:
        return _fail(
            state, audit, errors, "SchemaError",
            f"Missing required column(s): {sorted(missing)}.",
        )
    if not (DATE_COLUMNS & present):
        return _fail(
            state, audit, errors, "SchemaError",
            "Provide either 'days_outstanding' or 'invoice_date'.",
        )
    if unknown_cols:
        log.info("ingest: ignoring unrecognized columns: %s", sorted(unknown_cols))

    # ---- Row-level validation ---------------------------------------------
    rows: list[ExceptionRow] = []
    quarantined: list[QuarantinedRow] = []
    seen_ids: set[str] = set()
    log.info(
        "ingest: parsing file=%s bytes=%d rows=%d hash=%s unknown_cols=%d",
        filename, len(content), len(df), file_hash[:12], len(unknown_cols),
    )

    for idx, raw in enumerate(df.to_dict(orient="records")):
        try:
            prepared = prepare_model_row(raw)
            inv = str(prepared.get("invoice_id", "") or "").strip()
            if inv and inv.upper() in seen_ids:
                raise RowReject(
                    "DUPLICATE_INVOICE_ID",
                    f"Duplicate invoice_id '{inv}' already present earlier in this file.",
                )
            row = ExceptionRow.model_validate(prepared)
            seen_ids.add(row.invoice_id.upper())
            rows.append(row)
        except RowReject as rj:
            quarantined.append(
                QuarantinedRow(row_index=idx, raw=_jsonable(raw), reason_code=rj.code, reason=rj.message[:500])
            )
            _audit_quarantine(audit, state, idx, raw, rj.message)
        except (ValidationError, InvalidOperation, ValueError) as e:
            code, msg = friendly_reason(e)
            quarantined.append(
                QuarantinedRow(row_index=idx, raw=_jsonable(raw), reason_code=code, reason=msg)
            )
            _audit_quarantine(audit, state, idx, raw, msg)

    state["rows"] = rows
    state["quarantined"] = quarantined
    state["errors"] = errors

    audit.append(
        make_event(
            run_id=state["run_id"],
            node_name="ingest_node",
            event_type=AuditEventType.NODE_END,
            metadata={
                "rows_accepted": len(rows),
                "rows_quarantined": len(quarantined),
            },
        )
    )
    state["audit_events"] = audit
    return state


def _audit_quarantine(audit: list, state: RunState, idx: int, raw: dict, reason: str) -> None:
    log.warning(
        "ingest: quarantined row idx=%d invoice_id=%s reason=%s",
        idx, raw.get("invoice_id") or f"row_{idx}", reason[:120],
    )
    audit.append(
        make_event(
            run_id=state["run_id"],
            node_name="ingest_node",
            event_type=AuditEventType.INGEST_QUARANTINE,
            invoice_id=str(raw.get("invoice_id") or f"row_{idx}"),
            metadata={"reason": reason[:500]},
        )
    )


# LangGraph node entrypoint expects (state) -> state. The file bytes are
# attached to state under the key "_input_bytes" by the API layer prior to
# graph invocation.
def ingest_node(state: RunState) -> RunState:
    from app.graph._logging import step_log

    content = state.get("_input_bytes")  # type: ignore[assignment]
    filename = state.get("_input_filename", "exception_queue.csv")  # type: ignore[assignment]
    if content is None:
        raise RuntimeError("ingest_node: missing _input_bytes in state")
    with step_log("ingest_node", state) as info:
        out = ingest_from_bytes(state, content=content, filename=filename)
        info["accepted"] = len(out.get("rows", []))
        info["quarantined"] = len(out.get("quarantined", []))
        info["status"] = out.get("status")
    # Strip the transient input from state — never persist raw bytes.
    out.pop("_input_bytes", None)  # type: ignore[arg-type]
    out.pop("_input_filename", None)  # type: ignore[arg-type]
    return out
