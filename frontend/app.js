/**
 * AttentionX – Frontend Application Logic
 * Handles: upload flow, SSE progress, clip display, charts, modal, clipboard
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
const state = {
  currentJobId: null,
  selectedPlatform: 'tiktok',
  uploadedFile: null,
  clips: [],
  emotionTimeline: [],
  eventSource: null,
  emotionChart: null,
  modalClipData: null,
  modalEmotionChart: null,
};

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const dom = {
  fileInput: $('file-input'),
  dropZone: $('drop-zone'),
  browseBtn: $('browse-btn'),
  uploadProgressArea: $('upload-progress-area'),
  fileNameDisplay: $('file-name-display'),
  fileSizeDisplay: $('file-size-display'),
  uploadBar: $('upload-bar'),
  uploadPct: $('upload-pct'),
  removeFileBtn: $('remove-file-btn'),
  processBtn: $('process-btn'),
  uploadSection: $('upload-section'),
  processingSection: $('processing-section'),
  resultsSection: $('results-section'),
  processingSubtitle: $('processing-subtitle'),
  processingPct: $('processing-pct'),
  masterProgressBar: $('master-progress-bar'),
  masterProgressWrap: $('master-progress-wrap'),
  pipelineSteps: $('pipeline-steps'),
  clipsGrid: $('clips-grid'),
  emotionChart: $('emotion-chart'),
  resultSubtitle: $('results-subtitle'),
  newVideoBtn: $('new-video-btn'),
  // Modal
  clipModal: $('clip-modal'),
  modalClose: $('modal-close'),
  modalVideo: $('modal-video'),
  modalRank: $('modal-rank'),
  modalTitle: $('modal-title'),
  modalViralityBars: $('modal-virality-bars'),
  modalTotalScore: $('modal-total-score'),
  modalHooks: $('modal-hooks'),
  modalHashtags: $('modal-hashtags'),
  modalEmotionChart: $('modal-emotion-chart'),
  modalDownloadBtn: $('modal-download-btn'),
  modalCopyHooksBtn: $('modal-copy-hooks-btn'),
  modalCopyHashtagsBtn: $('modal-copy-hashtags-btn'),
  toastContainer: $('toast-container'),
  navStatus: $('nav-status'),
  maxClips: $('max-clips'),
  maxClipsVal: $('max-clips-val'),
  minDuration: $('min-duration'),
  minDurationVal: $('min-duration-val'),
  maxDuration: $('max-duration'),
  maxDurationVal: $('max-duration-val'),
};

// ── Pipeline step labels ──────────────────────────────────────────────────────
const STEP_LABELS = {
  audio_extraction:  { label: 'Audio Extraction',   icon: '🎵' },
  transcription:     { label: 'Transcription',       icon: '📝' },
  emotion_analysis:  { label: 'Emotion Analysis',    icon: '🧠' },
  virality_scoring:  { label: 'Virality Scoring',    icon: '📊' },
  clip_detection:    { label: 'Clip Detection',      icon: '🎯' },
  clip_generation:   { label: 'Clip Generation',     icon: '✂️'  },
  face_detection:    { label: 'Smart Crop (9:16)',   icon: '📱' },
  caption_generation:{ label: 'Caption Engine',      icon: '💬' },
  hook_generation:   { label: 'Hook Generator',      icon: '🪝' },
  hashtag_generation:{ label: 'Hashtag Generator',   icon: '#️⃣' },
  finalization:      { label: 'Finalization',        icon: '✅' },
};

const VIRALITY_SIGNALS = [
  { key: 'audio_intensity',    label: 'Audio Intensity',    color: '#f59e0b' },
  { key: 'sentiment_score',    label: 'Sentiment',          color: '#ec4899' },
  { key: 'semantic_importance',label: 'Semantic Importance',color: '#8b5cf6' },
  { key: 'keyword_triggers',   label: 'Keyword Triggers',   color: '#06b6d4' },
  { key: 'curiosity_hook',     label: 'Curiosity Hook',     color: '#10b981' },
];

// ── Platform Selector ─────────────────────────────────────────────────────────
document.querySelectorAll('.platform-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.platform-btn').forEach((b) => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    btn.classList.add('active');
    btn.setAttribute('aria-pressed', 'true');
    state.selectedPlatform = btn.dataset.platform;
  });
});

// ── Slider updates ────────────────────────────────────────────────────────────
dom.maxClips.addEventListener('input', () => {
  dom.maxClipsVal.textContent = dom.maxClips.value;
});
dom.minDuration.addEventListener('input', () => {
  dom.minDurationVal.textContent = dom.minDuration.value + 's';
});
dom.maxDuration.addEventListener('input', () => {
  dom.maxDurationVal.textContent = dom.maxDuration.value + 's';
});

// ── Drag & Drop ───────────────────────────────────────────────────────────────
dom.dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dom.dropZone.classList.add('drag-over');
});
dom.dropZone.addEventListener('dragleave', () => {
  dom.dropZone.classList.remove('drag-over');
});
dom.dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dom.dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelect(file);
});
dom.dropZone.addEventListener('click', () => dom.fileInput.click());
dom.dropZone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') dom.fileInput.click();
});
dom.browseBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  dom.fileInput.click();
});
dom.fileInput.addEventListener('change', (e) => {
  if (e.target.files[0]) handleFileSelect(e.target.files[0]);
});
dom.removeFileBtn.addEventListener('click', resetUpload);

function handleFileSelect(file) {
  if (!file.type.startsWith('video/')) {
    showToast('Please select a valid video file', 'error');
    return;
  }
  state.uploadedFile = file;
  dom.fileNameDisplay.textContent = file.name;
  dom.fileSizeDisplay.textContent = formatBytes(file.size);
  dom.dropZone.classList.add('hidden');
  dom.uploadProgressArea.classList.remove('hidden');
  dom.processBtn.disabled = false;
}

function resetUpload() {
  state.uploadedFile = null;
  dom.fileInput.value = '';
  dom.dropZone.classList.remove('hidden');
  dom.uploadProgressArea.classList.add('hidden');
  dom.uploadBar.style.width = '0%';
  dom.uploadPct.textContent = 'Uploading...';
  dom.processBtn.disabled = true;
}

// ── Upload + Process ──────────────────────────────────────────────────────────
dom.processBtn.addEventListener('click', startProcessing);

async function startProcessing() {
  if (!state.uploadedFile) {
    showToast('Please select a video first', 'error');
    return;
  }

  dom.processBtn.disabled = true;
  dom.processBtn.querySelector('.btn-text').textContent = 'Uploading...';

  try {
    // 1. Upload the file
    const formData = new FormData();
    formData.append('file', state.uploadedFile);
    formData.append('platform', state.selectedPlatform);

    const uploadRes = await uploadWithProgress(formData);
    if (!uploadRes.ok) {
      const err = await uploadRes.json();
      throw new Error(err.detail || 'Upload failed');
    }
    const uploadData = await uploadRes.json();
    state.currentJobId = uploadData.job_id;

    showToast(`✅ Uploaded! Starting pipeline...`, 'success');

    // 2. Trigger processing
    const processRes = await fetch('/api/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: state.currentJobId,
        platform: state.selectedPlatform,
        max_clips: parseInt(dom.maxClips.value),
        min_duration: parseInt(dom.minDuration.value),
        max_duration: parseInt(dom.maxDuration.value),
      }),
    });
    if (!processRes.ok) {
      const err = await processRes.json();
      throw new Error(err.detail || 'Failed to start processing');
    }

    // 3. Show processing UI
    showSection('processing');
    initPipelineSteps();
    startSSEStream(state.currentJobId);

  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
    dom.processBtn.disabled = false;
    dom.processBtn.querySelector('.btn-text').textContent = 'Process Video';
  }
}

function uploadWithProgress(formData) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        dom.uploadBar.style.width = pct + '%';
        dom.uploadBar.setAttribute('aria-valuenow', pct);
        dom.uploadPct.textContent = `Uploading... ${pct}%`;
      }
    });

    xhr.addEventListener('load', () => {
      resolve({
        ok: xhr.status < 400,
        json: () => JSON.parse(xhr.responseText),
      });
    });
    xhr.addEventListener('error', () => reject(new Error('Network error')));
    xhr.send(formData);
  });
}

// ── SSE Progress ─────────────────────────────────────────────────────────────
function startSSEStream(jobId) {
  if (state.eventSource) state.eventSource.close();

  state.eventSource = new EventSource(`/stream/${jobId}`);

  state.eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.error) {
      showToast(`Error: ${data.error}`, 'error');
      return;
    }

    if (data.type === 'done') {
      state.eventSource.close();
      if (data.status === 'completed') {
        loadAndShowClips(jobId);
      } else {
        showToast('Processing failed. Check server logs.', 'error');
        showSection('upload');
      }
      return;
    }

    // Update progress UI
    updatePipelineUI(data);
  };

  state.eventSource.onerror = () => {
    showToast('Connection lost. Retrying...', 'info');
  };
}

function updatePipelineUI(data) {
  const pct = data.total_progress || 0;
  dom.masterProgressBar.style.width = pct + '%';
  dom.masterProgressWrap.setAttribute('aria-valuenow', pct);
  dom.processingPct.textContent = pct + '%';

  // Find currently running step for subtitle
  const running = (data.steps || []).find((s) => s.status === 'running');
  if (running) {
    dom.processingSubtitle.textContent = running.message || running.name;
  }

  // Update each step card
  (data.steps || []).forEach((step) => {
    const el = document.querySelector(`.pipeline-step[data-step="${step.name}"]`);
    if (!el) return;

    el.className = `pipeline-step ${step.status}`;
    const indicator = el.querySelector('.step-indicator');
    indicator.className = `step-indicator ${step.status}`;

    if (step.status === 'done') indicator.textContent = '✓';
    else if (step.status === 'running') indicator.textContent = '';
    else if (step.status === 'error') indicator.textContent = '✕';
    else indicator.textContent = '○';

    el.querySelector('.step-msg').textContent = step.message || '';
  });
}

function initPipelineSteps() {
  dom.pipelineSteps.innerHTML = '';
  Object.entries(STEP_LABELS).forEach(([key, info]) => {
    const el = document.createElement('div');
    el.className = 'pipeline-step pending';
    el.dataset.step = key;
    el.setAttribute('role', 'listitem');
    el.innerHTML = `
      <div class="step-indicator pending" aria-label="${info.label} status">○</div>
      <div class="step-content">
        <div class="step-name">${info.icon} ${info.label}</div>
        <div class="step-msg">Waiting...</div>
      </div>
    `;
    dom.pipelineSteps.appendChild(el);
  });
}

// ── Load & Display Clips ──────────────────────────────────────────────────────
async function loadAndShowClips(jobId) {
  try {
    const res = await fetch(`/api/get-clips/${jobId}`);
    if (!res.ok) throw new Error('Failed to load clips');
    const data = await res.json();

    state.clips = data.clips || [];
    state.emotionTimeline = data.emotion_timeline || [];

    showSection('results');
    dom.resultSubtitle.textContent = `Generated ${state.clips.length} viral clips`;

    renderEmotionTimeline(state.emotionTimeline, state.clips);
    renderClipsGrid(state.clips);

    showToast(`🎉 ${state.clips.length} viral clips ready!`, 'success');
  } catch (err) {
    showToast(`Error loading clips: ${err.message}`, 'error');
    showSection('upload');
  }
}

// ── Emotion Timeline Chart ────────────────────────────────────────────────────
function renderEmotionTimeline(points, clips) {
  const canvas = dom.emotionChart;
  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth;
  const H = canvas.height;
  canvas.width = W;

  ctx.clearRect(0, 0, W, H);

  if (!points.length) return;

  const maxTime = points[points.length - 1].time;
  const timeToX = (t) => (t / maxTime) * W;
  const valToY = (v, min, max) => H - ((v - min) / (max - min + 0.001)) * H;

  // Draw clip markers first (background)
  clips.forEach((clip) => {
    const x1 = timeToX(clip.start_time);
    const x2 = timeToX(clip.end_time);
    ctx.fillStyle = 'rgba(245,158,11,0.12)';
    ctx.fillRect(x1, 0, x2 - x1, H);
    ctx.fillStyle = 'rgba(245,158,11,0.4)';
    ctx.fillRect(x1, 0, 2, H);
  });

  // Arousal line (purple)
  const arousals = points.map((p) => p.arousal);
  drawLine(ctx, points, arousals, timeToX, 0, 1, H, '#8b5cf6', 2.5);

  // Valence line (cyan)  
  const valences = points.map((p) => (p.valence + 1) / 2); // 0-1
  drawLine(ctx, points, valences, timeToX, 0, 1, H, '#06b6d4', 1.5);
}

function drawLine(ctx, points, values, timeToX, minV, maxV, H, color, lineWidth) {
  if (!points.length) return;

  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';

  // Fill under the curve
  ctx.fillStyle = color.replace(')', ', 0.1)').replace('rgb', 'rgba').replace('#', '');

  const pts = points.map((p, i) => ({
    x: timeToX(p.time),
    y: H - ((values[i] - minV) / (maxV - minV + 0.001)) * H
  }));

  ctx.moveTo(pts[0].x, pts[0].y);
  for (let i = 1; i < pts.length; i++) {
    const cp1x = (pts[i - 1].x + pts[i].x) / 2;
    ctx.bezierCurveTo(cp1x, pts[i - 1].y, cp1x, pts[i].y, pts[i].x, pts[i].y);
  }
  ctx.stroke();
}

// ── Clips Grid ────────────────────────────────────────────────────────────────
function renderClipsGrid(clips) {
  dom.clipsGrid.innerHTML = '';
  clips.forEach((clip, i) => {
    const card = createClipCard(clip, i);
    dom.clipsGrid.appendChild(card);
  });
}

function createClipCard(clip, index) {
  const div = document.createElement('div');
  div.className = 'clip-card';
  div.style.animationDelay = `${index * 0.08}s`;
  div.setAttribute('role', 'listitem');
  div.setAttribute('tabindex', '0');
  div.setAttribute('aria-label', `Clip ${clip.rank}: ${clip.title}`);

  const scorePercent = Math.round(clip.virality_score.total * 100);
  const rankClass = clip.rank <= 2 ? `rank-${clip.rank}` : '';
  const topHook = clip.hooks?.[0]?.text || '';

  const barsHtml = VIRALITY_SIGNALS.map((s) => {
    const height = Math.max(4, Math.round(clip.virality_score[s.key] * 32));
    return `<div class="virality-mini-bar bar-${s.key.replace('_', '-').split('_')[0]}"
              style="background:${s.color}; height:${height}px"
              title="${s.label}: ${(clip.virality_score[s.key]*100).toFixed(0)}%"></div>`;
  }).join('');

  div.innerHTML = `
    <div class="clip-thumbnail">
      <video class="clip-video-preview" src="${clip.preview_url}" 
             preload="metadata" muted playsinline
             aria-label="Preview of clip ${clip.rank}"></video>
      <div class="clip-rank-badge ${rankClass}">#${clip.rank}</div>
      <div class="clip-score-badge">🔥 ${scorePercent}%</div>
    </div>
    <div class="clip-info">
      <div class="clip-title">${escapeHtml(clip.title || 'Untitled Clip')}</div>
      <div class="clip-meta">
        <span>⏱ ${formatDuration(clip.duration)}</span>
        <span>📱 ${formatPlatform(clip.platform)}</span>
      </div>
      <div class="virality-mini-bars" aria-label="Virality signals breakdown">${barsHtml}</div>
      ${topHook ? `<div class="clip-hook-preview">"${escapeHtml(topHook)}"</div>` : ''}
    </div>
  `;

  // Hover video preview
  const video = div.querySelector('.clip-video-preview');
  div.addEventListener('mouseenter', () => { video.play().catch(() => {}); });
  div.addEventListener('mouseleave', () => { video.pause(); video.currentTime = 0; });

  // Click → open modal
  div.addEventListener('click', () => openClipModal(clip));
  div.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') openClipModal(clip);
  });

  return div;
}

// ── Clip Modal ────────────────────────────────────────────────────────────────
function openClipModal(clip) {
  state.modalClipData = clip;

  dom.modalVideo.src = clip.preview_url;
  dom.modalRank.textContent = `#${clip.rank}`;
  dom.modalTitle.textContent = clip.title || 'Untitled Clip';
  dom.modalTotalScore.textContent = (clip.virality_score.total * 100).toFixed(0) + '%';

  // Virality breakdown bars
  dom.modalViralityBars.innerHTML = VIRALITY_SIGNALS.map((s) => {
    const val = clip.virality_score[s.key];
    const pct = Math.round(val * 100);
    return `
      <div class="virality-bar-row">
        <span class="virality-bar-label">${s.label}</span>
        <div class="virality-bar-track">
          <div class="virality-bar-fill" style="width:${pct}%; background:${s.color}"></div>
        </div>
        <span class="virality-bar-val" style="color:${s.color}">${pct}%</span>
      </div>
    `;
  }).join('');

  // Hooks
  dom.modalHooks.innerHTML = (clip.hooks || []).map((h, i) => `
    <div class="hook-item">
      <div class="hook-text">${i + 1}. "${escapeHtml(h.text)}"</div>
      <div class="hook-meta">
        <span class="hook-style">${h.style}</span>
        <span class="hook-ctr">CTR: ${Math.round(h.predicted_ctr * 100)}%</span>
      </div>
    </div>
  `).join('');

  // Hashtags
  dom.modalHashtags.innerHTML = (clip.hashtags || []).map((tag) =>
    `<span class="hashtag-chip" title="Click to copy">${escapeHtml(tag)}</span>`
  ).join('');

  // Copy individual hashtag on click
  dom.modalHashtags.querySelectorAll('.hashtag-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      navigator.clipboard.writeText(chip.textContent).then(() => {
        showToast(`Copied ${chip.textContent}`, 'info');
      });
    });
  });

  // Emotion mini chart
  if (clip.emotion_points?.length) {
    setTimeout(() => renderMiniEmotion(clip.emotion_points), 100);
  }

  dom.clipModal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
  dom.modalVideo.play().catch(() => {});
}

function renderMiniEmotion(points) {
  const canvas = dom.modalEmotionChart;
  const ctx = canvas.getContext('2d');
  const W = canvas.offsetWidth || 400;
  const H = canvas.height;
  canvas.width = W;
  ctx.clearRect(0, 0, W, H);

  if (!points.length) return;
  const maxTime = points[points.length - 1].time;
  const tx = (t) => (t / maxTime) * W;

  const arousals = points.map((p) => p.arousal);
  drawLine(ctx, points, arousals, tx, 0, 1, H, '#8b5cf6', 2);
}

function closeModal() {
  dom.clipModal.classList.add('hidden');
  dom.modalVideo.pause();
  dom.modalVideo.src = '';
  document.body.style.overflow = '';
  state.modalClipData = null;
}

dom.modalClose.addEventListener('click', closeModal);
dom.clipModal.addEventListener('click', (e) => {
  if (e.target === dom.clipModal) closeModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !dom.clipModal.classList.contains('hidden')) closeModal();
});

// Modal actions
dom.modalDownloadBtn.addEventListener('click', () => {
  if (!state.currentJobId || !state.modalClipData) return;
  const url = `/api/download/${state.currentJobId}/${state.modalClipData.clip_id}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = `attentionx_clip_${state.modalClipData.rank}.mp4`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showToast('Download started!', 'success');
});

dom.modalCopyHooksBtn.addEventListener('click', () => {
  if (!state.modalClipData?.hooks) return;
  const text = state.modalClipData.hooks.map((h, i) => `${i + 1}. ${h.text}`).join('\n');
  navigator.clipboard.writeText(text).then(() => showToast('Hooks copied to clipboard!', 'success'));
});

dom.modalCopyHashtagsBtn.addEventListener('click', () => {
  if (!state.modalClipData?.hashtags) return;
  const text = state.modalClipData.hashtags.join(' ');
  navigator.clipboard.writeText(text).then(() => showToast('Hashtags copied!', 'success'));
});

// ── Navigation ────────────────────────────────────────────────────────────────
dom.newVideoBtn.addEventListener('click', () => {
  if (state.eventSource) state.eventSource.close();
  state.clips = [];
  state.emotionTimeline = [];
  state.currentJobId = null;
  resetUpload();
  showSection('upload');
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

function showSection(name) {
  dom.uploadSection.classList.toggle('hidden', name !== 'upload');
  dom.processingSection.classList.toggle('hidden', name !== 'processing');
  dom.resultsSection.classList.toggle('hidden', name !== 'results');

  if (name === 'processing') {
    dom.processingSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else if (name === 'results') {
    dom.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  toast.setAttribute('role', 'alert');
  dom.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ── Health check on load ──────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();

    const dot = document.querySelector('.status-dot');
    const label = dom.navStatus.querySelector('span:last-child');

    if (data.status === 'healthy') {
      dot.style.background = '#4ade80';
      dot.style.boxShadow = '0 0 8px #4ade80';
      label.textContent = data.ffmpeg ? 'System Ready' : 'Ready (no FFmpeg)';
      if (!data.ffmpeg) {
        showToast('⚠️ FFmpeg not found — install it for video processing', 'error');
      }
    }
  } catch {
    const dot = document.querySelector('.status-dot');
    dot.style.background = '#ef4444';
  }
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDuration(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatPlatform(platform) {
  const map = { tiktok: 'TikTok', reels: 'Reels', youtube_shorts: 'Shorts' };
  return map[platform] || platform;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// ── Init ──────────────────────────────────────────────────────────────────────
checkHealth();
