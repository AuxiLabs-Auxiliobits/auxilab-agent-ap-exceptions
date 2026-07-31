"""
Shared LLM Client — Provider Abstraction Layer

Reads LLM_PROVIDER from the environment and routes all LLM calls to either:
  - gemini  (default) — google.generativeai GenerativeModel
  - claude            — anthropic.Anthropic messages API

Usage (all existing call sites):
    from .llm_client import SharedLLMClient

    response_text, latency_ms = SharedLLMClient.generate(prompt)
    response_text, latency_ms = SharedLLMClient.generate(prompt, max_retries=5)

Environment variables:
    LLM_PROVIDER          = "gemini" | "claude"    (default: gemini)
    GEMINI_API_KEY        = ...                     (required for gemini)
    GEMINI_PRO_MODEL      = ...                     (default: gemini-2.5-pro)
    ANTHROPIC_API_KEY     = ...                     (required for claude)
    ANTHROPIC_MODEL       = ...                     (default: claude-sonnet-4-5)
    API_CALL_DELAY_SECONDS = ...                    (default: 1.0)
    DEMO_MODE             = "true"                  (skips all LLM calls)
"""

import logging
import os
import time

logger = logging.getLogger("APException.LLMClient")

# ---------------------------------------------------------------------------
# Provider constants
# ---------------------------------------------------------------------------

PROVIDER_GEMINI = "gemini"
PROVIDER_CLAUDE = "claude"
_VALID_PROVIDERS = {PROVIDER_GEMINI, PROVIDER_CLAUDE}

# ---------------------------------------------------------------------------
# Config helpers (mirrors core/config.py but self-contained for import safety)
# ---------------------------------------------------------------------------


def _get_provider() -> str:
    """Return the active LLM provider name (lower-cased, validated)."""
    raw = os.getenv("LLM_PROVIDER", PROVIDER_GEMINI).strip().lower()
    if raw not in _VALID_PROVIDERS:
        logger.warning(
            f"Unknown LLM_PROVIDER '{raw}'. "
            f"Valid values: {sorted(_VALID_PROVIDERS)}. "
            f"Falling back to '{PROVIDER_GEMINI}'."
        )
        return PROVIDER_GEMINI
    return raw


def _get_llm_call_delay() -> float:
    return float(os.getenv("API_CALL_DELAY_SECONDS", "1.0"))


def _is_demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------


class _GeminiBackend:
    """Lazy-initialized google.generativeai backend."""

    _model = None

    @classmethod
    def _get_model(cls):
        if cls._model is None:
            try:
                import google.generativeai as genai  # noqa: PLC0415
            except ImportError:
                raise ImportError(
                    "google-generativeai is required for LLM_PROVIDER=gemini. "
                    "Install with: pip install google-generativeai"
                ) from None

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not set. "
                    "Add it to your .env file or set DEMO_MODE=true to skip LLM calls."
                )

            model_name = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")
            genai.configure(api_key=api_key)
            cls._model = genai.GenerativeModel(
                model_name,
                generation_config={"temperature": 0},
            )
            logger.info(f"[LLMClient] Initialized Gemini backend: {model_name}")
        return cls._model

    @classmethod
    def generate(cls, prompt: str, max_retries: int = 5) -> tuple[str, float]:
        """Call Gemini and return (response_text, latency_ms) with retry on 429."""
        model = cls._get_model()
        for attempt in range(max_retries):
            try:
                start = time.time()
                response = model.generate_content(prompt)
                latency_ms = (time.time() - start) * 1000
                return response.text.strip(), latency_ms
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = (
                    "429" in err_str
                    or "resource exhausted" in err_str
                    or "quota" in err_str
                )
                if is_rate_limit and attempt < max_retries - 1:
                    backoff = (2 ** attempt) + 2  # 3s, 4s, 6s, 10s, 18s
                    logger.warning(
                        f"[LLMClient/Gemini] Rate limit hit. "
                        f"Retrying in {backoff}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(backoff)
                    continue
                raise


# ---------------------------------------------------------------------------
# Claude backend
# ---------------------------------------------------------------------------


class _ClaudeBackend:
    """Lazy-initialized anthropic backend."""

    _client = None

    @classmethod
    def _get_client(cls):
        if cls._client is None:
            try:
                import anthropic  # noqa: PLC0415
            except ImportError:
                raise ImportError(
                    "anthropic SDK is required for LLM_PROVIDER=claude. "
                    "Install with: pip install anthropic"
                ) from None

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is not set. "
                    "Add it to your .env file or set LLM_PROVIDER=gemini."
                )

            cls._client = anthropic.Anthropic(api_key=api_key)
            model_name = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
            logger.info(f"[LLMClient] Initialized Claude backend: {model_name}")
        return cls._client

    @classmethod
    def generate(cls, prompt: str, max_retries: int = 5) -> tuple[str, float]:
        """Call Claude and return (response_text, latency_ms) with retry on 429."""
        import anthropic  # noqa: PLC0415

        client = cls._get_client()
        model_name = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
        max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "4096"))

        for attempt in range(max_retries):
            try:
                start = time.time()
                message = client.messages.create(
                    model=model_name,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                latency_ms = (time.time() - start) * 1000
                response_text = message.content[0].text.strip()
                return response_text, latency_ms
            except anthropic.RateLimitError as e:
                if attempt < max_retries - 1:
                    backoff = (2 ** attempt) + 2
                    logger.warning(
                        f"[LLMClient/Claude] Rate limit hit. "
                        f"Retrying in {backoff}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(backoff)
                    continue
                raise
            except Exception:
                raise


# ---------------------------------------------------------------------------
# Demo backend (no API calls)
# ---------------------------------------------------------------------------


class _DemoBackend:
    """Returns a stub JSON response — no API key required."""

    @classmethod
    def generate(cls, prompt: str, max_retries: int = 5) -> tuple[str, float]:  # noqa: ARG002
        logger.info("[LLMClient] DEMO_MODE: returning stub response")
        stub = (
            '[{"primary_type": "VALID", "root_cause_hypothesis": "Demo mode — no LLM called.", '
            '"evidence_used": "Demo mode.", "evidence_checked": "Demo mode.", '
            '"missing_data": [], "business_rule_triggered": "", '
            '"recommended_action": "No action required (demo).", "confidence": 0.99}]'
        )
        return stub, 0.0


# ---------------------------------------------------------------------------
# Public SharedLLMClient
# ---------------------------------------------------------------------------


class SharedLLMClient:
    """
    Single entry point for all LLM calls across the pipeline.

    Routes to Gemini, Claude, or the demo stub based on environment variables.
    After each successful call, applies the configured API_CALL_DELAY_SECONDS.

    Usage:
        text, latency_ms = SharedLLMClient.generate(prompt)
        text, latency_ms = SharedLLMClient.generate(prompt, max_retries=3)
    """

    @classmethod
    def generate(cls, prompt: str, max_retries: int = 5) -> tuple[str, float]:
        """
        Call the active LLM provider and return (response_text, latency_ms).

        Args:
            prompt:      Full prompt string to send to the LLM.
            max_retries: Number of retry attempts on rate-limit errors.

        Returns:
            (response_text, latency_ms) where response_text is the raw LLM output
            and latency_ms is the wall-clock time for the API call in milliseconds.

        Raises:
            ValueError:  If a required API key is missing.
            ImportError: If the provider SDK is not installed.
            Exception:   On non-retryable API errors.
        """
        if _is_demo_mode():
            return _DemoBackend.generate(prompt, max_retries)

        provider = _get_provider()

        if provider == PROVIDER_CLAUDE:
            text, latency_ms = _ClaudeBackend.generate(prompt, max_retries)
        else:
            # Default: gemini
            text, latency_ms = _GeminiBackend.generate(prompt, max_retries)

        # Apply inter-call delay after every successful call
        delay = _get_llm_call_delay()
        if delay > 0:
            time.sleep(delay)

        logger.debug(
            f"[LLMClient/{provider}] Response in {latency_ms:.0f}ms "
            f"({len(text)} chars)"
        )
        return text, latency_ms

    @classmethod
    def active_provider(cls) -> str:
        """Return the currently configured provider name ('gemini' or 'claude')."""
        if _is_demo_mode():
            return "demo"
        return _get_provider()
