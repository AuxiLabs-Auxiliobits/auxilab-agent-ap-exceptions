"""Multi-provider AI client.

Provider precedence (set via env vars):
  1. ANTHROPIC_API_KEY                       → Claude (preferred)
  2. GEMINI_API_KEY                          → Google Gemini (fallback #1)
  3. AZURE_OPENAI_API_KEY + endpoint         → Azure OpenAI (fallback #2)
  4. none of the above                       → deterministic mock mode

All providers conform to the same `tool_call(...)` interface and return a
`ToolCallResult`, so downstream nodes never see provider-specific shapes.

Tool-use is forced on both providers — the model cannot reply with free
text. Schemas are authored once in JSON-Schema-lite form
(see app/ai/schemas.py) and are translated to each provider's native shape
at call time.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    RateLimitError,
)

from app.config import Settings, get_settings

log = logging.getLogger(__name__)


PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPT_VERSION = "classify.v1+drafting.v1"


def load_prompt(relative_path: str) -> str:
    p = PROMPTS_DIR / relative_path
    return p.read_text(encoding="utf-8")


def _extract_tag(text: str, tag: str) -> str | None:
    """Return the inner text of the LAST <tag>...</tag> block, or None if absent."""
    open_t = f"<{tag}>"
    close_t = f"</{tag}>"
    j = text.rfind(close_t)
    if j < 0:
        return None
    i = text.rfind(open_t, 0, j)
    if i < 0:
        return None
    return text[i + len(open_t):j].strip()


@dataclass
class ToolCallResult:
    name: str
    input: dict[str, Any]
    model_id: str
    stop_reason: str
    usage: dict[str, int]
    provider: str = "unknown"


_ANTHROPIC_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)


# ---------------------------------------------------------------------- #
# Client                                                                  #
# ---------------------------------------------------------------------- #


class ClaudeClient:
    """Multi-provider AI client.

    Historically named ClaudeClient. Now dispatches to Anthropic, Gemini, or
    a deterministic mock backend based on which API keys are configured.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._provider = self.settings.active_ai_provider
        self._sem = asyncio.Semaphore(self.settings.ai_max_concurrency)

        self._anthropic: AsyncAnthropic | None = None
        self._gemini: Any = None  # google.genai.Client, lazy-imported
        self._azure: Any = None   # openai.AsyncAzureOpenAI, lazy-imported

        if self._provider == "anthropic":
            self._anthropic = AsyncAnthropic(
                api_key=self.settings.anthropic_api_key,
                timeout=self.settings.ai_timeout_seconds,
            )
        elif self._provider == "gemini":
            self._gemini = self._init_gemini()
        elif self._provider == "azure":
            self._azure = self._init_azure()

        log.info(
            "AI client initialized: provider=%s endpoint=%s",
            self._provider,
            self.settings.azure_chat_openai_endpoint if self._provider == "azure" else "n/a",
        )

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def is_mock(self) -> bool:
        return self._provider == "mock"

    # ------------------------------------------------------------------ #
    # Provider init                                                       #
    # ------------------------------------------------------------------ #

    def _init_gemini(self):
        try:
            from google import genai  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "GEMINI_API_KEY is set but the 'google-genai' package is not "
                "installed. Run: pip install google-genai"
            ) from e
        return genai.Client(api_key=self.settings.gemini_api_key)

    def _init_azure(self):
        try:
            from openai import AsyncAzureOpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "AZURE_OPENAI_API_KEY is set but the 'openai' package is not "
                "installed. Run: pip install openai"
            ) from e
        return AsyncAzureOpenAI(
            api_key=self.settings.azure_openai_api_key,
            api_version=self.settings.azure_openai_version,
            azure_endpoint=self.settings.azure_chat_openai_endpoint,
            timeout=self.settings.ai_timeout_seconds,
        )

    # ------------------------------------------------------------------ #
    # Public call interface                                               #
    # ------------------------------------------------------------------ #

    async def tool_call(
        self,
        *,
        purpose: str,  # "classify" or "draft"
        system: str,
        user_text: str,
        tool: dict[str, Any],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> ToolCallResult:
        model = self.settings.model_for(purpose)

        async def _dispatch() -> ToolCallResult:
            if self._provider == "anthropic":
                return await self._anthropic_call(
                    model=model, system=system, user_text=user_text,
                    tool=tool, max_tokens=max_tokens, temperature=temperature,
                )
            if self._provider == "gemini":
                return await self._gemini_call(
                    model=model, system=system, user_text=user_text,
                    tool=tool, max_tokens=max_tokens, temperature=temperature,
                )
            if self._provider == "azure":
                return await self._azure_call(
                    model=model, system=system, user_text=user_text,
                    tool=tool, max_tokens=max_tokens, temperature=temperature,
                )
            return self._mock_response(tool, user_text, model_id=model)

        # Per-task wall-clock ceiling so a hung provider response (past the
        # retry/backoff budget) can't stall the whole run. Mock mode is sync
        # and instant, so the timeout only ever bites real providers.
        if self.is_mock:
            result = await _dispatch()
        else:
            result = await asyncio.wait_for(
                _dispatch(), timeout=self.settings.ai_task_timeout_seconds
            )

        # Single choke point for usage/cost accounting across every provider.
        try:
            from app.observability import record_ai_usage

            record_ai_usage(
                provider=result.provider,
                model=result.model_id,
                input_tokens=int(result.usage.get("input_tokens", 0) or 0),
                output_tokens=int(result.usage.get("output_tokens", 0) or 0),
            )
        except Exception:  # noqa: BLE001 — metrics must never break a call
            log.debug("metrics: record_ai_usage failed", exc_info=True)

        return result

    # ------------------------------------------------------------------ #
    # Anthropic path                                                      #
    # ------------------------------------------------------------------ #

    async def _anthropic_call(
        self,
        *,
        model: str,
        system: str,
        user_text: str,
        tool: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> ToolCallResult:
        assert self._anthropic is not None
        attempts = 0
        last_exc: Exception | None = None
        while attempts < self.settings.ai_max_retries:
            attempts += 1
            try:
                async with self._sem:
                    resp = await self._anthropic.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=[
                            {
                                "type": "text",
                                "text": system,
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                        tools=[tool],
                        tool_choice={"type": "tool", "name": tool["name"]},
                        messages=[{"role": "user", "content": user_text}],
                    )
                for block in resp.content:
                    if getattr(block, "type", None) == "tool_use":
                        return ToolCallResult(
                            name=block.name,
                            input=dict(block.input),
                            model_id=resp.model,
                            stop_reason=resp.stop_reason or "",
                            usage={
                                "input_tokens": resp.usage.input_tokens,
                                "output_tokens": resp.usage.output_tokens,
                            },
                            provider="anthropic",
                        )
                raise RuntimeError("Anthropic returned no tool_use block")
            except _ANTHROPIC_RETRYABLE as e:
                last_exc = e
                backoff = (2 ** (attempts - 1)) + random.random() * 0.5
                log.warning(
                    "Anthropic transient error attempt=%d backoff=%.2fs err=%s",
                    attempts,
                    backoff,
                    e,
                )
                await asyncio.sleep(backoff)
            except APIStatusError:
                raise
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------ #
    # Gemini path                                                         #
    # ------------------------------------------------------------------ #

    async def _gemini_call(
        self,
        *,
        model: str,
        system: str,
        user_text: str,
        tool: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> ToolCallResult:
        from google.genai import types as gt  # type: ignore

        # Translate our JSON-Schema-lite tool spec into Gemini's
        # FunctionDeclaration. Strip keys Gemini's validator dislikes.
        params_schema = _to_gemini_schema(tool["input_schema"])
        fn_decl = gt.FunctionDeclaration(
            name=tool["name"],
            description=tool["description"],
            parameters=params_schema,
        )
        gemini_tool = gt.Tool(function_declarations=[fn_decl])
        config = gt.GenerateContentConfig(
            system_instruction=system,
            tools=[gemini_tool],
            tool_config=gt.ToolConfig(
                function_calling_config=gt.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[tool["name"]],
                )
            ),
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Cap how long we'll wait for a single tool_call across all retries.
        # If the server demands retry_after > this, we bail to the fallback
        # rather than hold the request hostage.
        max_wait_budget_s = 20.0

        attempts = 0
        last_exc: Exception | None = None
        while attempts < self.settings.ai_max_retries:
            attempts += 1
            try:
                async with self._sem:
                    resp = await self._gemini.aio.models.generate_content(
                        model=model,
                        contents=user_text,
                        config=config,
                    )
                fc = _first_function_call(resp)
                if fc is None:
                    raise RuntimeError("Gemini returned no function_call")
                usage = getattr(resp, "usage_metadata", None)
                return ToolCallResult(
                    name=fc.name,
                    input=dict(fc.args or {}),
                    model_id=model,
                    stop_reason="tool_use",
                    usage={
                        "input_tokens": int(
                            getattr(usage, "prompt_token_count", 0) or 0
                        ),
                        "output_tokens": int(
                            getattr(usage, "candidates_token_count", 0) or 0
                        ),
                    },
                    provider="gemini",
                )
            except Exception as e:  # noqa: BLE001
                if not _is_gemini_retryable(e):
                    raise
                last_exc = e
                short_err, server_retry_s = _summarize_gemini_error(e)
                # Prefer the server's retryDelay when it gives us one,
                # but cap with our own exponential backoff ceiling.
                bo = (2 ** (attempts - 1)) + random.random() * 0.5
                if server_retry_s is not None and server_retry_s > max_wait_budget_s:
                    log.warning(
                        "Gemini %s — server requested retry in %.0fs, "
                        "exceeds budget %.0fs; giving up after attempt=%d",
                        short_err,
                        server_retry_s,
                        max_wait_budget_s,
                        attempts,
                    )
                    raise
                if server_retry_s is not None:
                    bo = max(bo, min(server_retry_s + 0.5, max_wait_budget_s))
                log.warning(
                    "Gemini %s attempt=%d/%d backoff=%.2fs (server_retry=%s)",
                    short_err,
                    attempts,
                    self.settings.ai_max_retries,
                    bo,
                    f"{server_retry_s:.0f}s" if server_retry_s else "n/a",
                )
                await asyncio.sleep(bo)
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------ #
    # Azure OpenAI path                                                   #
    # ------------------------------------------------------------------ #

    async def _azure_call(
        self,
        *,
        model: str,  # Azure deployment name
        system: str,
        user_text: str,
        tool: dict[str, Any],
        max_tokens: int,
        temperature: float,
    ) -> ToolCallResult:
        from openai import APIConnectionError as OAIConnErr  # type: ignore
        from openai import APIStatusError as OAIStatusErr  # type: ignore
        from openai import APITimeoutError as OAITimeoutErr  # type: ignore
        from openai import RateLimitError as OAIRateLimitErr  # type: ignore

        retryable = (OAIConnErr, OAITimeoutErr, OAIRateLimitErr)

        # Translate our JSON-Schema-lite tool spec into OpenAI's function-call shape.
        params_schema = _to_openai_schema(tool["input_schema"])
        oai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": params_schema,
            },
        }
        tool_choice = {
            "type": "function",
            "function": {"name": tool["name"]},
        }
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ]

        attempts = 0
        last_exc: Exception | None = None
        while attempts < self.settings.ai_max_retries:
            attempts += 1
            try:
                async with self._sem:
                    resp = await self._azure.chat.completions.create(
                        model=model,  # deployment name on Azure
                        messages=messages,
                        tools=[oai_tool],
                        tool_choice=tool_choice,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                choice = resp.choices[0].message
                if not choice.tool_calls:
                    raise RuntimeError(
                        "Azure OpenAI returned no tool_call (finish_reason="
                        f"{resp.choices[0].finish_reason})"
                    )
                tc = choice.tool_calls[0]
                args = json.loads(tc.function.arguments or "{}")
                usage = resp.usage
                return ToolCallResult(
                    name=tc.function.name,
                    input=args,
                    model_id=resp.model or model,
                    stop_reason=resp.choices[0].finish_reason or "tool_calls",
                    usage={
                        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
                        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
                    },
                    provider="azure",
                )
            except retryable as e:
                last_exc = e
                backoff = (2 ** (attempts - 1)) + random.random() * 0.5
                log.warning(
                    "Azure %s attempt=%d/%d backoff=%.2fs",
                    type(e).__name__,
                    attempts,
                    self.settings.ai_max_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
            except OAIStatusErr:
                # Non-retryable 4xx (bad request, auth, etc.) — surface immediately.
                raise
        assert last_exc is not None
        raise last_exc

    # ------------------------------------------------------------------ #
    # Mock path                                                           #
    # ------------------------------------------------------------------ #

    def _mock_response(
        self,
        tool: dict[str, Any],
        user_text: str,
        model_id: str = "mock",
    ) -> ToolCallResult:
        if tool["name"] == "emit_classification":
            payload = self._mock_classification(user_text)
            mid = model_id or "mock-classify"
        elif tool["name"] == "emit_draft":
            payload = self._mock_draft(user_text)
            mid = model_id or "mock-draft"
        else:
            payload = {}
            mid = model_id or "mock"
        return ToolCallResult(
            name=tool["name"],
            input=payload,
            model_id=mid,
            stop_reason="tool_use",
            usage={"input_tokens": 0, "output_tokens": 0},
            provider="mock",
        )

    @staticmethod
    def _mock_classification(user_text: str) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for candidate in (user_text, _extract_tag(user_text, "exception")):
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
                break
            except Exception:
                continue
        et = (data.get("exception_type") or "Other").strip()
        canonical = {
            "Price Variance",
            "Quantity Mismatch",
            "Missing PO",
            "Duplicate",
            "Unapproved Vendor",
            "GRN Not Received",
        }
        primary = et if et in canonical else "Other"
        amount = float(data.get("invoice_amount") or 0)
        days = int(data.get("days_outstanding") or 0)
        if amount > 25_000 or days > 30:
            sev = "HIGH"
        elif amount >= 5_000:
            sev = "MEDIUM"
        else:
            sev = "LOW"
        return {
            "invoice_id": data.get("invoice_id", "UNKNOWN"),
            "primary_exception_type": primary,
            "root_cause": f"Mock classification based on declared type {et!r}.",
            "severity": sev,
            "confidence_score": 0.82 if primary != "Other" else 0.45,
            "rationale": (
                "Mock mode: echoed ERP-declared type; deterministic severity "
                "from amount/age thresholds."
            ),
        }

    @staticmethod
    def _mock_draft(user_text: str) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for candidate in (user_text, _extract_tag(user_text, "context")):
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
                break
            except Exception:
                continue
        ctx = data.get("context", data) if isinstance(data, dict) else {}
        invoice = ctx.get("invoice_id", "INV-?")
        vendor = ctx.get("vendor_name", "Vendor")
        sla = ctx.get("sla_hours", 48)
        return {
            "subject": f"Action required: {invoice}",
            "body": (
                f"Hello {vendor} team,\n\n"
                f"We are following up on invoice {invoice}. Please review the "
                f"attached exception and respond within {sla} hours so we can "
                f"continue processing.\n\n"
                f"Regards,\nAccounts Payable Operations"
            ),
        }


# ---------------------------------------------------------------------- #
# Gemini helpers                                                          #
# ---------------------------------------------------------------------- #


# Keys that JSON Schema supports but Gemini's parameter validator rejects.
_GEMINI_DROP_KEYS = {"additionalProperties", "$schema", "$id"}


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip keys Gemini's schema validator does not accept."""
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in _GEMINI_DROP_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {pk: _to_gemini_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _to_gemini_schema(v) if isinstance(v, dict) else v
        else:
            out[k] = v
    return out


_OPENAI_DROP_KEYS = {"$schema", "$id"}


def _to_openai_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Trim keys OpenAI's function-call validator doesn't accept.

    Unlike Gemini, OpenAI is fine with `additionalProperties: false`, so we
    keep that — it makes tool outputs stricter.
    """
    if not isinstance(schema, dict):
        return schema
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k in _OPENAI_DROP_KEYS:
            continue
        if k == "properties" and isinstance(v, dict):
            out[k] = {pk: _to_openai_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = _to_openai_schema(v) if isinstance(v, dict) else v
        else:
            out[k] = v
    return out


def _first_function_call(resp: Any):
    for cand in getattr(resp, "candidates", None) or []:
        content = getattr(cand, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", None) or []:
            fc = getattr(part, "function_call", None)
            if fc and getattr(fc, "name", None):
                return fc
    return None


_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s")
_HUMAN_RETRY_RE = re.compile(r"retry in\s+(\d+(?:\.\d+)?)s", re.IGNORECASE)


def _summarize_gemini_error(exc: Exception) -> tuple[str, float | None]:
    """Pull (short_status, retry_after_seconds) out of a Gemini error.

    The raw 429 message is a ~3 KB JSON blob; we surface just the bits a
    human needs to triage: HTTP code, status name, and the API's own
    retryDelay hint if present.
    """
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    status = getattr(exc, "status", None)
    msg = str(exc)
    if not status:
        # try to scrape "'status': 'RESOURCE_EXHAUSTED'"
        m = re.search(r"'status':\s*'([A-Z_]+)'", msg)
        status = m.group(1) if m else None

    retry_s: float | None = None
    m = _RETRY_DELAY_RE.search(msg) or _HUMAN_RETRY_RE.search(msg)
    if m:
        try:
            retry_s = float(m.group(1))
        except ValueError:
            retry_s = None

    short = f"{type(exc).__name__}({code or '?'}/{status or '?'})"
    return short, retry_s


def _is_gemini_retryable(exc: Exception) -> bool:
    """Best-effort classification for Gemini errors.

    google-genai raises errors derived from google.genai.errors.APIError; we
    treat 408/429/5xx and network/timeout errors as retryable. Anything else
    bubbles up (schema rejections, auth failures).
    """
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and (code == 408 or code == 429 or 500 <= code < 600):
        return True
    name = type(exc).__name__.lower()
    if any(s in name for s in ("timeout", "connection", "transport", "service")):
        return True
    msg = str(exc).lower()
    if "rate limit" in msg or "deadline" in msg or "unavailable" in msg:
        return True
    return False
