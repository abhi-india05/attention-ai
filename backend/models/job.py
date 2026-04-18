"""
AttentionX – Job State Manager
In-memory job store with thread-safe operations.
For production: replace with Redis or a database.
"""

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional

from attentionx.backend.models.schemas import (
    JobState, JobStatus, ProcessingStep, Platform
)

# ── In-memory store ───────────────────────────────────────────────────────────
_jobs: Dict[str, JobState] = {}
_job_lock = asyncio.Lock()


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
    "audio_extraction":  "Extracting Audio",
    "transcription":     "Transcribing Speech",
    "emotion_analysis":  "Analyzing Emotions",
    "virality_scoring":  "Computing Virality Scores",
    "clip_detection":    "Detecting Best Moments",
    "clip_generation":   "Generating Clips",
    "face_detection":    "Smart Face Cropping (9:16)",
    "caption_generation":"Creating Captions",
    "hook_generation":   "Writing Viral Hooks",
    "hashtag_generation":"Generating Hashtags",
    "finalization":      "Finalizing Clips",
}


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
    return job_id


def get_job(job_id: str) -> Optional[JobState]:
    """Retrieve a job by ID."""
    return _jobs.get(job_id)


def get_all_jobs() -> Dict[str, JobState]:
    """Return all jobs."""
    return dict(_jobs)


def update_job_status(job_id: str, status: JobStatus) -> None:
    """Update the high-level status of a job."""
    if job_id in _jobs:
        _jobs[job_id].status = status
        _jobs[job_id].updated_at = datetime.now(timezone.utc).isoformat()


def update_step(job_id: str, step_name: str, status: str, message: str = "", progress: int = 0) -> None:
    """Update a specific pipeline step's state."""
    if job_id not in _jobs:
        return
    job = _jobs[job_id]
    for step in job.steps:
        if step.name == step_name:
            step.status = status
            step.message = message or STEP_LABELS.get(step_name, step_name)
            step.progress = progress
            break
    # Recompute total progress
    done_steps = sum(1 for s in job.steps if s.status == "done")
    job.total_progress = int((done_steps / len(job.steps)) * 100)
    job.updated_at = datetime.now(timezone.utc).isoformat()


def set_job_error(job_id: str, error: str) -> None:
    """Mark job as failed with an error message."""
    if job_id in _jobs:
        _jobs[job_id].status = JobStatus.FAILED
        _jobs[job_id].error = error
        _jobs[job_id].updated_at = datetime.now(timezone.utc).isoformat()


def set_job_clips(job_id: str, clips: list, emotion_timeline: list) -> None:
    """Store final clips and emotion timeline in the job."""
    if job_id in _jobs:
        _jobs[job_id].clips = clips
        _jobs[job_id].emotion_timeline = emotion_timeline
        _jobs[job_id].status = JobStatus.COMPLETED
        _jobs[job_id].total_progress = 100
        _jobs[job_id].updated_at = datetime.now(timezone.utc).isoformat()
