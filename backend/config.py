"""
AttentionX - Configuration Management
Centralizes all environment variables, paths, and system settings.
"""

import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Base Paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
CLIPS_DIR = OUTPUT_DIR / "clips"
VIDEOS_DIR = OUTPUT_DIR / "videos"
FRONTEND_DIR = BASE_DIR / "frontend"

# Ensure directories exist
for _dir in [UPLOAD_DIR, CLIPS_DIR, VIDEOS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

def _load_gemini_keys() -> list[str]:
    """Load one or more Gemini API keys from the environment."""
    raw_keys = os.getenv("GEMINI_API_KEYS", "").strip()
    if not raw_keys:
        raw_keys = os.getenv("GEMINI_API_KEY", "").strip()

    if not raw_keys:
        return []

    return [
        key.strip()
        for key in re.split(r"[;,\n]+", raw_keys)
        if key.strip()
    ]


# ── API Keys ─────────────────────────────────────────────────────────────────
GEMINI_API_KEYS: list[str] = _load_gemini_keys()
GEMINI_API_KEY: str = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else ""
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

# Groq Whisper model ID: whisper-large-v3 | whisper-large-v3-turbo
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "whisper-large-v3")

# ── Platform Presets ──────────────────────────────────────────────────────────
PLATFORM_PRESETS = {
    "tiktok": {
        "max_duration": 60,
        "min_duration": 15,
        "aspect_ratio": "9:16",
        "caption_style": "bold_center",
        "words_per_line": 3,
        "hashtag_count": 5,
    },
    "reels": {
        "max_duration": 90,
        "min_duration": 15,
        "aspect_ratio": "9:16",
        "caption_style": "bottom_white",
        "words_per_line": 4,
        "hashtag_count": 8,
    },
    "youtube_shorts": {
        "max_duration": 60,
        "min_duration": 30,
        "aspect_ratio": "9:16",
        "caption_style": "subtitle_style",
        "words_per_line": 5,
        "hashtag_count": 3,
    },
}

# ── Virality Scoring Weights ──────────────────────────────────────────────────
VIRALITY_WEIGHTS = {
    "audio_intensity": 0.20,       # RMS energy + spectral peaks
    "sentiment_score": 0.15,       # Positive/negative emotional polarity
    "semantic_importance": 0.30,   # LLM-rated content value
    "keyword_triggers": 0.20,      # Power words that drive clicks
    "curiosity_hook": 0.15,        # Questions, cliffhangers, incomplete loops
}

# Keyword triggers that boost virality score
VIRAL_KEYWORDS = [
    # Revelation triggers
    "secret", "reveal", "truth", "expose", "hidden", "leaked",
    # Value triggers
    "mistake", "wrong", "fail", "avoid", "never do", "stop", "warning",
    # FOMO triggers
    "most people", "nobody knows", "rarely talked about", "untold",
    # Authority triggers
    "study shows", "research", "proven", "science", "data",
    # Emotion triggers
    "incredible", "shocking", "unbelievable", "amazing", "life-changing",
    # Hook triggers
    "but here's the thing", "wait", "actually", "the real reason",
    "what nobody tells you", "here's why", "plot twist",
    # Urgency/importance
    "important", "critical", "must know", "pay attention", "listen",
    "game changer", "breakthrough", "revolutionary",
]

# ── Processing ────────────────────────────────────────────────────────────────
MAX_CLIPS = 10          # Maximum clips to generate per video
MIN_CLIP_DURATION = 15  # Minimum clip length in seconds
MAX_CLIP_DURATION = 90  # Maximum clip length in seconds
CLIP_CONTEXT_PADDING = 2.0  # Seconds to add before/after detected segment

# ── Video Output ──────────────────────────────────────────────────────────────
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920
OUTPUT_FPS = 30
OUTPUT_CODEC = "libx264"
OUTPUT_AUDIO_CODEC = "aac"
OUTPUT_BITRATE = "4000k"

# ── Face Detection ────────────────────────────────────────────────────────────
FACE_DETECTION_CONFIDENCE = 0.7
SMOOTHING_WINDOW = 15  # Frames for crop position smoothing (reduces jitter)
ZOOM_FACTOR = 1.05     # Subtle zoom-in on face for engagement
