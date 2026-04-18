"""
AttentionX – Video Upload & Management Router
Handles file uploads, job creation, and clip retrieval.
"""

import os
import logging
import aiofiles
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from attentionx.backend.config import UPLOAD_DIR, CLIPS_DIR, PLATFORM_PRESETS
from attentionx.backend.models.schemas import (
    UploadResponse, ClipsResponse, ProcessRequest, JobStatus, Platform, StatusResponse
)
from attentionx.backend.models.job import create_job, get_job, get_all_jobs, build_status_response
from attentionx.utils.file_utils import get_video_metadata, safe_filename
from attentionx.backend.pipeline import run_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    platform: Platform = Form(default=Platform.TIKTOK),
):
    """
    Upload a video file and create a processing job.

    Supported formats: MP4, MOV, AVI, MKV, WebM
    Max file size: 2GB (configurable)
    """
    # Validate file type
    allowed_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {file_ext}. Supported: {', '.join(allowed_extensions)}"
        )

    # Create safe filename
    safe_name = safe_filename(Path(file.filename).stem) + file_ext
    upload_path = UPLOAD_DIR / safe_name

    # Handle filename collisions
    counter = 1
    while upload_path.exists():
        upload_path = UPLOAD_DIR / f"{safe_filename(Path(file.filename).stem)}_{counter}{file_ext}"
        counter += 1

    # Stream file to disk
    logger.info(f"Uploading: {file.filename} → {upload_path}")
    file_size = 0
    async with aiofiles.open(upload_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            await out_file.write(chunk)
            file_size += len(chunk)

    if file_size == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Get video metadata
    metadata = get_video_metadata(str(upload_path))
    duration = metadata.get("duration")

    # Create processing job
    job_id = create_job(str(upload_path), platform)

    logger.info(f"Job created: {job_id} for {safe_name} ({file_size/1e6:.1f}MB)")

    return UploadResponse(
        job_id=job_id,
        filename=safe_name,
        file_size=file_size,
        duration=duration,
        message=f"Upload successful. Job {job_id} created.",
    )


@router.post("/process")
async def process_video(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start processing a previously uploaded video.
    Processing runs in the background. Poll /status/{job_id} for updates.
    """
    job = get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {request.job_id} not found")

    if job.status not in [JobStatus.QUEUED, JobStatus.FAILED]:
        raise HTTPException(
            status_code=409,
            detail=f"Job is already {job.status.value}. Cannot re-process."
        )

    # Start pipeline in background
    background_tasks.add_task(
        run_pipeline,
        job_id=request.job_id,
        video_path=job.video_filename,
        platform=request.platform,
        max_clips=request.max_clips,
        min_duration=request.min_duration,
        max_duration=request.max_duration,
    )

    return {
        "job_id": request.job_id,
        "status": "processing",
        "message": "Pipeline started. Use /status/{job_id} to track progress.",
        "sse_url": f"/stream/{request.job_id}",
    }


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str):
    """
    Lightweight polling endpoint for real-time status.

    Returns:
        {
          job_id, current_step, progress (0-100), message,
          status, eta_seconds, elapsed_seconds, steps_summary
        }

    Poll this every 1-2 seconds while status == 'processing'.
    Switch to GET /full-status/{job_id} or SSE /stream/{job_id} for full details.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return build_status_response(job)


@router.get("/full-status/{job_id}")
async def get_full_status(job_id: str):
    """Full JobState including steps timing, clips, emotion timeline."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


@router.get("/get-clips/{job_id}", response_model=ClipsResponse)
async def get_clips(job_id: str):
    """Retrieve generated clips for a completed job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status == JobStatus.PROCESSING:
        raise HTTPException(status_code=202, detail="Processing still in progress")

    if job.status == JobStatus.FAILED:
        raise HTTPException(status_code=500, detail=f"Job failed: {job.error}")

    return ClipsResponse(
        job_id=job_id,
        status=job.status,
        clips=job.clips,
        total_clips=len(job.clips),
        emotion_timeline=job.emotion_timeline,
    )


@router.get("/jobs")
async def list_jobs():
    """List all processing jobs (for admin/debugging)."""
    jobs = get_all_jobs()
    return {
        "total": len(jobs),
        "jobs": [
            {
                "job_id": jid,
                "status": j.status,
                "filename": Path(j.video_filename).name,
                "clips_count": len(j.clips),
                "progress": j.total_progress,
                "created_at": j.created_at,
            }
            for jid, j in sorted(jobs.items(), key=lambda x: x[1].created_at, reverse=True)
        ]
    }


@router.get("/download/{job_id}/{clip_id}")
async def download_clip(job_id: str, clip_id: str):
    """Download a specific clip by ID."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    clip = next((c for c in job.clips if c.clip_id == clip_id), None)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip_path = Path(clip.file_path)
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail="Clip file not found on disk")

    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=f"attentionx_{clip_id}.mp4",
    )
