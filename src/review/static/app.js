'use strict';

// ── State ────────────────────────────────────────────────────────────────────

let tracks = [];        // [{name, element_type, quality_score, mark_count, avg_interval_ms, marks_ms, selected, isHighDensity}]
let phonemeLayers = []; // [{name, type, marks}] where marks = [{label, start_ms, end_ms}]
                        // type: 'words' | 'phonemes'
let songSegments = [];  // [{label, start_ms, end_ms}] from song_structure
let durationMs = 0;
let focusIndex = null;  // int | null

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
const PHONEME_LANE_H = 40; // shorter lanes for word/phoneme layers
const AXIS_H = 24;
const PX_PER_SEC = 100; // default zoom; canvas width = duration_s * PX_PER_SEC

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtTime(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function canvasWidth() {
  return Math.max(canvasWrap.clientWidth, Math.ceil((durationMs / 1000) * PX_PER_SEC));
}

function canvasHeight() {
  return AXIS_H + tracks.length * LANE_H + phonemeLayers.length * PHONEME_LANE_H;
}

function phonemeLayerY(i) {
  return AXIS_H + tracks.length * LANE_H + i * PHONEME_LANE_H;
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
    const tracksH = tracks.length * LANE_H + phonemeLayers.length * PHONEME_LANE_H;
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
  tracks.forEach((track, i) => {
    const y = AXIS_H + i * LANE_H;
    const isEven = i % 2 === 0;
    bgCtx.fillStyle = isEven ? '#141414' : '#181818';
    bgCtx.fillRect(0, y, w, LANE_H);

    // Lane separator
    bgCtx.fillStyle = '#222';
    bgCtx.fillRect(0, y + LANE_H - 1, w, 1);

    // Marks
    const opacity = track.selected ? 1.0 : 0.4;
    bgCtx.globalAlpha = opacity;
    bgCtx.fillStyle = track.isHighDensity ? '#e44' : '#4a9';
    track.marks_ms.forEach(ms => {
      const x = timeToX(ms);
      bgCtx.fillRect(x, y + 4, 2, LANE_H - 8);
    });
    bgCtx.globalAlpha = 1.0;
  });

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

  // Focus dimming — drawn here because it only changes on user action, not every frame
  if (focusIndex !== null) {
    tracks.forEach((_, i) => {
      if (i !== focusIndex) {
        const y = AXIS_H + i * LANE_H;
        bgCtx.fillStyle = 'rgba(0,0,0,0.65)';
        bgCtx.fillRect(0, y, w, LANE_H);
      }
    });
    const focusY = AXIS_H + focusIndex * LANE_H;
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
  panel.innerHTML = '';
  tracks.forEach((track, i) => {
    const div = document.createElement('div');
    div.className = 'lane-control';
    div.dataset.index = i;

    const score = track.quality_score;
    const scoreClass = score >= 0.5 ? '' : score >= 0.2 ? 'mid' : 'low';

    const stemLabel = track.stem_source && track.stem_source !== 'full_mix'
      ? `<span class="stem-badge">${track.stem_source}</span>`
      : '';
    div.innerHTML = `
      <div class="lane-top">
        <span class="lane-name" title="${track.name}">${track.name}</span>
        <span class="score-badge ${scoreClass}">${score.toFixed(2)}</span>
        ${stemLabel}
      </div>
      <div class="lane-meta">
        <span class="type-tag">${track.element_type}</span>
        <span>${track.mark_count} marks</span>
        <button class="btn-solo" data-index="${i}">Solo</button>
        <input type="checkbox" class="chk-select" data-index="${i}" ${track.selected ? 'checked' : ''}>
      </div>
    `;
    panel.appendChild(div);
  });

  // Solo button clicks
  panel.querySelectorAll('.btn-solo').forEach(btn => {
    btn.addEventListener('click', e => {
      const i = parseInt(e.currentTarget.dataset.index);
      if (focusIndex === i) {
        clearFocus();
      } else {
        setFocus(i);
      }
    });
  });

  // Checkbox toggles
  panel.querySelectorAll('.chk-select').forEach(chk => {
    chk.addEventListener('change', e => {
      const i = parseInt(e.currentTarget.dataset.index);
      tracks[i].selected = e.currentTarget.checked;
      updatePanelClasses();
      updateSelectedCount();
      drawBackground();
    });
  });
}

function updatePanelClasses() {
  panel.querySelectorAll('.lane-control').forEach((div, i) => {
    div.classList.remove('focused', 'unfocused', 'deselected');
    if (!tracks[i].selected) {
      div.classList.add('deselected');
    } else if (focusIndex === null) {
      // normal
    } else if (i === focusIndex) {
      div.classList.add('focused');
    } else {
      div.classList.add('unfocused');
    }

    // Update solo button active state
    const soloBtn = div.querySelector('.btn-solo');
    if (soloBtn) {
      soloBtn.classList.toggle('active', focusIndex === i);
    }
  });
}

function updateSelectedCount() {
  const n = tracks.filter(t => t.selected).length;
  selectedCount.textContent = `${n} / ${tracks.length} selected`;
  btnExport.disabled = n === 0;
}

// ── Focus management ──────────────────────────────────────────────────────────

function setFocus(i) {
  focusIndex = i;
  focusLabel.textContent = `Focus: ${tracks[i].name}`;
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
  if (tracks.length === 0) return;
  if (focusIndex === null) {
    setFocus(0);
  } else {
    setFocus((focusIndex + 1) % tracks.length);
  }
}

function focusPrev() {
  if (tracks.length === 0) return;
  if (focusIndex === null) {
    setFocus(tracks.length - 1);
  } else {
    setFocus((focusIndex - 1 + tracks.length) % tracks.length);
  }
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
  const monitorTrack = focusIndex !== null ? tracks[focusIndex] : tracks.find(t => t.selected);
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

// Reposition the viewport-sized fg-canvas when the user scrolls
canvasWrap.addEventListener('scroll', drawForeground);

window.addEventListener('resize', () => {
  drawBackground();
  drawForeground();
});

// ── Initialise ────────────────────────────────────────────────────────────────

async function init() {
  try {
    const resp = await fetch('/analysis');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();

    durationMs = data.duration_ms || 0;

    // Build track list sorted by quality_score descending
    tracks = (data.timing_tracks || [])
      .sort((a, b) => b.quality_score - a.quality_score)
      .map(t => ({
        name: t.name,
        element_type: t.element_type,
        quality_score: t.quality_score,
        mark_count: t.mark_count,
        avg_interval_ms: t.avg_interval_ms,
        marks_ms: (t.marks || []).map(m => m.time_ms),
        stem_source: t.stem_source || 'full_mix',
        selected: true,
        isHighDensity: t.quality_score === 0 || (t.avg_interval_ms > 0 && t.avg_interval_ms < 200),
      }));

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

    buildPanel();
    updateSelectedCount();
    drawBackground();
    drawForeground();

    const phonemeInfo = phonemeLayers.length > 0
      ? ` | ${phonemeLayers[0].marks.length} words, ${phonemeLayers[1] ? phonemeLayers[1].marks.length + ' phonemes' : ''}`
      : '';
    status.textContent = `Loaded ${tracks.length} tracks${phonemeInfo} | ${fmtTime(durationMs / 1000)} | ${data.filename || ''}`;

    // Update time display when audio metadata loads
    player.addEventListener('loadedmetadata', () => {
      timeDisplay.textContent = `0:00 / ${fmtTime(player.duration)}`;
    });

  } catch (err) {
    status.textContent = `Error loading analysis: ${err.message}`;
  }
}

init();
