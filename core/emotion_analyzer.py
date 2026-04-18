"""
AttentionX – Emotion Analyzer
Analyzes emotional content over time using audio features and text sentiment.

Produces the "Emotion Timeline" — a 2D valence/arousal curve that helps
visualize where peaks of energy and emotion occur in the video.

Technical approach:
  1. RMS energy → arousal proxy (louder = more energetic)
  2. Spectral centroid → brightness (bright = excited vs dark = sad)
  3. Simple rule-based text sentiment → valence
"""

import numpy as np
import logging
from typing import List

from attentionx.backend.models.schemas import EmotionPoint, TranscriptResult

logger = logging.getLogger(__name__)

# Emotion label mapping based on valence/arousal quadrants
def _get_emotion_label(valence: float, arousal: float) -> str:
    """Map valence/arousal to emotion label."""
    if valence >= 0 and arousal >= 0.5:
        return "excited"
    elif valence >= 0 and arousal < 0.5:
        return "calm"
    elif valence < 0 and arousal >= 0.5:
        return "angry"
    else:
        return "sad"


def analyze_emotions(audio_path: str, transcript: TranscriptResult) -> List[EmotionPoint]:
    """
    Build a per-second emotion timeline combining audio features + text sentiment.

    Returns
    -------
    List[EmotionPoint]
        One point per second with valence and arousal values in [-1, 1] and [0, 1].
    """
    import librosa

    logger.info("Loading audio for emotion analysis...")
    y, sr = librosa.load(audio_path, sr=16000, mono=True)

    hop_length = sr  # 1-second frames
    frame_length = sr * 2

    # ── Audio-based arousal (RMS energy) ─────────────────────────────────────
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    rms_norm = (rms - rms.min()) / (rms.max() - rms.min() + 1e-8)

    # ── Spectral centroid (brightness) ────────────────────────────────────────
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
    centroid_norm = (centroid - centroid.min()) / (centroid.max() - centroid.min() + 1e-8)

    # ── Text-based valence ────────────────────────────────────────────────────
    # Build a time-indexed valence map from transcript sentiment
    valence_map = _compute_text_valence_map(transcript, duration=len(y) / sr)

    # ── Combine into emotion points ───────────────────────────────────────────
    n_frames = len(rms_norm)
    emotion_points: List[EmotionPoint] = []

    for i in range(n_frames):
        t = float(i)  # time in seconds

        # Arousal = blend of RMS energy and spectral brightness
        arousal = float(0.7 * rms_norm[i] + 0.3 * centroid_norm[i])
        arousal = round(min(1.0, max(0.0, arousal)), 3)

        # Valence from text, smoothed with audio brightness
        text_valence = valence_map.get(int(t), 0.0)
        audio_valence = centroid_norm[i] * 2 - 1  # convert 0–1 → -1–1
        valence = float(0.6 * text_valence + 0.4 * audio_valence)
        valence = round(min(1.0, max(-1.0, valence)), 3)

        label = _get_emotion_label(valence, arousal)

        emotion_points.append(EmotionPoint(
            time=t,
            valence=valence,
            arousal=arousal,
            label=label,
        ))

    logger.info(f"Emotion timeline computed: {len(emotion_points)} points")
    return emotion_points


def _compute_text_valence_map(transcript: TranscriptResult, duration: float) -> dict:
    """
    Compute per-second valence scores from transcript segments using
    keyword-based sentiment analysis.
    """
    POSITIVE_WORDS = {
        "amazing", "great", "excellent", "perfect", "love", "best", "wonderful",
        "incredible", "fantastic", "success", "win", "happy", "joy", "inspire",
        "motivate", "breakthrough", "achieve", "unlock", "powerful", "grow",
    }
    NEGATIVE_WORDS = {
        "wrong", "fail", "mistake", "bad", "terrible", "never", "avoid",
        "stop", "danger", "problem", "loss", "struggle", "difficult", "hard",
        "regret", "fear", "angry", "sad", "broken",
    }

    valence_map: dict = {}

    for seg in transcript.segments:
        words_in_seg = seg.text.lower().split()
        pos_count = sum(1 for w in words_in_seg if w.strip(".,!?") in POSITIVE_WORDS)
        neg_count = sum(1 for w in words_in_seg if w.strip(".,!?") in NEGATIVE_WORDS)
        seg_len = len(words_in_seg) + 1

        # Normalize valence: -1 to +1
        valence = (pos_count - neg_count) / seg_len * 3  # amplify
        valence = max(-1.0, min(1.0, valence))

        # Assign to each second in this segment
        for t in range(int(seg.start), int(seg.end) + 1):
            valence_map[t] = valence

    return valence_map


def find_emotion_peaks(emotion_points: List[EmotionPoint], top_n: int = 10):
    """
    Find timestamps where emotional intensity (arousal) peaks.
    Used to seed the virality segment detection.
    """
    if not emotion_points:
        return []

    # Simple local maxima detection
    peaks = []
    n = len(emotion_points)
    for i in range(1, n - 1):
        if (emotion_points[i].arousal > emotion_points[i - 1].arousal and
                emotion_points[i].arousal > emotion_points[i + 1].arousal and
                emotion_points[i].arousal > 0.4):
            peaks.append(emotion_points[i])

    # Sort by arousal and return top N
    peaks.sort(key=lambda p: p.arousal, reverse=True)
    return peaks[:top_n]
