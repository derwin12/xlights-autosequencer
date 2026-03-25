'use strict';

// ── State ────────────────────────────────────────────────────────────────────

let allResults = [];     // all timing track results from sweep report
let markCache = {};      // algo_stem → [time_ms, ...] loaded from per-algo files
let filteredResults = []; // after stem filter
let selectedSet = new Set(); // indices into allResults for export
let activeStem = null;   // stem filter or null = all
let durationMs = 0;
let pxPerSec = 80;
let waveformData = null; // {samples: number[], duration_s: number}
const ZOOM_MIN = 15, ZOOM_MAX = 500, ZOOM_DEFAULT = 80;
const AXIS_H = 22;
const WAVE_H = 60;
const LANE_H = 28;

const STEM_COLORS = {
  drums: '#e74c3c', bass: '#e67e22', vocals: '#f1c40f',
  guitar: '#27ae60', piano: '#3498db', other: '#9b59b6', full_mix: '#888',
};

// ── DOM ──────────────────────────────────────────────────────────────────────

const player = document.getElementById('player');
const bgCanvas = document.getElementById('bg-canvas');
const fgCanvas = document.getElementById('fg-canvas');
const bgCtx = bgCanvas.getContext('2d');
const fgCtx = fgCanvas.getContext('2d');
const panelEl = document.getElementById('panel');
const canvasWrap = document.getElementById('canvas-wrap');
const spacer = document.getElementById('canvas-spacer');
const statusEl = document.getElementById('status');

// ── Init ─────────────────────────────────────────────────────────────────────

async function init() {
  try {
    // Load sweep report + analysis for duration
    const [sweepResp, analysisResp] = await Promise.all([
      fetch('/sweep-report'),
      fetch('/analysis'),
    ]);
    if (!sweepResp.ok) {
      statusEl.textContent = 'No sweep results found. Run sweep-matrix first.';
      return;
    }
    const report = await sweepResp.json();
    const analysis = analysisResp.ok ? await analysisResp.json() : {};

    durationMs = analysis.duration_ms || report.segment_end_ms || 210000;

    // Filter to timing tracks only (not value curves), successful only
    allResults = (report.results || [])
      .filter(r => r.status === 'success' && r.result_type === 'timing')
      .sort((a, b) => b.quality_score - a.quality_score);

    // Build stem filter buttons
    const stems = [...new Set(allResults.map(r => r.stem))].sort();
    buildStemFilters(stems);

    applyFilter();

    // Load full mix waveform by default
    try {
      const wr = await fetch('/waveform?stem=');
      if (wr.ok) waveformData = await wr.json();
    } catch (e) { /* optional */ }

    // Load full-song winner marks first, then segment marks as fallback
    await loadWinnerMarks();
    loadSegmentMarks();  // background — fills in non-winner tracks

    statusEl.style.display = 'none';
  } catch (e) {
    statusEl.textContent = `Failed: ${e.message}`;
  }
}

async function loadWinnerMarks() {
  try {
    const resp = await fetch('/sweep-winners');
    if (!resp.ok) return;
    const data = await resp.json();
    for (const entry of (data.results || [])) {
      const key = `${entry.algorithm}_${entry.stem}_${JSON.stringify(entry.parameters || {})}`;
      if (entry.marks) {
        markCache[key] = entry.marks.map(m => m.time_ms);
      }
    }
    drawFast();
  } catch (e) { /* winners not available yet */ }
}

async function loadSegmentMarks() {
  // Load per-algorithm files for tracks that don't have winner marks
  const algos = [...new Set(allResults.map(r => r.algorithm))];
  for (const algo of algos) {
    try {
      const resp = await fetch(`/sweep-algo-detail?algorithm=${algo}`);
      if (!resp.ok) continue;
      const data = await resp.json();
      for (const entry of (data.results || [])) {
        const key = `${entry.algorithm}_${entry.stem}_${JSON.stringify(entry.parameters || {})}`;
        if (!markCache[key] && entry.marks) {
          markCache[key] = entry.marks.map(m => m.time_ms);
        }
      }
    } catch (e) { /* skip */ }
  }
  drawFast();
}

// ── Stem Filters ─────────────────────────────────────────────────────────────

function buildStemFilters(stems) {
  const container = document.getElementById('stem-filters');
  container.innerHTML = '';

  const allBtn = document.createElement('button');
  allBtn.textContent = 'All';
  allBtn.className = 'active';
  allBtn.addEventListener('click', () => { activeStem = null; applyFilter(); });
  container.appendChild(allBtn);

  for (const stem of stems) {
    const btn = document.createElement('button');
    btn.textContent = stem;
    btn.style.borderLeft = `3px solid ${STEM_COLORS[stem] || '#888'}`;
    btn.addEventListener('click', () => { activeStem = stem; applyFilter(); });
    container.appendChild(btn);
  }
}

function applyFilter() {
  filteredResults = activeStem
    ? allResults.filter(r => r.stem === activeStem)
    : [...allResults];

  // Update button styles
  document.querySelectorAll('#stem-filters button').forEach(btn => {
    btn.classList.toggle('active',
      (activeStem === null && btn.textContent === 'All') ||
      btn.textContent === activeStem
    );
  });

  document.getElementById('result-count').textContent =
    `${filteredResults.length} timing tracks`;

  // Switch audio source and load waveform for selected stem
  switchStemAudio(activeStem);

  buildPanel();
  drawAll();
  updateExportBar();
}

async function switchStemAudio(stem) {
  const wasPlaying = !player.paused;
  const currentTime = player.currentTime;

  if (stem && stem !== 'full_mix') {
    // Try to play the stem audio
    player.src = `/stem-audio?stem=${stem}`;
  } else {
    player.src = '/audio';
  }
  player.currentTime = currentTime;
  if (wasPlaying) player.play();

  // Load waveform for this stem
  const waveformStem = (stem && stem !== 'full_mix') ? stem : '';
  try {
    const url = waveformStem ? `/waveform?stem=${waveformStem}` : '/waveform?stem=';
    const resp = await fetch(url);
    if (resp.ok) {
      waveformData = await resp.json();
    } else {
      waveformData = null;
    }
  } catch (e) {
    waveformData = null;
  }
  drawAll();
}

// ── Panel (left sidebar) ─────────────────────────────────────────────────────

function buildPanel() {
  panelEl.innerHTML = '';

  // Axis spacer — must exactly match AXIS_H on the canvas
  const axisRow = document.createElement('div');
  axisRow.style.height = AXIS_H + 'px';
  axisRow.style.minHeight = AXIS_H + 'px';
  axisRow.style.maxHeight = AXIS_H + 'px';
  axisRow.style.boxSizing = 'border-box';
  axisRow.style.background = '#181818';
  panelEl.appendChild(axisRow);

  // Waveform spacer — must exactly match WAVE_H on the canvas
  if (waveformData) {
    const waveRow = document.createElement('div');
    waveRow.style.height = WAVE_H + 'px';
    waveRow.style.minHeight = WAVE_H + 'px';
    waveRow.style.maxHeight = WAVE_H + 'px';
    waveRow.style.boxSizing = 'border-box';
    waveRow.style.display = 'flex';
    waveRow.style.alignItems = 'center';
    waveRow.style.background = '#0a140a';
    waveRow.style.borderBottom = '1px solid #333';
    waveRow.style.color = '#4a8';
    waveRow.style.fontSize = '10px';
    waveRow.style.paddingLeft = '8px';
    waveRow.textContent = activeStem ? `${activeStem} waveform` : 'full mix waveform';
    panelEl.appendChild(waveRow);
  }

  filteredResults.forEach((r, i) => {
    const globalIdx = allResults.indexOf(r);
    const row = document.createElement('div');
    row.className = 'lane-row' + (selectedSet.has(globalIdx) ? ' selected' : '');

    const check = document.createElement('input');
    check.type = 'checkbox';
    check.className = 'check';
    check.checked = selectedSet.has(globalIdx);
    check.addEventListener('change', () => {
      if (check.checked) selectedSet.add(globalIdx);
      else selectedSet.delete(globalIdx);
      row.classList.toggle('selected', check.checked);
      updateExportBar();
    });

    const rank = document.createElement('span');
    rank.className = 'rank';
    rank.textContent = `${i + 1}`;

    const score = document.createElement('span');
    score.className = 'score';
    score.textContent = r.quality_score.toFixed(2);

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = r.algorithm;

    const badge = document.createElement('span');
    badge.className = 'stem-badge';
    badge.textContent = r.stem;
    badge.style.borderLeft = `2px solid ${STEM_COLORS[r.stem] || '#888'}`;

    row.appendChild(check);
    row.appendChild(rank);
    row.appendChild(score);
    row.appendChild(name);
    row.appendChild(badge);
    panelEl.appendChild(row);
  });
}

// ── Canvas Drawing ───────────────────────────────────────────────────────────

function totalW() { return Math.ceil((durationMs / 1000) * pxPerSec); }

function canvasH() {
  const waveH = waveformData ? WAVE_H : 0;
  return AXIS_H + waveH + filteredResults.length * LANE_H;
}

function laneY(i) {
  return AXIS_H + (waveformData ? WAVE_H : 0) + i * LANE_H;
}

function drawAll() {
  const vw = canvasWrap.clientWidth;
  const h = canvasH();
  bgCanvas.width = fgCanvas.width = vw;
  bgCanvas.height = fgCanvas.height = h;
  spacer.style.width = totalW() + 'px';
  spacer.style.height = h + 'px';
  drawFast();
}

function drawFast() {
  const vw = bgCanvas.width;
  const h = bgCanvas.height;
  const scrollX = canvasWrap.scrollLeft;
  bgCanvas.style.left = scrollX + 'px';
  fgCanvas.style.left = scrollX + 'px';
  bgCtx.clearRect(0, 0, vw, h);

  // Time axis
  bgCtx.fillStyle = '#181818';
  bgCtx.fillRect(0, 0, vw, AXIS_H);
  bgCtx.font = '10px monospace';
  const stepS = pxPerSec >= 50 ? 5 : pxPerSec >= 25 ? 10 : 30;
  for (let s = Math.floor(scrollX / pxPerSec / stepS) * stepS;
       s * pxPerSec < scrollX + vw + pxPerSec; s += stepS) {
    const x = s * pxPerSec - scrollX;
    bgCtx.fillStyle = '#2a2a2a';
    bgCtx.fillRect(x, 0, 1, AXIS_H);
    bgCtx.fillStyle = '#666';
    bgCtx.textAlign = 'left';
    bgCtx.fillText(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`, x + 2, 14);
  }

  // Waveform lane
  if (waveformData && waveformData.samples && waveformData.samples.length > 0) {
    const wy = AXIS_H;
    bgCtx.fillStyle = '#0a140a';
    bgCtx.fillRect(0, wy, vw, WAVE_H);
    const samples = waveformData.samples;
    const durS = waveformData.duration_s;
    const mid = wy + WAVE_H / 2;
    const halfH = (WAVE_H - 6) / 2;
    const stemColor = activeStem ? (STEM_COLORS[activeStem] || '#3a8') : '#3a8';
    bgCtx.fillStyle = stemColor + '99';
    const startIdx = Math.max(0, Math.floor((scrollX / pxPerSec) / durS * samples.length) - 1);
    const endIdx = Math.min(samples.length, Math.ceil(((scrollX + vw) / pxPerSec) / durS * samples.length) + 1);
    const barW = Math.max(1, Math.ceil((durS / samples.length) * pxPerSec));
    for (let si = startIdx; si < endIdx; si++) {
      const amp = samples[si] * halfH;
      if (amp < 0.5) continue;
      const x = Math.round((si / samples.length) * durS * pxPerSec) - scrollX;
      bgCtx.fillRect(x, Math.round(mid - amp), barW, Math.max(1, Math.round(amp * 2)));
    }
    // Divider
    bgCtx.fillStyle = '#333';
    bgCtx.fillRect(0, wy + WAVE_H - 1, vw, 1);
  }

  // Track lanes
  filteredResults.forEach((r, i) => {
    const y = laneY(i);
    const globalIdx = allResults.indexOf(r);
    const isSelected = selectedSet.has(globalIdx);

    // Lane background
    bgCtx.fillStyle = isSelected ? '#1a2a3a' : (i % 2 === 0 ? '#1a1a1a' : '#1d1d1d');
    bgCtx.fillRect(0, y, vw, LANE_H);

    // Marks — use real marks from cache if available, else estimate
    const stemColor = STEM_COLORS[r.stem] || '#888';
    bgCtx.fillStyle = stemColor + (isSelected ? '' : '88');

    const cacheKey = `${r.algorithm}_${r.stem}_${JSON.stringify(r.parameters || {})}`;
    const realMarks = markCache[cacheKey];

    if (realMarks && realMarks.length > 0) {
      for (const tMs of realMarks) {
        const absX = (tMs / 1000) * pxPerSec;
        if (absX + 2 < scrollX || absX > scrollX + vw) continue;
        const x = absX - scrollX;
        bgCtx.fillRect(x, y + 3, 2, LANE_H - 6);
      }
    } else if (r.mark_count > 0 && r.avg_interval_ms > 0) {
      // Fallback: estimate from average interval
      const interval = r.avg_interval_ms;
      for (let t = 0; t < durationMs; t += interval) {
        const absX = (t / 1000) * pxPerSec;
        if (absX + 2 < scrollX || absX > scrollX + vw) continue;
        const x = absX - scrollX;
        bgCtx.fillRect(x, y + 2, 1, LANE_H - 4);
      }
    }

    // Lane divider
    bgCtx.fillStyle = '#2a2a2a';
    bgCtx.fillRect(0, y + LANE_H - 1, vw, 1);
  });

  // Playhead
  const ph = canvasH();
  fgCtx.clearRect(0, 0, vw, ph);
  if (player.currentTime) {
    const x = (player.currentTime * pxPerSec) - scrollX;
    if (x >= 0 && x <= vw) {
      fgCtx.strokeStyle = '#ff4444';
      fgCtx.lineWidth = 1.5;
      fgCtx.beginPath();
      fgCtx.moveTo(x, 0);
      fgCtx.lineTo(x, ph);
      fgCtx.stroke();
    }
  }
}

// ── Scroll + Playback ────────────────────────────────────────────────────────

canvasWrap.addEventListener('scroll', () => drawFast());

// Sync vertical scroll between panel and canvas
let _syncingPanel = false, _syncingCanvas = false;
canvasWrap.addEventListener('scroll', () => {
  if (_syncingCanvas) return;
  _syncingPanel = true;
  panelEl.scrollTop = canvasWrap.scrollTop;
  _syncingPanel = false;
});
panelEl.addEventListener('scroll', () => {
  if (_syncingPanel) return;
  _syncingCanvas = true;
  canvasWrap.scrollTop = panelEl.scrollTop;
  _syncingCanvas = false;
});

// Click to seek
bgCanvas.addEventListener('click', (e) => {
  const rect = canvasWrap.getBoundingClientRect();
  const cx = e.clientX - rect.left + canvasWrap.scrollLeft;
  player.currentTime = cx / pxPerSec;
});

// Playback
const btnPlay = document.getElementById('btn-play');
btnPlay.addEventListener('click', () => { player.paused ? player.play() : player.pause(); });
player.addEventListener('play', () => { btnPlay.textContent = 'Pause'; animLoop(); });
player.addEventListener('pause', () => { btnPlay.textContent = 'Play'; });

let _animating = false;
function animLoop() {
  if (player.paused) { _animating = false; return; }
  _animating = true;
  const nowMs = player.currentTime * 1000;
  const dur = isFinite(player.duration) ? player.duration : durationMs / 1000;
  document.getElementById('time-display').textContent =
    `${fmtTime(player.currentTime)} / ${fmtTime(dur)}`;
  drawFast();
  // Auto-scroll
  const x = player.currentTime * pxPerSec;
  const vw = canvasWrap.clientWidth;
  const cur = canvasWrap.scrollLeft;
  if (x < cur + 60 || x > cur + vw - 60) {
    canvasWrap.scrollLeft = Math.max(0, x - vw / 2);
  }
  requestAnimationFrame(animLoop);
}

function fmtTime(s) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

// ── Zoom ─────────────────────────────────────────────────────────────────────

function setZoom(newPx) {
  const oldPx = pxPerSec;
  pxPerSec = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, Math.round(newPx)));
  if (pxPerSec === oldPx) return;
  const vw = canvasWrap.clientWidth;
  const centerTime = (canvasWrap.scrollLeft + vw / 2) / ((durationMs / 1000) * oldPx);
  drawAll();
  canvasWrap.scrollLeft = Math.max(0, centerTime * (durationMs / 1000) * pxPerSec - vw / 2);
  document.getElementById('zoom-level').textContent =
    Math.round((pxPerSec / ZOOM_DEFAULT) * 100) + '%';
}

document.getElementById('btn-zoom-in').addEventListener('click', () => setZoom(pxPerSec * 1.3));
document.getElementById('btn-zoom-out').addEventListener('click', () => setZoom(pxPerSec / 1.3));

// ── Select All / None ────────────────────────────────────────────────────────

document.getElementById('btn-select-all').addEventListener('click', () => {
  filteredResults.forEach(r => selectedSet.add(allResults.indexOf(r)));
  buildPanel();
  updateExportBar();
});

document.getElementById('btn-select-none').addEventListener('click', () => {
  selectedSet.clear();
  buildPanel();
  updateExportBar();
});

// ── Export Bar ────────────────────────────────────────────────────────────────

function updateExportBar() {
  const bar = document.getElementById('export-bar');
  if (selectedSet.size > 0) {
    bar.style.display = 'flex';
    document.getElementById('export-info').textContent =
      `${selectedSet.size} track(s) selected for export`;
  } else {
    bar.style.display = 'none';
  }
}

function exportSelected() {
  const items = [...selectedSet].map(i => allResults[i]);
  const names = items.map(r => `${r.algorithm}_${r.stem}`);
  alert(`Export ${items.length} tracks:\n\n${names.join('\n')}\n\n(Export integration coming next)`);
}

// ── Resize ───────────────────────────────────────────────────────────────────

window.addEventListener('resize', () => drawAll());

// ── Go ───────────────────────────────────────────────────────────────────────

init();
