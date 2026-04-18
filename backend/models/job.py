"""
AttentionX – Enhanced Job State Manager (v2)
In-memory job store with timing tracking, ETA calculation, and error logging.

New in v2:
  - Per-step start/completion timestamps
  - ETA calculation using historical step duration estimates
  - current_step_name for easy polling
  - Structured error logging per step
"""

import uuid
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from attentionx.backend.models.schemas import (
    JobState, JobStatus, ProcessingStep, Platform
)

# ── In-memory store ───────────────────────────────────────────────────────────
_jobs: Dict[str, JobState] = {}
# Track step start times separately (not serialized into the model directly)
_step_start_times: Dict[str, Dict[str, float]] = {}   # job_id → step_name → time.monotonic()
_pipeline_start_times: Dict[str, float] = {}           # job_id → time.monotonic()


# ── Predefined pipeline steps ─────────────────────────────────────────────────
PIPELINE_STEPS = [
    "audio_extraction",
    "transcription",
    "emotion_analysis",
    "virality_scoring",
    "clip_detection",
    "clip_generation",
    "face_detection",
    "caption_generation",
    "hook_generation",
    "hashtag_generation",
    "finalization",
]

STEP_LABELS = {
    "audio_extraction":   "Extracting Audio",
    "transcription":      "Transcribing Speech",
    "emotion_analysis":   "Analyzing Emotions",
    "virality_scoring":   "Computing Virality Scores",
    "clip_detection":     "Detecting Best Moments",
    "clip_generation":    "Generating Clips",
    "face_detection":     "Smart Face Cropping (9:16)",
    "caption_generation": "Creating Captions",
    "hook_generation":    "Writing Viral Hooks",
    "hashtag_generation": "Generating Hashtags",
    "finalization":       "Finalizing Clips",
}

# ── ETA: estimated seconds per step (calibrated for typical 10-min video) ────
# These are used to project how long remaining steps will take.
STEP_ESTIMATED_SECONDS: Dict[str, float] = {
    "audio_extraction":   8.0,
    "transcription":      40.0,
    "emotion_analysis":   12.0,
    "virality_scoring":   18.0,
    "clip_detection":     8.0,
    "clip_generation":    25.0,
    "face_detection":     50.0,
    "caption_generation": 15.0,
    "hook_generation":    10.0,
    "hashtag_generation": 6.0,
    "finalization":       4.0,
}

TOTAL_ESTIMATED_SECONDS = sum(STEP_ESTIMATED_SECONDS.values())


# ── Job creation ──────────────────────────────────────────────────────────────

def create_job(filename: str, platform: Platform = Platform.TIKTOK) -> str:
    """Create a new job and return its ID."""
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    steps = [
        ProcessingStep(name=s, status="pending", message=STEP_LABELS[s])
        for s in PIPELINE_STEPS
    ]

    _jobs[job_id] = JobState(
        job_id=job_id,
        status=JobStatus.QUEUED,
        video_filename=filename,
        platform=platform,
        created_at=now,
        updated_at=now,
        steps=steps,
        clips=[],
        total_progress=0,
    )
    _step_start_times[job_id] = {}
    return job_id


# ── Job retrieval ─────────────────────────────────────────────────────────────

def get_job(job_id: str) -> Optional[JobState]:
    """Retrieve a job by ID, with freshly computed ETA."""
    job = _jobs.get(job_id)
    if job:
        _refresh_eta(job)
    return job


def get_all_jobs() -> Dict[str, JobState]:
    """Return all jobs."""
    return dict(_jobs)


# ── Status updates ────────────────────────────────────────────────────────────

def update_job_status(job_id: str, status: JobStatus) -> None:
    """Update the high-level status of a job."""
    if job_id not in _jobs:
        return
    job = _jobs[job_id]
    job.status = status
    job.updated_at = datetime.now(timezone.utc).isoformat()

    if status == JobStatus.PROCESSING and job.pipeline_started_at is None:
        job.pipeline_started_at = job.updated_at
        _pipeline_start_times[job_id] = time.monotonic()


def update_step(
    job_id: str,
    step_name: str,
    status: str,
    message: str = "",
    progress: int = 0,
    error_detail: Optional[str] = None,
) -> None:
    """
    Update a specific pipeline step's state.

    When status transitions to 'running':
      - Records start timestamp
    When status transitions to 'done' or 'error':
      - Computes elapsed time
      - Updates current_step_name
    """
    if job_id not in _jobs:
        return

    job = _jobs[job_id]
    now_utc = datetime.now(timezone.utc).isoformat()
    now_mono = time.monotonic()

    for step in job.steps:
        if step.name != step_name:
            continue

        # Capture start time on first 'running' transition
        if status == "running" and step.status != "running":
            step.started_at = now_utc
            _step_start_times.setdefault(job_id, {})[step_name] = now_mono

        # Compute elapsed when finishing
        if status in ("done", "error"):
            step.completed_at = now_utc
            start_mono = _step_start_times.get(job_id, {}).get(step_name)
            if start_mono is not None:
                step.elapsed_seconds = round(now_mono - start_mono, 2)

        step.status = status
        step.message = message or STEP_LABELS.get(step_name, step_name)
        step.progress = progress
        if error_detail:
            step.error_detail = error_detail
        break

    # Recompute overall progress (weighted by done steps)
    done_steps = sum(1 for s in job.steps if s.status == "done")
    running_step = next((s for s in job.steps if s.status == "running"), None)
    base_progress = int((done_steps / len(job.steps)) * 100)
    # Add partial step progress
    if running_step:
        step_share = 100 / len(job.steps)
        base_progress += int(step_share * (running_step.progress / 100))

    job.total_progress = min(99, base_progress)  # cap at 99 until finalized
    job.current_step_name = step_name if status == "running" else job.current_step_name
    job.updated_at = now_utc

    _refresh_eta(job)


def set_job_error(job_id: str, error: str, step_name: Optional[str] = None) -> None:
    """Mark job as failed. Optionally marks a specific step as errored."""
    if job_id not in _jobs:
        return
    job = _jobs[job_id]
    job.status = JobStatus.FAILED
    job.error = error
    job.updated_at = datetime.now(timezone.utc).isoformat()

    if step_name:
        update_step(job_id, step_name, "error", f"Failed: {error[:120]}", error_detail=error)

    # Mark all pending steps as skipped (keep them pending for display)
    _refresh_eta(job)


def set_job_clips(job_id: str, clips: list, emotion_timeline: list) -> None:
    """Store final clips and emotion timeline in the job."""
    if job_id not in _jobs:
        return
    job = _jobs[job_id]
    job.clips = clips
    job.emotion_timeline = emotion_timeline
    job.status = JobStatus.COMPLETED
    job.total_progress = 100
    job.current_step_name = "finalization"
    job.eta_seconds = 0.0
    job.updated_at = datetime.now(timezone.utc).isoformat()

    # Compute total elapsed
    start = _pipeline_start_times.get(job_id)
    if start:
        job.elapsed_total_seconds = round(time.monotonic() - start, 1)


# ── ETA helpers ───────────────────────────────────────────────────────────────

def _refresh_eta(job: JobState) -> None:
    """
    Recompute estimated time remaining and total elapsed in-place.

    Algorithm:
      1. Sum the estimated durations of all steps not yet 'done'.
      2. For the currently-running step, subtract the time already spent.
      3. ETA = sum of pending step estimates + remaining time on running step.
    """
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        if job.status == JobStatus.COMPLETED:
            job.eta_seconds = 0.0
        return

    start = _pipeline_start_times.get(job.job_id)
    if start:
        job.elapsed_total_seconds = round(time.monotonic() - start, 1)

    remaining_secs = 0.0
    for step in job.steps:
        est = STEP_ESTIMATED_SECONDS.get(step.name, 10.0)

        if step.status == "done":
            continue
        elif step.status == "running":
            # Deduct time already spent on this step
            step_start = _step_start_times.get(job.job_id, {}).get(step.name)
            if step_start is not None:
                already_spent = time.monotonic() - step_start
                remaining_secs += max(0.0, est - already_spent)
            else:
                remaining_secs += est
        else:  # pending
            remaining_secs += est

    job.eta_seconds = round(remaining_secs, 0)


def build_status_response(job: JobState) -> dict:
    """
    Build the lightweight StatusResponse dict for the polling endpoint.
    Returns fields: job_id, current_step, progress, message, status, eta_seconds,
    elapsed_seconds, steps_summary.
    """
    # Find the currently active step message
    running = next((s for s in job.steps if s.status == "running"), None)
    last_done = next(
        (s for s in reversed(job.steps) if s.status == "done"), None
    )
    active = running or last_done

    current_step = STEP_LABELS.get(job.current_step_name or "", "Processing...")
    if job.status == JobStatus.QUEUED:
        message = "Waiting to start..."
    elif job.status == JobStatus.PROCESSING:
        message = (active.message if active else "Processing...")
    elif job.status == JobStatus.COMPLETED:
        message = "All clips are ready!"
    else:  # FAILED
        message = job.error or "Processing failed"

    steps_summary = [
        {
            "name": s.name,
            "label": STEP_LABELS.get(s.name, s.name),
            "status": s.status,
            "elapsed_seconds": s.elapsed_seconds,
            "error_detail": s.error_detail,
        }
        for s in job.steps
    ]

    return {
        "job_id": job.job_id,
        "current_step": current_step,
        "progress": job.total_progress,
        "message": message,
        "status": job.status.value,
        "eta_seconds": job.eta_seconds,
        "elapsed_seconds": job.elapsed_total_seconds,
        "steps_summary": steps_summary,
    }
