# ⚡ AttentionX — Automated Content Repurposing Engine

> **Turn long-form videos into viral short-form clips — automatically.**
> Hackathon-grade AI pipeline with 5-signal virality scoring, smart 9:16 cropping, word-synced captions, and LLM-powered hooks.

---

## 🧱 Architecture

```
┌──────────────────────────────────────────────────┐
│           Frontend (HTML + Vanilla CSS/JS)        │
│    Upload → SSE Progress → Clips Dashboard        │
└──────────────────┬───────────────────────────────┘
                   │ HTTP / SSE
┌──────────────────▼───────────────────────────────┐
│              FastAPI Backend                      │
│   /upload → /process → /stream/{id} → /get-clips │
└──────────────────┬───────────────────────────────┘
        ┌──────────┼──────────────┐
        ▼          ▼              ▼
     Groq Whisper Virality      MoviePy/CV2
   (Speech)   Engine          (Video)
        ▼          ▼              ▼
   Emotion    LLM Hooks      MediaPipe
   Analysis   Generator      (Face Crop)
```

---

## 📁 Project Structure

```
attentionx/
├── backend/
│   ├── main.py             # FastAPI app, SSE, routing
│   ├── config.py           # All configuration & constants
│   ├── pipeline.py         # Pipeline orchestrator
│   ├── models/
│   │   ├── schemas.py      # Pydantic request/response models
│   │   └── job.py          # In-memory job state manager
│   └── routers/
│       └── video.py        # Upload, process, clips endpoints
├── core/
│   ├── audio_extractor.py  # FFmpeg audio extraction (16kHz WAV)
│   ├── transcriber.py      # Groq Whisper with word timestamps
│   ├── emotion_analyzer.py # Librosa emotion timeline
│   ├── virality_engine.py  # 5-signal virality scoring
│   ├── clip_generator.py   # Intelligent clip boundary expansion
│   ├── smart_cropper.py    # MediaPipe face tracking + 9:16 crop
│   ├── caption_engine.py   # Word-level caption generation + burn
│   ├── hook_generator.py   # LLM viral hook generation
│   └── hashtag_generator.py# Platform-aware hashtag generation
├── frontend/
│   ├── index.html          # SPA - premium dark UI
│   ├── style.css           # Glassmorphism + animation CSS
│   └── app.js              # Upload, SSE, charts, modal logic
├── utils/
│   ├── llm_client.py       # Gemini client
│   └── file_utils.py       # FFprobe metadata, file helpers
├── uploads/                # Incoming video uploads
├── outputs/
│   └── clips/              # Generated clips (per job)
├── requirements.txt
├── .env.example
└── run.py                  # Entry point
```

---

## 🚀 Quick Start

### 1. Clone & Setup

```bash
cd d:/attentionai
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r attentionx/requirements.txt
```

### 2. Install FFmpeg

Download from https://ffmpeg.org/download.html and add to PATH.
Verify: `ffmpeg -version`

### 3. Configure Environment

```bash
copy attentionx\.env.example attentionx\.env
# Edit .env with your API keys
```

### 4. Run

```bash
python attentionx/run.py
# OR
uvicorn attentionx.backend.main:app --reload --port 8000
```

Open: **http://localhost:8000**

---

## 🎯 Virality Scoring System

Each transcript segment is scored across 5 signals:

| Signal | Weight | Method |
|--------|--------|--------|
| Audio Intensity | 20% | Librosa RMS + spectral flux |
| Sentiment Score | 15% | Emotion arousal × \|valence\| |
| Semantic Importance | 30% | LLM rates each segment's insight value |
| Keyword Triggers | 20% | "secret", "mistake", "nobody knows"... |
| Curiosity Hook | 15% | Question patterns, contrast structures |

---

## 🏆 Unique Features

1. **Emotion Timeline Graph** — real-time visualization of energy peaks
2. **Platform Optimization Mode** — TikTok / Reels / Shorts presets
3. **AI Hook Ranker** — 3 hooks per clip, predicted CTR ranked
4. **Auto Hashtag Generator** — content-aware + platform-specific
5. **Before/After Viewer** — video previews with hover-play
6. **Virality Score Dashboard** — per-signal breakdown radar bars

---

## 🔌 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/upload` | POST | Upload video, create job |
| `/api/process` | POST | Start processing job |
| `/api/status/{id}` | GET | Get job status + steps |
| `/stream/{id}` | GET | SSE real-time progress stream |
| `/api/get-clips/{id}` | GET | Retrieve final clips |
| `/video/{job}/{clip}` | GET | Serve clip for preview |
| `/api/download/{job}/{clip}` | GET | Download clip |
| `/health` | GET | System health check |
| `/api/docs` | GET | Swagger UI |

---

## ⚙️ Configuration

Edit `attentionx/backend/config.py` to tune:
- `VIRALITY_WEIGHTS` — adjust signal importance
- `VIRAL_KEYWORDS` — add your own trigger words
- `PLATFORM_PRESETS` — customize per-platform settings
- `GEMINI_API_KEYS` — one or more Gemini keys for automatic failover
- `WHISPER_MODEL` — Groq Whisper model id (e.g. `whisper-large-v3`)
- `SMOOTHING_WINDOW` — face tracking smoothness

---

## 🏆 Hackathon Winning Strategy

### Demo Flow (5 minutes)
1. Open http://localhost:8000 — let the UI wow them
2. Upload a 10-min lecture/podcast
3. Show pipeline steps progressing live (SSE)
4. Reveal the Emotion Timeline graph and explain peaks
5. Click a clip → show virality breakdown, hooks, hashtags
6. Download and play the clip — 9:16, captioned, ready to post

### Key Points to Highlight
- **5-signal virality engine** (no other team has this)
- **Real-time SSE progress** (feels like a real product)
- **MediaPipe face tracking** (judges love the tech depth)
- **LLM hook generation with CTR prediction** (monetization angle)
- **Zero manual editing** (pure automation story)

---

## 🔮 Future Improvements

### Performance
- If you need a local fallback, use `faster-whisper` (4x speed)
- GPU acceleration for video processing
- Redis job queue for horizontal scaling
- CDN delivery for clip files

### AI Enhancements
- Multi-face tracking (podcasts with 2 people)
- B-roll detection and insertion
- Music background generation
- Voice cloning for dubbing

### Product Features
- AI Content Calendar + scheduling
- Direct social media posting (TikTok API, Instagram API)
- Analytics dashboard (view count tracking)
- Team collaboration workspace
- Batch processing queue
