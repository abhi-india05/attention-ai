"""
AttentionX – FastAPI Application Entry Point
Main application with all routes, middleware, and static file serving.
"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
import asyncio
import json

from attentionx.backend.config import FRONTEND_DIR, CLIPS_DIR
from attentionx.backend.routers.video import router as video_router
from attentionx.backend.models.job import get_job, build_status_response
from attentionx.utils.file_utils import check_ffmpeg_installed

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("🚀 AttentionX starting up...")

    # Check dependencies
    if not check_ffmpeg_installed():
        logger.warning("⚠️  FFmpeg not found! Video processing will fail.")
        logger.warning("   Install: https://ffmpeg.org/download.html")
    else:
        logger.info("✅ FFmpeg found")

    logger.info(f"📁 Frontend: {FRONTEND_DIR}")
    logger.info(f"📁 Clips output: {CLIPS_DIR}")
    logger.info("✅ AttentionX ready!")

    yield

    logger.info("AttentionX shutting down...")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="AttentionX",
    description="Automated Content Repurposing Engine – Turn long videos into viral clips",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API Routes ────────────────────────────────────────────────────────────────
app.include_router(video_router, prefix="/api", tags=["Video Processing"])


# ── Server-Sent Events (SSE) for real-time progress ──────────────────────────
@app.get("/stream/{job_id}")
async def stream_progress(job_id: str):
    """
    SSE endpoint for real-time pipeline progress updates.
    Client connects once and receives updates until job is done.

    Usage (JavaScript):
        const es = new EventSource(`/stream/${jobId}`);
        es.onmessage = (e) => { const data = JSON.parse(e.data); ... };
    """
    async def event_generator():
        last_progress = -1
        last_status = None
        max_polls = 600  # 10-minute timeout (1 poll/second)

        for _ in range(max_polls):
            job = get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found', 'type': 'error'})}\n\n"
                break

            # Build rich status payload (same shape as polling endpoint)
            payload = build_status_response(job)

            # Also include the per-step detail list for the live step cards
            payload["steps"] = [
                {
                    "name": s.name,
                    "status": s.status,
                    "message": s.message,
                    "progress": s.progress,
                    "elapsed_seconds": s.elapsed_seconds,
                    "error_detail": s.error_detail,
                }
                for s in job.steps
            ]
            payload["clips_count"] = len(job.clips)

            # Send only when something changes (de-duplicate)
            current_key = (job.status.value, job.total_progress, job.current_step_name)
            if (job.total_progress != last_progress or job.status != last_status):
                last_progress = job.total_progress
                last_status = job.status
                yield f"data: {json.dumps(payload)}\n\n"

            # Terminate stream on final states
            if job.status.value in ("completed", "failed"):
                final = {"type": "done", "status": job.status.value,
                         "clips_count": len(job.clips), "error": job.error}
                yield f"data: {json.dumps(final)}\n\n"
                break

            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ── Video serving ─────────────────────────────────────────────────────────────
@app.get("/video/{job_id}/{clip_id}")
async def serve_video(job_id: str, clip_id: str):
    """Serve a clip video file for preview in the browser."""
    job = get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    clip = next((c for c in job.clips if c.clip_id == clip_id), None)
    if not clip:
        return JSONResponse({"error": "Clip not found"}, status_code=404)

    clip_path = Path(clip.file_path)
    if not clip_path.exists():
        return JSONResponse({"error": "Clip file missing"}, status_code=404)

    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """API health check endpoint."""
    return {
        "status": "healthy",
        "service": "AttentionX",
        "version": "1.0.0",
        "ffmpeg": check_ffmpeg_installed(),
    }


# ── Serve Frontend SPA ────────────────────────────────────────────────────────
# Serve static files (CSS, JS, assets) from frontend directory
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/", include_in_schema=False)
async def serve_frontend():
    """Serve the AttentionX frontend."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse({"message": "AttentionX API running. Frontend not found."})

@app.get("/{path:path}", include_in_schema=False)
async def catch_all(path: str):
    """Catch-all for SPA routing."""
    # Don't catch API routes
    if path.startswith("api/") or path.startswith("stream/") or path.startswith("video/"):
        return JSONResponse({"error": "Not found"}, status_code=404)

    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse({"error": "Frontend not found"}, status_code=404)
