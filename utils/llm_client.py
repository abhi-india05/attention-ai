"""
AttentionX - Gemini LLM Client
Unified interface for Gemini-powered content generation with key rotation.
"""

import json
import logging
from threading import Lock
from typing import Optional

from attentionx.backend.config import GEMINI_API_KEY, GEMINI_API_KEYS

logger = logging.getLogger(__name__)


class LLMClient:
    """Gemini-only client with key rotation and a mock fallback."""

    def __init__(self):
        self.gemini_keys = self._load_gemini_keys()
        self._key_cursor = 0
        self._gemini_lock = Lock()
        self._initialize()

    def _load_gemini_keys(self) -> list[str]:
        """Normalize the configured Gemini keys into a unique ordered list."""
        keys = [key.strip() for key in GEMINI_API_KEYS if key.strip()]
        if not keys and GEMINI_API_KEY.strip():
            keys = [GEMINI_API_KEY.strip()]

        unique_keys: list[str] = []
        for key in keys:
            if key not in unique_keys:
                unique_keys.append(key)
        return unique_keys

    def _initialize(self):
        """Initialize the Gemini client."""
        if not self.gemini_keys:
            logger.warning("No Gemini API keys configured; using intelligent mock responses")
            return

        logger.info("LLM: Gemini key rotation enabled (%d keys)", len(self.gemini_keys))

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Send a prompt and return the completion text.
        Falls back to a mock response when Gemini is unavailable.
        """
        if self.gemini_keys:
            return self._gemini_complete(prompt, max_tokens)
        return self._mock_complete(prompt)

    def _gemini_complete(self, prompt: str, max_tokens: int) -> str:
        with self._gemini_lock:
            last_error: Exception | None = None

            for offset in range(len(self.gemini_keys)):
                key_index = (self._key_cursor + offset) % len(self.gemini_keys)
                api_key = self.gemini_keys[key_index]
                try:
                    response = self._generate_with_key(api_key, prompt, max_tokens)
                    text = (getattr(response, "text", "") or "").strip()
                    if text:
                        self._key_cursor = key_index
                        return text

                    last_error = RuntimeError("Gemini returned an empty response")
                    logger.warning("Gemini returned an empty response; rotating to next key")
                except Exception as exc:
                    last_error = exc
                    if self._is_quota_or_rate_limit_error(exc):
                        logger.warning("Gemini key hit quota/rate limit; rotating to next key: %s", exc)
                    else:
                        logger.warning("Gemini key failed; rotating to next key: %s", exc)

            if last_error is not None:
                logger.error("All Gemini keys failed; using mock fallback. Last error: %s", last_error)
                self._key_cursor = (self._key_cursor + 1) % len(self.gemini_keys)
            return self._mock_complete(prompt)

    def _generate_with_key(self, api_key: str, prompt: str, max_tokens: int):
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        return model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.8,
                "max_output_tokens": max_tokens,
            },
        )

    @staticmethod
    def _is_quota_or_rate_limit_error(exc: Exception) -> bool:
        message = str(exc).lower()
        error_name = exc.__class__.__name__.lower()

        if any(token in message for token in ["quota", "rate limit", "too many requests", "resource exhausted", "429"]):
            return True

        try:
            from google.api_core import exceptions as google_exceptions

            return isinstance(
                exc,
                (
                    google_exceptions.ResourceExhausted,
                    google_exceptions.TooManyRequests,
                    google_exceptions.ServiceUnavailable,
                    google_exceptions.DeadlineExceeded,
                ),
            )
        except Exception:
            return any(token in error_name for token in ["resourceexhausted", "toomanyrequests"])

    def _mock_complete(self, prompt: str) -> str:
        """
        Rule-based mock for demo without API keys.
        Returns sensible JSON structures based on prompt keywords.
        """
        prompt_lower = prompt.lower()

        if "virality" in prompt_lower or "rank" in prompt_lower:
            return json.dumps({
                "semantic_importance": 0.78,
                "curiosity_hook": 0.72,
                "reasoning": "This segment contains a clear revelation moment with strong emotional build-up and actionable insight that audiences will want to share."
            })

        if "hook" in prompt_lower:
            return json.dumps([
                {"text": "Nobody talks about this mistake...", "style": "revelation", "predicted_ctr": 0.87},
                {"text": "This changed everything for me.", "style": "transformation", "predicted_ctr": 0.81},
                {"text": "Wait — did you know this?", "style": "curiosity", "predicted_ctr": 0.75},
            ])

        if "hashtag" in prompt_lower:
            return json.dumps([
                "#viral", "#learnontiktok", "#mindblown", "#didyouknow",
                "#fyp", "#lifehacks", "#motivation", "#trending"
            ])

        if "title" in prompt_lower or "summarize" in prompt_lower:
            return "The Hidden Truth You Need to Hear"

        return "Generated content based on provided context."

    def complete_json(self, prompt: str, max_tokens: int = 1024) -> dict | list:
        """Complete and parse as JSON. Returns empty dict on failure."""
        raw = self.complete(prompt, max_tokens)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON substring
            import re
            match = re.search(r'(\{.*\}|\[.*\])', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            logger.warning(f"Could not parse Gemini JSON response: {raw[:200]}")
            return {}


# Singleton instance
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
