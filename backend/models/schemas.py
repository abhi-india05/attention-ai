"""
AttentionX – Pydantic Schemas
All request/response models for the API.
"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────

class Platform(str, Enum):
    TIKTOK = "tiktok"
    REELS = "reels"
    YOUTUBE_SHORTS = "youtube_shorts"


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ── Virality Scores ───────────────────────────────────────────────────────────

class ViralityBreakdown(BaseModel):
    audio_intensity: float = Field(ge=0, le=1, description="RMS energy normalized score")
    sentiment_score: float = Field(ge=0, le=1, description="Emotional intensity score")
    semantic_importance: float = Field(ge=0, le=1, description="LLM-rated content value")
    keyword_triggers: float = Field(ge=0, le=1, description="Viral keyword density score")
    curiosity_hook: float = Field(ge=0, le=1, description="Hook and curiosity potential")
    total: float = Field(ge=0, le=1, description="Weighted composite virality score")


# ── Transcript ────────────────────────────────────────────────────────────────

class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: Optional[List[Dict[str, Any]]] = None


class TranscriptResult(BaseModel):
    language: str
    duration: float
    segments: List[TranscriptSegment]
    full_text: str


# ── Emotion ───────────────────────────────────────────────────────────────────

class EmotionPoint(BaseModel):
    time: float
    valence: float       # -1 (negative) to +1 (positive)
    arousal: float       # 0 (calm) to 1 (energetic)
    label: str           # "excited", "calm", "sad", etc.


# ── Clip ─────────────────────────────────────────────────────────────────────

class Hook(BaseModel):
    text: str
    style: str           # "question" | "statement" | "shock"
    predicted_ctr: float # Estimated click-through rate 0–1


class Caption(BaseModel):
    start: float
    end: float
    text: str
    words: List[Dict[str, Any]]
    is_highlight: bool


class ClipResult(BaseModel):
    clip_id: str
    job_id: str
    rank: int
    title: str
    start_time: float
    end_time: float
    duration: float
    platform: Platform
    virality_score: ViralityBreakdown
    hooks: List[Hook]
    captions: List[Caption]
    hashtags: List[str]
    file_path: str
    preview_url: str
    thumbnail_url: Optional[str] = None
    emotion_points: List[EmotionPoint] = []
    transcript_excerpt: str = ""


# ── Job ───────────────────────────────────────────────────────────────────────

class ProcessingStep(BaseModel):
    name: str
    status: str   # "pending" | "running" | "done" | "error"
    message: str = ""
    progress: int = 0  # 0–100


class JobState(BaseModel):
    job_id: str
    status: JobStatus
    video_filename: str
    platform: Platform
    created_at: str
    updated_at: str
    steps: List[ProcessingStep]
    clips: List[ClipResult] = []
    error: Optional[str] = None
    emotion_timeline: List[EmotionPoint] = []
    total_progress: int = 0


# ── Request / Response ────────────────────────────────────────────────────────

class ProcessRequest(BaseModel):
    job_id: str
    platform: Platform = Platform.TIKTOK
    max_clips: int = Field(default=5, ge=1, le=10)
    min_duration: int = Field(default=20, ge=10, le=60)
    max_duration: int = Field(default=60, ge=30, le=180)


class UploadResponse(BaseModel):
    job_id: str
    filename: str
    file_size: int
    duration: Optional[float] = None
    message: str


class ClipsResponse(BaseModel):
    job_id: str
    status: JobStatus
    clips: List[ClipResult]
    total_clips: int
    emotion_timeline: List[EmotionPoint] = []
