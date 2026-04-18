"""
AttentionX – Caption Engine
Generates punchy, synced captions and burns them onto clips using FFmpeg.

Caption philosophy:
  - Max 3-5 words per line (mobile screen readability)
    - Word-level timing from Groq Whisper for perfect sync
  - Key words highlighted in a contrasting color
  - Clean, readable font with stroke/shadow
"""

import re
import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

from attentionx.backend.models.schemas import (
    Caption, TranscriptResult, TranscriptSegment, Platform
)
from attentionx.backend.config import PLATFORM_PRESETS

logger = logging.getLogger(__name__)

# Words to highlight (these get a different color)
HIGHLIGHT_WORDS = {
    "secret", "never", "always", "free", "best", "worst", "first",
    "last", "only", "most", "least", "important", "critical",
    "wrong", "right", "mistake", "truth", "lie", "real", "hidden",
    "reveal", "shocking", "incredible", "amazing", "powerful",
}

# Caption style presets for each platform
CAPTION_STYLES = {
    "bold_center": {
        "fontsize": 72,
        "fontcolor": "white",
        "highlight_color": "#FFD700",  # Gold
        "font": "Arial-Bold",
        "box": True,
        "boxcolor": "black@0.6",
        "x": "w/2",
        "y": "h*0.75",
    },
    "bottom_white": {
        "fontsize": 64,
        "fontcolor": "white",
        "highlight_color": "#FF4D4D",  # Red
        "font": "Arial-Bold",
        "box": True,
        "boxcolor": "black@0.7",
        "x": "w/2",
        "y": "h*0.80",
    },
    "subtitle_style": {
        "fontsize": 56,
        "fontcolor": "white",
        "highlight_color": "#00CFFF",  # Cyan
        "font": "Arial",
        "box": True,
        "boxcolor": "black@0.5",
        "x": "w/2",
        "y": "h*0.85",
    },
}


def _chunk_words(words: List[dict], words_per_line: int = 4) -> List[List[dict]]:
    """Split word list into chunks for caption lines."""
    chunks = []
    for i in range(0, len(words), words_per_line):
        chunks.append(words[i:i + words_per_line])
    return chunks


def _is_highlight_word(word: str) -> bool:
    """Determine if a word should be highlighted."""
    clean = word.strip(".,!?;:'\"").lower()
    return clean in HIGHLIGHT_WORDS


def build_captions(
    transcript: TranscriptResult,
    clip_start: float,
    clip_end: float,
    platform: Platform = Platform.TIKTOK,
) -> List[Caption]:
    """
    Build Caption objects for a specific clip time window.
    Groups words into short caption lines with timing.

    Args:
        transcript: Full transcript with word-level timestamps.
        clip_start: Start time of the clip in the original video.
        clip_end: End time of the clip in the original video.
        platform: Target platform (affects words per line).

    Returns:
        List of Caption objects with relative timestamps.
    """
    preset = PLATFORM_PRESETS[platform.value]
    words_per_line = preset["words_per_line"]

    # Collect all words within the clip time window
    clip_words: List[dict] = []
    for seg in transcript.segments:
        for w in (seg.words or []):
            w_start = w["start"]
            w_end = w["end"]
            if clip_start <= w_start <= clip_end:
                # Convert to clip-relative timestamps
                clip_words.append({
                    "word": w["word"],
                    "start": round(w_start - clip_start, 3),
                    "end": round(w_end - clip_start, 3),
                    "is_highlight": _is_highlight_word(w["word"]),
                })

    if not clip_words:
        return []

    # Chunk into caption lines
    chunks = _chunk_words(clip_words, words_per_line)
    captions: List[Caption] = []

    for chunk in chunks:
        if not chunk:
            continue

        line_start = chunk[0]["start"]
        line_end = chunk[-1]["end"]
        line_text = " ".join(w["word"] for w in chunk)
        has_highlight = any(w["is_highlight"] for w in chunk)

        captions.append(Caption(
            start=line_start,
            end=line_end,
            text=line_text,
            words=chunk,
            is_highlight=has_highlight,
        ))

    return captions


def generate_srt(captions: List[Caption], output_path: str) -> str:
    """
    Generate an SRT subtitle file from captions.

    Args:
        captions: List of Caption objects.
        output_path: Where to save the .srt file.

    Returns:
        Path to the generated SRT file.
    """
    def _format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds * 1000) % 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, cap in enumerate(captions, 1):
        lines.append(str(i))
        lines.append(f"{_format_time(cap.start)} --> {_format_time(cap.end)}")
        lines.append(cap.text)
        lines.append("")

    srt_content = "\n".join(lines)
    Path(output_path).write_text(srt_content, encoding="utf-8")
    return output_path


def burn_captions(
    video_path: str,
    captions: List[Caption],
    output_path: str,
    platform: Platform = Platform.TIKTOK,
) -> str:
    """
    Burn captions onto the video using FFmpeg drawtext filter.
    Each caption line appears at the correct timestamp.

    Args:
        video_path: Input clip (9:16 cropped).
        captions: List of Caption objects.
        output_path: Output path with captions burned in.
        platform: Platform determines caption style.

    Returns:
        Path to the output clip with burned captions.
    """
    preset = PLATFORM_PRESETS[platform.value]
    style_name = preset["caption_style"]
    style = CAPTION_STYLES.get(style_name, CAPTION_STYLES["bold_center"])

    # Generate SRT file
    srt_path = str(output_path) + ".srt"
    generate_srt(captions, srt_path)

    # Use FFmpeg subtitles filter to burn captions
    font_size = style["fontsize"]
    font_color = style["fontcolor"]

    # Build the subtitles filter string
    subtitles_filter = (
        f"subtitles={srt_path.replace('\\', '/').replace(':', '\\:')}:"
        f"force_style='Fontsize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"Outline=3,Shadow=2,"
        f"Alignment=2,"  # Bottom center
        f"Bold=1'"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", subtitles_filter,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        logger.warning(f"Caption burn failed, returning uncaptioned: {result.stderr[:200]}")
        # Fall back to returning the original if caption burning fails
        import shutil
        shutil.copy(video_path, output_path)
    else:
        logger.info(f"Captions burned: {output_path}")

    # Cleanup SRT
    try:
        Path(srt_path).unlink()
    except Exception:
        pass

    return output_path
