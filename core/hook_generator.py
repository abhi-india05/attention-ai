"""
AttentionX – Hook Generator
Generates 3 viral hooks per clip using LLM, then ranks them by predicted CTR.

Hook types:
  1. Revelation hook: "Nobody talks about this..."
  2. Curiosity hook: "Why does this happen?"
  3. Value hook: "Here's how to get X without Y"
  4. Transformation hook: "This changed everything for me"
  5. Shock hook: "I can't believe this actually works"
"""

import logging
from typing import List

from attentionx.backend.models.schemas import Hook, TranscriptSegment
from attentionx.utils.llm_client import get_llm_client

logger = logging.getLogger(__name__)

HOOK_STYLES = ["revelation", "curiosity", "value", "transformation", "shock"]


def generate_hooks(
    transcript_excerpt: str,
    clip_title: str = "",
    platform: str = "tiktok",
) -> List[Hook]:
    """
    Generate 3 viral hooks for a clip using LLM, ranked by predicted CTR.

    Args:
        transcript_excerpt: The text content of the clip.
        clip_title: Optional title context.
        platform: Target platform for tone calibration.

    Returns:
        List of 3 Hook objects sorted by predicted_ctr descending.
    """
    llm = get_llm_client()

    platform_instructions = {
        "tiktok": "casual, Gen-Z friendly, short (max 8 words), uses CapCut-style language",
        "reels": "Instagram-style, aspirational, modern, max 10 words",
        "youtube_shorts": "curiosity-driven, educational, slightly longer, authority-building",
    }

    style_guide = platform_instructions.get(platform, platform_instructions["tiktok"])

    prompt = f"""You are a viral content strategist with a proven track record of creating hooks that get millions of views.

CLIP CONTENT:
{transcript_excerpt[:600]}

PLATFORM: {platform} — hooks should be {style_guide}

Generate EXACTLY 3 viral hooks for this clip. Each hook must:
1. Be under 12 words
2. Create a strong curiosity gap or emotional trigger
3. Work as a text overlay at the START of the video

HOOK TYPES to use (pick the 3 most fitting):
- revelation: "Nobody talks about this..."
- curiosity: "Why does [X] actually happen?"  
- value: "Here's how to [achieve X] without [Y]"
- transformation: "This changed how I think about [X]"
- shock: "I can't believe [X] is actually [Y]"
- warning: "Stop doing this if you want [X]"

Return ONLY valid JSON array:
[
  {{"text": "hook text here", "style": "revelation", "predicted_ctr": 0.87}},
  {{"text": "hook text here", "style": "curiosity", "predicted_ctr": 0.79}},
  {{"text": "hook text here", "style": "value", "predicted_ctr": 0.71}}
]

predicted_ctr should be between 0.5–0.95 based on how compelling the hook is.
No explanations. Only JSON."""

    result = llm.complete_json(prompt, max_tokens=512)

    hooks: List[Hook] = []

    if isinstance(result, list):
        for item in result[:3]:
            if isinstance(item, dict):
                hooks.append(Hook(
                    text=str(item.get("text", "Wait for this...")),
                    style=str(item.get("style", "curiosity")),
                    predicted_ctr=float(item.get("predicted_ctr", 0.7)),
                ))

    # Fallback if LLM fails
    if not hooks:
        hooks = _fallback_hooks(transcript_excerpt)

    # Sort by predicted CTR
    hooks.sort(key=lambda h: h.predicted_ctr, reverse=True)
    return hooks[:3]


def _fallback_hooks(text: str) -> List[Hook]:
    """Rule-based fallback hooks when LLM is unavailable."""
    # Extract a key phrase from the transcript
    words = text.split()
    key_phrase = " ".join(words[:5]) if len(words) >= 5 else text[:50]

    return [
        Hook(text="Nobody talks about this...", style="revelation", predicted_ctr=0.82),
        Hook(text="This will change how you think.", style="transformation", predicted_ctr=0.75),
        Hook(text="Wait — this is important.", style="curiosity", predicted_ctr=0.68),
    ]


def generate_clip_title(transcript_excerpt: str) -> str:
    """Generate a short, catchy title for the clip."""
    llm = get_llm_client()

    prompt = f"""Create a short, catchy title (max 8 words) for this video clip that would work as a YouTube Shorts / TikTok title.

Content: {transcript_excerpt[:400]}

Rules:
- Sound natural, not clickbait
- Include the core idea
- Use strong action words
- Max 8 words

Return ONLY the title text, nothing else."""

    result = llm.complete(prompt, max_tokens=64).strip().strip('"\'')
    if len(result) > 80 or not result:
        # Fallback
        words = transcript_excerpt.split()[:6]
        result = " ".join(words).capitalize() + "..."

    return result
