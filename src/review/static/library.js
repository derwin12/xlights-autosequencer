/* library.js — fetch /library + /hierarchy-library, render song tables */
'use strict';

const loadingEl  = document.getElementById('library-loading');
const emptyEl    = document.getElementById('library-empty');
const tableEl    = document.getElementById('library-table');
const tbodyEl    = document.getElementById('library-tbody');

const hierarchySectionEl = document.getElementById('hierarchy-section');
const hierarchyLoadingEl = document.getElementById('hierarchy-loading');
const hierarchyTableEl   = document.getElementById('hierarchy-table');
const hierarchyTbodyEl   = document.getElementById('hierarchy-tbody');

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDuration(ms) {
  const totalS = Math.floor(ms / 1000);
  const m = Math.floor(totalS / 60);
  const s = totalS % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatDate(timestampMs) {
  const d = new Date(timestampMs);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function escapeHtml(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function scoreBar(value) {
  if (value == null) return '<span class="score-val" style="color:#555">—</span>';
  const pct = Math.round(value * 100);
  const cls = value >= 0.75 ? 'score-good' : value >= 0.5 ? 'score-mid' : 'score-low';
  return `<span class="score-bar-wrap"><span class="score-bar-fill ${cls}" style="width:${pct}%"></span></span>` +
         `<span class="score-val">${value.toFixed(2)}</span>`;
}

// ── Hierarchy library ─────────────────────────────────────────────────────────

async function loadHierarchyLibrary() {
  let data;
  try {
    const resp = await fetch('/hierarchy-library');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (err) {
    hierarchyLoadingEl.textContent = `Failed: ${err.message}`;
    return;
  }

  const entries = data.entries || [];
  if (entries.length === 0) {
    hierarchyLoadingEl.style.display = 'none';
    return;
  }

  hierarchySectionEl.style.display = 'block';
  hierarchyLoadingEl.style.display = 'none';
  hierarchyTableEl.style.display = 'table';
  hierarchyTbodyEl.innerHTML = '';

  // Show scan dir in heading
  if (data.scan_dir) {
    const h2 = hierarchySectionEl.querySelector('h2');
    h2.textContent = `Song Library — ${data.scan_dir}`;
  }

  for (const entry of entries) {
    const tr = document.createElement('tr');
    tr.title = entry.source_file || entry.json_path;
    tr.style.cursor = 'pointer';

    tr.innerHTML =
      `<td class="col-filename">${escapeHtml(entry.name)}</td>` +
      `<td>${entry.duration}</td>` +
      `<td style="text-align:right" class="col-bpm">${Math.round(entry.bpm)}</td>` +
      `<td style="text-align:center">${entry.stems}</td>` +
      `<td class="score-cell">${scoreBar(entry.bars)}</td>` +
      `<td class="score-cell">${scoreBar(entry.beats)}</td>` +
      `<td class="score-cell">${scoreBar(entry.sections)}</td>` +
      `<td class="score-cell">${scoreBar(entry.l4)}</td>` +
      `<td class="score-cell col-overall">${scoreBar(entry.overall)}</td>`;

    tr.addEventListener('click', () => openHierarchySong(entry));
    hierarchyTbodyEl.appendChild(tr);
  }
}

async function openHierarchySong(entry) {
  let resp;
  try {
    resp = await fetch('/open-hierarchy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ json_path: entry.json_path }),
    });
  } catch (err) {
    alert(`Failed to open: ${err.message}`);
    return;
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    alert(`Cannot open: ${body.error || resp.status}`);
    return;
  }
  window.location.href = '/';
}

// ── Old library (upload-mode entries) ────────────────────────────────────────

async function loadLibrary() {
  let data;
  try {
    const resp = await fetch('/library');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (err) {
    loadingEl.textContent = `Failed to load library: ${err.message}`;
    return;
  }

  loadingEl.style.display = 'none';

  const entries = data.entries || [];
  if (entries.length === 0) {
    emptyEl.style.display = 'block';
    return;
  }

  tableEl.style.display = 'table';
  tbodyEl.innerHTML = '';

  for (const entry of entries) {
    const tr = document.createElement('tr');
    tr.title = entry.source_file;

    const warnBadge = entry.source_file_exists === false
      ? '<span class="badge-warn" title="Source file not found on disk">missing</span>'
      : '';
    const stemBadge = entry.stem_separation
      ? '<span class="badge-stems">stems</span>'
      : '';
    const phonemesBadge = entry.has_phonemes
      ? '<span class="badge-phonemes badge-phonemes-link" title="Open phoneme review">vocals ↗</span>'
      : '';

    tr.innerHTML =
      `<td class="col-filename">${escapeHtml(entry.filename)}${warnBadge}</td>` +
      `<td>${formatDuration(entry.duration_ms)}</td>` +
      `<td class="col-bpm">${entry.estimated_tempo_bpm.toFixed(1)}</td>` +
      `<td>${entry.track_count}</td>` +
      `<td>${stemBadge}</td>` +
      `<td>${phonemesBadge}</td>` +
      `<td class="col-date">${formatDate(entry.analyzed_at)}</td>`;

    tr.addEventListener('click', (e) => {
      if (e.target.classList.contains('badge-phonemes-link')) {
        e.stopPropagation();
        openPhonemes(entry);
        return;
      }
      openAnalysis(entry);
    });
    tbodyEl.appendChild(tr);
  }
}

async function openPhonemes(entry) {
  const resp = await fetch(
    `/open-from-library?hash=${encodeURIComponent(entry.source_hash)}`,
    { method: 'POST' }
  ).catch(err => { alert(err.message); return null; });
  if (!resp || !resp.ok) return;
  window.location.href = '/phonemes-view';
}

async function openAnalysis(entry) {
  const resp = await fetch(
    `/open-from-library?hash=${encodeURIComponent(entry.source_hash)}`,
    { method: 'POST' }
  ).catch(err => { alert(err.message); return null; });
  if (!resp || !resp.ok) return;
  window.location.href = '/';
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadHierarchyLibrary();
loadLibrary();
