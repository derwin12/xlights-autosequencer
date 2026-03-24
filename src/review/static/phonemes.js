'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────

let pxPerSec       = 100;
const ZOOM_MIN     = 20;
const ZOOM_MAX     = 2000;
const ZOOM_DEFAULT = 100;
const AXIS_H       = 20;
const WORD_H       = 48;
const PHONEME_H    = 48;
const WAVE_H       = 120;

const PHONEME_COLORS = {
  AI:  '#e67e22', E:   '#f1c40f', O:   '#3498db',
  U:   '#2980b9', WQ:  '#9b59b6', L:   '#27ae60',
  MBP: '#e74c3c', FV:  '#1abc9c', etc: '#3a3a3a',
  rest:'#222',
};

// ── DOM ───────────────────────────────────────────────────────────────────────

const player      = document.getElementById('player');
const btnPlay     = document.getElementById('btn-play');
const btnFullMix  = document.getElementById('btn-full-mix');
const btnVocals   = document.getElementById('btn-vocals');
const timeDisplay = document.getElementById('time-display');
const lyricsWrap  = document.getElementById('lyrics-wrap');
const panel       = document.getElementById('panel');
const canvasWrap  = document.getElementById('canvas-wrap');
const bgCanvas    = document.getElementById('bg-canvas');
const fgCanvas    = document.getElementById('fg-canvas');
const bgCtx       = bgCanvas.getContext('2d');
const fgCtx       = fgCanvas.getContext('2d');
const statusEl    = document.getElementById('status');

// ── State ─────────────────────────────────────────────────────────────────────

let wordMarks    = [];
let phonemeMarks = [];
let cmuDict      = null;  // loaded from server or built client-side
let durationMs   = 0;
let hasVocals    = false;
let usingVocals  = false;
let waveformData = null;
let audioOffsetMs = 0;  // MP3 encoder padding — browser includes it, WhisperX doesn't

// Drag
let dragIdx       = null;
let dragLayer     = null;   // 'word' | 'phoneme'
let dragEdge      = null;   // 'start' | 'end' | 'move'
let dragStartX    = 0;
let dragOrigStart = 0;
let dragOrigEnd   = 0;
let dirty         = false;

// Pre-rendered waveform image (avoid redrawing thousands of rects on every frame)
let waveformImage = null;

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  let phonemeData;
  try {
    const pr = await fetch('/phonemes');
    if (!pr.ok) {
      statusEl.textContent = (await pr.json().catch(() => ({}))).error || 'No phoneme data.';
      return;
    }
    phonemeData = await pr.json();
  } catch (e) {
    statusEl.textContent = `Failed to load: ${e.message}`;
    return;
  }

  wordMarks      = phonemeData.word_track?.marks    || [];
  phonemeMarks   = phonemeData.phoneme_track?.marks  || [];
  durationMs     = phonemeData.duration_ms           || 0;
  hasVocals      = phonemeData.has_vocals_audio       || false;
  // Start with the detected MP3 encoder padding as initial sync offset
  syncOffsetMs = -(phonemeData.audio_offset_ms || 0);
  console.log(`Initial sync offset: ${syncOffsetMs}ms`);
  const syncEl = document.getElementById('sync-offset');
  if (syncEl) syncEl.textContent = `${syncOffsetMs >= 0 ? '+' : ''}${syncOffsetMs}ms`;

  document.getElementById('song-name').textContent = phonemeData.filename || '';
  document.title = `Phonemes — ${phonemeData.filename || 'xlight-analyze'}`;
  player.src = '/audio';

  if (!hasVocals) {
    btnVocals.disabled = true;
    btnVocals.title = 'No vocals stem available';
  }

  try {
    const wr = await fetch('/waveform?stem=vocals');
    if (wr.ok) {
      waveformData = await wr.json();
      console.log(`Waveform: ${waveformData.samples.length} samples`);
    }
  } catch (e) { /* optional */ }

  buildWordPhonemeMap();
  renderLyrics();
  buildPanel();
  renderWaveformImage();
  drawAll();
  statusEl.style.display = 'none';
}

// ── Time conversion (compensate for audio/alignment offset) ───────────────────
// Adjustable sync offset: positive = words appear earlier, negative = later.
// User can tune with +/- buttons in toolbar.
let syncOffsetMs = 0;

function playerToTrackMs()  { return player.currentTime * 1000 - syncOffsetMs; }
function trackMsToPlayer(ms) { return (ms + syncOffsetMs) / 1000; }

function adjustSync(deltaMs) {
  syncOffsetMs += deltaMs;
  const el = document.getElementById('sync-offset');
  if (el) el.textContent = `${syncOffsetMs >= 0 ? '+' : ''}${syncOffsetMs}ms`;
}

// ── Zoom (buttons + keyboard only) ────────────────────────────────────────────

function setZoom(newPx) {
  const oldPx = pxPerSec;
  pxPerSec = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.round(newPx)));
  if (pxPerSec === oldPx) return;
  const vw = canvasWrap.clientWidth;
  const centerTime = (canvasWrap.scrollLeft + vw / 2) / ((durationMs / 1000) * oldPx);
  updateSpacer();
  drawAll();
  canvasWrap.scrollLeft = Math.max(0, centerTime * (durationMs / 1000) * pxPerSec - vw / 2);
  const label = document.getElementById('zoom-level');
  if (label) label.textContent = Math.round((pxPerSec / ZOOM_DEFAULT) * 100) + '%';
}

document.getElementById('btn-zoom-in')?.addEventListener('click', () => setZoom(pxPerSec * 1.3));
document.getElementById('btn-zoom-out')?.addEventListener('click', () => setZoom(pxPerSec / 1.3));
document.getElementById('btn-sync-earlier')?.addEventListener('click', () => adjustSync(25));
document.getElementById('btn-sync-later')?.addEventListener('click', () => adjustSync(-25));

document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && (e.key === '=' || e.key === '+')) {
    e.preventDefault(); setZoom(pxPerSec * 1.3);
  } else if ((e.ctrlKey || e.metaKey) && e.key === '-') {
    e.preventDefault(); setZoom(pxPerSec / 1.3);
  } else if ((e.ctrlKey || e.metaKey) && e.key === '0') {
    e.preventDefault(); setZoom(ZOOM_DEFAULT);
  } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault(); saveEdits();
  }
});

// ── Lyrics bar ────────────────────────────────────────────────────────────────

function renderLyrics() {
  lyricsWrap.innerHTML = '';
  for (const wm of wordMarks) {
    const span = document.createElement('span');
    span.className = 'word';
    span.textContent = wm.label;
    span.dataset.start = wm.start_ms;
    span.dataset.end   = wm.end_ms;
    span.addEventListener('click', () => { player.currentTime = trackMsToPlayer(wm.start_ms); });
    lyricsWrap.appendChild(span);
  }
}

function updateLyrics(nowMs) {
  for (const el of lyricsWrap.querySelectorAll('.word')) {
    const s = +el.dataset.start, e = +el.dataset.end;
    el.classList.toggle('active', nowMs >= s && nowMs < e);
    el.classList.toggle('past', nowMs >= e);
  }
}

// ── Face / mouth preview ──────────────────────────────────────────────────────

const faceCanvas = document.getElementById('face-canvas');
const faceCtx = faceCanvas ? faceCanvas.getContext('2d') : null;
let currentPhoneme = 'etc';

function drawFace(phoneme) {
  if (!faceCtx) return;
  const W = faceCanvas.width, H = faceCanvas.height;
  const cx = W / 2, cy = H / 2;
  faceCtx.clearRect(0, 0, W, H);

  // Head
  faceCtx.fillStyle = '#f5d0a0';
  faceCtx.beginPath();
  faceCtx.ellipse(cx, cy, 42, 46, 0, 0, Math.PI * 2);
  faceCtx.fill();
  faceCtx.strokeStyle = '#c4a070';
  faceCtx.lineWidth = 1.5;
  faceCtx.stroke();

  // Eyes
  faceCtx.fillStyle = '#fff';
  faceCtx.beginPath();
  faceCtx.ellipse(cx - 14, cy - 14, 7, 8, 0, 0, Math.PI * 2);
  faceCtx.fill();
  faceCtx.beginPath();
  faceCtx.ellipse(cx + 14, cy - 14, 7, 8, 0, 0, Math.PI * 2);
  faceCtx.fill();
  // Pupils
  faceCtx.fillStyle = '#333';
  faceCtx.beginPath();
  faceCtx.arc(cx - 14, cy - 13, 3.5, 0, Math.PI * 2);
  faceCtx.fill();
  faceCtx.beginPath();
  faceCtx.arc(cx + 14, cy - 13, 3.5, 0, Math.PI * 2);
  faceCtx.fill();

  // Nose
  faceCtx.strokeStyle = '#c4a070';
  faceCtx.lineWidth = 1;
  faceCtx.beginPath();
  faceCtx.moveTo(cx - 2, cy - 2);
  faceCtx.lineTo(cx - 4, cy + 6);
  faceCtx.lineTo(cx + 4, cy + 6);
  faceCtx.stroke();

  // Mouth — varies by phoneme
  const my = cy + 20;  // mouth center Y
  faceCtx.fillStyle = '#8b0000';
  faceCtx.strokeStyle = '#6b0000';
  faceCtx.lineWidth = 1.5;

  switch (phoneme) {
    case 'AI':
      // Wide open — big oval
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my, 14, 12, 0, 0, Math.PI * 2);
      faceCtx.fill();
      faceCtx.stroke();
      // Teeth top
      faceCtx.fillStyle = '#fff';
      faceCtx.fillRect(cx - 12, my - 12, 24, 5);
      // Tongue
      faceCtx.fillStyle = '#cc4444';
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my + 5, 8, 5, 0, 0, Math.PI);
      faceCtx.fill();
      break;

    case 'E':
      // Mid open — wide rectangle with teeth
      faceCtx.beginPath();
      faceCtx.roundRect(cx - 13, my - 6, 26, 12, 4);
      faceCtx.fill();
      faceCtx.stroke();
      // Teeth
      faceCtx.fillStyle = '#fff';
      faceCtx.fillRect(cx - 11, my - 6, 22, 4);
      faceCtx.fillRect(cx - 11, my + 2, 22, 4);
      break;

    case 'O':
      // Round open
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my, 9, 11, 0, 0, Math.PI * 2);
      faceCtx.fill();
      faceCtx.stroke();
      break;

    case 'WQ':
      // Pursed / pucker — small circle
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my, 5, 6, 0, 0, Math.PI * 2);
      faceCtx.fill();
      faceCtx.stroke();
      break;

    case 'L':
      // Tongue forward — open mouth with tongue tip visible
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my, 10, 8, 0, 0, Math.PI * 2);
      faceCtx.fill();
      faceCtx.stroke();
      // Tongue tip
      faceCtx.fillStyle = '#cc4444';
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my - 3, 5, 3, 0, 0, Math.PI * 2);
      faceCtx.fill();
      break;

    case 'MBP':
      // Closed lips — horizontal line
      faceCtx.strokeStyle = '#8b0000';
      faceCtx.lineWidth = 2.5;
      faceCtx.beginPath();
      faceCtx.moveTo(cx - 12, my);
      faceCtx.lineTo(cx + 12, my);
      faceCtx.stroke();
      // Slight lip color
      faceCtx.fillStyle = '#c07070';
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my - 1, 12, 2, 0, 0, Math.PI * 2);
      faceCtx.fill();
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my + 1, 12, 2, 0, 0, Math.PI * 2);
      faceCtx.fill();
      break;

    case 'U':
      // Rounded closed — small round opening (like "oo")
      faceCtx.beginPath();
      faceCtx.ellipse(cx, my, 7, 8, 0, 0, Math.PI * 2);
      faceCtx.fill();
      faceCtx.stroke();
      break;

    case 'FV':
      // Teeth on lower lip
      faceCtx.beginPath();
      faceCtx.roundRect(cx - 12, my - 4, 24, 8, 3);
      faceCtx.fill();
      faceCtx.stroke();
      // Upper teeth biting lower lip
      faceCtx.fillStyle = '#fff';
      faceCtx.fillRect(cx - 10, my - 4, 20, 5);
      break;

    case 'rest':
      // Rest — mouth fully closed, relaxed
      faceCtx.strokeStyle = '#a07060';
      faceCtx.lineWidth = 1.5;
      faceCtx.beginPath();
      faceCtx.moveTo(cx - 10, my);
      faceCtx.lineTo(cx + 10, my);
      faceCtx.stroke();
      break;

    default: // 'etc' — neutral / consonants (CDGKNRSThYZ)
      // Gentle closed smile
      faceCtx.strokeStyle = '#8b0000';
      faceCtx.lineWidth = 2;
      faceCtx.beginPath();
      faceCtx.arc(cx, my - 4, 11, 0.2, Math.PI - 0.2);
      faceCtx.stroke();
      break;
  }

  // Label
  faceCtx.fillStyle = '#888';
  faceCtx.font = 'bold 9px monospace';
  faceCtx.textAlign = 'center';
  faceCtx.fillText(phoneme, cx, H - 4);
}

function updateFace(nowMs) {
  // Find current phoneme. If it's 'etc' (generic consonant) and we're
  // inside a word, hold the previous non-etc shape instead of snapping
  // to rest — the mouth doesn't actually go neutral between sounds
  // within a word.
  let found = null;
  let insideWord = false;
  for (const wm of wordMarks) {
    if (nowMs >= wm.start_ms && nowMs < wm.end_ms) {
      insideWord = true;
      break;
    }
  }
  for (const pm of phonemeMarks) {
    if (nowMs >= pm.start_ms && nowMs < pm.end_ms) {
      found = pm.label;
      break;
    }
  }
  if (found === null) {
    // Between words — rest
    found = 'etc';
  } else if (found === 'etc' && insideWord && currentPhoneme !== 'etc') {
    // Inside a word on a consonant — hold previous shape
    found = currentPhoneme;
  }
  if (found !== currentPhoneme) {
    currentPhoneme = found;
    drawFace(found);
  }
}

// Draw initial face
drawFace('etc');

// ── Panel ─────────────────────────────────────────────────────────────────────

function buildPanel() {
  panel.innerHTML = '';
  const lanes = [
    { label: 'Words (drag to edit)', h: WORD_H, color: '#2855a5' },
    { label: 'Phonemes', h: PHONEME_H, color: '#555' },
    ...(waveformData ? [{ label: 'Vocals Waveform', h: WAVE_H, color: '#4a6' }] : []),
  ];
  for (const lane of lanes) {
    const div = document.createElement('div');
    div.className = 'lane-control';
    div.style.height = lane.h + 'px';
    div.style.minHeight = lane.h + 'px';
    if (lane.color) div.style.borderLeft = `2px solid ${lane.color}`;
    const n = document.createElement('div');
    n.className = 'lane-name';
    n.textContent = lane.label;
    div.appendChild(n);
    panel.appendChild(div);
  }
}

// ── Canvas sizing ─────────────────────────────────────────────────────────────
// Virtual width = full song at current zoom.  Actual canvas = viewport width
// only (avoids browser canvas pixel limits at high zoom).  A spacer div inside
// canvas-wrap provides the scroll range.

function totalW() {
  return Math.ceil((durationMs / 1000) * pxPerSec);
}
function canvasH() {
  return AXIS_H + WORD_H + PHONEME_H + (waveformData ? WAVE_H : 0);
}

// Ensure spacer div exists for scroll range
let _spacer = document.getElementById('canvas-spacer');
if (!_spacer) {
  _spacer = document.createElement('div');
  _spacer.id = 'canvas-spacer';
  _spacer.style.position = 'absolute';
  _spacer.style.top = '0';
  _spacer.style.left = '0';
  _spacer.style.height = '1px';
  _spacer.style.pointerEvents = 'none';
  canvasWrap.appendChild(_spacer);
}

function updateSpacer() {
  _spacer.style.width = totalW() + 'px';
}

// Waveform is drawn directly in drawWaveform() using viewport clipping.
// No offscreen pre-render needed — we only draw visible samples.
function renderWaveformImage() {
  // no-op, kept for compatibility with zoom/init calls
}

function drawAll() {
  updateSpacer();
  drawFast();
}

function drawFast() {
  const vw = canvasWrap.clientWidth;
  const h = canvasH();
  // Resize canvas if needed
  if (bgCanvas.width !== vw || bgCanvas.height !== h) {
    bgCanvas.width = fgCanvas.width = vw;
    bgCanvas.height = fgCanvas.height = h;
  }
  const scrollX = canvasWrap.scrollLeft;

  // Move canvases to track the scroll position so the browser never
  // shows stale pixels between scroll and redraw.
  bgCanvas.style.left = scrollX + 'px';
  fgCanvas.style.left = scrollX + 'px';

  bgCtx.clearRect(0, 0, vw, h);
  drawAxis(vw, scrollX);
  drawWords(vw, scrollX);
  drawPhonemes(vw, scrollX);
  drawWaveform(vw, scrollX);
  // Redraw playhead
  if (player.currentTime) {
    drawPlayhead(playerToTrackMs());
  }
}

// Redraw on every scroll — synchronous to avoid tearing
canvasWrap.addEventListener('scroll', () => { drawFast(); });

function drawAxis(vw, scrollX) {
  bgCtx.fillStyle = '#111';
  bgCtx.fillRect(0, 0, vw, AXIS_H);
  bgCtx.font = '10px monospace';
  const stepS = pxPerSec >= 60 ? 5 : pxPerSec >= 30 ? 10 : 30;
  const startS = Math.floor((scrollX / pxPerSec) / stepS) * stepS;
  const endS = (scrollX + vw) / pxPerSec + stepS;
  for (let s = startS; s <= endS; s += stepS) {
    const x = s * pxPerSec - scrollX;
    bgCtx.fillStyle = '#2a2a2a';
    bgCtx.fillRect(x, 0, 1, AXIS_H);
    bgCtx.fillStyle = '#555';
    bgCtx.textAlign = 'left';
    bgCtx.fillText(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`, x + 2, 13);
  }
}

function drawWords(vw, scrollX) {
  const y = AXIS_H;
  bgCtx.fillStyle = '#1c1c2a';
  bgCtx.fillRect(0, y, vw, WORD_H);
  const HANDLE_W = 6;
  const ARROW_H = 10;
  for (let i = 0; i < wordMarks.length; i++) {
    const wm = wordMarks[i];
    const absX = (wm.start_ms / 1000) * pxPerSec;
    const bw = Math.max(4, ((wm.end_ms - wm.start_ms) / 1000) * pxPerSec - 1);
    // Skip if entirely off-screen
    if (absX + bw < scrollX || absX > scrollX + vw) continue;
    const x = absX - scrollX;
    const isDrag = (dragIdx === i && dragLayer === 'word');

    // Word body
    bgCtx.fillStyle = isDrag ? '#3a70cc' : '#2855a5';
    bgCtx.fillRect(x, y + 4, bw, WORD_H - 8);

    // Left handle — arrow pointing left ◀
    bgCtx.fillStyle = isDrag ? '#aad4ff' : '#79b8ff';
    bgCtx.fillRect(x, y + 4, HANDLE_W, WORD_H - 8);
    bgCtx.fillStyle = '#fff';
    bgCtx.beginPath();
    bgCtx.moveTo(x + HANDLE_W - 1, y + WORD_H / 2 - ARROW_H / 2);
    bgCtx.lineTo(x + 1, y + WORD_H / 2);
    bgCtx.lineTo(x + HANDLE_W - 1, y + WORD_H / 2 + ARROW_H / 2);
    bgCtx.fill();

    // Right handle — arrow pointing right ▶
    bgCtx.fillStyle = isDrag ? '#aad4ff' : '#79b8ff';
    bgCtx.fillRect(x + bw - HANDLE_W, y + 4, HANDLE_W, WORD_H - 8);
    bgCtx.fillStyle = '#fff';
    bgCtx.beginPath();
    bgCtx.moveTo(x + bw - HANDLE_W + 1, y + WORD_H / 2 - ARROW_H / 2);
    bgCtx.lineTo(x + bw - 1, y + WORD_H / 2);
    bgCtx.lineTo(x + bw - HANDLE_W + 1, y + WORD_H / 2 + ARROW_H / 2);
    bgCtx.fill();

    // Label
    if (bw > HANDLE_W * 2 + 8) {
      bgCtx.fillStyle = '#cdf';
      bgCtx.font = '10px system-ui';
      bgCtx.textAlign = 'left';
      bgCtx.save();
      bgCtx.beginPath();
      bgCtx.rect(x + HANDLE_W + 2, y + 4, bw - HANDLE_W * 2 - 4, WORD_H - 8);
      bgCtx.clip();
      bgCtx.fillText(wm.label, x + HANDLE_W + 3, y + WORD_H / 2 + 3);
      bgCtx.restore();
    }
  }
}

function drawPhonemes(vw, scrollX) {
  const y = AXIS_H + WORD_H;
  bgCtx.fillStyle = '#191919';
  bgCtx.fillRect(0, y, vw, PHONEME_H);
  for (let i = 0; i < phonemeMarks.length; i++) {
    const pm = phonemeMarks[i];
    const absX = (pm.start_ms / 1000) * pxPerSec;
    const bw = Math.max(2, ((pm.end_ms - pm.start_ms) / 1000) * pxPerSec - 1);
    if (absX + bw < scrollX || absX > scrollX + vw) continue;
    const x = absX - scrollX;
    bgCtx.fillStyle = PHONEME_COLORS[pm.label] || PHONEME_COLORS.etc;
    bgCtx.fillRect(x, y + 4, bw, PHONEME_H - 8);
    if (bw > 18) {
      bgCtx.fillStyle = 'rgba(0,0,0,0.8)';
      bgCtx.font = 'bold 9px monospace';
      bgCtx.textAlign = 'center';
      bgCtx.fillText(pm.label, x + bw / 2, y + PHONEME_H / 2 + 3);
    }
  }
}

function drawWaveform(vw, scrollX) {
  if (!waveformData || !waveformData.samples.length) return;
  const vy = AXIS_H + WORD_H + PHONEME_H;
  bgCtx.fillStyle = '#0a140a';
  bgCtx.fillRect(0, vy, vw, WAVE_H);

  const samples = waveformData.samples;
  const durS = waveformData.duration_s;
  const mid = vy + WAVE_H / 2;
  const halfH = (WAVE_H - 6) / 2;
  const barW = Math.max(1, Math.ceil((durS / samples.length) * pxPerSec));
  bgCtx.fillStyle = '#3a8';

  // Only draw samples visible in viewport
  const startIdx = Math.max(0, Math.floor((scrollX / pxPerSec) / durS * samples.length) - 1);
  const endIdx = Math.min(samples.length, Math.ceil(((scrollX + vw) / pxPerSec) / durS * samples.length) + 1);
  for (let i = startIdx; i < endIdx; i++) {
    const amp = samples[i] * halfH;
    if (amp < 0.5) continue;
    const x = Math.round((i / samples.length) * durS * pxPerSec) - scrollX;
    bgCtx.fillRect(x, Math.round(mid - amp), barW, Math.max(1, Math.round(amp * 2)));
  }
}

function drawPlayhead(nowMs) {
  const w = fgCanvas.width, h = fgCanvas.height;
  fgCtx.clearRect(0, 0, w, h);
  const x = Math.round((nowMs / 1000) * pxPerSec) - canvasWrap.scrollLeft;
  if (x < 0 || x > w) return;
  fgCtx.strokeStyle = '#ff4444';
  fgCtx.lineWidth = 1.5;
  fgCtx.beginPath();
  fgCtx.moveTo(x, 0);
  fgCtx.lineTo(x, h);
  fgCtx.stroke();
}

// ── Phoneme recalculation from word timing ────────────────────────────────────

// Build a word→phoneme index on load so we know which phonemes belong to each word.
// This avoids the fragile time-overlap guessing that inflated phoneme counts.
let wordPhonemeMap = [];  // wordPhonemeMap[i] = [phoneme indices]

function buildWordPhonemeMap() {
  wordPhonemeMap = [];
  for (let wi = 0; wi < wordMarks.length; wi++) {
    const wm = wordMarks[wi];
    const indices = [];
    for (let pi = 0; pi < phonemeMarks.length; pi++) {
      const pm = phonemeMarks[pi];
      if (pm.start_ms >= wm.start_ms && pm.start_ms < wm.end_ms) {
        indices.push(pi);
      }
    }
    wordPhonemeMap.push(indices);
  }
}

// Redistribute phonemes within each word's current timing.
function recalcPhonemes() {
  if (wordPhonemeMap.length !== wordMarks.length) buildWordPhonemeMap();
  for (let wi = 0; wi < wordMarks.length; wi++) {
    const wm = wordMarks[wi];
    const pIndices = wordPhonemeMap[wi];
    if (pIndices.length === 0) continue;
    const dur = wm.end_ms - wm.start_ms;
    const each = dur / pIndices.length;
    for (let j = 0; j < pIndices.length; j++) {
      const pm = phonemeMarks[pIndices[j]];
      pm.start_ms = Math.round(wm.start_ms + j * each);
      pm.end_ms = Math.round(wm.start_ms + (j + 1) * each);
    }
  }
}

// ── Hit testing ───────────────────────────────────────────────────────────────

function hitTest(cx, cy) {
  const wy = AXIS_H;
  const HANDLE_ZONE = 8;  // pixels from edge that count as handle grab
  if (cy >= wy && cy < wy + WORD_H) {
    // First pass: check edge handles (priority over body)
    for (let i = 0; i < wordMarks.length; i++) {
      const wm = wordMarks[i];
      const x1 = (wm.start_ms / 1000) * pxPerSec;
      const x2 = (wm.end_ms / 1000) * pxPerSec;
      // Left handle zone: extends a few px outside the word too
      if (cx >= x1 - 4 && cx <= x1 + HANDLE_ZONE) {
        return { layer: 'word', idx: i, edge: 'start' };
      }
      // Right handle zone
      if (cx >= x2 - HANDLE_ZONE && cx <= x2 + 4) {
        return { layer: 'word', idx: i, edge: 'end' };
      }
    }
    // Second pass: check word body (move)
    for (let i = 0; i < wordMarks.length; i++) {
      const wm = wordMarks[i];
      const x1 = (wm.start_ms / 1000) * pxPerSec;
      const x2 = (wm.end_ms / 1000) * pxPerSec;
      if (cx >= x1 + HANDLE_ZONE && cx <= x2 - HANDLE_ZONE) {
        return { layer: 'word', idx: i, edge: 'move' };
      }
    }
  }
  return { layer: 'none', idx: -1, edge: null };
}

// ── Mouse interaction ─────────────────────────────────────────────────────────

bgCanvas.addEventListener('mousedown', (e) => {
  const rect = canvasWrap.getBoundingClientRect();
  const cx = e.clientX - rect.left + canvasWrap.scrollLeft;
  const cy = e.clientY - rect.top + canvasWrap.scrollTop;
  const hit = hitTest(cx, cy);

  if (hit.idx >= 0) {
    e.preventDefault();
    e.stopPropagation();
    dragLayer = hit.layer;
    dragIdx = hit.idx;
    dragEdge = hit.edge;
    dragStartX = cx;
    const mk = wordMarks[hit.idx];
    dragOrigStart = mk.start_ms;
    dragOrigEnd = mk.end_ms;
    bgCanvas.style.cursor = hit.edge === 'move' ? 'grabbing' : 'ew-resize';
    return;
  }

  // Click anywhere else → seek
  const clickMs = (cx / pxPerSec) * 1000;
  player.currentTime = trackMsToPlayer(clickMs);
});

window.addEventListener('mousemove', (e) => {
  const rect = canvasWrap.getBoundingClientRect();
  const cx = e.clientX - rect.left + canvasWrap.scrollLeft;
  const cy = e.clientY - rect.top + canvasWrap.scrollTop;

  if (dragIdx === null) {
    const hit = hitTest(cx, cy);
    bgCanvas.style.cursor = hit.idx >= 0
      ? (hit.edge === 'move' ? 'grab' : 'ew-resize')
      : 'default';
    return;
  }

  // Dragging a word — constrained so words can't cross neighbors
  const deltaMs = ((cx - dragStartX) / pxPerSec) * 1000;
  const mk = wordMarks[dragIdx];
  const prev = dragIdx > 0 ? wordMarks[dragIdx - 1] : null;
  const next = dragIdx < wordMarks.length - 1 ? wordMarks[dragIdx + 1] : null;
  const MIN_GAP = 5;  // minimum ms between adjacent words
  const MIN_DUR = 20; // minimum word duration ms

  if (dragEdge === 'start') {
    let newStart = Math.max(0, Math.round(dragOrigStart + deltaMs));
    if (prev) newStart = Math.max(newStart, prev.end_ms + MIN_GAP);
    if (newStart >= mk.end_ms - MIN_DUR) newStart = mk.end_ms - MIN_DUR;
    mk.start_ms = newStart;
  } else if (dragEdge === 'end') {
    let newEnd = Math.max(mk.start_ms + MIN_DUR, Math.round(dragOrigEnd + deltaMs));
    if (next) newEnd = Math.min(newEnd, next.start_ms - MIN_GAP);
    mk.end_ms = newEnd;
  } else {
    const dur = dragOrigEnd - dragOrigStart;
    let newStart = Math.max(0, Math.round(dragOrigStart + deltaMs));
    if (prev) newStart = Math.max(newStart, prev.end_ms + MIN_GAP);
    if (next) newStart = Math.min(newStart, next.start_ms - MIN_GAP - dur);
    mk.start_ms = newStart;
    mk.end_ms = newStart + dur;
  }

  dirty = true;
  drawFast();
});

window.addEventListener('mouseup', () => {
  if (dragIdx !== null) {
    recalcPhonemes();
    drawFast();
    dragIdx = null;
    dragLayer = null;
    dragEdge = null;
    bgCanvas.style.cursor = 'default';
    updateSaveButton();
  }
});

function updateSaveButton() {
  const btn = document.getElementById('btn-save');
  if (btn) {
    btn.disabled = !dirty;
    btn.textContent = dirty ? 'Save *' : 'Save';
  }
}

// ── Context menu (right-click on word) ────────────────────────────────────────

const wordMenu = document.getElementById('word-menu');
let menuWordIdx = null;

bgCanvas.addEventListener('contextmenu', (e) => {
  e.preventDefault();
  const rect = canvasWrap.getBoundingClientRect();
  const cx = e.clientX - rect.left + canvasWrap.scrollLeft;
  const cy = e.clientY - rect.top + canvasWrap.scrollTop;
  const hit = hitTest(cx, cy);

  if (hit.idx >= 0 && hit.layer === 'word') {
    menuWordIdx = hit.idx;
    wordMenu.style.display = 'block';
    wordMenu.style.left = e.clientX + 'px';
    wordMenu.style.top = e.clientY + 'px';
  } else {
    // Right-click on empty space — offer to add a word at this position
    menuWordIdx = -1;
    wordMenu.style.display = 'block';
    wordMenu.style.left = e.clientX + 'px';
    wordMenu.style.top = e.clientY + 'px';
    wordMenu._insertMs = Math.round((cx / pxPerSec) * 1000);
    document.getElementById('menu-edit').style.display = 'none';
    document.getElementById('menu-add-before').textContent = 'Add word here';
    document.getElementById('menu-add-after').style.display = 'none';
    document.getElementById('menu-delete').style.display = 'none';
  }
});

function hideMenu() {
  wordMenu.style.display = 'none';
  menuWordIdx = null;
  // Reset menu items
  document.getElementById('menu-edit').style.display = '';
  document.getElementById('menu-add-before').textContent = 'Add word before';
  document.getElementById('menu-add-after').style.display = '';
  document.getElementById('menu-delete').style.display = '';
}

document.addEventListener('click', (e) => {
  if (!wordMenu.contains(e.target)) hideMenu();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') hideMenu();
});

// ── Edit word ─────────────────────────────────────────────────────────────────

document.getElementById('menu-edit').addEventListener('click', async () => {
  if (menuWordIdx === null || menuWordIdx < 0) return hideMenu();
  const idx = menuWordIdx;
  const wm = wordMarks[idx];
  const newLabel = prompt('Edit word:', wm.label);
  hideMenu();
  if (newLabel === null || newLabel.trim() === '') return;

  const oldLabel = wm.label;
  wm.label = newLabel.trim().toUpperCase();
  console.log(`Edit word ${idx}: "${oldLabel}" → "${wm.label}"`);

  // Regenerate phonemes for this word (removes old, fetches new)
  await regeneratePhonemes(idx);
  dirty = true;
  buildWordPhonemeMap();
  renderLyrics();
  drawFast();
  updateSaveButton();
});

// ── Delete word ───────────────────────────────────────────────────────────────

document.getElementById('menu-delete').addEventListener('click', () => {
  if (menuWordIdx === null || menuWordIdx < 0) return hideMenu();
  const idx = menuWordIdx;
  const wm = wordMarks[idx];
  const label = wm.label;
  hideMenu();
  if (!confirm(`Delete "${label}"?`)) return;

  console.log(`Deleting word ${idx}: "${label}" (${wm.start_ms}-${wm.end_ms}ms)`);
  console.log(`Before: ${wordMarks.length} words, ${phonemeMarks.length} phonemes`);

  // Remove phonemes that fall within this word's time range
  const wStart = wm.start_ms, wEnd = wm.end_ms;
  phonemeMarks = phonemeMarks.filter(pm =>
    pm.start_ms < wStart || pm.start_ms >= wEnd
  );

  // Remove the word
  wordMarks.splice(idx, 1);

  console.log(`After: ${wordMarks.length} words, ${phonemeMarks.length} phonemes`);

  dirty = true;
  buildWordPhonemeMap();
  renderLyrics();
  drawFast();
  updateSaveButton();
});

// ── Add word ──────────────────────────────────────────────────────────────────

document.getElementById('menu-add-before').addEventListener('click', async () => {
  const idx = menuWordIdx;
  hideMenu();
  if (idx >= 0) {
    const wm = wordMarks[idx];
    const dur = Math.min(300, Math.floor((wm.end_ms - wm.start_ms) / 2));
    const newStart = wm.start_ms;
    const newEnd = newStart + dur;
    const oldWordStart = wm.start_ms;
    // Push existing word forward
    wm.start_ms = newEnd + 5;
    // Redistribute existing word's phonemes to its new time range
    const oldPhonemes = phonemeMarks.filter(pm =>
      pm.start_ms >= oldWordStart && pm.start_ms < wm.end_ms
    );
    if (oldPhonemes.length > 0) {
      const newDur = wm.end_ms - wm.start_ms;
      const each = newDur / oldPhonemes.length;
      for (let j = 0; j < oldPhonemes.length; j++) {
        oldPhonemes[j].start_ms = Math.round(wm.start_ms + j * each);
        oldPhonemes[j].end_ms = Math.round(wm.start_ms + (j + 1) * each);
      }
    }
    await addWordAt(newStart, idx, dur);
  } else {
    const ms = wordMenu._insertMs || 0;
    await addWordAt(ms, findInsertIdx(ms), 300);
  }
});

document.getElementById('menu-add-after').addEventListener('click', async () => {
  const idx = menuWordIdx;
  if (idx === null || idx < 0) return hideMenu();
  hideMenu();
  const wm = wordMarks[idx];
  const next = idx + 1 < wordMarks.length ? wordMarks[idx + 1] : null;
  // Find available gap after this word
  const gapStart = wm.end_ms + 5;
  const gapEnd = next ? next.start_ms - 5 : wm.end_ms + 305;
  const dur = Math.min(300, gapEnd - gapStart);
  if (dur < 20) {
    alert('No room to insert a word here. Move adjacent words apart first.');
    return;
  }
  await addWordAt(gapStart, idx + 1, dur);
});

function findInsertIdx(ms) {
  for (let i = 0; i < wordMarks.length; i++) {
    if (wordMarks[i].start_ms > ms) return i;
  }
  return wordMarks.length;
}

async function addWordAt(startMs, insertIdx, dur) {
  const label = prompt('New word:');
  if (!label || !label.trim()) return;
  const word = label.trim().toUpperCase();
  dur = dur || 300;
  const endMs = startMs + dur;

  console.log(`Adding word "${word}" at ${startMs}ms, insertIdx=${insertIdx}`);

  // Fetch phonemes from server
  let newPhonemes = [];
  try {
    const resp = await fetch('/phonemize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word, start_ms: startMs, end_ms: endMs }),
    });
    const data = await resp.json();
    if (data.phonemes) newPhonemes = data.phonemes;
    console.log(`Phonemize returned ${newPhonemes.length} phonemes`);
  } catch (e) {
    console.warn('Phonemize failed:', e);
  }

  // Insert word
  const newWord = { label: word, start_ms: startMs, end_ms: endMs };
  wordMarks.splice(insertIdx, 0, newWord);

  // Insert phonemes — just push them, buildWordPhonemeMap will sort them out by time
  for (const p of newPhonemes) {
    phonemeMarks.push(p);
  }
  // Sort phonemes by time
  phonemeMarks.sort((a, b) => a.start_ms - b.start_ms);

  console.log(`After add: ${wordMarks.length} words, ${phonemeMarks.length} phonemes`);

  dirty = true;
  buildWordPhonemeMap();
  // Recalc phonemes for all words to fix any that shifted
  recalcPhonemes();
  renderLyrics();
  drawFast();
  updateSaveButton();
}

// ── Regenerate phonemes for a single word ─────────────────────────────────────

async function regeneratePhonemes(wordIdx) {
  const wm = wordMarks[wordIdx];
  try {
    const resp = await fetch('/phonemize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word: wm.label, start_ms: wm.start_ms, end_ms: wm.end_ms }),
    });
    const data = await resp.json();
    if (data.phonemes) {
      // Remove old phonemes in this word's time range
      phonemeMarks = phonemeMarks.filter(pm =>
        pm.start_ms < wm.start_ms || pm.start_ms >= wm.end_ms
      );
      // Add new phonemes
      phonemeMarks.push(...data.phonemes);
      phonemeMarks.sort((a, b) => a.start_ms - b.start_ms);
      buildWordPhonemeMap();
      console.log(`Regenerated phonemes for "${wm.label}": ${data.phonemes.length} phonemes`);
    }
  } catch (e) {
    console.warn('Phonemize failed:', e);
  }
}

// ── Save ──────────────────────────────────────────────────────────────────────

async function saveEdits() {
  if (!dirty) return;
  const wMarks = wordMarks.map(wm => ({
    label: wm.label, start_ms: wm.start_ms, end_ms: wm.end_ms,
  }));
  const pMarks = phonemeMarks.map(pm => ({
    label: pm.label, start_ms: pm.start_ms, end_ms: pm.end_ms,
  }));
  try {
    const resp = await fetch('/save-words', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word_marks: wMarks, phoneme_marks: pMarks }),
    });
    const data = await resp.json();
    if (data.ok) {
      dirty = false;
      updateSaveButton();
      statusEl.textContent = `Saved ${data.count} words`;
      statusEl.style.display = '';
      setTimeout(() => { statusEl.style.display = 'none'; }, 2000);
    } else {
      alert('Save failed: ' + (data.error || 'unknown'));
    }
  } catch (e) {
    alert('Save failed: ' + e.message);
  }
}

document.getElementById('btn-save')?.addEventListener('click', saveEdits);

// ── Playback ──────────────────────────────────────────────────────────────────

function fmtTime(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

btnPlay.addEventListener('click', () => { player.paused ? player.play() : player.pause(); });
player.addEventListener('play',  () => { btnPlay.textContent = 'Pause'; });
player.addEventListener('pause', () => { btnPlay.textContent = 'Play'; });

// Use requestAnimationFrame for smooth 60fps playhead, face, and lyrics updates
let _animating = false;

function animationLoop() {
  if (player.paused && !_animating) return;
  const nowMs = playerToTrackMs();
  const dur = isFinite(player.duration) ? player.duration : durationMs / 1000;
  timeDisplay.textContent = `${fmtTime(nowMs / 1000)} / ${fmtTime(dur)}`;
  updateLyrics(nowMs);
  updateFace(nowMs);
  drawPlayhead(nowMs);
  autoScroll(nowMs);
  if (!player.paused) {
    requestAnimationFrame(animationLoop);
  } else {
    _animating = false;
  }
}

player.addEventListener('play', () => {
  _animating = true;
  requestAnimationFrame(animationLoop);
});
player.addEventListener('seeked', () => {
  const nowMs = playerToTrackMs();
  updateLyrics(nowMs);
  updateFace(nowMs);
  drawPlayhead(nowMs);
});

function autoScroll(nowMs) {
  const x = (nowMs / 1000) * pxPerSec;
  const vw = canvasWrap.clientWidth;
  const cur = canvasWrap.scrollLeft;
  if (x < cur + 60 || x > cur + vw - 60) {
    canvasWrap.scrollLeft = Math.max(0, x - vw / 2);
    // scroll event handler will trigger drawFast via rAF
  }
}

// ── Audio toggle ──────────────────────────────────────────────────────────────

btnFullMix.addEventListener('click', () => {
  if (usingVocals) switchAudio('/audio', false);
});
btnVocals.addEventListener('click', () => {
  if (!usingVocals && hasVocals) switchAudio('/vocal-audio', true);
});

function switchAudio(src, vocals) {
  const t = player.currentTime;
  const wasPlaying = !player.paused;
  player.src = src;
  player.currentTime = t;
  if (wasPlaying) player.play();
  usingVocals = vocals;
  btnVocals.classList.toggle('active', vocals);
  btnFullMix.classList.toggle('active', !vocals);
}

// ── Resize ────────────────────────────────────────────────────────────────────

window.addEventListener('resize', () => { renderWaveformImage(); drawAll(); });

// ── Go ────────────────────────────────────────────────────────────────────────

init();
