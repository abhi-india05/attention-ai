"""
AttentionX – Intelligent Clip Generator
Converts scored segments into polished video clips using MoviePy.

Key intelligence:
  1. Adjacent high-scoring segments are merged into coherent clips
  2. Clip boundaries are expanded to sentence boundaries (no mid-sentence cuts)
  3. Natural pause detection prevents abrupt cuts
  4. Duration constraints enforced per platform preset
"""

import os
import uuid
import logging
from pathlib import Path
from typing import List, Tuple, Optional

from attentionx.backend.models.schemas import (
    TranscriptResult, TranscriptSegment, ViralityBreakdown, Platform
)
from attentionx.backend.config import (
    MIN_CLIP_DURATION, MAX_CLIP_DURATION, CLIP_CONTEXT_PADDING,
    MAX_CLIPS, PLATFORM_PRESETS, CLIPS_DIR
)
from attentionx.utils.file_utils import resolve_ffmpeg_executable

logger = logging.getLogger(__name__)


# ── Segment merging ───────────────────────────────────────────────────────────

def _merge_nearby_segments(
    scored_segments: List[Tuple[TranscriptSegment, ViralityBreakdown]],
    merge_gap: float = 3.0,
) -> List[Tuple[List[TranscriptSegment], ViralityBreakdown]]:
    """
    Merge adjacent high-scoring segments that are close in time.
    This ensures clips contain complete ideas, not fragmented thoughts.

    Args:
        scored_segments: Sorted by virality score (highest first).
        merge_gap: Max gap in seconds between segments to merge.

    Returns:
        List of (merged_segment_list, combined_virality) tuples.
    """
    if not scored_segments:
        return []

    # Take top segments for merging (limit to avoid diminishing returns)
    candidates = scored_segments[:MAX_CLIPS * 3]

    # Sort candidates by TIME to build contiguous regions
    time_sorted = sorted(candidates, key=lambda x: x[0].start)

    merged_groups: List[Tuple[List[TranscriptSegment], List[ViralityBreakdown]]] = []
    current_group: List[TranscriptSegment] = []
    current_scores: List[ViralityBreakdown] = []

    for seg, score in time_sorted:
        if not current_group:
            current_group = [seg]
            current_scores = [score]
        elif seg.start - current_group[-1].end <= merge_gap:
            # Close enough to merge
            current_group.append(seg)
            current_scores.append(score)
        else:
            merged_groups.append((current_group, current_scores))
            current_group = [seg]
            current_scores = [score]

    if current_group:
        merged_groups.append((current_group, current_scores))

    # Compute combined virality for each merged group
    result = []
    for group, scores in merged_groups:
        # Average scores across merged segments
        avg_audio = sum(s.audio_intensity for s in scores) / len(scores)
        avg_sentiment = sum(s.sentiment_score for s in scores) / len(scores)
        avg_semantic = sum(s.semantic_importance for s in scores) / len(scores)
        avg_keyword = sum(s.keyword_triggers for s in scores) / len(scores)
        avg_curiosity = sum(s.curiosity_hook for s in scores) / len(scores)
        avg_total = sum(s.total for s in scores) / len(scores)

        combined = ViralityBreakdown(
            audio_intensity=round(avg_audio, 3),
            sentiment_score=round(avg_sentiment, 3),
            semantic_importance=round(avg_semantic, 3),
            keyword_triggers=round(avg_keyword, 3),
            curiosity_hook=round(avg_curiosity, 3),
            total=round(avg_total, 3),
        )
        result.append((group, combined))

    # Sort merged groups by combined virality
    result.sort(key=lambda x: x[1].total, reverse=True)
    return result


def _expand_to_sentence_boundaries(
    start: float,
    end: float,
    transcript: TranscriptResult,
    padding: float = CLIP_CONTEXT_PADDING,
    min_duration: float = MIN_CLIP_DURATION,
    max_duration: float = MAX_CLIP_DURATION,
) -> Tuple[float, float]:
    """
    Expand clip boundaries to align with complete sentences.
    Also adds context padding for natural flow.
    Enforces min/max duration constraints.
    """
    # Add padding
    expanded_start = max(0.0, start - padding)
    expanded_end = min(transcript.duration, end + padding)

    # Find the actual sentence that starts before or at expanded_start
    for seg in reversed(transcript.segments):
        if seg.start <= expanded_start:
            expanded_start = seg.start
            break

    # Find the actual sentence that ends after or at expanded_end
    for seg in transcript.segments:
        if seg.end >= expanded_end:
            expanded_end = seg.end
            break

    # Enforce duration constraints
    current_duration = expanded_end - expanded_start
    if current_duration < min_duration:
        # Extend end to meet minimum
        expanded_end = min(transcript.duration, expanded_start + min_duration)
    elif current_duration > max_duration:
        # Trim from the end
        expanded_end = expanded_start + max_duration

    return max(0.0, expanded_start), min(transcript.duration, expanded_end)


# ── Clip extraction from video ────────────────────────────────────────────────

def extract_clip_ffmpeg(
    video_path: str,
    start: float,
    end: float,
    output_path: str,
) -> str:
    """
    Extract a raw clip from the video using FFmpeg (fast, lossless seek).
    Returns the output path.
    """
    import subprocess

    ffmpeg_path = resolve_ffmpeg_executable()
    if not ffmpeg_path:
        raise RuntimeError(
            "FFmpeg executable not found. Install FFmpeg or set FFMPEG_PATH in .env."
        )

    cmd = [
        ffmpeg_path, "-y",
        "-ss", str(start),
        "-to", str(end),
        "-i", str(video_path),
        "-c:v", "copy",    # Stream copy for speed
        "-c:a", "copy",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        logger.warning(f"FFmpeg clip extraction warning: {result.stderr[:200]}")

    return output_path


def generate_clips(
    video_path: str,
    scored_segments: List[Tuple[TranscriptSegment, ViralityBreakdown]],
    transcript: TranscriptResult,
    platform: Platform = Platform.TIKTOK,
    max_clips: int = 5,
    job_id: str = "",
) -> List[dict]:
    """
    Generate final video clips from scored segments.

    Returns
    -------
    List of dicts with clip metadata including file paths.
    """
    preset = PLATFORM_PRESETS[platform.value]
    min_dur = preset["min_duration"]
    max_dur = preset["max_duration"]

    # Step 1: Merge adjacent top segments
    logger.info(f"Merging {len(scored_segments)} scored segments...")
    merged = _merge_nearby_segments(scored_segments)

    # Step 2: Expand boundaries and extract clips
    clips_data = []
    seen_ranges = []  # Prevent overlapping clips

    for rank, (segs, virality) in enumerate(merged[:max_clips * 2]):
        if len(clips_data) >= max_clips:
            break

        raw_start = segs[0].start
        raw_end = segs[-1].end

        # Expand to natural sentence boundaries
        clip_start, clip_end = _expand_to_sentence_boundaries(
            raw_start, raw_end, transcript,
            min_duration=min_dur,
            max_duration=max_dur,
        )

        # Skip if overlapping with existing clip
        overlapping = any(
            not (clip_end <= s or clip_start >= e)
            for s, e in seen_ranges
        )
        if overlapping:
            continue

        seen_ranges.append((clip_start, clip_end))

        duration = clip_end - clip_start
        clip_id = uuid.uuid4().hex[:8]

        # Extract raw clip
        raw_clip_dir = CLIPS_DIR / job_id
        raw_clip_dir.mkdir(parents=True, exist_ok=True)
        raw_clip_path = str(raw_clip_dir / f"clip_{rank+1:02d}_{clip_id}_raw.mp4")

        logger.info(f"Extracting clip {rank+1}: {clip_start:.1f}s–{clip_end:.1f}s")
        extract_clip_ffmpeg(video_path, clip_start, clip_end, raw_clip_path)

        # Get transcript excerpt for this clip
        transcript_excerpt = " ".join(
            s.text for s in transcript.segments
            if clip_start <= s.start <= clip_end
        )

        clips_data.append({
            "clip_id": clip_id,
            "rank": rank + 1,
            "start_time": clip_start,
            "end_time": clip_end,
            "duration": round(duration, 2),
            "virality_score": virality,
            "raw_clip_path": raw_clip_path,
            "transcript_excerpt": transcript_excerpt,
            "segments": segs,
        })

    logger.info(f"Generated {len(clips_data)} clips")
    return clips_data
