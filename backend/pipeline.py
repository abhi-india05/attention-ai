"""
AttentionX – Processing Pipeline Orchestrator
Coordinates all pipeline steps and updates job state.

This is the heart of AttentionX — it orchestrates every processing
step in the correct order, with proper error handling and progress tracking.
"""

import logging
import asyncio
from pathlib import Path
from typing import Optional

from attentionx.backend.config import CLIPS_DIR
from attentionx.backend.models.schemas import Platform, ClipResult
from attentionx.backend.models.job import (
    update_job_status, update_step, set_job_error, set_job_clips,
    JobStatus
)

logger = logging.getLogger(__name__)


async def run_pipeline(
    job_id: str,
    video_path: str,
    platform: Platform = Platform.TIKTOK,
    max_clips: int = 5,
    min_duration: int = 20,
    max_duration: int = 60,
) -> None:
    """
    Main async pipeline orchestrator.
    Runs in background via FastAPI BackgroundTasks.

    Steps:
      1. Extract audio
      2. Transcribe
      3. Analyze emotions
      4. Score virality
      5. Detect clips
      6. Generate clips (crop, captions, hooks, hashtags)
      7. Finalize
    """
    import concurrent.futures
    loop = asyncio.get_event_loop()

    def _run_sync():
        _pipeline_sync(
            job_id=job_id,
            video_path=video_path,
            platform=platform,
            max_clips=max_clips,
            min_duration=min_duration,
            max_duration=max_duration,
        )

    try:
        update_job_status(job_id, JobStatus.PROCESSING)
        # Run sync pipeline in thread pool to not block event loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            await loop.run_in_executor(pool, _run_sync)
    except Exception as e:
        logger.error(f"Pipeline failed for job {job_id}: {e}", exc_info=True)
        set_job_error(job_id, str(e))


def _pipeline_sync(
    job_id: str,
    video_path: str,
    platform: Platform,
    max_clips: int,
    min_duration: int,
    max_duration: int,
) -> None:
    """Synchronous pipeline (runs in thread pool)."""

    from attentionx.core.audio_extractor import extract_audio
    from attentionx.core.transcriber import transcribe
    from attentionx.core.emotion_analyzer import analyze_emotions
    from attentionx.core.virality_engine import score_segments
    from attentionx.core.clip_generator import generate_clips
    from attentionx.core.smart_cropper import smart_crop_to_vertical
    from attentionx.core.caption_engine import build_captions, burn_captions
    from attentionx.core.hook_generator import generate_hooks, generate_clip_title
    from attentionx.core.hashtag_generator import generate_hashtags
    from attentionx.backend.models.schemas import ClipResult

    job_clip_dir = CLIPS_DIR / job_id
    job_clip_dir.mkdir(parents=True, exist_ok=True)

    temp_audio_path: Optional[str] = None

    try:
        # ── Step 1: Extract Audio ─────────────────────────────────────────────
        update_step(job_id, "audio_extraction", "running",
                    "Extracting audio track from video...", 10)
        try:
            temp_audio_path = extract_audio(video_path, job_clip_dir)
        except Exception as e:
            update_step(job_id, "audio_extraction", "error",
                        f"Audio extraction failed: {e}", error_detail=str(e))
            raise
        update_step(job_id, "audio_extraction", "done",
                    "✓ Audio track extracted successfully", 100)

        # ── Step 2: Transcribe ────────────────────────────────────────────────
        update_step(job_id, "transcription", "running",
                    "Running Groq Whisper transcription... (this takes a moment)", 5)
        try:
            transcript = transcribe(temp_audio_path)
        except Exception as e:
            update_step(job_id, "transcription", "error",
                        f"Transcription failed: {e}", error_detail=str(e))
            raise
        update_step(job_id, "transcription", "done",
                    f"✓ Transcribed {len(transcript.segments)} segments · language: {transcript.language}", 100)

        if not transcript.segments:
            raise ValueError("No speech detected in video – ensure the video has audible speech")

        # ── Step 3: Emotion Analysis ──────────────────────────────────────────
        update_step(job_id, "emotion_analysis", "running",
                    "Analyzing emotional peaks and valence...", 20)
        try:
            emotion_timeline = analyze_emotions(temp_audio_path, transcript)
        except Exception as e:
            update_step(job_id, "emotion_analysis", "error",
                        f"Emotion analysis failed: {e}", error_detail=str(e))
            raise
        update_step(job_id, "emotion_analysis", "done",
                    f"✓ Emotion timeline built · {len(emotion_timeline)} data points", 100)

        # ── Step 4: Virality Scoring ──────────────────────────────────────────
        update_step(job_id, "virality_scoring", "running",
                    "Scoring segments across 5 virality signals (AI analysis)...", 10)
        try:
            scored_segments = score_segments(transcript, temp_audio_path, emotion_timeline)
        except Exception as e:
            update_step(job_id, "virality_scoring", "error",
                        f"Virality scoring failed: {e}", error_detail=str(e))
            raise
        top_score = f"{scored_segments[0][1].total:.2f}" if scored_segments else "N/A"
        update_step(job_id, "virality_scoring", "done",
                    f"✓ Scored {len(scored_segments)} segments · top score: {top_score}", 100)

        # ── Step 5: Clip Detection ────────────────────────────────────────────
        update_step(job_id, "clip_detection", "running",
                    "Detecting highest-scoring viral moments...", 30)
        try:
            raw_clips = generate_clips(
                video_path=video_path,
                scored_segments=scored_segments,
                transcript=transcript,
                platform=platform,
                max_clips=max_clips,
                job_id=job_id,
            )
        except Exception as e:
            update_step(job_id, "clip_detection", "error",
                        f"Clip detection failed: {e}", error_detail=str(e))
            raise
        update_step(job_id, "clip_detection", "done",
                    f"✓ Detected {len(raw_clips)} viral moments", 100)

        # ── Step 6–10: Per-clip processing ───────────────────────────────────
        total_clips = len(raw_clips)
        final_clips: list[ClipResult] = []

        for i, clip_data in enumerate(raw_clips):
            clip_id = clip_data["clip_id"]
            clip_num = i + 1
            raw_path = clip_data["raw_clip_path"]

            logger.info(f"Processing clip {clip_num}/{total_clips}: {clip_id}")

            # Step 6a: Smart crop to 9:16
            update_step(job_id, "face_detection", "running",
                        f"Smart cropping clip {clip_num}/{total_clips} to 9:16...",
                        int((i / total_clips) * 100))

            cropped_path = str(job_clip_dir / f"clip_{clip_num:02d}_{clip_id}_cropped.mp4")
            smart_crop_to_vertical(raw_path, cropped_path)

            # Step 6b: Build captions
            update_step(job_id, "caption_generation", "running",
                        f"Generating captions for clip {clip_num}/{total_clips}...",
                        int((i / total_clips) * 100))

            captions = build_captions(
                transcript=transcript,
                clip_start=clip_data["start_time"],
                clip_end=clip_data["end_time"],
                platform=platform,
            )

            # Step 6c: Burn captions
            captioned_path = str(job_clip_dir / f"clip_{clip_num:02d}_{clip_id}_captioned.mp4")
            if captions:
                burn_captions(cropped_path, captions, captioned_path, platform)
            else:
                import shutil
                shutil.copy(cropped_path, captioned_path)

            # Step 6d: Generate hooks
            update_step(job_id, "hook_generation", "running",
                        f"Writing viral hooks for clip {clip_num}/{total_clips}...",
                        int((i / total_clips) * 100))

            hooks = generate_hooks(
                transcript_excerpt=clip_data["transcript_excerpt"],
                platform=platform.value,
            )

            # Generate clip title
            clip_title = generate_clip_title(clip_data["transcript_excerpt"])

            # Step 6e: Generate hashtags
            update_step(job_id, "hashtag_generation", "running",
                        f"Generating hashtags for clip {clip_num}/{total_clips}...",
                        int((i / total_clips) * 100))

            hashtags = generate_hashtags(
                transcript_excerpt=clip_data["transcript_excerpt"],
                platform=platform.value,
            )

            # Final output path
            final_path = str(job_clip_dir / f"clip_{clip_num:02d}_{clip_id}_final.mp4")
            import shutil
            shutil.copy(captioned_path, final_path)

            # Cleanup intermediate files
            for p in [raw_path, cropped_path, captioned_path]:
                try:
                    if p != final_path:
                        Path(p).unlink(missing_ok=True)
                except Exception:
                    pass

            # Get emotion points for this clip's time window
            clip_emotions = [
                ep for ep in emotion_timeline
                if clip_data["start_time"] <= ep.time <= clip_data["end_time"]
            ]

            # Build ClipResult
            clip_result = ClipResult(
                clip_id=clip_id,
                job_id=job_id,
                rank=clip_data["rank"],
                title=clip_title,
                start_time=clip_data["start_time"],
                end_time=clip_data["end_time"],
                duration=clip_data["duration"],
                platform=platform,
                virality_score=clip_data["virality_score"],
                hooks=hooks,
                captions=captions,
                hashtags=hashtags,
                file_path=final_path,
                preview_url=f"/video/{job_id}/{clip_id}",
                emotion_points=clip_emotions,
                transcript_excerpt=clip_data["transcript_excerpt"],
            )
            final_clips.append(clip_result)

        # Mark per-clip steps as done
        for step in ["face_detection", "caption_generation", "hook_generation", "hashtag_generation"]:
            update_step(job_id, step, "done", "Complete", 100)

        # ── Step 11: Finalize ─────────────────────────────────────────────────
        update_step(job_id, "clip_generation", "done", f"Generated {len(final_clips)} clips", 100)
        update_step(job_id, "finalization", "running", "Finalizing output...", 50)

        # Sort by virality score
        final_clips.sort(key=lambda c: c.virality_score.total, reverse=True)
        for i, clip in enumerate(final_clips):
            clip.rank = i + 1

        update_step(job_id, "finalization", "done",
                    f"✅ {len(final_clips)} viral clips ready!", 100)

        set_job_clips(job_id, final_clips, emotion_timeline)
        logger.info(f"Pipeline complete for job {job_id}: {len(final_clips)} clips")

    except Exception as e:
        logger.error(f"Pipeline error for job {job_id}: {e}", exc_info=True)
        # Find the currently-running step and mark it as errored
        from attentionx.backend.models.job import get_job as _get_job
        job = _get_job(job_id)
        if job:
            running_step = next((s.name for s in job.steps if s.status == "running"), None)
        else:
            running_step = None
        set_job_error(job_id, str(e), step_name=running_step)
        raise
    finally:
        # Cleanup temp audio
        if temp_audio_path:
            try:
                Path(temp_audio_path).unlink(missing_ok=True)
            except Exception:
                pass
