"""
Summarization Service
==================

Business logic for LLM-based text summarization using Ollama (local LLM).

Replaces the prior MagicMock-based stub with a real, async Ollama HTTP client.
The public interface (`summarize_content`, `batch_summarize`, `health_check`) is
preserved so existing routes and tests continue to work; internal calls now hit
a running Ollama server (default http://localhost:11434).
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..core.config import get_settings
from ..core.exceptions import LLMError, ValidationError
from ..models.article import ArticleSummary, SummarizationRequest

settings = get_settings()
logger = logging.getLogger(__name__)


class SummarizationService:
    """
    Service for handling LLM-based text summarization via Ollama.

    Configuration is read from `Settings`:
      - settings.ollama_host    (default: http://localhost:11434)
      - settings.ollama_model   (default: llama3.2)
      - settings.ollama_timeout (default: 60s)

    The service is safe to instantiate even when Ollama is not running; failures
    only surface when `summarize_content` / `health_check` are actually called.
    """

    # Min/max content lengths accepted for summarization
    MIN_CONTENT_LENGTH = 10
    MAX_CONTENT_LENGTH = 100_000  # 100k chars
    # Approximate char limit we forward to the LLM (keeps prompts within context)
    MAX_PROMPT_CHARS = 8_000

    def __init__(self, skip_api_key_validation: bool = False):
        """
        Initialize the summarization service.

        Args:
            skip_api_key_validation: kept for backward compatibility with prior
                signature; Ollama does not require an API key, so this is a no-op.
        """
        # Read Ollama configuration
        self.base_url: str = getattr(
            settings, "ollama_host", "http://localhost:11434"
        ).rstrip("/")
        self.model: str = getattr(settings, "ollama_model", "llama3.2")
        self.timeout: int = getattr(settings, "ollama_timeout", 60)

        # Generation defaults (overridable per-request via SummarizationRequest)
        self.max_length: int = getattr(settings, "max_summary_length", 200)
        self.temperature: float = getattr(settings, "temperature", 0.3)

        # Log whichever provider _call_llm will actually use so prod
        # boot logs don't claim "provider=ollama" when Groq is in play.
        from ..core.config import LLMProvider as _LLMProvider
        if settings.default_llm_provider == _LLMProvider.GROQ:
            logger.info(
                "SummarizationService initialised (provider=groq, model=%s)",
                getattr(settings, "groq_model", ""),
            )
        else:
            logger.info(
                "SummarizationService initialised (provider=ollama, model=%s, host=%s)",
                self.model,
                self.base_url,
            )

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    async def summarize_content(
        self, request: SummarizationRequest
    ) -> ArticleSummary:
        """
        Summarize the provided content using Ollama.

        Args:
            request: SummarizationRequest with content and parameters

        Returns:
            ArticleSummary with summary text and metadata

        Raises:
            ValidationError: if content fails validation
            LLMError: if the Ollama call fails
        """
        start_time = time.time()

        # Validate content
        if not self._validate_content(request.content):
            raise ValidationError("Content validation failed")

        target_length = getattr(request, "max_length", None) or self.max_length
        style = getattr(request, "style", None)

        prompt = self._get_summary_prompt(request.content, target_length, style)

        try:
            response_text, word_count = await self._call_llm(prompt, style)
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            logger.error("Ollama HTTP failure: %s", exc, exc_info=True)
            raise LLMError(f"Ollama call failed: {exc}") from exc
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - last-resort catch-all
            logger.error("Summarization failed: %s", exc, exc_info=True)
            raise LLMError(f"Summarization failed: {exc}") from exc

        summary = self._clean_summary(response_text)
        if not summary:
            raise LLMError("Empty summary returned from Ollama")

        original_len = max(len(request.content), 1)  # avoid div-by-zero
        # `ArticleSummary` is dual-purpose in this codebase (article-view +
        # summary metadata) and requires id/title/source/url. The summarizer
        # works on raw text and doesn't know the article it came from, so we
        # fill those with safe placeholders. Callers that have an article
        # context (e.g. routes/article-by-id) can patch them after the fact.
        return ArticleSummary(
            id=0,
            title="",
            source="",
            url="",
            summary=summary,
            word_count=word_count,
            original_length=len(request.content),
            summary_length=len(summary),
            compression_ratio=round(len(summary) / original_len, 4),
            processing_time=self._calculate_processing_time(start_time),
            model_used=self.model,
            created_at=datetime.now(timezone.utc),
        )

    async def batch_summarize(
        self, requests: List[SummarizationRequest]
    ) -> List[ArticleSummary]:
        """
        Summarize multiple pieces of content. Failures inside the batch are
        logged but do not abort the rest of the batch.
        """
        batch_size = 5
        results: List[ArticleSummary] = []

        for i in range(0, len(requests), batch_size):
            batch = requests[i : i + batch_size]
            tasks = [self.summarize_content(r) for r in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in batch_results:
                if isinstance(r, ArticleSummary):
                    results.append(r)
                else:
                    logger.error("Batch item failed: %s", r)

        return results

    async def health_check(self) -> Dict[str, Any]:
        """Probe whichever LLM provider is actually configured.

        ``_call_llm`` already dispatches between Groq (production default
        on Fly) and Ollama (local dev). The health check used to probe
        Ollama unconditionally, which made ``/health/detailed`` report
        the summarization component as ``unhealthy`` on Fly even though
        Groq was happily handling every request. We now mirror the same
        dispatch: when ``settings.default_llm_provider == GROQ`` probe
        Groq's ``/models`` endpoint; otherwise probe Ollama.
        """
        from ..core.config import LLMProvider as _LLMProvider

        if settings.default_llm_provider == _LLMProvider.GROQ:
            return await self._health_check_groq()
        return await self._health_check_ollama()

    async def _health_check_groq(self) -> Dict[str, Any]:
        """Probe Groq via /models. Cheap, requires only the API key."""
        from .groq_client import _resolve_api_key  # type: ignore[attr-defined]

        groq_model = getattr(settings, "groq_model", "")
        groq_base = getattr(
            settings, "groq_base_url", "https://api.groq.com/openai/v1"
        ).rstrip("/")
        result: Dict[str, Any] = {
            "provider": "groq",
            "model": groq_model,
            "host": groq_base,
            "max_length": self.max_length,
            "temperature": self.temperature,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            api_key = _resolve_api_key()
        except Exception as exc:  # LLMError when key is missing/empty
            result.update(
                {
                    "status": "unhealthy",
                    "api_accessible": False,
                    "error": str(exc),
                }
            )
            return result

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    f"{groq_base}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code != 200:
                result.update(
                    {
                        "status": "unhealthy",
                        "api_accessible": False,
                        "error": f"/models returned {resp.status_code}",
                    }
                )
                return result
            models = [
                m.get("id", "")
                for m in resp.json().get("data", [])
                if isinstance(m, dict)
            ]
            model_loaded = bool(groq_model) and groq_model in models
            result.update(
                {
                    "status": "healthy" if model_loaded else "degraded",
                    "api_accessible": True,
                    "model_loaded": model_loaded,
                    # Don't dump the whole catalogue — Groq returns 20+
                    # entries. The configured model presence is what
                    # matters for the health-check signal.
                    "model_count": len(models),
                }
            )
            return result
        except Exception as exc:  # noqa: BLE001
            result.update(
                {
                    "status": "unhealthy",
                    "api_accessible": False,
                    "error": str(exc),
                }
            )
            return result

    async def _health_check_ollama(self) -> Dict[str, Any]:
        """Probe Ollama (local-dev path)."""
        result: Dict[str, Any] = {
            "provider": "ollama",
            "model": self.model,
            "host": self.base_url,
            "max_length": self.max_length,
            "temperature": self.temperature,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                tags_resp = await client.get(f"{self.base_url}/api/tags")
                if tags_resp.status_code != 200:
                    result.update(
                        {
                            "status": "unhealthy",
                            "api_accessible": False,
                            "error": f"/api/tags returned {tags_resp.status_code}",
                        }
                    )
                    return result

                models = [
                    m.get("name", "")
                    for m in tags_resp.json().get("models", [])
                ]
                model_loaded = any(
                    m == self.model or m.startswith(f"{self.model}:") for m in models
                )

                result.update(
                    {
                        "status": "healthy" if model_loaded else "degraded",
                        "api_accessible": True,
                        "model_loaded": model_loaded,
                        "available_models": models,
                    }
                )
                return result
        except Exception as exc:  # noqa: BLE001
            result.update(
                {
                    "status": "unhealthy",
                    "api_accessible": False,
                    "error": str(exc),
                }
            )
            return result

    # ------------------------------------------------------------------ #
    #  Internals
    # ------------------------------------------------------------------ #

    async def _call_llm(
        self, prompt: str, style: Optional[str] = None
    ) -> tuple[str, int]:
        """
        Send the prompt to the configured LLM and return ``(text, word_count)``.

        Dispatches on ``settings.default_llm_provider``:
          * ``groq``   -> :func:`groq_client.groq_generate` (cloud, prod default)
          * anything else -> local Ollama at ``/api/generate``
        """
        # --- Groq path (prod default; no local Ollama available on Fly) ---
        from ..core.config import LLMProvider as _LLMProvider
        from .groq_client import groq_generate

        if settings.default_llm_provider == _LLMProvider.GROQ:
            return await groq_generate(
                prompt,
                num_predict=min(self.max_length * 2, 1024),
                temperature=self.temperature,
                label="summarize",
            )

        # --- Ollama path (local dev) ---
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "top_p": 0.9,
                # `num_predict` caps token output (rough proxy for word count)
                "num_predict": min(self.max_length * 2, 1024),
            },
        }
        if getattr(settings, "ollama_keep_alive", None):
            payload["keep_alive"] = settings.ollama_keep_alive

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate", json=payload
            )

        if resp.status_code != 200:
            raise LLMError(
                f"Ollama returned {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        text = (data.get("response") or "").strip()
        if not text:
            raise LLMError("Ollama returned empty response")

        # Ollama reports `eval_count` (tokens generated). Fall back to a word count.
        word_count = data.get("eval_count") or len(text.split())
        return text, int(word_count)

    def _get_summary_prompt(
        self,
        content: str,
        target_length: Optional[int] = None,
        style: Optional[str] = None,
    ) -> str:
        """Build a summarization prompt tuned for tech-news content."""
        length_hint = (
            f" Keep the summary to roughly {target_length} words."
            if target_length
            else ""
        )

        style_hint = {
            "bullet_points": "Return the summary as 3-5 short bullet points.",
            "detailed": "Provide a thorough, multi-paragraph summary.",
            "technical": "Emphasise technical details, architectures, and trade-offs.",
            "executive": "Provide an executive summary suitable for a non-technical reader.",
            "concise": "Provide a concise 2-3 sentence summary.",
        }.get(style or "", "Provide a concise 3-5 sentence summary.")

        # Truncate content sent to the LLM to stay inside context limits
        truncated = content[: self.MAX_PROMPT_CHARS]

        return (
            "You are an AI assistant that summarises technology news articles.\n"
            f"{style_hint}{length_hint}\n"
            "Focus on: the main announcement, key technical details, the companies "
            "or people involved, and the significance.\n\n"
            "Article:\n"
            f"{truncated}\n\n"
            "Summary:"
        )

    def _validate_content(self, content: str) -> bool:
        """Reject empty / too-short / too-long content."""
        if not content or not content.strip():
            return False
        if len(content) < self.MIN_CONTENT_LENGTH:
            return False
        if len(content) >= self.MAX_CONTENT_LENGTH:
            return False
        return True

    def _clean_summary(self, summary: str) -> str:
        """Normalise whitespace and strip basic markdown artefacts."""
        if not summary:
            return ""
        summary = re.sub(r"\s+", " ", summary.strip())
        summary = re.sub(r"\*\*(.*?)\*\*", r"\1", summary)  # bold
        summary = re.sub(r"\*(.*?)\*", r"\1", summary)        # italics
        summary = re.sub(r"#{1,6}\s*", "", summary)            # headings
        # Strip any leading "Summary:" / "Here is the summary:" the model emits
        summary = re.sub(
            r"^\s*(here(?:'s| is)? (?:the )?summary[:.\-]\s*|summary[:.\-]\s*)",
            "",
            summary,
            flags=re.IGNORECASE,
        )
        return summary.strip()

    def _calculate_processing_time(self, start_time) -> float:
        """Return seconds elapsed since `start_time` (timestamp or datetime)."""
        if isinstance(start_time, datetime):
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            return round(time.time() - start_time.timestamp(), 3)
        return round(time.time() - start_time, 3)
