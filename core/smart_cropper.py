"""
AttentionX – Smart Cropper (9:16)
Uses MediaPipe face detection to intelligently crop horizontal video to
9:16 vertical format for TikTok, Reels, and YouTube Shorts.

Features:
  - Real-time face detection per frame
  - Smooth position transitions (no jitter)
  - Subtle zoom-in effect for engagement
  - Falls back to center/rule-of-thirds crop when no face detected
"""

import cv2
import numpy as np
import logging
import subprocess
from pathlib import Path
from collections import deque
from typing import Optional, Tuple

from attentionx.backend.config import (
    OUTPUT_WIDTH, OUTPUT_HEIGHT,
    FACE_DETECTION_CONFIDENCE, SMOOTHING_WINDOW, ZOOM_FACTOR
)

logger = logging.getLogger(__name__)


# ── Smoothing helper ──────────────────────────────────────────────────────────

class PositionSmoother:
    """
    Maintains a rolling average of crop center positions to prevent jitter.
    Uses an exponential moving average for natural-feeling tracking.
    """
    def __init__(self, window: int = SMOOTHING_WINDOW, alpha: float = 0.1):
        self.history: deque = deque(maxlen=window)
        self.alpha = alpha   # EMA smoothing factor
        self.last_x: Optional[float] = None
        self.last_y: Optional[float] = None

    def update(self, x: float, y: float) -> Tuple[float, float]:
        """Update with new position and return smoothed position."""
        self.history.append((x, y))

        if self.last_x is None:
            self.last_x, self.last_y = x, y
        else:
            # Exponential moving average
            self.last_x = self.alpha * x + (1 - self.alpha) * self.last_x
            self.last_y = self.alpha * y + (1 - self.alpha) * self.last_y

        return self.last_x, self.last_y

    def get_last(self) -> Tuple[float, float]:
        if self.last_x is None:
            return 0.5, 0.5
        return self.last_x, self.last_y


# ── Core cropping pipeline ────────────────────────────────────────────────────

def _get_crop_box(
    frame_w: int,
    frame_h: int,
    center_x: float,
    center_y: float,
    target_w: int = OUTPUT_WIDTH,
    target_h: int = OUTPUT_HEIGHT,
    zoom: float = ZOOM_FACTOR,
) -> Tuple[int, int, int, int]:
    """
    Compute the crop box (x1, y1, x2, y2) for a given center point.
    Maintains 9:16 aspect ratio. Adjusts for zoom.
    """
    # Target aspect ratio: 9:16
    aspect = target_w / target_h

    # Determine crop dimensions
    if frame_w / frame_h > aspect:
        # Frame is wider than 9:16 → crop sides
        crop_h = frame_h
        crop_w = int(crop_h * aspect)
    else:
        crop_w = frame_w
        crop_h = int(crop_w / aspect)

    # Apply zoom (crop a smaller area → scale up → subtle zoom)
    crop_w = int(crop_w / zoom)
    crop_h = int(crop_h / zoom)

    # Center around detected face
    cx = int(center_x * frame_w)
    cy = int(center_y * frame_h)

    x1 = max(0, cx - crop_w // 2)
    y1 = max(0, cy - crop_h // 2)
    x2 = x1 + crop_w
    y2 = y1 + crop_h

    # Clamp to frame boundaries
    if x2 > frame_w:
        x2 = frame_w
        x1 = x2 - crop_w
    if y2 > frame_h:
        y2 = frame_h
        y1 = y2 - crop_h

    x1 = max(0, x1)
    y1 = max(0, y1)

    return x1, y1, x2, y2


def smart_crop_to_vertical(
    input_path: str,
    output_path: str,
) -> str:
    """
    Crop a video to 9:16 vertical format using face detection.

    Falls back to center crop if mediapipe is not available or no face found.

    Args:
        input_path: Path to the source clip (any aspect ratio).
        output_path: Output path for the vertical clip.

    Returns:
        Path to the output clip.
    """
    try:
        import mediapipe as mp
        _crop_with_mediapipe(input_path, output_path, mp)
    except ImportError:
        logger.warning("MediaPipe not available. Using smart center crop.")
        _crop_center_ffmpeg(input_path, output_path)
    except Exception as e:
        logger.error(f"Smart crop failed: {e}. Falling back to center crop.")
        _crop_center_ffmpeg(input_path, output_path)

    return output_path


def _crop_with_mediapipe(input_path: str, output_path: str, mp) -> None:
    """Full face-tracking crop using MediaPipe."""
    mp_face = mp.solutions.face_detection

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logger.info(f"Cropping {frame_w}x{frame_h} → {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}, {total_frames} frames")

    # Write output with OpenCV (no audio – we'll mux later)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    tmp_video = str(output_path) + "_noaudio.mp4"
    out = cv2.VideoWriter(tmp_video, fourcc, fps, (OUTPUT_WIDTH, OUTPUT_HEIGHT))

    smoother = PositionSmoother(window=SMOOTHING_WINDOW)

    face_detector = mp_face.FaceDetection(
        model_selection=0,
        min_detection_confidence=FACE_DETECTION_CONFIDENCE
    )

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_detector.process(rgb_frame)

        if results.detections:
            # Use the largest/most confident detection
            det = max(results.detections, key=lambda d: d.score[0])
            bbox = det.location_data.relative_bounding_box
            face_cx = bbox.xmin + bbox.width / 2
            face_cy = bbox.ymin + bbox.height / 2
            cx, cy = smoother.update(face_cx, face_cy)
        else:
            # No face: use previous position or center
            cx, cy = smoother.get_last()
            if frame_count == 1:
                cx, cy = 0.5, 0.4  # Slightly above center (rule of thirds)

        x1, y1, x2, y2 = _get_crop_box(frame_w, frame_h, cx, cy)
        cropped = frame[y1:y2, x1:x2]

        # Resize to exact target dimensions
        resized = cv2.resize(cropped, (OUTPUT_WIDTH, OUTPUT_HEIGHT),
                             interpolation=cv2.INTER_LANCZOS4)
        out.write(resized)

    cap.release()
    out.release()
    face_detector.close()

    # Mux audio back in
    _mux_audio(input_path, tmp_video, output_path)

    try:
        Path(tmp_video).unlink()
    except Exception:
        pass


def _crop_center_ffmpeg(input_path: str, output_path: str) -> None:
    """
    Fallback: Use FFmpeg to center-crop to 9:16.
    Quick, no face detection.
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-vf", (
            f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,"
            f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}"
        ),
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg crop failed: {result.stderr[:300]}")


def _mux_audio(source_video: str, video_no_audio: str, output: str) -> None:
    """Combine video track from cropped file with audio from original."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_no_audio),
        "-i", str(source_video),
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        # If audio mux fails, just rename video-only
        import shutil
        shutil.copy(video_no_audio, output)
        logger.warning(f"Audio mux failed, using video-only: {result.stderr[:200]}")
