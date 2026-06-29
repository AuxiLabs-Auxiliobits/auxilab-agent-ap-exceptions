"""File-backed VendorProfileStore.

Persists per-vendor history to a single JSON file on disk so profiles
survive process restarts. Thread-safe via an RLock. Reads are O(1)
(in-memory dict); writes touch the disk once per `observe()`.

This is the deliberate "v1" implementation. For production scale, swap
the JSON file for a row-per-vendor table in Postgres — the public
interface here (get, get_all, observe) is designed so that swap is a
single-module change.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings, get_settings
from app.rules.engine import parse_variance_pct
from app.schemas import (
    ClassificationResult,
    ExceptionRow,
    PrimaryExceptionType,
    ResolutionDecision,
    ResolutionPath,
    VendorProfile,
)

log = logging.getLogger("ap_agent.vendor")


def _now() -> datetime:
    return datetime.now(UTC)


def _rolling_mean(prev: float, count: int, new: float) -> float:
    """Update a running mean given previous-count observations."""
    if count <= 0:
        return new
    return ((prev * count) + new) / (count + 1)


def _rolling_mean_opt(
    prev: float | None, count: int, new: float | None
) -> float | None:
    """Rolling mean that tolerates missing observations."""
    if new is None:
        return prev
    if prev is None or count <= 0:
        return new
    return ((prev * count) + new) / (count + 1)


def _fold_observation(
    existing: VendorProfile | None,
    row: ExceptionRow,
    classification: ClassificationResult,
    resolution: ResolutionDecision,
) -> VendorProfile:
    """Pure function: fold one observation into a vendor profile.

    Shared by the file-backed and DB-backed stores so the update math lives in
    exactly one place.
    """
    now = _now()
    if existing is None:
        profile = VendorProfile(vendor_name=row.vendor_name, first_seen_at=now, last_seen_at=now)
        n_prev = 0
    else:
        profile = existing.model_copy(deep=True)
        n_prev = profile.total_invoices_seen

    variance = parse_variance_pct(row.exception_description)
    return profile.model_copy(
        update={
            "total_invoices_seen": n_prev + 1,
            "total_amount_processed": profile.total_amount_processed + row.invoice_amount,
            "exception_type_counts": _bump(
                profile.exception_type_counts, classification.primary_exception_type.value
            ),
            "resolution_path_counts": _bump(
                profile.resolution_path_counts, resolution.resolution_path.value
            ),
            "average_variance_pct": _rolling_mean_opt(
                profile.average_variance_pct, n_prev, variance
            ),
            "average_days_outstanding": _rolling_mean(
                profile.average_days_outstanding, n_prev, float(row.days_outstanding)
            ),
            "average_confidence": _rolling_mean(
                profile.average_confidence, n_prev, float(classification.confidence_score)
            ),
            "duplicate_count": profile.duplicate_count
            + (1 if classification.primary_exception_type == PrimaryExceptionType.DUPLICATE else 0),
            "auto_approved_count": profile.auto_approved_count
            + (1 if resolution.resolution_path == ResolutionPath.AUTO_APPROVE else 0),
            "escalated_count": profile.escalated_count
            + (1 if resolution.resolution_path == ResolutionPath.ESCALATE_CONTROLLER else 0),
            "missing_po_count": profile.missing_po_count
            + (1 if classification.primary_exception_type == PrimaryExceptionType.MISSING_PO else 0),
            "unapproved_vendor_count": profile.unapproved_vendor_count
            + (
                1
                if classification.primary_exception_type == PrimaryExceptionType.UNAPPROVED_VENDOR
                else 0
            ),
            "last_seen_at": now,
        }
    )


class VendorProfileStore:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._lock = threading.RLock()
        self._profiles: dict[str, VendorProfile] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            log.info("vendor: no profile file at %s — starting empty", self._path)
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            log.error("vendor: profile file corrupt (%s); refusing to load", e)
            return
        for name, p in raw.items():
            try:
                self._profiles[name] = VendorProfile.model_validate(p)
            except Exception as e:  # noqa: BLE001
                log.warning("vendor: dropping bad profile %s: %s", name, e)
        log.info("vendor: loaded %d profile(s) from %s", len(self._profiles), self._path)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            name: p.model_dump(mode="json") for name, p in self._profiles.items()
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._path)

    # ------------------------------------------------------------------ #
    # Read API                                                            #
    # ------------------------------------------------------------------ #

    def get(self, vendor_name: str) -> VendorProfile | None:
        with self._lock:
            return self._profiles.get(vendor_name)

    def get_all(self) -> list[VendorProfile]:
        with self._lock:
            # Sorted by total_invoices_seen DESC so the most-active vendors come first.
            return sorted(
                self._profiles.values(),
                key=lambda p: -p.total_invoices_seen,
            )

    def count(self) -> int:
        with self._lock:
            return len(self._profiles)

    # ------------------------------------------------------------------ #
    # Write API                                                           #
    # ------------------------------------------------------------------ #

    def observe(
        self,
        row: ExceptionRow,
        classification: ClassificationResult,
        resolution: ResolutionDecision,
    ) -> VendorProfile:
        """Fold one observation into the vendor's profile. Returns the updated profile."""
        with self._lock:
            updated = _fold_observation(
                self._profiles.get(row.vendor_name), row, classification, resolution
            )
            self._profiles[updated.vendor_name] = updated
            return updated

    def flush(self) -> None:
        """Persist the in-memory state to disk. Call once per run, not per observation."""
        with self._lock:
            self._save()


def _bump(d: dict[str, int], key: str) -> dict[str, int]:
    out = dict(d)
    out[key] = out.get(key, 0) + 1
    return out


# Global vendor master (the file store was already tenant-agnostic). Keyed so
# the id matches what the normalized persistence layer uses for exception FKs.
_VENDOR_NS = uuid.UUID("0a5e8b9c-2d3f-4a1b-8c7d-1e2f3a4b5c6d")
_VENDOR_TENANT = "default"


def vendor_id_for(name: str):
    """Deterministic vendor row id — shared by the store and persistence."""
    return uuid.uuid5(_VENDOR_NS, f"vendor:{name}")


class DbVendorProfileStore:
    """Vendor profile store backed by the `vendors` table.

    Concurrency-safe: each ``observe`` is an atomic read-modify-write in its own
    transaction (SELECT ... FOR UPDATE on Postgres; SQLite serializes writes),
    with an insert/update retry to absorb the new-vendor race. The full
    ``VendorProfile`` lives in the ``profile`` JSON column, with the indexed
    scalar columns kept in sync for queries.
    """

    def __init__(self) -> None:
        from app.db.session import init_db

        init_db()

    def _sync_columns(self, vendor, profile: VendorProfile) -> None:
        vendor.tenant_id = _VENDOR_TENANT
        vendor.vendor_name = profile.vendor_name
        vendor.total_invoices_seen = profile.total_invoices_seen
        vendor.total_amount_processed = profile.total_amount_processed
        vendor.reliability_score = profile.reliability_score()
        vendor.exception_type_counts = dict(profile.exception_type_counts)
        vendor.first_seen_at = profile.first_seen_at
        vendor.last_seen_at = profile.last_seen_at
        vendor.profile = profile.model_dump(mode="json")

    def get(self, vendor_name: str) -> VendorProfile | None:
        from app.db import models as m
        from app.db.session import session_scope

        with session_scope() as s:
            v = s.get(m.Vendor, vendor_id_for(vendor_name))
            if v is None or not v.profile:
                return None
            return VendorProfile.model_validate(v.profile)

    def get_all(self) -> list[VendorProfile]:
        from sqlalchemy import select

        from app.db import models as m
        from app.db.session import session_scope

        with session_scope() as s:
            rows = s.scalars(
                select(m.Vendor).where(m.Vendor.tenant_id == _VENDOR_TENANT)
            ).all()
            profiles = [VendorProfile.model_validate(r.profile) for r in rows if r.profile]
            return sorted(profiles, key=lambda p: -p.total_invoices_seen)

    def count(self) -> int:
        from sqlalchemy import func, select

        from app.db import models as m
        from app.db.session import session_scope

        with session_scope() as s:
            # Vendors with an actual observation (persistence may add bare FK rows).
            return (
                s.scalar(
                    select(func.count())
                    .select_from(m.Vendor)
                    .where(m.Vendor.tenant_id == _VENDOR_TENANT, m.Vendor.total_invoices_seen > 0)
                )
                or 0
            )

    def observe(
        self,
        row: ExceptionRow,
        classification: ClassificationResult,
        resolution: ResolutionDecision,
    ) -> VendorProfile:
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from app.db import models as m
        from app.db.session import session_scope

        vid = vendor_id_for(row.vendor_name)
        for attempt in range(2):
            try:
                with session_scope() as s:
                    stmt = select(m.Vendor).where(m.Vendor.vendor_id == vid)
                    if s.bind.dialect.name != "sqlite":
                        stmt = stmt.with_for_update()  # row lock on Postgres
                    v = s.scalars(stmt).first()
                    existing = (
                        VendorProfile.model_validate(v.profile) if (v and v.profile) else None
                    )
                    updated = _fold_observation(existing, row, classification, resolution)
                    if v is None:
                        v = m.Vendor(vendor_id=vid)
                        self._sync_columns(v, updated)
                        s.add(v)
                    else:
                        self._sync_columns(v, updated)
                    return updated
            except IntegrityError:
                if attempt == 0:
                    continue  # concurrent insert — retry, now as an update
                raise

    def flush(self) -> None:
        """No-op: each observe() commits its own transaction."""


# ---------------------------------------------------------------------- #
# Singleton                                                               #
# ---------------------------------------------------------------------- #

_STORE: VendorProfileStore | DbVendorProfileStore | None = None
_STORE_LOCK = threading.Lock()


def get_vendor_store(settings: Settings | None = None):
    """Return the process-wide vendor store.

    DB-backed when DB persistence is enabled (durable + concurrency-safe);
    otherwise the file-backed store (dev default).
    """
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                s = settings or get_settings()
                if s.db_persistence_enabled:
                    try:
                        _STORE = DbVendorProfileStore()
                    except Exception:  # noqa: BLE001
                        log.exception("DB vendor store init failed — using file store")
                        _STORE = VendorProfileStore(s.vendor_profiles_path)
                else:
                    _STORE = VendorProfileStore(s.vendor_profiles_path)
    return _STORE


def reset_vendor_store() -> None:
    """Test helper — drops the singleton so a fresh store is built next time."""
    global _STORE
    with _STORE_LOCK:
        _STORE = None
