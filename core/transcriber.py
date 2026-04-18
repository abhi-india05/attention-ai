"""
AttentionX – Whisper Transcriber
Transcribes audio using OpenAI Whisper with word-level timestamps.

Whisper gives us:
  - Full transcript text
  - Segment-level timestamps (sentence level)
  - Word-level timestamps (when using word_timestamps=True)

This is the FOUNDATION for the entire virality engine.
"""

import logging
from typing import Optional
from pathlib import Path

from attentionx.backend.models.schemas import TranscriptSegment, TranscriptResult
from attentionx.backend.config import WHISPER_MODEL

logger = logging.getLogger(__name__)


def transcribe(audio_path: str) -> TranscriptResult:
    """
    Transcribe audio using OpenAI Whisper.

    Parameters
    ----------
    audio_path : str
        Path to the 16kHz mono WAV audio file.

    Returns
    -------
    TranscriptResult
        Structured transcript with segments and word-level timestamps.
    """
    import whisper

    logger.info(f"Loading Whisper model: {WHISPER_MODEL}")
    model = whisper.load_model(WHISPER_MODEL)

    logger.info(f"Transcribing: {audio_path}")
    result = model.transcribe(
        audio_path,
        word_timestamps=True,    # Critical: enables word-level timing
        verbose=False,
        language=None,           # Auto-detect language
        condition_on_previous_text=True,
    )

    # ── Parse segments ────────────────────────────────────────────────────────
    segments: list[TranscriptSegment] = []
    for i, seg in enumerate(result.get("segments", [])):
        words = []
        for w in seg.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
                "probability": round(w.get("probability", 1.0), 3),
            })

        segments.append(TranscriptSegment(
            id=i,
            start=round(seg["start"], 3),
            end=round(seg["end"], 3),
            text=seg["text"].strip(),
            words=words,
        ))

    full_text = " ".join(s.text for s in segments)

    # Get audio duration from last segment
    total_duration = segments[-1].end if segments else 0.0

    transcript = TranscriptResult(
        language=result.get("language", "en"),
        duration=round(total_duration, 2),
        segments=segments,
        full_text=full_text,
    )

    logger.info(
        f"Transcription complete: {len(segments)} segments, "
        f"language={transcript.language}, duration={transcript.duration}s"
    )
    return transcript
