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
  loadStory(path);
  wireToolbar();
  wireAudio();
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

  const totalDuration = story.song.duration_seconds || 1;
  const sections = story.sections;

  ctx.clearRect(0, 0, W, H);

  // ── Draw waveform from decoded audio PCM data ──
  if (state.waveformData && state.waveformData.mono) {
    drawWaveform(ctx, state.waveformData.mono, W, 0, H, "rgba(255,255,255,0.35)");
  }

  // ── Draw section blocks ──
  sections.forEach((section, idx) => {
    const x = (section.start / totalDuration) * W;
    const w = ((section.end - section.start) / totalDuration) * W;

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
      ctx.rect(x, 0, w, H);
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

  // T056: Low-confidence warning indicators
  sections.forEach((section) => {
    if (section.role_confidence != null && section.role_confidence < 0.5) {
      const x = (section.start / totalDuration) * W;
      const w = ((section.end - section.start) / totalDuration) * W;
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

  // Register click handler once
  if (!_timelineClickBound) {
    canvas.addEventListener("click", onTimelineClick);
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

    // Draw real decoded waveform (pixel-perfect, re-binned to canvas width)
    const stemWf = state.stemWaveforms[stemName];
    if (stemWf && stemWf.mono) {
      drawWaveform(ctx, stemWf.mono, W, y0, trackH, color);
    } else if (rms.length > 0) {
      // Fallback: RMS as mirrored shape
      const numPts = rms.length;
      ctx.beginPath();
      ctx.moveTo(0, midY);
      for (let i = 0; i < numPts; i++) {
        const t = i / sampleRate;
        const x = (t / totalDuration) * W;
        const val = Math.min(1, rms[i]);
        ctx.lineTo(x, midY - val * amp);
      }
      for (let i = numPts - 1; i >= 0; i--) {
        const t = i / sampleRate;
        const x = (t / totalDuration) * W;
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

  // Draw section boundary lines across stem tracks
  const sections = story.sections || [];
  sections.forEach((section) => {
    const x = (section.start / totalDuration) * W;
    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  });

  // Highlight current section
  if (sections[state.currentSectionIdx]) {
    const sec = sections[state.currentSectionIdx];
    const x = (sec.start / totalDuration) * W;
    const w = ((sec.end - sec.start) / totalDuration) * W;
    ctx.fillStyle = "rgba(255,255,255,0.06)";
    ctx.fillRect(x, 0, w, H);
    ctx.strokeStyle = "rgba(255,255,255,0.2)";
    ctx.lineWidth = 1;
    ctx.strokeRect(x, 0, w, H);
  }

  if (!_stemTracksClickBound) {
    canvas.addEventListener("click", onTimelineClick);
    _stemTracksClickBound = true;
  }
}

// ── Timeline click handler ───────────────────────────────────────────────────

function onTimelineClick(e) {
  const story = state.story;
  if (!story || !story.sections) return;

  const canvas = e.currentTarget;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const pct = x / rect.width;
  const totalDuration = story.song.duration_seconds || 1;
  const clickTime = pct * totalDuration;

  const idx = story.sections.findIndex(
    (s, i) => clickTime >= s.start && (clickTime < s.end || i === story.sections.length - 1)
  );
  if (idx >= 0) selectSection(idx);

  // Seek audio to the section start
  const player = document.getElementById("player");
  if (player && story.sections[idx]) {
    player.currentTime = story.sections[idx].start;
  }
}

function _roleLabel(role) {
  return (role || "unknown").replace(/_/g, " ").replace(/-/g, " ");
}

function _fmtSec(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

// ── Section selection ─────────────────────────────────────────────────────────

function selectSection(idx) {
  const story = state.story;
  if (!story || !story.sections) return;
  if (idx < 0 || idx >= story.sections.length) return;

  state.currentSectionIdx = idx;
  renderTimeline();
  renderStemTracks();
  renderSectionDetail(idx);
  renderStemsPanel(story.sections[idx]);
  renderMomentsPanel(story.sections[idx], story.moments || []);
}

// ── Section detail panel ──────────────────────────────────────────────────────

function renderSectionDetail(idx) {
  const section = state.story.sections[idx];
  const el = document.getElementById("section-detail");

  const role = section.role || "unknown";
  const char = section.character || {};
  const stems = section.stems || {};
  const lighting = section.lighting || {};
  const overrides = section.overrides || {};

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
    ["Drum style",  stems.drum_pattern ? stems.drum_pattern.style : "—"],
    ["Active tiers", lighting.active_tiers ? lighting.active_tiers.join(", ") : "—"],
    ["Brightness ceil.", lighting.brightness_ceiling != null ? `${(lighting.brightness_ceiling * 100).toFixed(0)}%` : "—"],
    ["Moments",     `${lighting.moment_count ?? 0} (${lighting.moment_pattern || "isolated"})`],
  ];

  if (overrides.notes) {
    rows.push(["Notes", overrides.notes]);
  }
  if (overrides.is_highlight) {
    rows.push(["Highlight", "⭐ yes"]);
  }

  el.innerHTML = `
    <h3 data-role="${role}">${_roleLabel(role).toUpperCase()} <small style="font-size:10px;opacity:0.6">${section.id}</small></h3>
    ${rows.map(([label, value]) => `
      <div class="detail-row">
        <span class="detail-label">${label}</span>
        <span class="detail-value">${value}</span>
      </div>
    `).join("")}
  `;

  addSectionEditControls(section);
}

// ── Stems panel ───────────────────────────────────────────────────────────────

const STEM_ORDER = ["drums", "bass", "vocals", "guitar", "piano", "other"];

function renderStemsPanel(section) {
  const stems = section.stems || {};
  const stemLevels = stems.stem_levels || {};

  const barsEl = document.getElementById("stems-bars");
  barsEl.innerHTML = STEM_ORDER.map(stem => {
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
}

// ── Moments panel ─────────────────────────────────────────────────────────────

function renderMomentsPanel(section, allMoments) {
  const sectionId = section.id;
  const filtered = (allMoments || []).filter(m => m.section_id === sectionId);

  const listEl = document.getElementById("moments-list");

  if (!filtered.length) {
    listEl.innerHTML = '<p class="placeholder">No moments in this section</p>';
    return;
  }

  listEl.innerHTML = filtered.map(moment => {
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
  }).join("");

  // Wire dismiss buttons
  listEl.querySelectorAll(".moment-dismiss-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const mid = btn.dataset.id;
      const currentlyDismissed = btn.dataset.dismissed === "true";
      toggleMomentDismiss(mid, !currentlyDismissed);
    });
  });
}

// ── Toolbar wiring ────────────────────────────────────────────────────────────

function wireToolbar() {
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
}

// ── Section edit controls ─────────────────────────────────────────────────────

const VALID_ROLES = [
  "intro", "verse", "pre_chorus", "chorus", "post_chorus",
  "bridge", "instrumental_break", "climax", "ambient_bridge",
  "outro", "interlude",
];

function addSectionEditControls(section) {
  const el = document.getElementById("section-detail");
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
  // Re-fetch the current loaded story via /story/load with same path
  const params = new URLSearchParams(window.location.search);
  const path = params.get("path");
  if (!path) return;
  const resp = await fetch(`/story/load?path=${encodeURIComponent(path)}`);
  if (!resp.ok) return;
  state.story = await resp.json();
  renderTimeline();
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
      renderMomentsPanel(section, state.story.moments);
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

    // Move playhead
    const canvas = document.getElementById("timeline");
    if (canvas) {
      const rect = canvas.getBoundingClientRect();
      const pct = currentTime / (state.story ? state.story.song.duration_seconds || duration : duration);
      playheadBar.style.left = `${pct * rect.width}px`;
    }

    // Auto-select current section without re-rendering timeline (avoids flicker)
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
  }
});

