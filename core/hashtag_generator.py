"""
AttentionX – Auto Hashtag Generator
Platform-aware hashtag generation combining content analysis and trending topics.

Strategy:
  1. Content-based hashtags (from transcript keywords)
  2. Niche community hashtags (topic-specific)
  3. Reach hashtags (broad, high-volume)
  4. Platform-specific mandatory hashtags (#fyp, etc.)
"""

import re
import logging
from typing import List

from attentionx.backend.config import PLATFORM_PRESETS
from attentionx.utils.llm_client import get_llm_client

logger = logging.getLogger(__name__)

# Universal reach hashtags by platform
PLATFORM_HASHTAGS = {
    "tiktok":          ["#fyp", "#foryoupage", "#viral", "#learnontiktok"],
    "reels":           ["#reelsinstagram", "#viral", "#trending", "#explore"],
    "youtube_shorts":  ["#shorts", "#youtubeshorts", "#viral", "#subscribe"],
}

# Topic category → niche hashtags
NICHE_HASHTAGS = {
    "business":    ["#entrepreneur", "#startuptips", "#businessadvice", "#success"],
    "tech":        ["#tech", "#ai", "#coding", "#programming", "#innovation"],
    "motivation":  ["#motivation", "#mindset", "#selfimprovement", "#growth"],
    "health":      ["#health", "#wellness", "#fitness", "#lifestyle"],
    "finance":     ["#money", "#investing", "#personalfinance", "#wealth"],
    "education":   ["#education", "#learning", "#facts", "#knowledge"],
    "science":     ["#science", "#research", "#facts", "#nature"],
}


def _detect_topic_category(text: str) -> str:
    """Simple keyword-based topic detection."""
    text_lower = text.lower()
    topic_keywords = {
        "business": ["customer", "product", "startup", "company", "revenue", "sales", "founder"],
        "tech": ["ai", "software", "code", "programming", "algorithm", "data", "machine"],
        "motivation": ["mindset", "success", "goal", "inspire", "achieve", "believe", "growth"],
        "health": ["health", "body", "workout", "diet", "sleep", "stress", "mental"],
        "finance": ["money", "invest", "stock", "wealth", "saving", "portfolio", "finance"],
        "education": ["learn", "study", "teach", "school", "knowledge", "skill", "university"],
        "science": ["research", "study", "experiment", "discover", "science", "data", "physics"],
    }

    scores = {}
    for topic, keywords in topic_keywords.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        scores[topic] = score

    if not scores or max(scores.values()) == 0:
        return "education"

    return max(scores, key=scores.get)


def generate_hashtags(
    transcript_excerpt: str,
    platform: str = "tiktok",
    count: int = 5,
) -> List[str]:
    """
    Generate platform-optimized hashtags for a clip.

    Args:
        transcript_excerpt: Clip transcript text.
        platform: Target platform.
        count: Number of hashtags to generate.

    Returns:
        List of hashtag strings (with #).
    """
    llm = get_llm_client()
    preset_count = PLATFORM_PRESETS.get(platform, {}).get("hashtag_count", count)

    # Detect topic for niche hashtags
    topic = _detect_topic_category(transcript_excerpt)
    niche = NICHE_HASHTAGS.get(topic, [])[:3]
    platform_base = PLATFORM_HASHTAGS.get(platform, [])[:2]

    # LLM-generated content-specific hashtags
    prompt = f"""Generate {preset_count} specific hashtags for this {platform} clip.

Clip content: {transcript_excerpt[:400]}
Topic category: {topic}

Rules:
- Mix of broad (1M+ posts) and specific (50K–500K posts) hashtags  
- No banned or spam hashtags
- Relevant to the actual content
- Include some searchable topic hashtags users actually look up

Return ONLY a JSON array of strings with # symbol, like:
["#hashtag1", "#hashtag2", "#hashtag3"]"""

    result = llm.complete_json(prompt, max_tokens=200)

    llm_hashtags = []
    if isinstance(result, list):
        llm_hashtags = [h for h in result if isinstance(h, str) and h.startswith("#")][:4]

    # Combine: LLM content hashtags + niche + platform
    all_hashtags = llm_hashtags + niche + platform_base

    # Deduplicate while preserving order
    seen = set()
    final = []
    for tag in all_hashtags:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            final.append(tag)

    return final[:preset_count]
