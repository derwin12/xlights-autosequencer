/* library.js — fetch /library, render song table, navigate to timeline */
'use strict';

const loadingEl  = document.getElementById('library-loading');
const emptyEl    = document.getElementById('library-empty');
const tableEl    = document.getElementById('library-table');
const tbodyEl    = document.getElementById('library-tbody');

// ── Helpers ──────────────────────────────────────────────────────────────────

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
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Library fetch & render ────────────────────────────────────────────────────

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

    tr.innerHTML =
      `<td class="col-filename">${escapeHtml(entry.filename)}${warnBadge}</td>` +
      `<td>${formatDuration(entry.duration_ms)}</td>` +
      `<td class="col-bpm">${entry.estimated_tempo_bpm.toFixed(1)}</td>` +
      `<td>${entry.track_count}</td>` +
      `<td>${stemBadge}</td>` +
      `<td class="col-date">${formatDate(entry.analyzed_at)}</td>`;

    tr.addEventListener('click', () => openAnalysis(entry));
    tbodyEl.appendChild(tr);
  }
}

// ── Open analysis from library ────────────────────────────────────────────────
//
// POST /open-from-library?hash=<md5> tells the server to set the active
// analysis to this library entry.  The server marks the job as "done" so
// GET / serves index.html and GET /analysis returns the correct data.
// app.js then loads normally without any changes.

async function openAnalysis(entry) {
  let resp;
  try {
    resp = await fetch(
      `/open-from-library?hash=${encodeURIComponent(entry.source_hash)}`,
      { method: 'POST' }
    );
  } catch (err) {
    alert(`Failed to open analysis: ${err.message}`);
    return;
  }

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    alert(`Cannot open analysis: ${body.error || resp.status}`);
    return;
  }

  // Server has set active analysis — navigate to timeline
  window.location.href = '/';
}

// ── Init ──────────────────────────────────────────────────────────────────────

loadLibrary();
