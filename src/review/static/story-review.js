/**
 * story-review.js — Vanilla JS SPA for the Song Story Review UI (Phase 4).
 *
 * No frameworks, no external CDN dependencies.
 * All communication is via the /story/* Flask blueprint routes.
 */

"use strict";

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  story: null,
  currentSectionIdx: 0,
  audio: null,
  audioCtx: null,
  waveformData: null,   // {peaks: Float32Array} for full mix
  stemWaveforms: {},     // {drums: {peaks}, bass: {peaks}, ...}
  isPlaying: false,
  // Zoom state: visible time window (seconds)
  zoomLevel: 1.0,       // 1.0 = full song visible; 2.0 = 2× zoomed, etc.
  scrollOffset: 0,      // left edge of visible window (seconds)
  // Accent layer visibility: which stems' accents are shown on the timeline
  accentLayers: { drums: true, bass: true, vocals: true, guitar: false, piano: false, other: false },
  // Flyout panel state
  flyoutOpen: false,
  activeTab: "details", // "details" | "moments" | "themes"
  // Theme data (loaded from /themes/api/list)
  themeList: [],         // full list of theme objects
  themePalettes: {},     // {themeName: [hex, hex, ...]} lookup
  themeFilters: { mood: null, occasion: null },
  themesLoadFailed: false,
};

// ── Role → CSS var mapping ────────────────────────────────────────────────────

const ROLE_CSS_VAR = {
  intro:               "--role-intro",
  verse:               "--role-verse",
  pre_chorus:          "--role-pre-chorus",
  "pre-chorus":        "--role-pre-chorus",
  chorus:              "--role-chorus",
  post_chorus:         "--role-post-chorus",
  "post-chorus":       "--role-post-chorus",
  bridge:              "--role-bridge",
  instrumental_break:  "--role-instrumental-break",
  "instrumental-break":"--role-instrumental-break",
  climax:              "--role-climax",
  ambient_bridge:      "--role-ambient-bridge",
  "ambient-bridge":    "--role-ambient-bridge",
  outro:               "--role-outro",
  interlude:           "--role-interlude",
};

function roleColor(role) {
  const varName = ROLE_CSS_VAR[role] || "--role-outro";
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || "#666";
}

// ── Zoom helpers ─────────────────────────────────────────────────────────────

function visibleDuration() {
  const total = state.story ? state.story.song.duration_seconds || 1 : 1;
  return total / state.zoomLevel;
}

/** Convert a song time (seconds) to canvas pixel X. */
function timeToX(timeSec, canvasW) {
  return ((timeSec - state.scrollOffset) / visibleDuration()) * canvasW;
}

/** Convert a canvas pixel X to song time (seconds). */
function xToTime(px, canvasW) {
  return state.scrollOffset + (px / canvasW) * visibleDuration();
}

/** Clamp scrollOffset so visible window stays within [0, totalDuration]. */
function clampScroll() {
  const total = state.story ? state.story.song.duration_seconds || 1 : 1;
  const visDur = visibleDuration();
  state.scrollOffset = Math.max(0, Math.min(state.scrollOffset, total - visDur));
}

function zoomIn() {
  const maxZoom = 16;
  if (state.zoomLevel >= maxZoom) return;
  const center = state.scrollOffset + visibleDuration() / 2;
  state.zoomLevel = Math.min(maxZoom, state.zoomLevel * 1.5);
  state.scrollOffset = center - visibleDuration() / 2;
  clampScroll();
  renderTimeline();
  renderStemTracks();
  _updatePlayheadPosition();
}

function zoomOut() {
  if (state.zoomLevel <= 1.0) return;
  const center = state.scrollOffset + visibleDuration() / 2;
  state.zoomLevel = Math.max(1.0, state.zoomLevel / 1.5);
  state.scrollOffset = center - visibleDuration() / 2;
  clampScroll();
  renderTimeline();
  renderStemTracks();
  _updatePlayheadPosition();
}

function zoomReset() {
  state.zoomLevel = 1.0;
  state.scrollOffset = 0;
  renderTimeline();
  renderStemTracks();
  _updatePlayheadPosition();
}

/** Scroll so that a given time is centered (or at least visible). */
function scrollToTime(timeSec) {
  const visDur = visibleDuration();
  if (timeSec < state.scrollOffset || timeSec > state.scrollOffset + visDur) {
    state.scrollOffset = timeSec - visDur / 2;
    clampScroll();
  }
}

function _updatePlayheadPosition() {
  const player = document.getElementById("player");
  const playheadBar = document.getElementById("playhead-bar");
  const canvas = document.getElementById("timeline");
  if (!player || !playheadBar || !canvas) return;
  const rect = canvas.getBoundingClientRect();
  const px = timeToX(player.currentTime, rect.width);
  playheadBar.style.left = `${px}px`;
}

// ── Audio waveform decoding ───────────────────────────────────────────────────

function _getAudioContext() {
  if (!state.audioCtx) {
    state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  return state.audioCtx;
}

/**
 * Fetch an audio URL, decode it, and return the mono PCM Float32Array.
 */
async function decodeAudioMono(url) {
  const resp = await fetch(url);
  if (!resp.ok) return null;
  const arrayBuf = await resp.arrayBuffer();
  const actx = _getAudioContext();
  const audioBuf = await actx.decodeAudioData(arrayBuf);

  // Mix down to mono
  const numChannels = audioBuf.numberOfChannels;
  if (numChannels === 1) {
    return audioBuf.getChannelData(0);
  }
  const len = audioBuf.getChannelData(0).length;
  const mono = new Float32Array(len);
  for (let ch = 0; ch < numChannels; ch++) {
    const chData = audioBuf.getChannelData(ch);
    for (let i = 0; i < len; i++) {
      mono[i] += chData[i] / numChannels;
    }
  }
  return mono;
}

/**
 * Compute min/max peaks from raw PCM for a given pixel width.
 * Returns Float32Array of [min0, max0, min1, max1, ...] with exactly pixelW pairs.
 */
function computePeaks(mono, pixelW) {
  const n = mono.length;
  const bins = Math.max(Math.round(pixelW), 1);
  const binSize = n / bins;
  const peaks = new Float32Array(bins * 2);
  for (let b = 0; b < bins; b++) {
    const start = Math.floor(b * binSize);
    const end = Math.min(Math.floor((b + 1) * binSize), n);
    let min = 1, max = -1;
    for (let i = start; i < end; i++) {
      if (mono[i] < min) min = mono[i];
      if (mono[i] > max) max = mono[i];
    }
    peaks[b * 2] = min;
    peaks[b * 2 + 1] = max;
  }
  return peaks;
}

/**
 * Draw a waveform from raw mono PCM data onto a canvas context region.
 * Bins to exactly W pixels for pixel-perfect rendering.
 * yOffset/h define the vertical region to draw into.
 */
function drawWaveform(ctx, mono, W, yOffset, h, fillColor) {
  if (!mono || mono.length < 2) return;
  const peaks = computePeaks(mono, W);
  const numBins = peaks.length / 2;
  const centerY = yOffset + h * 0.5;
  const maxAmp = h * 0.45;

  ctx.save();
  ctx.beginPath();
  ctx.moveTo(0, centerY);
  for (let b = 0; b < numBins; b++) {
    ctx.lineTo(b, centerY - peaks[b * 2 + 1] * maxAmp);
  }
  for (let b = numBins - 1; b >= 0; b--) {
    ctx.lineTo(b, centerY - peaks[b * 2] * maxAmp);
  }
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();

  // Center line
  ctx.strokeStyle = "rgba(255,255,255,0.06)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, centerY);
  ctx.lineTo(W, centerY);
  ctx.stroke();
  ctx.restore();
}

/**
 * Load and decode the full mix + all stem audio files, then re-render.
 */
async function loadWaveforms() {
  // Decode full mix
  try {
    const mono = await decodeAudioMono("/story/audio");
    if (mono) {
      state.waveformData = { mono };
      renderTimeline();
    }
  } catch (e) {
    console.warn("Could not decode main audio waveform:", e);
  }

  // Decode stems in parallel
  try {
    const stemResp = await fetch("/story/stem-list");
    if (stemResp.ok) {
      const { stems } = await stemResp.json();
      const promises = (stems || []).map(async (name) => {
        try {
          const mono = await decodeAudioMono(`/story/stem-audio/${name}`);
          if (mono) {
            state.stemWaveforms[name] = { mono };
          }
        } catch (e) {
          console.warn(`Could not decode stem "${name}":`, e);
        }
      });
      await Promise.all(promises);
      renderStemTracks();
    }
  } catch (e) {
    console.warn("Could not load stem list:", e);
  }
}

// ── Initialization ────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const path = params.get("path");
  if (!path) {
    document.getElementById("loading").textContent =
      'Error: missing ?path= query parameter. Usage: /story-review?path=/absolute/path/to/story.json';
    return;
  }
  wireToolbar();
  // Load story first, THEN wire audio (player needs /story/load to complete
  // before it can fetch /story/audio).
  loadStory(path).then(() => wireAudio());
});

async function loadStory(path) {
  try {
    const resp = await fetch(`/story/load?path=${encodeURIComponent(path)}`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      document.getElementById("loading").textContent =
        `Error loading story: ${err.error || resp.statusText}`;
      return;
    }
    const responseData = await resp.json();
    // T054: check for stale edits warning from server
    if (typeof showStaleBanner === "function") {
      showStaleBanner(!!(responseData._meta && responseData._meta.stale_edits));
    }
    state.story = responseData;
  } catch (e) {
    document.getElementById("loading").textContent = `Network error: ${e.message}`;
    return;
  }

  // Update page title with song info
  const song = state.story.song || {};
  const title = [song.artist !== "Unknown" ? song.artist : null, song.title]
    .filter(Boolean).join(" — ");
  document.title = `Story Review — ${title}`;
  document.getElementById("song-title").textContent = title || "Song Story Review";

  // Show app, hide loading spinner
  document.getElementById("loading").style.display = "none";
  document.getElementById("app").style.display = "";

  // T054: Stale edits detection — show banner if edits are out of date
  const meta = state.story._meta || {};
  showStaleBanner(!!meta.stale_edits);

  renderTimeline();
  renderStemTracks();
  selectSection(0);
  renderPreferencesPanel();

  // Load and decode actual audio waveforms (async, re-renders when ready)
  loadWaveforms();

  // Load theme data for palette strips on timeline (async, re-renders when ready)
  loadThemes().then(() => { if (state.themeList.length) renderTimeline(); });
}

// ── Timeline rendering ────────────────────────────────────────────────────────

let _timelineClickBound = false;

function renderTimeline() {
  const story = state.story;
  if (!story || !story.sections || !story.sections.length) return;

  const canvas = document.getElementById("timeline");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  // Make the canvas pixel-perfect at device resolution
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const W = rect.width;
  const H = rect.height;
  if (W === 0 || H === 0) return; // not visible yet

  canvas.width = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);

  const sections = story.sections;

  ctx.clearRect(0, 0, W, H);

  // ── Draw waveform from decoded audio PCM data (zoom-aware) ──
  if (state.waveformData && state.waveformData.mono) {
    const mono = state.waveformData.mono;
    const total = story.song.duration_seconds || 1;
    const sampleRate = mono.length / total;
    const startSample = Math.floor(state.scrollOffset * sampleRate);
    const endSample = Math.floor((state.scrollOffset + visibleDuration()) * sampleRate);
    const visibleMono = mono.slice(startSample, endSample);
    drawWaveform(ctx, visibleMono, W, 0, H, "rgba(255,255,255,0.35)");
  }

  // ── Draw section blocks (zoom-aware) ──
  sections.forEach((section, idx) => {
    const x = timeToX(section.start, W);
    const x2 = timeToX(section.end, W);
    const w = x2 - x;

    // Skip sections entirely outside view
    if (x2 < 0 || x > W) return;

    const color = roleColor(section.role);
    const isSelected = idx === state.currentSectionIdx;

    // Section fill overlay
    ctx.fillStyle = color;
    ctx.globalAlpha = isSelected ? 0.45 : 0.2;
    ctx.fillRect(x, 0, w, H);

    // Top color bar
    ctx.globalAlpha = isSelected ? 1.0 : 0.7;
    ctx.fillRect(x, 0, w, 4);

    // Selected outline
    if (isSelected) {
      ctx.globalAlpha = 1;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 1, 1, Math.max(w - 2, 0), H - 2);
    }

    // Section label
    ctx.globalAlpha = 1;
    ctx.fillStyle = isSelected ? "#ffffff" : "rgba(255,255,255,0.85)";
    ctx.font = `${isSelected ? "bold " : ""}11px monospace`;
    ctx.textAlign = "left";
    ctx.textBaseline = "top";

    const label = _roleLabel(section.role);
    const padding = 5;
    const maxLabelW = w - padding * 2;

    if (maxLabelW > 20) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(Math.max(x, 0), 0, Math.min(w, W), H);
      ctx.clip();
      ctx.fillText(label, x + padding, 8, maxLabelW);

      // Time label
      ctx.fillStyle = isSelected ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.5)";
      ctx.font = "10px monospace";
      ctx.fillText(section.start_fmt || _fmtSec(section.start), x + padding, 22, maxLabelW);

      // Energy indicator at bottom
      const eScore = section.character ? section.character.energy_score : 0;
      ctx.fillStyle = `rgba(255,255,255,0.3)`;
      ctx.fillRect(x, H - 3, w * (eScore / 100), 3);

      ctx.restore();
    }

    // Vertical separator
    ctx.globalAlpha = 0.6;
    ctx.strokeStyle = "rgba(255,255,255,0.15)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
    ctx.globalAlpha = 1;
  });

  // ── Theme palette strip (4px at bottom of section bar) ──
  sections.forEach((section, idx) => {
    const themeName = (section.overrides || {}).theme;
    if (!themeName) return;
    const palette = (state.themePalettes[themeName] || []).filter(_isHexColor);
    if (!palette.length) return;
    const x = timeToX(section.start, W);
    const x2 = timeToX(section.end, W);
    if (x2 < 0 || x > W) return;
    const w = x2 - x;
    const stripH = 4;
    const stripY = H - stripH;
    const sliceW = w / palette.length;
    ctx.save();
    ctx.globalAlpha = 0.9;
    palette.forEach((color, ci) => {
      ctx.fillStyle = color;
      ctx.fillRect(x + ci * sliceW, stripY, sliceW + 0.5, stripH);
    });
    ctx.restore();
  });

  // ── Drop target highlight during drag ──
  if (_highlightedSectionIdx >= 0 && sections[_highlightedSectionIdx]) {
    const hs = sections[_highlightedSectionIdx];
    const hx = timeToX(hs.start, W);
    const hx2 = timeToX(hs.end, W);
    ctx.save();
    ctx.strokeStyle = "#5a9e5a";
    ctx.lineWidth = 3;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(hx, 0, hx2 - hx, H);
    ctx.restore();
  }

  // T056: Low-confidence warning indicators
  sections.forEach((section) => {
    if (section.role_confidence != null && section.role_confidence < 0.5) {
      const x = timeToX(section.start, W);
      const x2 = timeToX(section.end, W);
      if (x2 < 0 || x > W) return;
      const w = x2 - x;
      ctx.save();
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = "#ffaa00";
      ctx.font = "bold 10px monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("\u26A0", x + w - 12, 4);
      ctx.restore();
    }
  });

  // ── Draw accent bars as full-height lines on the waveform ──
  // Each enabled stem's accents are drawn as vertical lines spanning
  // the entire timeline height, colored by stem, opacity by intensity.
  const enabledStems = Object.entries(state.accentLayers)
    .filter(([, on]) => on).map(([s]) => s);

  enabledStems.forEach((stemName) => {
    const color = ACCENT_COLORS[stemName] || STEM_COLORS[stemName] || "#fff";

    sections.forEach((section) => {
      const accents = (section.stems || {}).accents || {};
      const hits = accents[stemName];
      if (!hits || !hits.length) return;

      hits.forEach((hit) => {
        const hx = timeToX(hit.time_ms / 1000, W);
        if (hx < -2 || hx > W + 2) return;
        const intensity = (hit.intensity || 50) / 100;
        ctx.save();
        ctx.globalAlpha = 0.25 + intensity * 0.45;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(hx, 0);
        ctx.lineTo(hx, H);
        ctx.stroke();
        ctx.restore();
      });
    });
  });

  // Register click + wheel + drag handlers once
  if (!_timelineClickBound) {
    canvas.addEventListener("click", onTimelineClick);
    canvas.addEventListener("wheel", onTimelineWheel, { passive: false });
    canvas.addEventListener("mousedown", onBoundaryDragStart);
    canvas.addEventListener("mousemove", onBoundaryHover);
    _timelineClickBound = true;
  }
}

// ── Stem tracks rendering ────────────────────────────────────────────────────

const STEM_TRACK_NAMES = ["drums", "bass", "vocals", "guitar", "piano", "other"];
const STEM_COLORS = {
  drums:  "#e05050",
  bass:   "#e09030",
  vocals: "#50b0e0",
  guitar: "#50e080",
  piano:  "#a050e0",
  other:  "#808080",
};

// Accent bar colors — high-contrast so they stand out against the waveform
const ACCENT_COLORS = {
  drums:  "#ffee44",  // bright yellow — pops against red waveform
  bass:   "#ff6020",  // bright orange
  vocals: "#00e0ff",  // cyan
  guitar: "#40ff90",  // bright green
  piano:  "#d080ff",  // bright purple
  other:  "#ffffff",  // white
};

let _stemTracksClickBound = false;

function renderStemTracks() {
  const story = state.story;
  if (!story) return;

  const canvas = document.getElementById("stem-tracks");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const W = rect.width;
  const H = rect.height;
  if (W === 0 || H === 0) return;

  canvas.width = W * dpr;
  canvas.height = H * dpr;
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);

  const stems = story.stems || {};
  const sampleRate = stems.sample_rate_hz || 2;
  const totalDuration = story.song.duration_seconds || 1;
  const trackH = H / STEM_TRACK_NAMES.length;

  STEM_TRACK_NAMES.forEach((stemName, trackIdx) => {
    const y0 = trackIdx * trackH;
    const stemData = stems[stemName] || {};
    const rms = stemData.rms || [];

    // Track background — alternating subtle shade
    ctx.fillStyle = trackIdx % 2 === 0 ? "rgba(255,255,255,0.02)" : "rgba(0,0,0,0.02)";
    ctx.fillRect(0, y0, W, trackH);

    const color = STEM_COLORS[stemName] || "#888";
    const midY = y0 + trackH * 0.5;
    const amp = trackH * 0.45;

    // Draw real decoded waveform (zoom-aware)
    const stemWf = state.stemWaveforms[stemName];
    if (stemWf && stemWf.mono) {
      const mono = stemWf.mono;
      const sr = mono.length / totalDuration;
      const startSample = Math.floor(state.scrollOffset * sr);
      const endSample = Math.floor((state.scrollOffset + visibleDuration()) * sr);
      const visibleMono = mono.slice(startSample, endSample);
      drawWaveform(ctx, visibleMono, W, y0, trackH, color);
    } else if (rms.length > 0) {
      // Fallback: RMS as mirrored shape (zoom-aware)
      const numPts = rms.length;
      ctx.beginPath();
      ctx.moveTo(timeToX(0, W), midY);
      for (let i = 0; i < numPts; i++) {
        const t = i / sampleRate;
        const x = timeToX(t, W);
        if (x < -10 || x > W + 10) continue;
        const val = Math.min(1, rms[i]);
        ctx.lineTo(x, midY - val * amp);
      }
      for (let i = numPts - 1; i >= 0; i--) {
        const t = i / sampleRate;
        const x = timeToX(t, W);
        if (x < -10 || x > W + 10) continue;
        const val = Math.min(1, rms[i]);
        ctx.lineTo(x, midY + val * amp);
      }
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.globalAlpha = 0.35;
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    // Stem label (draw on top of waveform)
    ctx.fillStyle = color;
    ctx.globalAlpha = 0.8;
    ctx.font = "bold 10px monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText(stemName, 4, y0 + 3);
    ctx.globalAlpha = 1;

    // Horizontal separator
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, y0 + trackH);
    ctx.lineTo(W, y0 + trackH);
    ctx.stroke();
  });

  // Draw section boundary lines across stem tracks (zoom-aware)
  const sections = story.sections || [];
  sections.forEach((section) => {
    const x = timeToX(section.start, W);
    if (x < 0 || x > W) return;
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  });

  // Highlight current section (zoom-aware)
  if (sections[state.currentSectionIdx]) {
    const sec = sections[state.currentSectionIdx];
    const x = timeToX(sec.start, W);
    const x2 = timeToX(sec.end, W);
    const w = x2 - x;
    ctx.fillStyle = "rgba(255,255,255,0.06)";
    ctx.fillRect(x, 0, w, H);
    ctx.strokeStyle = "rgba(255,255,255,0.2)";
    ctx.lineWidth = 1;
    ctx.strokeRect(x, 0, w, H);
  }

  if (!_stemTracksClickBound) {
    canvas.addEventListener("click", onTimelineClick);
    canvas.addEventListener("wheel", onTimelineWheel, { passive: false });
    canvas.addEventListener("mousedown", onBoundaryDragStart);
    canvas.addEventListener("mousemove", onBoundaryHover);
    _stemTracksClickBound = true;
  }
}

// ── Timeline click handler ───────────────────────────────────────────────────

let _suppressNextClick = false;

function onTimelineClick(e) {
  if (_suppressNextClick) { _suppressNextClick = false; return; }

  const story = state.story;
  if (!story || !story.sections) return;

  const canvas = e.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;

  // Don't seek if clicking on a boundary (drag handles it)
  if (_findBoundaryAt(x, rect.width) >= 0) return;

  const clickTime = xToTime(x, rect.width);

  // Select the section under the click
  const idx = story.sections.findIndex(
    (s, i) => clickTime >= s.start && (clickTime < s.end || i === story.sections.length - 1)
  );
  if (idx >= 0) {
    selectSection(idx);
  } else {
    closeFlyout();
  }

  // Seek audio to the exact click position (not section start)
  const player = document.getElementById("player");
  if (player) {
    player.currentTime = Math.max(0, clickTime);
    _updatePlayheadPosition();
  }
}

function onTimelineWheel(e) {
  e.preventDefault();
  if (!state.story) return;

  const canvas = e.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseTime = xToTime(mouseX, rect.width);

  if (e.ctrlKey || e.metaKey || Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
    // Vertical scroll or pinch = zoom
    if (e.deltaY < 0) {
      // Zoom in, keep mouse position stable
      const oldZoom = state.zoomLevel;
      state.zoomLevel = Math.min(16, state.zoomLevel * 1.15);
      // Adjust scroll so the time under the mouse stays at the same pixel
      state.scrollOffset = mouseTime - (mouseX / rect.width) * visibleDuration();
    } else {
      state.zoomLevel = Math.max(1.0, state.zoomLevel / 1.15);
      state.scrollOffset = mouseTime - (mouseX / rect.width) * visibleDuration();
    }
  } else {
    // Horizontal scroll = pan
    const panAmount = visibleDuration() * 0.1 * Math.sign(e.deltaX);
    state.scrollOffset += panAmount;
  }
  clampScroll();
  renderTimeline();
  renderStemTracks();
  _updatePlayheadPosition();
}

// ── Boundary drag ────────────────────────────────────────────────────────────

const BOUNDARY_HIT_PX = 8; // grab zone width in pixels

/** Find the section boundary index closest to a pixel X, within hit zone. */
function _findBoundaryAt(px, canvasW) {
  const story = state.story;
  if (!story || !story.sections) return -1;
  const sections = story.sections;
  // Check interior boundaries only (not first start or last end)
  for (let i = 1; i < sections.length; i++) {
    const bx = timeToX(sections[i].start, canvasW);
    if (Math.abs(px - bx) <= BOUNDARY_HIT_PX) return i;
  }
  return -1;
}

let _dragBoundaryIdx = -1;
let _dragStartX = 0;
let _isDragging = false;

function onBoundaryHover(e) {
  const canvas = e.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const idx = _findBoundaryAt(x, rect.width);
  canvas.style.cursor = idx >= 0 ? "col-resize" : "pointer";
}

function onBoundaryDragStart(e) {
  const canvas = e.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const idx = _findBoundaryAt(x, rect.width);
  if (idx < 0) return; // not near a boundary — let click handler take it

  e.preventDefault();
  e.stopPropagation();
  _dragBoundaryIdx = idx;
  _dragStartX = x;
  _isDragging = true;

  const onMove = (me) => {
    if (!_isDragging) return;
    const mx = me.clientX - rect.left;
    const newTime = xToTime(mx, rect.width);
    const story = state.story;
    if (!story) return;

    const sections = story.sections;
    const prevSection = sections[_dragBoundaryIdx - 1];
    const nextSection = sections[_dragBoundaryIdx];

    // Enforce minimum section duration of 2s
    const minDur = 2.0;
    const minTime = prevSection.start + minDur;
    const maxTime = nextSection.end - minDur;
    const clampedTime = Math.max(minTime, Math.min(maxTime, newTime));

    // Update in-memory (preview only)
    prevSection.end = Math.round(clampedTime * 1000) / 1000;
    prevSection.end_fmt = _fmtSec(clampedTime);
    prevSection.duration = Math.round((prevSection.end - prevSection.start) * 1000) / 1000;
    nextSection.start = prevSection.end;
    nextSection.start_fmt = prevSection.end_fmt;
    nextSection.duration = Math.round((nextSection.end - nextSection.start) * 1000) / 1000;

    renderTimeline();
    renderStemTracks();
  };

  const onUp = (me) => {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    _isDragging = false;

    if (!state.story) return;
    const sections = state.story.sections;
    const section = sections[_dragBoundaryIdx - 1];
    const newEnd = section.end;

    // Persist to server
    fetch("/story/boundary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section_id: section.id, new_end: newEnd }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) { alert("Boundary move failed: " + data.error); return; }
        return reloadStoryFromSession();
      })
      .catch(e => alert("Boundary error: " + e));
  };

  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

function _roleLabel(role) {
  return (role || "unknown").replace(/_/g, " ").replace(/-/g, " ");
}

function _accentSummary(accents) {
  if (!accents) return "—";
  const parts = [];
  for (const [stem, hits] of Object.entries(accents)) {
    if (hits && hits.length > 0) parts.push(`${stem}: ${hits.length}`);
  }
  return parts.length > 0 ? parts.join(", ") : "—";
}

function _fmtSec(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

// ── Flyout panel controls ────────────────────────────────────────────────────

function openFlyout() {
  if (state.flyoutOpen) return;
  state.flyoutOpen = true;
  const flyout = document.getElementById("flyout");
  const main = document.getElementById("main");
  if (flyout) flyout.classList.remove("flyout--closed");
  if (main) main.classList.add("flyout-open");
}

function closeFlyout() {
  if (!state.flyoutOpen) return;
  state.flyoutOpen = false;
  const flyout = document.getElementById("flyout");
  const main = document.getElementById("main");
  if (flyout) flyout.classList.add("flyout--closed");
  if (main) main.classList.remove("flyout-open");
  // Canvas re-render handled by transitionend listener on #main
}

function switchTab(tabName) {
  state.activeTab = tabName;
  // Update tab button active states
  document.querySelectorAll(".flyout-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  // Show/hide content
  document.querySelectorAll(".flyout-content").forEach(el => {
    el.hidden = el.dataset.tabContent !== tabName;
  });
  // Render the active tab content
  renderActiveTab();
}

function renderActiveTab() {
  const story = state.story;
  if (!story || !story.sections) return;
  const section = story.sections[state.currentSectionIdx];
  if (!section) return;

  switch (state.activeTab) {
    case "details":
      renderDetailsTab(state.currentSectionIdx);
      break;
    case "moments":
      renderMomentsTab(section, story.moments || []);
      break;
    case "themes":
      renderThemesTab(section);
      break;
  }
}

// ── Section selection ─────────────────────────────────────────────────────────

function selectSection(idx) {
  const story = state.story;
  if (!story || !story.sections) return;
  if (idx < 0 || idx >= story.sections.length) return;

  state.currentSectionIdx = idx;

  // When zoomed, scroll to keep the selected section visible
  if (state.zoomLevel > 1.0) {
    const sec = story.sections[idx];
    const visDur = visibleDuration();
    const secMid = (sec.start + sec.end) / 2;
    if (secMid < state.scrollOffset || secMid > state.scrollOffset + visDur) {
      state.scrollOffset = secMid - visDur / 2;
      clampScroll();
    }
  }

  renderTimeline();
  renderStemTracks();
  openFlyout();
  renderActiveTab();
}

// ── Details tab (section detail + stems) ─────────────────────────────────────

const STEM_ORDER = ["drums", "bass", "vocals", "guitar", "piano", "other"];

function renderDetailsTab(idx) {
  const section = state.story.sections[idx];
  const el = document.querySelector('.flyout-content[data-tab-content="details"]');
  if (!el || !section) return;

  const role = section.role || "unknown";
  const char = section.character || {};
  const stems = section.stems || {};
  const lighting = section.lighting || {};
  const overrides = section.overrides || {};
  const stemLevels = stems.stem_levels || {};

  const rows = [
    ["Time",        `${section.start_fmt || _fmtSec(section.start)} → ${section.end_fmt || _fmtSec(section.end)}`],
    ["Duration",    `${section.duration ? section.duration.toFixed(1) : "?"}s`],
    ["Confidence",  section.role_confidence != null ? `${(section.role_confidence * 100).toFixed(0)}%` : "—"],
    ["Energy",      `${char.energy_level || "?"} (${char.energy_score ?? "?"})`],
    ["Trajectory",  char.energy_trajectory || "—"],
    ["Texture",     char.texture || "—"],
    ["Brightness",  char.spectral_brightness || "—"],
    ["Tempo",       char.local_tempo_bpm ? `${char.local_tempo_bpm.toFixed(1)} bpm` : "—"],
    ["Vocals",      stems.vocals_active ? "yes" : "no"],
    ["Dominant stem", stems.dominant_stem || "—"],
    ["Drum style",  stems.drum_pattern ? stems.drum_pattern.style.replace(/_/g, " ") : "—"],
    ["Accents",     _accentSummary(stems.accents)],
    ["Active tiers", lighting.active_tiers ? lighting.active_tiers.join(", ") : "—"],
    ["Brightness ceil.", lighting.brightness_ceiling != null ? `${(lighting.brightness_ceiling * 100).toFixed(0)}%` : "—"],
    ["Moments",     `${lighting.moment_count ?? 0} (${lighting.moment_pattern || "isolated"})`],
  ];

  if (overrides.notes) {
    rows.push(["Notes", overrides.notes]);
  }
  if (overrides.is_highlight) {
    rows.push(["Highlight", "\u2b50 yes"]);
  }

  const stemBarsHtml = STEM_ORDER.map(stem => {
    const level = stemLevels[stem] != null ? stemLevels[stem] : 0;
    const pct = Math.round(level * 100);
    const isDominant = stems.dominant_stem === stem;
    return `
      <div class="stem-row" title="${stem}: ${pct}%">
        <span class="stem-name" style="${isDominant ? "color:#e0e0e0;font-weight:bold" : ""}">${stem}</span>
        <div class="stem-bar-bg">
          <div class="stem-bar-fill" data-stem="${stem}" style="width:${pct}%"></div>
        </div>
        <span class="stem-pct">${pct}%</span>
      </div>
    `;
  }).join("");

  el.innerHTML = `
    <h3 data-role="${role}">${_roleLabel(role).toUpperCase()} <small style="font-size:10px;opacity:0.6">${section.id}</small></h3>
    ${rows.map(([label, value]) => `
      <div class="detail-row">
        <span class="detail-label">${label}</span>
        <span class="detail-value">${value}</span>
      </div>
    `).join("")}
    <div class="stems-section">
      <h4>Stem Levels</h4>
      ${stemBarsHtml}
    </div>
  `;

  addSectionEditControls(section);
}

// ── Moments tab ──────────────────────────────────────────────────────────────

function renderMomentsTab(section, allMoments) {
  const el = document.querySelector('.flyout-content[data-tab-content="moments"]');
  if (!el || !section) return;

  const sectionId = section.id;
  const filtered = (allMoments || []).filter(m => m.section_id === sectionId);

  if (!filtered.length) {
    el.innerHTML = '<p class="placeholder">No dramatic moments detected in this section</p>';
    return;
  }

  el.innerHTML = `<div class="moments-section"><h4>Moments</h4>` + filtered.map(moment => {
    const typeBadge = (moment.type || "unknown").replace(/_/g, " ");
    const dismissed = moment.dismissed ? " dismissed" : "";
    const dismissLabel = moment.dismissed ? "Restore" : "Dismiss";
    return `
      <div class="moment-item${dismissed}" data-moment-id="${moment.id}" title="Rank #${moment.rank || "?"}  |  intensity: ${(moment.intensity || 0).toFixed(3)}">
        <span class="moment-time">${moment.time_fmt || _fmtSec(moment.time || 0)}</span>
        <div class="moment-body">
          <span class="moment-badge" data-type="${moment.type || ""}">${typeBadge}</span>
          <div class="moment-desc">${moment.description || ""}</div>
        </div>
        <button class="moment-dismiss-btn" data-id="${moment.id}" data-dismissed="${moment.dismissed ? "true" : "false"}">${dismissLabel}</button>
      </div>
    `;
  }).join("") + `</div>`;

  // Wire dismiss buttons
  el.querySelectorAll(".moment-dismiss-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const mid = btn.dataset.id;
      const currentlyDismissed = btn.dataset.dismissed === "true";
      toggleMomentDismiss(mid, !currentlyDismissed);
    });
  });
}

// ── HTML escaping ────────────────────────────────────────────────────────────

const _ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
function _esc(str) {
  return String(str).replace(/[&<>"']/g, c => _ESC_MAP[c]);
}

function _isHexColor(c) {
  return /^#[0-9a-fA-F]{3,8}$/.test(c);
}

// ── Themes tab ───────────────────────────────────────────────────────────────

async function loadThemes() {
  if (state.themeList.length > 0 || state.themesLoadFailed) return;
  try {
    const resp = await fetch("/themes/api/list");
    if (!resp.ok) {
      state.themesLoadFailed = true;
      return;
    }
    const data = await resp.json();
    state.themeList = data.themes || [];
    state.themePalettes = {};
    state.themeList.forEach(t => {
      state.themePalettes[t.name] = t.palette || [];
    });
  } catch (e) {
    console.warn("Could not load themes:", e);
    state.themesLoadFailed = true;
  }
}

function _recommendThemes(section) {
  if (!state.themeList.length || !section) return [];
  const char = section.character || {};
  const prefs = (state.story && state.story.preferences) || {};
  const occasion = prefs.occasion || "general";

  // Filter by occasion: match occasion or include general themes
  let candidates = state.themeList.filter(t =>
    t.occasion === occasion || t.occasion === "general"
  );

  // Score by mood/energy match
  const energyScore = char.energy_score || 50;
  const isHighEnergy = energyScore > 65;
  const isLowEnergy = energyScore < 35;

  const scored = candidates.map(t => {
    let score = 0;
    // Mood match: map energy to expected moods
    if (isHighEnergy && (t.mood === "aggressive" || t.mood === "structural")) score += 3;
    if (isLowEnergy && (t.mood === "ethereal" || t.mood === "dark")) score += 3;
    // Mid-energy: use texture to differentiate
    if (!isHighEnergy && !isLowEnergy) {
      if (char.texture === "harmonic" && t.mood === "ethereal") score += 2;
      else if (char.texture === "percussive" && t.mood === "structural") score += 2;
      else if (t.mood === "structural" || t.mood === "ethereal") score += 1;
    }
    // Occasion bonus
    if (t.occasion === occasion && occasion !== "general") score += 2;
    // Trajectory bonus
    if (char.energy_trajectory === "rising" && t.mood === "aggressive") score += 1;
    if (char.energy_trajectory === "falling" && t.mood === "ethereal") score += 1;
    if (char.energy_trajectory === "stable" && t.mood === "structural") score += 1;
    return { theme: t, score };
  });

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, 3).map(s => ({
    theme: s.theme,
    reason: _recommendReason(s.theme, char, occasion),
  }));
}

function _recommendReason(theme, char, occasion) {
  const parts = [];
  if (occasion !== "general" && theme.occasion === occasion) {
    parts.push(`matches ${occasion} occasion`);
  }
  const energy = char.energy_score || 50;
  if (energy > 65) parts.push("high-energy section");
  else if (energy < 35) parts.push("low-energy section");
  parts.push(`${theme.mood} mood`);
  return parts.join(", ");
}

function renderThemesTab(section) {
  const el = document.querySelector('.flyout-content[data-tab-content="themes"]');
  if (!el) return;

  if (!state.themeList.length) {
    if (state.themesLoadFailed) {
      el.innerHTML = '<p class="placeholder">Could not load themes. Check that the theme editor is available.</p>';
      return;
    }
    el.innerHTML = '<p class="placeholder">Loading themes...</p>';
    loadThemes().then(() => renderActiveTab());
    return;
  }

  // Recommendations
  const recs = _recommendThemes(section);

  // Filter themes
  const { mood, occasion } = state.themeFilters;
  let filtered = state.themeList;
  if (mood) filtered = filtered.filter(t => t.mood === mood);
  if (occasion) filtered = filtered.filter(t => t.occasion === occasion || t.occasion === "general");

  // Current section's assigned theme
  const assignedTheme = (section.overrides || {}).theme || null;

  let html = "";

  // Filter bar
  html += `<div class="theme-filters">
    <select class="theme-filter-mood">
      <option value="">All moods</option>
      <option value="ethereal"${mood === "ethereal" ? " selected" : ""}>ethereal</option>
      <option value="aggressive"${mood === "aggressive" ? " selected" : ""}>aggressive</option>
      <option value="dark"${mood === "dark" ? " selected" : ""}>dark</option>
      <option value="structural"${mood === "structural" ? " selected" : ""}>structural</option>
    </select>
    <select class="theme-filter-occasion">
      <option value="">All occasions</option>
      <option value="general"${occasion === "general" ? " selected" : ""}>general</option>
      <option value="christmas"${occasion === "christmas" ? " selected" : ""}>christmas</option>
      <option value="halloween"${occasion === "halloween" ? " selected" : ""}>halloween</option>
    </select>
  </div>`;

  // Assigned theme display
  if (assignedTheme) {
    const palette = (state.themePalettes[assignedTheme] || []).filter(_isHexColor);
    html += `<div class="theme-assigned">
      <span class="theme-assigned-label">Assigned:</span>
      <strong>${_esc(assignedTheme)}</strong>
      <span class="theme-palette-inline">${palette.map(c => `<span class="palette-dot" style="background:${c}"></span>`).join("")}</span>
      <button class="theme-remove-btn" data-section-id="${_esc(section.id)}">Remove</button>
    </div>`;
  }

  // Recommended themes section
  if (recs.length > 0 && !mood && !occasion) {
    html += `<div class="theme-rec-header">Recommended</div>`;
    recs.forEach(r => {
      html += _renderThemeCard(r.theme, r.reason, assignedTheme);
    });
    html += `<div class="theme-all-header">All Themes</div>`;
  }

  // All themes (or filtered)
  if (filtered.length === 0) {
    html += '<p class="placeholder">No themes match filters</p>';
  } else {
    filtered.forEach(t => {
      html += _renderThemeCard(t, null, assignedTheme);
    });
  }

  // Bulk action
  html += `<div class="theme-bulk-actions">
    <button class="theme-apply-unassigned-btn" title="Apply the first recommended theme to all sections without a theme">Apply recommended to unassigned</button>
  </div>`;

  el.innerHTML = html;

  // Helper to get the current section (avoids stale closures)
  const currentSection = () => state.story.sections[state.currentSectionIdx];

  // Wire filter handlers
  el.querySelector(".theme-filter-mood").addEventListener("change", (e) => {
    state.themeFilters.mood = e.target.value || null;
    renderActiveTab();
  });
  el.querySelector(".theme-filter-occasion").addEventListener("change", (e) => {
    state.themeFilters.occasion = e.target.value || null;
    renderActiveTab();
  });

  // Wire remove button
  const removeBtn = el.querySelector(".theme-remove-btn");
  if (removeBtn) {
    removeBtn.addEventListener("click", () => {
      const sec = currentSection();
      if (sec) _assignThemeToSection(sec.id, null).then(() => renderActiveTab());
    });
  }

  // Wire "Assign" buttons on cards
  el.querySelectorAll(".theme-assign-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const sec = currentSection();
      if (!sec) return;
      const name = btn.dataset.themeName;
      _assignThemeToSection(sec.id, name).then(() => {
        renderTimeline();
        renderActiveTab();
      });
    });
  });

  // Wire drag-and-drop on theme cards
  el.querySelectorAll(".theme-card").forEach(card => {
    card.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", card.dataset.themeName);
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      _clearDropHighlight();
    });
  });

  // Wire bulk apply
  const bulkBtn = el.querySelector(".theme-apply-unassigned-btn");
  if (bulkBtn) {
    bulkBtn.addEventListener("click", () => {
      _applyToUnassigned(recs.length > 0 ? recs[0].theme.name : (filtered[0] || {}).name);
    });
  }
}

function _renderThemeCard(theme, reason, assignedTheme) {
  const isAssigned = theme.name === assignedTheme;
  const name = _esc(theme.name);
  const mood = _esc(theme.mood || "");
  const intent = _esc(theme.intent || "");
  const palette = (theme.palette || []).filter(_isHexColor).map(c =>
    `<span class="palette-swatch" style="background:${c}"></span>`
  ).join("");
  const accent = (theme.accent_palette || []).filter(_isHexColor).map(c =>
    `<span class="palette-swatch accent" style="background:${c}"></span>`
  ).join("");
  return `
    <div class="theme-card${isAssigned ? " assigned" : ""}" draggable="true" data-theme-name="${name}">
      <div class="theme-card-header">
        <span class="theme-name">${name}</span>
        <span class="theme-mood-badge mood-${mood}">${mood}</span>
      </div>
      ${reason ? `<div class="theme-rec-reason">${_esc(reason)}</div>` : ""}
      <p class="theme-intent">${intent}</p>
      <div class="theme-palette">${palette}</div>
      ${accent ? `<div class="theme-palette accent-row">${accent}</div>` : ""}
      <button class="theme-assign-btn" data-theme-name="${name}">${isAssigned ? "Assigned" : "Assign"}</button>
    </div>
  `;
}

async function _assignThemeToSection(sectionId, themeName) {
  try {
    const resp = await fetch("/story/section/overrides", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section_id: sectionId, overrides: { theme: themeName } }),
    });
    const data = await resp.json();
    if (data.error) { alert("Theme assign failed: " + data.error); return; }
    // Update local state
    const idx = state.story.sections.findIndex(s => s.id === sectionId);
    if (idx >= 0) state.story.sections[idx] = data.section;
  } catch (e) {
    alert("Theme assign error: " + e);
  }
}

async function _applyToUnassigned(themeName) {
  if (!themeName) return;
  const sections = state.story.sections || [];
  const unassigned = sections.filter(s => !(s.overrides || {}).theme);
  if (unassigned.length === 0) { alert("All sections already have themes assigned."); return; }

  await Promise.all(unassigned.map(s => _assignThemeToSection(s.id, themeName)));
  renderTimeline();
  renderActiveTab();
  const n = unassigned.length;
  _showToast(`Applied "${_esc(themeName)}" to ${n} section${n !== 1 ? "s" : ""}`);
}

function _showToast(message) {
  let toast = document.getElementById("flyout-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "flyout-toast";
    toast.style.cssText = "position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#333;color:#e0e0e0;padding:8px 16px;border-radius:4px;font-size:12px;z-index:999;transition:opacity 0.3s;";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.opacity = "1";
  setTimeout(() => { toast.style.opacity = "0"; }, 2500);
}

// ── Drag-and-drop overlay for timeline ──────────────────────────────────────

let _dropOverlay = null;
let _highlightedSectionIdx = -1;

function _ensureDropOverlay() {
  if (_dropOverlay) return _dropOverlay;
  const timelineArea = document.getElementById("timeline-area");
  if (!timelineArea) return null;
  _dropOverlay = document.createElement("div");
  _dropOverlay.id = "drop-overlay";
  _dropOverlay.style.cssText = "position:absolute;top:0;left:0;right:0;bottom:0;z-index:10;display:none;background:rgba(90,158,90,0.05);border:2px dashed rgba(90,158,90,0.3);pointer-events:auto;";
  timelineArea.appendChild(_dropOverlay);

  _dropOverlay.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    const rect = _dropOverlay.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const clickTime = xToTime(x, rect.width);
    const sections = state.story ? state.story.sections : [];
    const idx = sections.findIndex(
      (s, i) => clickTime >= s.start && (clickTime < s.end || i === sections.length - 1)
    );
    if (idx !== _highlightedSectionIdx) {
      _highlightedSectionIdx = idx;
      renderTimeline();
    }
  });

  _dropOverlay.addEventListener("dragleave", () => {
    _clearDropHighlight();
  });

  _dropOverlay.addEventListener("drop", (e) => {
    e.preventDefault();
    const themeName = e.dataTransfer.getData("text/plain");
    if (!themeName || _highlightedSectionIdx < 0) { _clearDropHighlight(); return; }
    const section = state.story.sections[_highlightedSectionIdx];
    _clearDropHighlight();
    _assignThemeToSection(section.id, themeName).then(() => {
      renderTimeline();
      renderActiveTab();
    });
  });

  return _dropOverlay;
}

function _clearDropHighlight() {
  _highlightedSectionIdx = -1;
  if (_dropOverlay) _dropOverlay.style.display = "none";
  renderTimeline();
}

// Show/hide drop overlay when dragging starts/ends
document.addEventListener("dragstart", (e) => {
  if (e.target.closest && e.target.closest(".theme-card")) {
    const overlay = _ensureDropOverlay();
    if (overlay) overlay.style.display = "block";
  }
});
document.addEventListener("dragend", () => {
  if (_dropOverlay) _dropOverlay.style.display = "none";
  _clearDropHighlight();
});

// ── Toolbar wiring ────────────────────────────────────────────────────────────

function wireToolbar() {
  // Zoom controls
  document.getElementById("zoom-in-btn").addEventListener("click", zoomIn);
  document.getElementById("zoom-out-btn").addEventListener("click", zoomOut);
  document.getElementById("zoom-reset-btn").addEventListener("click", zoomReset);

  // Accent layer toggles
  document.getElementById("accents-btn").addEventListener("click", () => {
    const panel = document.getElementById("accent-toggles");
    panel.style.display = panel.style.display === "none" ? "flex" : "none";
  });
  document.querySelectorAll(".accent-toggle input").forEach((cb) => {
    cb.addEventListener("change", () => {
      const stem = cb.closest(".accent-toggle").dataset.stem;
      state.accentLayers[stem] = cb.checked;
      renderTimeline();
      renderStemTracks();
    });
  });

  document.getElementById("save-btn").addEventListener("click", () => {
    fetch("/story/save", { method: "POST" })
      .then(r => r.json())
      .then(d => {
        if (d.error) { alert("Save failed: " + d.error); return; }
        const btn = document.getElementById("save-btn");
        const prev = btn.textContent;
        btn.textContent = "Saved!";
        setTimeout(() => { btn.textContent = prev; }, 1500);
        console.log("Saved to:", d.path);
      })
      .catch(e => alert("Save error: " + e));
  });

  document.getElementById("export-btn").addEventListener("click", () => {
    fetch("/story/export", { method: "POST" })
      .then(r => r.json())
      .then(d => {
        if (d.error) { alert("Export failed: " + d.error); return; }
        alert("Exported to: " + d.path);
        console.log("Exported to:", d.path);
      })
      .catch(e => alert("Export error: " + e));
  });

  // Preferences panel toggle
  const prefBtn = document.getElementById("prefs-btn");
  if (prefBtn) {
    prefBtn.addEventListener("click", () => {
      const panel = document.getElementById("prefs-panel");
      if (panel) panel.style.display = panel.style.display === "none" ? "" : "none";
    });
  }

  // Flyout controls
  const flyoutCloseBtn = document.querySelector(".flyout-close");
  if (flyoutCloseBtn) {
    flyoutCloseBtn.addEventListener("click", closeFlyout);
  }
  document.querySelectorAll(".flyout-tab").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

// ── Section edit controls ─────────────────────────────────────────────────────

const VALID_ROLES = [
  "intro", "verse", "pre_chorus", "chorus", "post_chorus",
  "bridge", "instrumental_break", "climax", "ambient_bridge",
  "outro", "interlude",
];

function addSectionEditControls(section) {
  const el = document.querySelector('.flyout-content[data-tab-content="details"]');
  if (!el || !section) return;

  // Remove any existing edit controls before re-adding
  const existing = el.querySelector(".section-edit-controls");
  if (existing) existing.remove();

  const wrapper = document.createElement("div");
  wrapper.className = "section-edit-controls";

  // Role rename row
  const roleRow = document.createElement("div");
  roleRow.className = "edit-row";
  roleRow.innerHTML = `
    <label class="edit-label">Rename role</label>
    <div class="edit-control">
      <select id="role-select">
        ${VALID_ROLES.map(r =>
          `<option value="${r}"${r === section.role ? " selected" : ""}>${r.replace(/_/g, " ")}</option>`
        ).join("")}
      </select>
      <button id="rename-apply-btn" class="edit-btn">Apply</button>
    </div>
  `;

  // Split at playhead row
  const splitRow = document.createElement("div");
  splitRow.className = "edit-row";
  splitRow.innerHTML = `
    <label class="edit-label">Split here</label>
    <div class="edit-control">
      <span id="split-time-display" class="edit-hint">—</span>
      <button id="split-btn" class="edit-btn">Split at playhead</button>
    </div>
  `;

  // Highlight toggle
  const hlRow = document.createElement("div");
  hlRow.className = "edit-row";
  const isHighlight = (section.overrides || {}).is_highlight;
  hlRow.innerHTML = `
    <label class="edit-label">Highlight</label>
    <div class="edit-control">
      <button id="highlight-btn" class="edit-btn${isHighlight ? " active" : ""}">
        ${isHighlight ? "★ Highlighted" : "☆ Mark as highlight"}
      </button>
    </div>
  `;

  wrapper.appendChild(roleRow);
  wrapper.appendChild(splitRow);
  wrapper.appendChild(hlRow);
  el.appendChild(wrapper);

  // Wire rename button
  document.getElementById("rename-apply-btn").addEventListener("click", () => {
    const newRole = document.getElementById("role-select").value;
    if (!newRole || newRole === section.role) return;
    fetch("/story/rename", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section_id: section.id, new_role: newRole }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) { alert("Rename failed: " + data.error); return; }
        // Update in-place
        const idx = state.story.sections.findIndex(s => s.id === data.section.id);
        if (idx >= 0) state.story.sections[idx] = data.section;
        selectSection(idx >= 0 ? idx : state.currentSectionIdx);
        renderTimeline();
      })
      .catch(e => alert("Rename error: " + e));
  });

  // Wire split button — uses current audio playhead time
  const player = document.getElementById("player");
  const splitTimeDisplay = document.getElementById("split-time-display");

  function updateSplitTimeDisplay() {
    if (player) splitTimeDisplay.textContent = _fmtSec(player.currentTime);
  }
  if (player) {
    player.addEventListener("timeupdate", updateSplitTimeDisplay);
    updateSplitTimeDisplay();
  }

  document.getElementById("split-btn").addEventListener("click", () => {
    const splitTime = player ? player.currentTime : null;
    if (splitTime == null) { alert("No audio loaded"); return; }
    fetch("/story/split", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section_id: section.id, split_time: splitTime }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) { alert("Split failed: " + data.error); return; }
        // Full reload from session — sections list has changed
        return reloadStoryFromSession();
      })
      .catch(e => alert("Split error: " + e));
  });

  // Wire highlight button
  document.getElementById("highlight-btn").addEventListener("click", () => {
    const currentHL = (section.overrides || {}).is_highlight || false;
    fetch("/story/section/highlight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ section_id: section.id, is_highlight: !currentHL }),
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) { alert("Highlight failed: " + data.error); return; }
        const idx = state.story.sections.findIndex(s => s.id === data.section.id);
        if (idx >= 0) state.story.sections[idx] = data.section;
        selectSection(idx >= 0 ? idx : state.currentSectionIdx);
      })
      .catch(e => alert("Highlight error: " + e));
  });
}

// ── Reload full story from session (after structural edits) ───────────────────

async function reloadStoryFromSession() {
  // Fetch the current in-memory story (includes unsaved edits like splits)
  const resp = await fetch("/story/current");
  if (!resp.ok) return;
  state.story = await resp.json();
  renderTimeline();
  renderStemTracks();
  selectSection(Math.min(state.currentSectionIdx, state.story.sections.length - 1));
}

// ── Moment curation ───────────────────────────────────────────────────────────

function toggleMomentDismiss(momentId, dismissed) {
  fetch("/story/moment/dismiss", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ moment_id: momentId, dismissed: dismissed }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) { alert("Dismiss failed: " + data.error); return; }
      const idx = (state.story.moments || []).findIndex(m => m.id === momentId);
      if (idx >= 0) state.story.moments[idx].dismissed = dismissed;
      const section = state.story.sections[state.currentSectionIdx];
      renderMomentsTab(section, state.story.moments);
    })
    .catch(e => alert("Dismiss error: " + e));
}

// ── Preferences panel ─────────────────────────────────────────────────────────

const MOOD_OPTIONS = ["", "ethereal", "structural", "aggressive", "dark"];
const OCCASION_OPTIONS = ["general", "christmas", "halloween"];
const STEM_OPTIONS = ["", "drums", "bass", "vocals", "guitar", "piano", "other"];

function renderPreferencesPanel() {
  const panel = document.getElementById("prefs-panel");
  if (!panel || !state.story) return;

  const prefs = state.story.preferences || {};

  panel.innerHTML = `
    <h4>Song Preferences</h4>
    <div class="pref-form">
      <div class="pref-row">
        <label class="pref-label">Mood</label>
        <select id="pref-mood">
          ${MOOD_OPTIONS.map(o => `<option value="${o}"${o === (prefs.mood || "") ? " selected" : ""}>${o || "(auto)"}</option>`).join("")}
        </select>
      </div>
      <div class="pref-row">
        <label class="pref-label">Occasion</label>
        <select id="pref-occasion">
          ${OCCASION_OPTIONS.map(o => `<option value="${o}"${o === (prefs.occasion || "general") ? " selected" : ""}>${o}</option>`).join("")}
        </select>
      </div>
      <div class="pref-row">
        <label class="pref-label">Focus stem</label>
        <select id="pref-focus-stem">
          ${STEM_OPTIONS.map(o => `<option value="${o}"${o === (prefs.focus_stem || "") ? " selected" : ""}>${o || "(auto)"}</option>`).join("")}
        </select>
      </div>
      <div class="pref-row">
        <label class="pref-label">Intensity</label>
        <input id="pref-intensity" type="range" min="0" max="2" step="0.05"
               value="${prefs.intensity != null ? prefs.intensity : 1.0}"
               style="width:120px">
        <span id="pref-intensity-val">${prefs.intensity != null ? Number(prefs.intensity).toFixed(2) : "1.00"}</span>
      </div>
      <div class="pref-row">
        <label class="pref-label">Theme lock</label>
        <input id="pref-theme" type="text" placeholder="(auto)" value="${prefs.theme || ""}" style="width:120px">
        <a id="pref-theme-edit-link" href="#" title="Edit in Theme Editor" style="margin-left:4px;font-size:11px;color:#5a9e5a;text-decoration:none;${prefs.theme ? '' : 'display:none'}">&#9998;</a>
      </div>
      <div class="pref-row">
        <button id="pref-apply-btn" class="edit-btn">Apply preferences</button>
      </div>
    </div>
  `;

  // Live intensity display
  const intensitySlider = document.getElementById("pref-intensity");
  const intensityVal = document.getElementById("pref-intensity-val");
  intensitySlider.addEventListener("input", () => {
    intensityVal.textContent = Number(intensitySlider.value).toFixed(2);
  });

  // Theme editor deep link
  const themeEditLink = document.getElementById("pref-theme-edit-link");
  const themeInput = document.getElementById("pref-theme");
  if (themeEditLink) {
    themeEditLink.addEventListener("click", (e) => {
      e.preventDefault();
      const themeName = themeInput.value.trim();
      if (themeName) window.open(`/themes?theme=${encodeURIComponent(themeName)}&mode=edit`, "_blank");
    });
    themeInput.addEventListener("input", () => {
      themeEditLink.style.display = themeInput.value.trim() ? "" : "none";
    });
  }

  // Apply button
  document.getElementById("pref-apply-btn").addEventListener("click", () => {
    const payload = {
      mood: document.getElementById("pref-mood").value || null,
      occasion: document.getElementById("pref-occasion").value || "general",
      focus_stem: document.getElementById("pref-focus-stem").value || null,
      intensity: parseFloat(document.getElementById("pref-intensity").value),
      theme: document.getElementById("pref-theme").value.trim() || null,
    };
    fetch("/story/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(r => r.json())
      .then(data => {
        if (data.error) { alert("Preferences failed: " + data.error); return; }
        state.story.preferences = data.preferences;
        console.log("Preferences updated:", data.preferences);
        const btn = document.getElementById("pref-apply-btn");
        if (btn) { btn.textContent = "Applied!"; setTimeout(() => { btn.textContent = "Apply preferences"; }, 1500); }
      })
      .catch(e => alert("Preferences error: " + e));
  });
}

// ── Audio playback ────────────────────────────────────────────────────────────

function wireAudio() {
  const player = document.getElementById("player");
  player.src = "/story/audio";

  const playBtn = document.getElementById("play-btn");
  const timeDisplay = document.getElementById("time-display");
  const playheadBar = document.getElementById("playhead-bar");

  playBtn.addEventListener("click", () => {
    if (player.paused) {
      player.play().catch(e => console.warn("Audio play error:", e));
    } else {
      player.pause();
    }
  });

  player.addEventListener("play", () => {
    state.isPlaying = true;
    playBtn.textContent = "⏸ Pause";
    playheadBar.style.display = "block";
  });

  player.addEventListener("pause", () => {
    state.isPlaying = false;
    playBtn.textContent = "▶ Play";
  });

  player.addEventListener("ended", () => {
    state.isPlaying = false;
    playBtn.textContent = "▶ Play";
  });

  player.addEventListener("timeupdate", () => {
    const currentTime = player.currentTime;
    const duration = player.duration || 1;

    // Update time display
    timeDisplay.textContent = `${_fmtSec(currentTime)} / ${_fmtSec(duration)}`;

    // Move playhead (zoom-aware)
    const canvas = document.getElementById("timeline");
    if (canvas) {
      const rect = canvas.getBoundingClientRect();
      const px = timeToX(currentTime, rect.width);
      playheadBar.style.left = `${px}px`;
      // Hide playhead when it scrolls out of view
      playheadBar.style.display = (px >= 0 && px <= rect.width) ? "block" : "none";

      // Auto-scroll during playback to keep playhead visible
      if (state.isPlaying && state.zoomLevel > 1.0) {
        if (px > rect.width * 0.85 || px < 0) {
          scrollToTime(currentTime);
          renderTimeline();
          renderStemTracks();
        }
      }
    }

    // Auto-select current section
    const story = state.story;
    if (!story || !story.sections) return;

    const idx = story.sections.findIndex(
      (s, i) => currentTime >= s.start &&
        (currentTime < s.end || i === story.sections.length - 1)
    );
    if (idx >= 0 && idx !== state.currentSectionIdx) {
      selectSection(idx);
    }
  });
}

// ── Window resize: re-render timeline ────────────────────────────────────────

window.addEventListener("resize", () => {
  if (state.story) { renderTimeline(); renderStemTracks(); }
});

// Re-render canvases after flyout open animation completes
document.addEventListener("DOMContentLoaded", () => {
  const main = document.getElementById("main");
  if (main) {
    main.addEventListener("transitionend", (e) => {
      if (e.propertyName === "grid-template-columns" && state.story) {
        renderTimeline();
        renderStemTracks();
      }
    });
  }
});

// ── T054: Stale edits banner ──────────────────────────────────────────────────
// Called after loadStory() checks _meta.stale_edits from the load response.

function showStaleBanner(hasStaleEdits) {
  let banner = document.getElementById("stale-banner");
  if (!hasStaleEdits) {
    if (banner) banner.style.display = "none";
    return;
  }
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "stale-banner";
    banner.style.cssText = "background:#7a4a00;color:#ffe0a0;padding:8px 16px;font-size:0.85em;display:flex;align-items:center;gap:12px;";
    banner.innerHTML = `
      <span>⚠ Your previous edits were made against a different version of this story file.</span>
      <button id="stale-discard" style="background:#a06020;border:none;color:#fff;padding:4px 10px;cursor:pointer;border-radius:3px;">Discard old edits</button>
    `;
    const toolbar = document.getElementById("toolbar");
    if (toolbar) toolbar.after(banner);
    document.getElementById("stale-discard").addEventListener("click", () => {
      banner.style.display = "none";
    });
  } else {
    banner.style.display = "flex";
  }
}

// T055: Keyboard shortcuts — prev/next section navigation ─────────────────────

document.addEventListener("keydown", (e) => {
  if (!state.story || !state.story.sections) return;
  // Ignore when typing in an input/textarea
  const tag = document.activeElement && document.activeElement.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return;

  if (e.key === "Escape") {
    closeFlyout();
    return;
  }

  if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
    e.preventDefault();
    const idx = Math.max(0, state.currentSectionIdx - 1);
    if (idx !== state.currentSectionIdx) selectSection(idx);
  } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
    e.preventDefault();
    const idx = Math.min(state.story.sections.length - 1, state.currentSectionIdx + 1);
    if (idx !== state.currentSectionIdx) selectSection(idx);
  } else if (e.key === " ") {
    // Spacebar: play/pause
    e.preventDefault();
    const player = document.getElementById("player");
    if (player) {
      if (player.paused) player.play().catch(() => {});
      else player.pause();
    }
  } else if (e.key === "=" || e.key === "+") {
    e.preventDefault();
    zoomIn();
  } else if (e.key === "-" || e.key === "_") {
    e.preventDefault();
    zoomOut();
  } else if (e.key === "0") {
    e.preventDefault();
    zoomReset();
  }
});

