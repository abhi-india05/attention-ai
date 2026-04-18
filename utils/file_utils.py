"""
AttentionX - File & Video Utilities
Helper functions for file management and video metadata extraction.
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


def resolve_ffmpeg_executable() -> Optional[str]:
    """Return a usable ffmpeg executable path if one can be found."""
    explicit = os.getenv("FFMPEG_PATH", "").strip().strip('"')
    if explicit and Path(explicit).exists():
        return explicit

    which_path = shutil.which("ffmpeg")
    if which_path:
        return which_path

    common_paths = [
        Path(r"C:\Program Files\ShareX\ffmpeg.exe"),
        Path(r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"),
        Path(r"C:\ffmpeg\bin\ffmpeg.exe"),
    ]
    for candidate in common_paths:
        if candidate.exists():
            return str(candidate)

    return None


def resolve_ffprobe_executable() -> Optional[str]:
    """Return a usable ffprobe executable path if one can be found."""
    explicit = os.getenv("FFPROBE_PATH", "").strip().strip('"')
    if explicit and Path(explicit).exists():
        return explicit

    which_path = shutil.which("ffprobe")
    if which_path:
        return which_path

    ffmpeg_path = resolve_ffmpeg_executable()
    if ffmpeg_path:
        ffprobe_candidate = Path(ffmpeg_path).with_name("ffprobe.exe")
        if ffprobe_candidate.exists():
            return str(ffprobe_candidate)

    return None


def get_unique_path(directory: Path, suffix: str) -> Path:
    """Generate a unique file path with a given suffix."""
    return directory / f"{uuid.uuid4().hex}{suffix}"


def get_video_metadata(video_path: str) -> dict:
    """
    Use ffprobe to extract video metadata: duration, fps, width, height.
    Falls back to OpenCV when ffprobe is unavailable.
    """
    try:
        ffprobe_path = resolve_ffprobe_executable()
        if ffprobe_path:
            cmd = [
                ffprobe_path, "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(video_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.warning(f"ffprobe failed: {result.stderr}")
            else:
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

        # Fallback: OpenCV metadata (duration is estimated from frame count / fps)
        import cv2

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            return {}

        fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        capture.release()

        return {
            "duration": round(frame_count / fps if fps else 0.0, 2),
            "width": width,
            "height": height,
            "fps": fps,
            "has_audio": False,
            "format": "opencv_fallback",
            "size_bytes": int(Path(video_path).stat().st_size),
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
    """Check if ffmpeg is available either on PATH or in a common local install."""
    return resolve_ffmpeg_executable() is not None
