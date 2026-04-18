"""
AttentionX – File & Video Utilities
Helper functions for file management and ffprobe metadata extraction.
"""

import os
import subprocess
import json
import shutil
import uuid
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def get_unique_path(directory: Path, suffix: str) -> Path:
    """Generate a unique file path with a given suffix."""
    return directory / f"{uuid.uuid4().hex}{suffix}"


def get_video_metadata(video_path: str) -> dict:
    """
    Use ffprobe to extract video metadata: duration, fps, width, height.
    Returns a dict with the metadata or empty dict on failure.
    """
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            logger.warning(f"ffprobe failed: {result.stderr}")
            return {}

        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            {}
        )
        audio_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
            {}
        )

        duration = float(data.get("format", {}).get("duration", 0))
        fps_str = video_stream.get("r_frame_rate", "30/1")
        fps = eval(fps_str) if "/" in fps_str else float(fps_str)

        return {
            "duration": duration,
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "fps": fps,
            "has_audio": bool(audio_stream),
            "format": data.get("format", {}).get("format_name", "unknown"),
            "size_bytes": int(data.get("format", {}).get("size", 0)),
        }
    except Exception as e:
        logger.error(f"Failed to get video metadata: {e}")
        return {}


def cleanup_temp_files(*paths: str) -> None:
    """Delete temporary files/directories."""
    for path in paths:
        try:
            p = Path(path)
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
        except Exception as e:
            logger.debug(f"Cleanup warning for {path}: {e}")


def format_duration(seconds: float) -> str:
    """Format seconds to MM:SS string."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def safe_filename(name: str) -> str:
    """Sanitize a filename by removing unsafe characters."""
    import re
    name = re.sub(r'[^\w\-_.]', '_', name)
    return name[:100]  # Limit length


def check_ffmpeg_installed() -> bool:
    """Check if ffmpeg and ffprobe are available on PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
