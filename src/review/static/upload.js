/* upload.js — drag-drop upload, SSE progress, auto-navigate */
'use strict';

const dropZone   = document.getElementById('drop-zone');
const fileInput  = document.getElementById('file-input');
const btnBrowse  = document.getElementById('btn-browse');
const fileNameEl = document.getElementById('file-name');
const fileErrorEl= document.getElementById('file-error');
const chkVamp     = document.getElementById('chk-vamp');
const chkMadmom   = document.getElementById('chk-madmom');
const chkStems     = document.getElementById('chk-stems');
const chkPhonemes  = document.getElementById('chk-phonemes');
const chkStructure = document.getElementById('chk-structure');

// Phonemes requires stems — keep them in sync
if (chkPhonemes) {
  chkPhonemes.addEventListener('change', () => {
    if (chkPhonemes.checked && chkStems) {
      chkStems.checked = true;
    }
  });
}
if (chkStems) {
  chkStems.addEventListener('change', () => {
    if (!chkStems.checked && chkPhonemes) {
      chkPhonemes.checked = false;
    }
  });
}
const btnAnalyze = document.getElementById('btn-analyze');
const uploadForm = document.getElementById('upload-form');
const progressSection = document.getElementById('progress-section');
const statusLine = document.getElementById('status-line');
const progressBar= document.getElementById('progress-bar');
const algoList   = document.getElementById('algo-list');
const errorBlock = document.getElementById('error-block');
const errorMsg   = document.getElementById('error-message');
const btnRetry   = document.getElementById('btn-retry');

let selectedFile = null;
let totalAlgos   = 0;
let doneCount    = 0;

// ── File selection helpers ─────────────────────────────────────────────────

function isValidMp3(file) {
  return file && file.name.toLowerCase().endsWith('.mp3');
}

function setFile(file) {
  fileErrorEl.textContent = '';
  if (!isValidMp3(file)) {
    fileErrorEl.textContent = 'Only .mp3 files are accepted.';
    selectedFile = null;
    fileNameEl.textContent = '';
    btnAnalyze.disabled = true;
    return;
  }
  selectedFile = file;
  fileNameEl.textContent = file.name;
  btnAnalyze.disabled = false;
}

// ── Drag-and-drop ──────────────────────────────────────────────────────────

// Prevent Chrome from opening the file in a new tab when dropped anywhere
document.addEventListener('dragover', (e) => e.preventDefault());
document.addEventListener('drop',     (e) => e.preventDefault());

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', (e) => {
  if (!dropZone.contains(e.relatedTarget)) {
    dropZone.classList.remove('drag-over');
  }
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  setFile(file);
});


btnBrowse.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
  setFile(fileInput.files[0]);
});

// ── Analyze button ─────────────────────────────────────────────────────────

btnAnalyze.addEventListener('click', async () => {
  if (!selectedFile) return;

  const formData = new FormData();
  formData.append('mp3', selectedFile, selectedFile.name);
  formData.append('vamp',     chkVamp.checked             ? 'true' : 'false');
  formData.append('madmom',   chkMadmom.checked           ? 'true' : 'false');
  formData.append('stems',     chkStems     && chkStems.checked     ? 'true' : 'false');
  formData.append('phonemes',  chkPhonemes  && chkPhonemes.checked  ? 'true' : 'false');
  formData.append('structure', chkStructure && chkStructure.checked ? 'true' : 'false');

  // Update status hint
  const families = [];
  if (chkVamp.checked)   families.push('Vamp');
  if (chkMadmom.checked) families.push('madmom');
  families.push('librosa');
  const familyStr = families.join(' + ');

  btnAnalyze.disabled = true;

  let resp;
  try {
    resp = await fetch('/upload', { method: 'POST', body: formData });
  } catch (err) {
    fileErrorEl.textContent = `Upload failed: ${err.message}`;
    btnAnalyze.disabled = false;
    return;
  }

  if (resp.status === 409) {
    fileErrorEl.textContent = 'Analysis already running. Please wait.';
    btnAnalyze.disabled = false;
    return;
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    fileErrorEl.textContent = body.error || `Upload failed (${resp.status})`;
    btnAnalyze.disabled = false;
    return;
  }

  const data = await resp.json();
  totalAlgos = data.total || 0;

  showProgress(familyStr);
  startProgressStream();
});

// ── Progress UI ────────────────────────────────────────────────────────────

function showProgress(familyStr) {
  uploadForm.style.display = 'none';
  progressSection.style.display = 'flex';
  doneCount = 0;
  algoList.innerHTML = '';
  errorBlock.style.display = 'none';
  updateStatusLine(familyStr);
}

function updateStatusLine(context) {
  if (totalAlgos > 0) {
    statusLine.textContent = `Running ${context || 'algorithms'}… (${doneCount} / ${totalAlgos})`;
  } else {
    statusLine.textContent = `Running ${context || 'algorithms'}…`;
  }
}

function startProgressStream() {
  const evtSource = new EventSource('/progress');

  evtSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);

    if (msg.done) {
      evtSource.close();
      statusLine.textContent = 'Done! Navigating to timeline…';
      progressBar.style.width = '100%';
      setTimeout(() => { window.location.href = '/'; }, 500);
      return;
    }

    if (msg.error) {
      evtSource.close();
      statusLine.textContent = 'Analysis failed.';
      errorMsg.textContent = msg.error;
      errorBlock.style.display = 'flex';
      return;
    }

    if (msg.warning) {
      const row = document.createElement('div');
      row.className = 'algo-row';
      row.innerHTML = `<span class="err">⚠</span><span>${msg.warning}</span>`;
      algoList.appendChild(row);
      algoList.scrollTop = algoList.scrollHeight;
      return;
    }

    // Progress event
    doneCount += 1;
    if (msg.total) totalAlgos = msg.total;
    const pct = totalAlgos > 0 ? Math.round(doneCount / totalAlgos * 100) : 0;
    progressBar.style.width = `${pct}%`;
    statusLine.textContent = `Analyzing… (${doneCount} / ${totalAlgos})`;

    const ok = msg.mark_count > 0;
    const row = document.createElement('div');
    row.className = 'algo-row';
    row.innerHTML =
      `<span class="${ok ? 'ok' : 'err'}">${ok ? '✓' : '✗'}</span>` +
      `<span>${msg.name}</span>` +
      `<span class="marks">(${msg.mark_count} marks)</span>`;
    algoList.appendChild(row);
    algoList.scrollTop = algoList.scrollHeight;
  };

  evtSource.onerror = () => {
    evtSource.close();
    statusLine.textContent = 'Connection lost.';
    errorMsg.textContent = 'Lost connection to server. The analysis may still be running.';
    errorBlock.style.display = 'flex';
  };
}

// ── Retry button ───────────────────────────────────────────────────────────

btnRetry.addEventListener('click', () => window.location.reload());

// ── Reconnect on page load ─────────────────────────────────────────────────

async function checkJobStatus() {
  let status;
  try {
    const resp = await fetch('/job-status');
    status = await resp.json();
  } catch {
    return; // server not ready yet — show upload form normally
  }

  if (status.status === 'running') {
    totalAlgos = status.total || 0;
    doneCount  = status.events_count || 0;
    showProgress('algorithms');
    startProgressStream();
  } else if (status.status === 'done') {
    // Only auto-navigate to the timeline when not already on the library view
    if (window.location.pathname !== '/library-view') {
      window.location.reload();
    }
  }
  // idle → show upload form normally (already visible)
}

checkJobStatus();
