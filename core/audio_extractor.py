"""
AttentionX - Audio Extractor
Extracts audio from video using FFmpeg for Groq Whisper transcription.
"""

import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_audio(video_path: str, output_dir: Path) -> str:
    """
    Extract audio from video as a 16kHz mono FLAC file.
    Groq recommends compact audio inputs, and FLAC keeps the file size smaller.

    Args:
        video_path: Path to the source video file.
        output_dir: Directory to save the extracted audio.

    Returns:
        Path to the extracted FLAC file.

    Raises:
        RuntimeError: If FFmpeg extraction fails.
    """
    video_path = Path(video_path)
    audio_path = output_dir / f"{video_path.stem}_audio.flac"

    logger.info(f"Extracting audio from: {video_path}")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",                    # No video
        "-acodec", "flac",        # Lossless compression for Groq uploads
        "-ar", "16000",           # 16kHz sample rate for speech recognition
        "-ac", "1",               # Mono
        "-af", "loudnorm",        # Normalize audio levels
        str(audio_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio extraction failed:\n{result.stderr}"
        )

    logger.info(f"Audio extracted to: {audio_path}")
    return str(audio_path)
