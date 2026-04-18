"""
AttentionX – Virality Engine
The core differentiator: multi-signal virality scoring for each transcript segment.

═══════════════════════════════════════════════════════════════════
HOW VIRALITY SCORING WORKS
═══════════════════════════════════════════════════════════════════

Each transcript segment is scored across 5 orthogonal signals:

1. AUDIO INTENSITY (weight: 20%)
   ─────────────────────────────
   Uses Librosa to compute RMS energy and spectral flux for each
   segment's audio window. Loud, dynamic moments score higher.
   Formula: 0.6 * rms_norm + 0.4 * spectral_flux_norm

2. SENTIMENT SCORE (weight: 15%)
   ─────────────────────────────
   Measures emotional polarity and intensity. Both strongly positive
   and strongly negative content performs well on social media
   (outrage and inspiration both drive shares).
   Formula: |valence| * arousal  (absolute value – direction doesn't matter)

3. SEMANTIC IMPORTANCE (weight: 30%)
   ─────────────────────────────────
   Sends each segment to the LLM with context asking it to rate:
   - Does this contain a key insight or revelation?
   - Is this a turning point in the narrative?
   - Would a viewer feel they learned something valuable?
   Highest weight because content quality determines shareability.

4. KEYWORD TRIGGERS (weight: 20%)
   ─────────────────────────────
   Presence of proven viral trigger words (see config.VIRAL_KEYWORDS).
   Words like "secret", "mistake", "nobody knows" create curiosity gaps
   that drive clicks and shares. 
   Formula: min(1.0, keyword_count / segment_word_count * 10)

5. CURIOSITY HOOK POTENTIAL (weight: 15%)
   ────────────────────────────────────────
   Detects:
   - Open-ended questions ("but why?", "what if?")
   - Incomplete thoughts that create loops ("here's the thing...")
   - Contrast structures ("everyone thinks X, but actually Y")
   - Numbers and lists ("3 reasons why...", "the #1 mistake...")
   These structures naturally create viewer retention.

COMPOSITE SCORE:
   final = Σ(signal_i * weight_i) ∈ [0, 1]

SEGMENT SELECTION:
   After scoring all segments, adjacent high-scoring segments are
   merged into candidate clips. Boundaries are then expanded to
   include complete sentences and natural pauses.
═══════════════════════════════════════════════════════════════════
"""

import re
import numpy as np
import logging
from typing import List, Tuple, Optional

from attentionx.backend.config import VIRALITY_WEIGHTS, VIRAL_KEYWORDS
from attentionx.backend.models.schemas import (
    TranscriptResult, TranscriptSegment, ViralityBreakdown, EmotionPoint
)
from attentionx.utils.llm_client import get_llm_client

logger = logging.getLogger(__name__)


# ── Audio-based scoring ───────────────────────────────────────────────────────

def _compute_audio_intensity(
    audio_path: str,
    segment_start: float,
    segment_end: float,
    y: Optional[np.ndarray] = None,
    sr: int = 16000,
) -> float:
    """
    Compute audio intensity for a segment window.
    Combines RMS energy (loudness) and spectral flux (dynamic changes).
    """
    import librosa

    if y is None:
        y, sr = librosa.load(audio_path, sr=sr, offset=segment_start,
                              duration=segment_end - segment_start, mono=True)

    if len(y) == 0:
        return 0.0

    # Clip to segment window
    start_sample = int(segment_start * sr)
    end_sample = int(segment_end * sr)
    segment_y = y[start_sample:end_sample]

    if len(segment_y) == 0:
        return 0.0

    # RMS energy (loudness proxy)
    rms = float(np.sqrt(np.mean(segment_y ** 2)))

    # Spectral flux (rate of change in spectrum → sudden events)
    hop = 512
    stft = np.abs(librosa.stft(segment_y, hop_length=hop))
    flux = float(np.mean(np.diff(stft, axis=1) ** 2)) if stft.shape[1] > 1 else 0.0

    # Return combined metric (will be normalized globally later)
    return rms * 0.6 + flux * 0.4


def _normalize_scores(scores: List[float]) -> List[float]:
    """Min-max normalize a list of scores to [0, 1]."""
    if not scores:
        return scores
    min_s, max_s = min(scores), max(scores)
    if max_s == min_s:
        return [0.5] * len(scores)
    return [(s - min_s) / (max_s - min_s) for s in scores]


# ── Keyword scoring ───────────────────────────────────────────────────────────

def _compute_keyword_score(text: str) -> float:
    """
    Score based on presence of viral trigger keywords.
    Longer segments get more keywords, so normalize by word count.
    """
    text_lower = text.lower()
    words = text_lower.split()
    if not words:
        return 0.0

    hit_count = 0
    for keyword in VIRAL_KEYWORDS:
        if keyword in text_lower:
            hit_count += 1

    # Normalize: 3+ keyword hits = score of 1.0
    score = min(1.0, hit_count / 3.0)
    return score


# ── Curiosity / hook scoring ──────────────────────────────────────────────────

# Patterns that indicate strong curiosity gap potential
CURIOSITY_PATTERNS = [
    r'\?',                              # Any question
    r'but here\'?s? the thing',        # Reveal setup
    r'wait\b',                          # Pause triggers
    r'actually\b',                      # Contradiction
    r'the real reason',                 # Revelation  
    r'nobody (knows|talks)',            # Exclusivity
    r'what (if|most people)',           # Hypothetical / contrast
    r'here\'?s? why',                   # Explanation hook
    r'\d+\s+(reason|tip|way|mistake)',  # Listicle hook
    r'plot twist',                      # Narrative surprise
    r'you won\'?t believe',             # Shock hook
    r'secret\b',                        # Exclusivity
    r'never (do|say|think)',            # Warning hook
    r'always\b.{0,20}(wrong|right)',   # Correction hook
]

def _compute_curiosity_score(text: str) -> float:
    """Score text for curiosity gap / hook potential using regex patterns."""
    text_lower = text.lower()
    matches = sum(1 for p in CURIOSITY_PATTERNS if re.search(p, text_lower))
    return min(1.0, matches / 3.0)


# ── LLM semantic scoring ──────────────────────────────────────────────────────

def _compute_semantic_score_batch(
    segments: List[TranscriptSegment],
    full_context: str,
) -> List[float]:
    """
    Use LLM to rate semantic importance of each segment in batch.
    Batching reduces API calls significantly.
    """
    llm = get_llm_client()

    # Build compact batch request with indices
    segment_texts = []
    for i, seg in enumerate(segments):
        segment_texts.append(f"[{i}] ({seg.start:.0f}s-{seg.end:.0f}s): {seg.text}")

    prompt = f"""You are a viral content expert analyzing a video transcript.

Context (first 500 chars of video): {full_context[:500]}

Rate each segment's VIRALITY potential from 0.0 to 1.0 based on:
- Does it contain a key insight, revelation, or turning point?
- Would viewers feel compelled to share this?
- Does it have strong narrative momentum or emotional impact?
- Is it self-contained enough to work as a standalone clip?

Segments to rate:
{chr(10).join(segment_texts[:20])}

Return ONLY a JSON object mapping index to score, like:
{{"0": 0.3, "1": 0.8, "2": 0.6}}

No explanations. Only the JSON object."""

    result = llm.complete_json(prompt, max_tokens=512)

    # Map results back to segments
    scores = []
    for i in range(len(segments)):
        score = float(result.get(str(i), 0.5))
        scores.append(max(0.0, min(1.0, score)))

    return scores


# ── Sentiment from emotion timeline ──────────────────────────────────────────

def _get_emotion_score_for_segment(
    segment: TranscriptSegment,
    emotion_points: List[EmotionPoint],
) -> float:
    """Extract averaged emotion intensity for a segment's time range."""
    if not emotion_points:
        return 0.5

    # Find emotion points within this segment's time window
    relevant = [
        ep for ep in emotion_points
        if segment.start <= ep.time <= segment.end
    ]

    if not relevant:
        # If no exact match, find nearest point
        nearest = min(emotion_points, key=lambda ep: abs(ep.time - segment.start))
        relevant = [nearest]

    # Intensity = |valence| * arousal (strong emotion in either direction is good)
    intensities = [abs(ep.valence) * ep.arousal for ep in relevant]
    return float(np.mean(intensities))


# ── Main scoring function ─────────────────────────────────────────────────────

def score_segments(
    transcript: TranscriptResult,
    audio_path: str,
    emotion_points: List[EmotionPoint],
) -> List[Tuple[TranscriptSegment, ViralityBreakdown]]:
    """
    Score all transcript segments and return them sorted by virality score descending.

    Returns
    -------
    List of (segment, virality_breakdown) tuples sorted by total score.
    """
    import librosa

    logger.info(f"Scoring {len(transcript.segments)} transcript segments...")

    # Load full audio once for efficiency
    y, sr = librosa.load(audio_path, sr=16000, mono=True)

    segments = transcript.segments

    # ── Signal 1: Audio intensity (batch) ─────────────────────────────────────
    logger.info("Computing audio intensity scores...")
    raw_audio = [
        _compute_audio_intensity("", s.start, s.end, y=y, sr=sr)
        for s in segments
    ]
    audio_scores = _normalize_scores(raw_audio)

    # ── Signal 2: Sentiment / emotion ─────────────────────────────────────────
    logger.info("Computing emotion scores...")
    emotion_scores = [
        _get_emotion_score_for_segment(s, emotion_points)
        for s in segments
    ]
    emotion_scores = _normalize_scores(emotion_scores)

    # ── Signal 3: Semantic importance (LLM) ───────────────────────────────────
    logger.info("Computing semantic importance via LLM...")
    semantic_scores = _compute_semantic_score_batch(segments, transcript.full_text)

    # ── Signal 4: Keyword triggers ────────────────────────────────────────────
    keyword_scores = [_compute_keyword_score(s.text) for s in segments]

    # ── Signal 5: Curiosity / hook potential ──────────────────────────────────
    curiosity_scores = [_compute_curiosity_score(s.text) for s in segments]

    # ── Composite score ───────────────────────────────────────────────────────
    w = VIRALITY_WEIGHTS
    scored = []

    for i, seg in enumerate(segments):
        # Duration filter: skip very short segments
        duration = seg.end - seg.start
        if duration < 2.0:
            continue

        a = audio_scores[i]
        e = emotion_scores[i]
        s = semantic_scores[i]
        k = keyword_scores[i]
        c = curiosity_scores[i]

        total = (
            a * w["audio_intensity"] +
            e * w["sentiment_score"] +
            s * w["semantic_importance"] +
            k * w["keyword_triggers"] +
            c * w["curiosity_hook"]
        )

        breakdown = ViralityBreakdown(
            audio_intensity=round(a, 3),
            sentiment_score=round(e, 3),
            semantic_importance=round(s, 3),
            keyword_triggers=round(k, 3),
            curiosity_hook=round(c, 3),
            total=round(total, 3),
        )

        scored.append((seg, breakdown))

    # Sort by total virality score descending
    scored.sort(key=lambda x: x[1].total, reverse=True)

    logger.info(f"Scoring complete. Top score: {scored[0][1].total if scored else 0:.3f}")
    return scored
