"""
AttentionX - Groq Whisper Transcriber
Transcribes audio using Groq's Whisper models with word-level timestamps.

Groq returns:
  - Full transcript text
  - Segment-level timestamps
  - Word-level timestamps when requested

This is the FOUNDATION for the entire virality engine.
"""

import logging
from pathlib import Path

from attentionx.backend.config import GROQ_API_KEY, WHISPER_MODEL
from attentionx.backend.models.schemas import TranscriptResult, TranscriptSegment

logger = logging.getLogger(__name__)


def _get_value(item, key, default=None):
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _coerce_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def transcribe(audio_path: str) -> TranscriptResult:
    """Transcribe audio using Groq Whisper."""
    try:
        from groq import Groq  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise RuntimeError(
            "Groq SDK is not installed. Add 'groq' to requirements and install dependencies."
        ) from exc

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured in .env")

    audio_file = Path(audio_path)
    file_size_mb = audio_file.stat().st_size / (1024 * 1024)
    if file_size_mb > 95:
        logger.warning(
            "Groq speech-to-text uploads above ~100MB may fail; consider shorter inputs or chunking."
        )

    client = Groq(api_key=GROQ_API_KEY)

    logger.info(f"Loading Groq Whisper model: {WHISPER_MODEL}")
    logger.info(f"Transcribing with Groq: {audio_file}")

    with audio_file.open("rb") as file_handle:
        result = client.audio.transcriptions.create(
            file=file_handle,
            model=WHISPER_MODEL,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            temperature=0.0,
        )

    raw_segments = _get_value(result, "segments", []) or []
    segments: list[TranscriptSegment] = []

    for index, segment in enumerate(raw_segments):
        raw_words = _get_value(segment, "words", []) or []
        words = []

        for raw_word in raw_words:
            word_text = str(_get_value(raw_word, "word", "") or "").strip()
            if not word_text:
                continue

            words.append({
                "word": word_text,
                "start": round(_coerce_float(_get_value(raw_word, "start", 0.0)), 3),
                "end": round(_coerce_float(_get_value(raw_word, "end", 0.0)), 3),
                "probability": round(_coerce_float(_get_value(raw_word, "probability", 1.0), 1.0), 3),
            })

        segment_text = str(_get_value(segment, "text", "") or "").strip()
        if not segment_text:
            segment_text = " ".join(word["word"] for word in words).strip()

        segments.append(TranscriptSegment(
            id=index,
            start=round(_coerce_float(_get_value(segment, "start", 0.0)), 3),
            end=round(_coerce_float(_get_value(segment, "end", 0.0)), 3),
            text=segment_text,
            words=words or None,
        ))

    full_text = str(_get_value(result, "text", "") or "").strip()
    if not full_text:
        full_text = " ".join(segment.text for segment in segments).strip()

    transcript = TranscriptResult(
        language=str(_get_value(result, "language", "en") or "en"),
        duration=round(max((segment.end for segment in segments), default=0.0), 2),
        segments=segments,
        full_text=full_text,
    )

    logger.info(
        f"Transcription complete: {len(segments)} segments, "
        f"language={transcript.language}, duration={transcript.duration}s"
    )
    return transcript
