"""
AttentionX – LLM Client
Unified interface for OpenAI / Google Gemini.
Switch provider via LLM_PROVIDER env var.
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified LLM client supporting OpenAI GPT-4 and Google Gemini.
    Falls back to a rule-based mock if no API keys are configured.
    """

    def __init__(self):
        from attentionx.backend.config import LLM_PROVIDER, OPENAI_API_KEY, GEMINI_API_KEY
        self.provider = LLM_PROVIDER
        self.openai_key = OPENAI_API_KEY
        self.gemini_key = GEMINI_API_KEY
        self._openai_client = None
        self._gemini_model = None
        self._initialize()

    def _initialize(self):
        """Initialize the appropriate client."""
        if self.provider == "openai" and self.openai_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.openai_key)
                logger.info("LLM: Using OpenAI GPT-4o-mini")
            except ImportError:
                logger.warning("openai package not installed; falling back to mock")
        elif self.provider == "gemini" and self.gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_key)
                self._gemini_model = genai.GenerativeModel("gemini-1.5-flash")
                logger.info("LLM: Using Google Gemini 1.5 Flash")
            except ImportError:
                logger.warning("google-generativeai not installed; falling back to mock")
        else:
            logger.warning("No LLM API key configured – using intelligent mock responses")

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """
        Send a prompt and return the completion text.
        Automatically falls back to mock if no client is ready.
        """
        if self._openai_client:
            return self._openai_complete(prompt, max_tokens)
        elif self._gemini_model:
            return self._gemini_complete(prompt, max_tokens)
        else:
            return self._mock_complete(prompt)

    def _openai_complete(self, prompt: str, max_tokens: int) -> str:
        try:
            response = self._openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert viral content strategist specializing in short-form video."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.8,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return self._mock_complete(prompt)

    def _gemini_complete(self, prompt: str, max_tokens: int) -> str:
        try:
            response = self._gemini_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return self._mock_complete(prompt)

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
            logger.warning(f"Could not parse LLM JSON response: {raw[:200]}")
            return {}


# Singleton instance
_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
