'use strict';

// ── State ────────────────────────────────────────────────────────────────────

let tracks = [];          // all tracks, in user-defined order within each group
let dragSrcIndex = null;
let phonemeLayers = [];   // [{name, type, marks}]
let songSegments = [];    // [{label, start_ms, end_ms}]
let durationMs = 0;
let focusIndex = null;    // index into displayTracks() | null
let activeStemFilter = null; // stem name string | null

const SEGMENT_FILL = {
  'intro':        'rgba(60,  180,  80, 0.10)',
  'verse':        'rgba(80,  140, 220, 0.10)',
  'pre-chorus':   'rgba(160,  80, 220, 0.10)',
  'chorus':       'rgba(220,  70,  70, 0.14)',
  'bridge':       'rgba(220, 160,  40, 0.12)',
  'outro':        'rgba(120, 120, 120, 0.10)',
  'instrumental': 'rgba( 40, 200, 200, 0.10)',
  'break':        'rgba(200, 200,  40, 0.10)',
  'silence':      'rgba( 40,  40,  40, 0.08)',
};
const SEGMENT_LABEL_COLOR = {
  'intro':        '#3b6',
  'verse':        '#58d',
  'pre-chorus':   '#a5d',
  'chorus':       '#d55',
  'bridge':       '#da4',
  'outro':        '#888',
  'instrumental': '#4cc',
  'break':        '#cc4',
  'silence':      '#555',
};

const player = document.getElementById('player');
const bgCanvas = document.getElementById('bg-canvas');
const fgCanvas = document.getElementById('fg-canvas');
const bgCtx = bgCanvas.getContext('2d');
const fgCtx = fgCanvas.getContext('2d');
const panel = document.getElementById('panel');
const stemFilterBar = document.getElementById('stem-filter-bar');
const trackList = document.getElementById('track-list');
const canvasWrap = document.getElementById('canvas-wrap');
const beatFlash = document.getElementById('beat-flash');
const btnPlay = document.getElementById('btn-play');
const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');
const btnClear = document.getElementById('btn-clear');
const btnExport = document.getElementById('btn-export');
const timeDisplay = document.getElementById('time-display');
const focusLabel = document.getElementById('focus-label');
const selectedCount = document.getElementById('selected-count');
const status = document.getElementById('status');

const LANE_H = 60;
const PHONEME_LANE_H = 40;
const AXIS_H = 24;
const QUEUE_DIVIDER_H = 20; // canvas height of the export-queue / available divider
let pxPerSec = 100;
const ZOOM_MIN = 20;
const ZOOM_MAX = 500;
const ZOOM_DEFAULT = 100;

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function canvasWidth() {
  return Math.max(canvasWrap.clientWidth, Math.ceil((durationMs / 1000) * pxPerSec));
}

// ── Zoom ──────────────────────────────────────────────────────────────────

const zoomLabel = document.getElementById('zoom-level');
const btnZoomIn = document.getElementById('btn-zoom-in');
const btnZoomOut = document.getElementById('btn-zoom-out');

function setZoom(newPxPerSec, anchorFraction) {
  // anchorFraction: the fraction of the visible viewport to keep stable
  // (0 = left edge, 0.5 = center). Default to center of viewport.
  if (anchorFraction === undefined) anchorFraction = 0.5;

  const oldPx = pxPerSec;
  pxPerSec = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.round(newPxPerSec)));
  if (pxPerSec === oldPx) return;

  // Preserve the time position under the anchor point
  const viewW = canvasWrap.clientWidth;
  const oldScroll = canvasWrap.scrollLeft;
  const anchorX = oldScroll + viewW * anchorFraction;
  const anchorTime = anchorX / ((durationMs / 1000) * oldPx);

  drawBackground();
  buildPanel();

  const newAnchorX = anchorTime * (durationMs / 1000) * pxPerSec;
  canvasWrap.scrollLeft = Math.max(0, newAnchorX - viewW * anchorFraction);

  zoomLabel.textContent = Math.round((pxPerSec / ZOOM_DEFAULT) * 100) + '%';
}

if (btnZoomIn) btnZoomIn.addEventListener('click', () => setZoom(pxPerSec * 1.3));
if (btnZoomOut) btnZoomOut.addEventListener('click', () => setZoom(pxPerSec / 1.3));

// Ctrl+scroll or pinch-to-zoom on the canvas
canvasWrap.addEventListener('wheel', (e) => {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault();
    const rect = canvasWrap.getBoundingClientRect();
    const anchorFrac = (e.clientX - rect.left) / rect.width;
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setZoom(pxPerSec * factor, anchorFrac);
  }
}, { passive: false });

// Keyboard shortcuts: Ctrl+ / Ctrl- / Ctrl+0
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && (e.key === '=' || e.key === '+')) {
    e.preventDefault();
    setZoom(pxPerSec * 1.3);
  } else if ((e.ctrlKey || e.metaKey) && e.key === '-') {
    e.preventDefault();
    setZoom(pxPerSec / 1.3);
  } else if ((e.ctrlKey || e.metaKey) && e.key === '0') {
    e.preventDefault();
    setZoom(ZOOM_DEFAULT);
  }
});

// Returns the tracks to display: selected (all stems) first, then unselected
// filtered by activeStemFilter.
function displayTracks() {
  const sel = tracks.filter(t => t.selected);
  const avail = tracks.filter(t => !t.selected &&
    (!activeStemFilter || t.stem_source === activeStemFilter));
  return [...sel, ...avail];
}

// Y position on the canvas for a given index into displayTracks().
// Phoneme layers sit at the top (just below the time axis), so all tracks
// are offset down by their combined height.
function trackY(displayIdx) {
  const dt = displayTracks();
  const queueLen = dt.filter(t => t.selected).length;
  const phonemeOffset = phonemeLayers.length * PHONEME_LANE_H;
  if (displayIdx < queueLen) return AXIS_H + phonemeOffset + displayIdx * LANE_H;
  return AXIS_H + phonemeOffset + queueLen * LANE_H + QUEUE_DIVIDER_H + (displayIdx - queueLen) * LANE_H;
}

function canvasHeight() {
  const dt = displayTracks();
  const queueLen = dt.filter(t => t.selected).length;
  const availLen = dt.length - queueLen;
  return AXIS_H + phonemeLayers.length * PHONEME_LANE_H +
         queueLen * LANE_H + QUEUE_DIVIDER_H + availLen * LANE_H;
}

function phonemeLayerY(i) {
  return AXIS_H + i * PHONEME_LANE_H;
}

function timeToX(ms) {
  return (ms / durationMs) * canvasWidth();
}

// ── Background canvas (track marks + time axis) ───────────────────────────────

function drawBackground() {
  const w = canvasWidth();
  const h = canvasHeight();
  bgCanvas.width = w;
  bgCanvas.height = h;
  fgCanvas.width = w;
  fgCanvas.height = h;

  bgCtx.clearRect(0, 0, w, h);

  // Time axis
  bgCtx.fillStyle = '#222';
  bgCtx.fillRect(0, 0, w, AXIS_H);
  bgCtx.fillStyle = '#555';
  bgCtx.font = '10px system-ui';
  bgCtx.textBaseline = 'middle';
  const stepSec = durationMs > 120000 ? 30 : 10;
  for (let t = 0; t <= durationMs / 1000; t += stepSec) {
    const x = timeToX(t * 1000);
    bgCtx.fillStyle = '#444';
    bgCtx.fillRect(x, 0, 1, AXIS_H);
    bgCtx.fillStyle = '#888';
    bgCtx.fillText(fmtTime(t), x + 2, AXIS_H / 2);
  }

  // Song structure segments — colored bands behind track lanes
  if (songSegments.length > 0) {
    const tracksH = canvasHeight() - AXIS_H;
    songSegments.forEach(seg => {
      const x1 = timeToX(seg.start_ms);
      const x2 = timeToX(seg.end_ms);
      bgCtx.fillStyle = SEGMENT_FILL[seg.label] || 'rgba(255,255,255,0.05)';
      bgCtx.fillRect(x1, AXIS_H, x2 - x1, tracksH);

      // Segment label on time axis
      bgCtx.fillStyle = SEGMENT_LABEL_COLOR[seg.label] || '#888';
      bgCtx.font = 'bold 9px system-ui';
      bgCtx.textBaseline = 'top';
      bgCtx.fillText(seg.label, x1 + 3, 3);

      // Dividing line at segment start
      bgCtx.fillStyle = SEGMENT_LABEL_COLOR[seg.label] || '#555';
      bgCtx.globalAlpha = 0.4;
      bgCtx.fillRect(x1, AXIS_H, 1, tracksH);
      bgCtx.globalAlpha = 1.0;
    });
  }

  // Track lanes
  const dt = displayTracks();
  const queueLen = dt.filter(t => t.selected).length;

  dt.forEach((track, i) => {
    const y = trackY(i);
    const inQueue = i < queueLen;
    const isEven = i % 2 === 0;
    bgCtx.fillStyle = inQueue
      ? (isEven ? '#141820' : '#161a24')   // slight blue tint for export queue
      : (isEven ? '#141414' : '#181818');
    bgCtx.fillRect(0, y, w, LANE_H);

    // Lane separator
    bgCtx.fillStyle = '#222';
    bgCtx.fillRect(0, y + LANE_H - 1, w, 1);

    // Marks
    bgCtx.globalAlpha = track.selected ? 1.0 : 0.4;
    bgCtx.fillStyle = track.isHighDensity ? '#e44' : '#4a9';
    track.marks_ms.forEach(ms => {
      const x = timeToX(ms);
      bgCtx.fillRect(x, y + 4, 2, LANE_H - 8);
    });
    bgCtx.globalAlpha = 1.0;
  });

  // Queue / available divider band
  const divY = AXIS_H + phonemeLayers.length * PHONEME_LANE_H + queueLen * LANE_H;
  bgCtx.fillStyle = '#16161e';
  bgCtx.fillRect(0, divY, w, QUEUE_DIVIDER_H);
  bgCtx.fillStyle = '#3a4a7a';
  bgCtx.fillRect(0, divY, w, 1);
  bgCtx.fillStyle = '#3a4a7a';
  bgCtx.fillRect(0, divY + QUEUE_DIVIDER_H - 1, w, 1);
  bgCtx.fillStyle = '#4af';
  bgCtx.font = '10px system-ui';
  bgCtx.textBaseline = 'middle';
  bgCtx.fillText(
    queueLen > 0 ? `▲ ${queueLen} track${queueLen !== 1 ? 's' : ''} selected for export  ·  available below` : '▲ export queue empty  ·  check tracks below to add',
    8, divY + QUEUE_DIVIDER_H / 2
  );

  // Phoneme / word layers
  const PHONEME_COLORS = { words: '#7ab', phonemes: '#a87', default: '#888' };
  phonemeLayers.forEach((layer, i) => {
    const y = phonemeLayerY(i);
    const isEven = i % 2 === 0;
    bgCtx.fillStyle = isEven ? '#161a1a' : '#1a1a16';
    bgCtx.fillRect(0, y, w, PHONEME_LANE_H);

    // Lane label
    bgCtx.fillStyle = '#666';
    bgCtx.font = '10px system-ui';
    bgCtx.textBaseline = 'top';
    bgCtx.fillText(layer.name, 4, y + 2);

    // Lane separator
    bgCtx.fillStyle = '#222';
    bgCtx.fillRect(0, y + PHONEME_LANE_H - 1, w, 1);

    const color = PHONEME_COLORS[layer.type] || PHONEME_COLORS.default;
    bgCtx.font = '9px system-ui';
    bgCtx.textBaseline = 'middle';

    layer.marks.forEach(m => {
      const x1 = timeToX(m.start_ms);
      const x2 = timeToX(m.end_ms);
      const barW = Math.max(1, x2 - x1 - 1);

      bgCtx.fillStyle = color;
      bgCtx.globalAlpha = 0.7;
      bgCtx.fillRect(x1, y + 12, barW, PHONEME_LANE_H - 16);
      bgCtx.globalAlpha = 1.0;

      // Draw label if bar is wide enough
      if (barW > 12) {
        bgCtx.fillStyle = '#eee';
        bgCtx.fillText(m.label, x1 + 2, y + PHONEME_LANE_H / 2);
      }
    });
  });

  // Focus dimming
  if (focusIndex !== null && focusIndex < dt.length) {
    dt.forEach((_, i) => {
      if (i !== focusIndex) {
        bgCtx.fillStyle = 'rgba(0,0,0,0.65)';
        bgCtx.fillRect(0, trackY(i), w, LANE_H);
      }
    });
    const focusY = trackY(focusIndex);
    bgCtx.strokeStyle = '#4af';
    bgCtx.lineWidth = 2;
    bgCtx.strokeRect(1, focusY + 1, w - 2, LANE_H - 2);
  }
}

// ── Foreground canvas (playhead only — viewport-sized for performance) ────────
//
// fg-canvas is kept the same width as the visible viewport, not the full song
// width. Its `left` CSS property is updated to match canvasWrap.scrollLeft so
// it always overlays the visible portion. This means clearing and redrawing
// only ~1400×viewportWidth pixels per frame instead of ~1400×21000px.

function drawForeground() {
  const vw = canvasWrap.clientWidth;
  const h = canvasHeight();
  const scrollLeft = canvasWrap.scrollLeft;

  // Resize only when dimensions actually change (avoids clearing the canvas unnecessarily)
  if (fgCanvas.width !== vw)  fgCanvas.width  = vw;
  if (fgCanvas.height !== h)  fgCanvas.height = h;

  // Slide fg-canvas to cover the currently visible strip of the bg-canvas
  fgCanvas.style.left = scrollLeft + 'px';

  fgCtx.clearRect(0, 0, vw, h);

  if (!player.duration || !isFinite(player.duration)) return;

  const totalW = canvasWidth();
  const currentMs = player.currentTime * 1000;

  // Highlight active word/phoneme mark at playhead position
  phonemeLayers.forEach((layer, i) => {
    const y = phonemeLayerY(i);
    const active = layer.marks.find(m => currentMs >= m.start_ms && currentMs < m.end_ms);
    if (active) {
      const x1 = timeToX(active.start_ms) - scrollLeft;
      const x2 = timeToX(active.end_ms) - scrollLeft;
      if (x2 > 0 && x1 < vw) {
        fgCtx.fillStyle = 'rgba(255,220,80,0.35)';
        fgCtx.fillRect(Math.max(0, x1), y + 1, Math.max(2, x2 - x1), PHONEME_LANE_H - 2);
      }
    }
  });

  // Playhead
  const x = (player.currentTime / player.duration) * totalW - scrollLeft;
  if (x >= 0 && x <= vw) {
    fgCtx.fillStyle = '#f44';
    fgCtx.fillRect(Math.floor(x), 0, 1, h);
  }
}

// ── Panel (left lane controls) ────────────────────────────────────────────────

function buildPanel() {
  trackList.innerHTML = '';

  // Phoneme / word layers at the top of the panel, matching their canvas position
  const PHONEME_TYPE_LABEL = { words: 'words', phonemes: 'phonemes' };
  phonemeLayers.forEach(layer => {
    const div = document.createElement('div');
    div.className = 'lane-control phoneme-lane-control';
    div.style.height = PHONEME_LANE_H + 'px';
    div.innerHTML = `
      <div class="lane-content">
        <div class="lane-top">
          <span class="lane-name" title="${layer.name}">${layer.name}</span>
          <span class="stem-badge">${PHONEME_TYPE_LABEL[layer.type] || layer.type}</span>
        </div>
        <div class="lane-meta"><span>${layer.marks.length} marks</span></div>
      </div>
    `;
    trackList.appendChild(div);
  });

  const dt = displayTracks();
  const queueLen = dt.filter(t => t.selected).length;

  dt.forEach((track, displayIdx) => {
    // Export queue / available divider
    if (displayIdx === queueLen) {
      const div = document.createElement('div');
      div.className = 'queue-divider';
      div.textContent = 'Available tracks';
      trackList.appendChild(div);
    }

    // Sweep section separator within available tracks
    if (displayIdx >= queueLen && track.isSweep) {
      const prev = displayIdx > 0 ? dt[displayIdx - 1] : null;
      if (!prev || !prev.isSweep || prev.selected) {
        const sep = document.createElement('div');
        sep.className = 'sweep-separator';
        sep.textContent = 'Sweep variants';
        trackList.appendChild(sep);
      }
    }

    const div = document.createElement('div');
    div.className = 'lane-control' + (track.isSweep ? ' sweep-track' : '');
    div.dataset.trackName = track.name;
    div.dataset.displayIdx = displayIdx;
    div.draggable = true;

    const score = track.quality_score;
    const scoreClass = score >= 0.5 ? '' : score >= 0.2 ? 'mid' : 'low';
    const stemLabel = track.stem_source && track.stem_source !== 'full_mix'
      ? `<span class="stem-badge">${track.stem_source}</span>` : '';
    const sweepLabel = track.isSweep
      ? `<span class="sweep-badge" title="rank ${track.sweepRank}">sweep #${track.sweepRank}</span>` : '';

    div.innerHTML = `
      <div class="lane-drag-handle" title="Drag to reorder">&#8942;</div>
      <div class="lane-content">
        <div class="lane-top">
          <span class="lane-name" title="${track.name}">${track.isSweep ? track.algorithm : track.name}</span>
          <span class="score-badge ${scoreClass}">${score.toFixed(2)}</span>
          ${stemLabel}${sweepLabel}
        </div>
        <div class="lane-meta">
          <span class="type-tag">${track.element_type}</span>
          <span>${track.mark_count} marks</span>
          <button class="btn-solo" data-display-idx="${displayIdx}">Solo</button>
          <input type="checkbox" class="chk-select" data-track-name="${track.name}" ${track.selected ? 'checked' : ''}>
        </div>
      </div>
    `;
    trackList.appendChild(div);
  });

  // Solo button clicks
  trackList.querySelectorAll('.btn-solo').forEach(btn => {
    btn.addEventListener('click', e => {
      const i = parseInt(e.currentTarget.dataset.displayIdx);
      focusIndex === i ? clearFocus() : setFocus(i);
    });
  });

  // Checkbox toggles — rebuild display (moves track between queue/available)
  trackList.querySelectorAll('.chk-select').forEach(chk => {
    chk.addEventListener('change', e => {
      const name = e.currentTarget.dataset.trackName;
      const t = tracks.find(tr => tr.name === name);
      if (t) t.selected = e.currentTarget.checked;
      focusIndex = null; // reset focus as display order changes
      buildPanel();
      updateSelectedCount();
      drawBackground();
    });
  });

  // Drag-to-reorder within tracks[]
  trackList.querySelectorAll('.lane-control').forEach(div => {
    div.addEventListener('dragstart', e => {
      dragSrcIndex = parseInt(div.dataset.displayIdx);
      e.dataTransfer.effectAllowed = 'move';
      div.classList.add('dragging');
    });
    div.addEventListener('dragend', () => {
      div.classList.remove('dragging');
      trackList.querySelectorAll('.lane-control').forEach(d => d.classList.remove('drag-over'));
    });
    div.addEventListener('dragover', e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      trackList.querySelectorAll('.lane-control').forEach(d => d.classList.remove('drag-over'));
      div.classList.add('drag-over');
    });
    div.addEventListener('dragleave', () => div.classList.remove('drag-over'));
    div.addEventListener('drop', e => {
      e.preventDefault();
      div.classList.remove('drag-over');
      const destDisplayIdx = parseInt(div.dataset.displayIdx);
      if (dragSrcIndex !== null && dragSrcIndex !== destDisplayIdx) {
        const dt2 = displayTracks();
        const srcTrack = dt2[dragSrcIndex];
        const destTrack = dt2[destDisplayIdx];
        const si = tracks.indexOf(srcTrack);
        const di = tracks.indexOf(destTrack);
        if (si !== -1 && di !== -1) {
          tracks.splice(si, 1);
          const newDi = tracks.indexOf(destTrack);
          tracks.splice(newDi >= 0 ? newDi : di, 0, srcTrack);
        }
        if (focusIndex === dragSrcIndex) focusIndex = destDisplayIdx;
        buildPanel();
        drawBackground();
        drawForeground();
      }
      dragSrcIndex = null;
    });
  });

  updatePanelClasses();
}

function updatePanelClasses() {
  trackList.querySelectorAll('.lane-control').forEach(div => {
    const displayIdx = parseInt(div.dataset.displayIdx);
    const dt = displayTracks();
    const track = dt[displayIdx];
    if (!track) return;

    div.classList.remove('focused', 'unfocused', 'deselected');
    if (!track.selected) {
      div.classList.add('deselected');
    } else if (focusIndex !== null) {
      div.classList.add(displayIdx === focusIndex ? 'focused' : 'unfocused');
    }

    const soloBtn = div.querySelector('.btn-solo');
    if (soloBtn) soloBtn.classList.toggle('active', focusIndex === displayIdx);
  });
}

function updateSelectedCount() {
  const n = tracks.filter(t => t.selected).length;
  selectedCount.textContent = `${n} / ${tracks.length} selected`;
  btnExport.disabled = n === 0;
}

// ── Focus management ──────────────────────────────────────────────────────────

function setFocus(i) {
  const dt = displayTracks();
  if (i < 0 || i >= dt.length) return;
  focusIndex = i;
  focusLabel.textContent = `Focus: ${dt[i].name}`;
  updatePanelClasses();
  drawBackground();
  drawForeground();
  scheduleFlashes();
}

function clearFocus() {
  focusIndex = null;
  focusLabel.textContent = '';
  updatePanelClasses();
  drawBackground();
  drawForeground();
  scheduleFlashes();
}

function focusNext() {
  const n = displayTracks().length;
  if (n === 0) return;
  setFocus(focusIndex === null ? 0 : (focusIndex + 1) % n);
}

function focusPrev() {
  const n = displayTracks().length;
  if (n === 0) return;
  setFocus(focusIndex === null ? n - 1 : (focusIndex - 1 + n) % n);
}

// ── Playback ──────────────────────────────────────────────────────────────────

let rafId = null;
let flashTimers = [];
let flashAnim = null;

// Fire slightly early to compensate for visual processing latency (~1 frame).
// Increase this value if flashes feel late; decrease if they feel early.
const VISUAL_LEAD_MS = 20;

function triggerFlash() {
  if (flashAnim) flashAnim.cancel();
  flashAnim = beatFlash.animate([
    { background: '#fff', boxShadow: '0 0 10px #fff, 0 0 4px #adf' },
    { background: '#4af', boxShadow: '0 0 6px #4af', offset: 0.4 },
    { background: '#2a2a2a', boxShadow: 'none' },
  ], { duration: 250, easing: 'ease-out' });
}

function cancelFlashTimers() {
  flashTimers.forEach(clearTimeout);
  flashTimers = [];
}

// Schedule a setTimeout for every upcoming mark in the monitored track.
// This fires independent of the render loop, giving much tighter timing than
// per-frame currentTime polling.
function scheduleFlashes() {
  cancelFlashTimers();
  if (player.paused || player.ended || !player.duration) return;
  const dt = displayTracks();
  const monitorTrack = focusIndex !== null ? dt[focusIndex] : dt.find(t => t.selected);
  if (!monitorTrack) return;
  const currentMs = player.currentTime * 1000;
  for (const markMs of monitorTrack.marks_ms) {
    const delay = markMs - currentMs - VISUAL_LEAD_MS;
    if (delay < -50) continue; // already passed
    flashTimers.push(setTimeout(triggerFlash, Math.max(0, delay)));
  }
}

function rafLoop() {
  drawForeground();
  timeDisplay.textContent = `${fmtTime(player.currentTime)} / ${fmtTime(player.duration || 0)}`;

  // Auto-scroll to keep playhead in view
  if (player.duration && isFinite(player.duration)) {
    const x = (player.currentTime / player.duration) * canvasWidth();
    const viewLeft = canvasWrap.scrollLeft;
    const viewRight = viewLeft + canvasWrap.clientWidth;
    if (x > viewRight - 60) {
      canvasWrap.scrollLeft = Math.max(0, x - canvasWrap.clientWidth * 0.25);
    } else if (x < viewLeft) {
      canvasWrap.scrollLeft = Math.max(0, x - 50);
    }
  }

  if (!player.paused && !player.ended) {
    rafId = requestAnimationFrame(rafLoop);
  }
}

btnPlay.addEventListener('click', () => {
  if (player.paused) {
    player.play();
    btnPlay.textContent = 'Pause';
    rafId = requestAnimationFrame(rafLoop);
    scheduleFlashes();
  } else {
    player.pause();
    btnPlay.textContent = 'Play';
    cancelAnimationFrame(rafId);
    cancelFlashTimers();
    drawForeground();
  }
});

player.addEventListener('ended', () => {
  btnPlay.textContent = 'Play';
  cancelAnimationFrame(rafId);
  cancelFlashTimers();
  drawForeground();
});

// Timeline seek (click on canvas wrap)
canvasWrap.addEventListener('mousedown', e => {
  if (!player.duration || !isFinite(player.duration)) return;
  const rect = canvasWrap.getBoundingClientRect();
  const scrollX = canvasWrap.scrollLeft;
  const x = e.clientX - rect.left + scrollX;
  const w = canvasWidth();
  const seekTime = (x / w) * player.duration;
  player.currentTime = Math.max(0, Math.min(seekTime, player.duration));
  scheduleFlashes(); // reschedule from new position
  drawForeground();
  timeDisplay.textContent = `${fmtTime(player.currentTime)} / ${fmtTime(player.duration)}`;
});

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
  switch (e.key) {
    case ' ':
      e.preventDefault();
      btnPlay.click();
      break;
    case 'ArrowRight':
    case 'n':
      e.preventDefault();
      focusNext();
      break;
    case 'ArrowLeft':
    case 'p':
      e.preventDefault();
      focusPrev();
      break;
    case 'Escape':
      clearFocus();
      break;
  }
});

// ── Focus/Nav buttons ─────────────────────────────────────────────────────────

btnNext.addEventListener('click', focusNext);
btnPrev.addEventListener('click', focusPrev);
btnClear.addEventListener('click', clearFocus);

// ── Export ───────────────────────────────────────────────────────────────────

async function doExport(overwrite = false) {
  const names = tracks.filter(t => t.selected).map(t => t.name);
  if (names.length === 0) {
    status.textContent = 'No tracks selected — nothing to export.';
    return;
  }

  const body = { selected_track_names: names };
  if (overwrite) body.overwrite = true;

  let resp;
  try {
    resp = await fetch('/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (err) {
    status.textContent = `Export failed: ${err.message}`;
    return;
  }

  const data = await resp.json();

  if (resp.status === 409) {
    if (confirm(`File already exists:\n${data.path}\n\nOverwrite?`)) {
      doExport(true);
    }
    return;
  }

  if (resp.status === 400) {
    status.textContent = `Export error: ${data.error}`;
    return;
  }

  if (resp.ok) {
    status.textContent = `Exported ${names.length} track(s) to: ${data.path}`;
  } else {
    status.textContent = `Export error: ${data.error || resp.status}`;
  }
}

btnExport.addEventListener('click', () => doExport(false));

// ── Scroll / resize handling ──────────────────────────────────────────────────

// Sync vertical scroll between panel and canvas-wrap so lane labels always
// align with canvas rows. Use flags to prevent infinite scroll loops.
let _syncingPanelScroll = false;
let _syncingCanvasScroll = false;

trackList.addEventListener('scroll', () => {
  if (_syncingCanvasScroll) return;
  _syncingPanelScroll = true;
  canvasWrap.scrollTop = trackList.scrollTop;
  _syncingPanelScroll = false;
});

canvasWrap.addEventListener('scroll', () => {
  if (_syncingPanelScroll) return;
  _syncingCanvasScroll = true;
  trackList.scrollTop = canvasWrap.scrollTop;
  _syncingCanvasScroll = false;
  drawForeground();
});

window.addEventListener('resize', () => {
  drawBackground();
  drawForeground();
});

// ── Stem filter ───────────────────────────────────────────────────────────────

function switchStemAudio(stemName) {
  const wasPlaying = !player.paused;
  const pos = player.currentTime;
  player.src = stemName ? `/stem-audio?stem=${encodeURIComponent(stemName)}` : '/audio';
  player.currentTime = pos;
  if (wasPlaying) player.play().catch(() => {});
}

function buildStemFilter() {
  const stems = [...new Set(tracks.map(t => t.stem_source).filter(s => s && s !== 'full_mix'))];
  if (stems.length === 0) {
    stemFilterBar.innerHTML = '';
    return;
  }
  const label = document.createElement('div');
  label.className = 'filter-label';
  label.textContent = 'Filter by stem';
  stemFilterBar.innerHTML = '';
  stemFilterBar.appendChild(label);

  const allBtn = document.createElement('button');
  allBtn.className = 'stem-btn' + (!activeStemFilter ? ' active' : '');
  allBtn.textContent = 'all';
  allBtn.addEventListener('click', () => {
    activeStemFilter = null;
    focusIndex = null;
    switchStemAudio(null);
    stemFilterBar.querySelectorAll('.stem-btn').forEach(b => b.classList.remove('active'));
    allBtn.classList.add('active');
    buildPanel();
    drawBackground();
    drawForeground();
  });
  stemFilterBar.appendChild(allBtn);

  stems.sort().forEach(stem => {
    const btn = document.createElement('button');
    btn.className = 'stem-btn' + (activeStemFilter === stem ? ' active' : '');
    btn.textContent = stem;
    btn.addEventListener('click', () => {
      activeStemFilter = activeStemFilter === stem ? null : stem;
      focusIndex = null;
      switchStemAudio(activeStemFilter);
      stemFilterBar.querySelectorAll('.stem-btn').forEach(b => b.classList.remove('active'));
      (activeStemFilter ? btn : allBtn).classList.add('active');
      buildPanel();
      drawBackground();
      drawForeground();
    });
    stemFilterBar.appendChild(btn);
  });
}

// ── Initialise ────────────────────────────────────────────────────────────────

async function init() {
  try {
    const resp = await fetch('/analysis');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    durationMs = data.duration_ms || 0;

    // Build track list sorted by quality_score descending
    const regularTracks = (data.timing_tracks || [])
      .sort((a, b) => b.quality_score - a.quality_score)
      .map(t => ({
        name: t.name,
        element_type: t.element_type,
        quality_score: t.quality_score,
        mark_count: t.mark_count,
        avg_interval_ms: t.avg_interval_ms,
        marks_ms: (t.marks || []).map(m => m.time_ms),
        stem_source: t.stem_source || 'full_mix',
        selected: false,
        isSweep: false,
        isHighDensity: t.quality_score === 0 || (t.avg_interval_ms > 0 && t.avg_interval_ms < 200),
      }));

    const sweepTracks = (data.sweep_tracks || [])
      .sort((a, b) => b.quality_score - a.quality_score)
      .map(t => ({
        name: t.name,
        element_type: t.element_type || 'beat',
        quality_score: t.quality_score,
        mark_count: t.mark_count,
        avg_interval_ms: t.avg_interval_ms,
        marks_ms: (t.marks || []).map(m => m.time_ms),
        stem_source: t.stem_source || t.stem || 'full_mix',
        selected: false,
        isSweep: true,
        algorithm: t.algorithm || '',
        sweepRank: t.rank,
        sweepParams: t.parameters || {},
        isHighDensity: t.avg_interval_ms > 0 && t.avg_interval_ms < 200,
      }));

    tracks = [...regularTracks, ...sweepTracks];

    // Enable Phonemes button when phoneme data is present
    const btnPhonemes = document.getElementById('btn-phonemes');
    if (btnPhonemes && data.phoneme_result) {
      btnPhonemes.disabled = false;
      btnPhonemes.title = '';
    }

    // Load song structure segments
    songSegments = [];
    if (data.song_structure && data.song_structure.segments) {
      songSegments = data.song_structure.segments;
    }

    // Build phoneme layers from phoneme_result (if present)
    phonemeLayers = [];
    const pr = data.phoneme_result;
    if (pr) {
      if (pr.word_track && pr.word_track.marks && pr.word_track.marks.length > 0) {
        phonemeLayers.push({
          name: pr.word_track.name || 'whisperx-words',
          type: 'words',
          marks: pr.word_track.marks,
        });
      }
      if (pr.phoneme_track && pr.phoneme_track.marks && pr.phoneme_track.marks.length > 0) {
        phonemeLayers.push({
          name: pr.phoneme_track.name || 'whisperx-phonemes',
          type: 'phonemes',
          marks: pr.phoneme_track.marks,
        });
      }
    }

    buildStemFilter();
    buildPanel();
    updateSelectedCount();
    drawBackground();
    drawForeground();

    const phonemeInfo = phonemeLayers.length > 0
      ? ` | ${phonemeLayers[0].marks.length} words, ${phonemeLayers[1] ? phonemeLayers[1].marks.length + ' phonemes' : ''}`
      : '';
    const sweepInfo = sweepTracks.length > 0 ? ` | ${sweepTracks.length} sweep variants` : '';
    status.textContent = `Loaded ${regularTracks.length} tracks${sweepInfo}${phonemeInfo} | ${fmtTime(durationMs / 1000)} | ${data.filename || ''}`;

    // Update time display when audio metadata loads
    player.addEventListener('loadedmetadata', () => {
      timeDisplay.textContent = `0:00 / ${fmtTime(player.duration)}`;
    });

  } catch (err) {
    status.textContent = `Error loading analysis: ${err.message}`;
  }
}

init();
