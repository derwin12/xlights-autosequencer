'use strict';

// song-workspace.js — spec 046 tab shell + wiring for Analysis and Generate.

(function () {
  // --- Source hash extracted from URL path (/song/<hash>) -----------------
  const pathParts = location.pathname.split('/').filter(Boolean);
  const sourceHash = pathParts[pathParts.length - 1] || '';

  // --- Per-tab mount guards (SC-005: fetch each bundle at most once) -----
  const mounted = {
    analysis: false,
    brief: false,
    preview: false,
    generate: false,
  };

  const VALID_TABS = ['analysis', 'brief', 'preview', 'generate'];

  function fmtDurationMs(ms) {
    if (!ms || ms <= 0) return '';
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  function fmtTimestamp(epochSec) {
    if (!epochSec) return '';
    const d = new Date(epochSec * 1000);
    return d.toLocaleString();
  }

  // --- Tab switching -----------------------------------------------------
  function activateTab(tabId) {
    if (!VALID_TABS.includes(tabId)) tabId = 'analysis';

    document.querySelectorAll('.workspace-tab').forEach(btn => {
      const isActive = btn.dataset.tab === tabId;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    document.querySelectorAll('.workspace-panel').forEach(panel => {
      panel.hidden = panel.id !== 'panel-' + tabId;
    });

    // URL fragment: replaceState (NOT pushState) — browser Back exits the
    // workspace instead of cycling through tabs (edge case in spec).
    history.replaceState(null, '', '#' + tabId);

    // Mount-on-first-activation for tabs that need deferred init.
    if (tabId === 'analysis' && !mounted.analysis) {
      mountAnalysisTab();
      mounted.analysis = true;
    }
    if (tabId === 'brief' && !mounted.brief) {
      mountBriefTabInWorkspace();
      mounted.brief = true;
    }
    if (tabId === 'generate' && !mounted.generate) {
      mountGenerateTab();
      mounted.generate = true;
    }
    if (tabId === 'preview' && !mounted.preview) {
      mountPreviewTab();
      mounted.preview = true;
    }
  }

  function bindTabClicks() {
    document.querySelectorAll('.workspace-tab').forEach(btn => {
      btn.addEventListener('click', () => activateTab(btn.dataset.tab));
    });
  }

  // --- Header population from /library -----------------------------------
  async function populateHeader() {
    try {
      const resp = await fetch('/library');
      if (!resp.ok) return;
      const data = await resp.json();
      const entry = (data.entries || []).find(e => e.source_hash === sourceHash);
      if (!entry) return;

      const titleEl = document.getElementById('song-title');
      const durationEl = document.getElementById('song-duration');
      const statusEl = document.getElementById('song-analysis-status');

      titleEl.textContent = entry.title || entry.filename || sourceHash;
      const durTxt = fmtDurationMs(entry.duration_ms);
      durationEl.textContent = durTxt ? `Duration: ${durTxt}` : '';

      const analysisOk = entry.analysis_exists !== false;
      if (!analysisOk) {
        statusEl.textContent = 'Analysis missing';
        statusEl.style.color = '#d55';
      } else if (entry.is_stale) {
        statusEl.textContent = 'Analysis stale';
        statusEl.style.color = '#da4';
      } else {
        statusEl.textContent = 'Analyzed';
      }

      // Spec 046 edge case: analysis missing -> Analysis tab empty state.
      if (!analysisOk) {
        window.__xoAnalysisMissing = true;
      }
    } catch (err) {
      // Non-fatal — header just stays with its placeholder values.
    }
  }

  // --- Analysis tab: lazy-load app.js + call createTimeline() ------------
  //
  // Spec 046 wraps the /timeline UI in a createTimeline(rootEl, hashParam)
  // factory (see app.js). Since the workspace doesn't ship a full HTML page,
  // we build the timeline's expected subtree here and hand it to the factory.
  function buildTimelineSubtree() {
    const root = document.createElement('div');
    root.id = 'timeline-root';
    root.dataset.xoMounted = 'true'; // suppresses the app.js auto-mount guard
    root.innerHTML = [
      '<div id="toolbar">',
      '  <button id="btn-play" aria-label="Play or pause audio">Play</button>',
      '  <span id="time-display" aria-live="polite">0:00 / 0:00</span>',
      '  <div id="beat-flash" title="Beat indicator" role="presentation"></div>',
      '  <button id="btn-prev" aria-label="Focus previous track">&#9664; Prev</button>',
      '  <button id="btn-next" aria-label="Focus next track">Next &#9654;</button>',
      '  <button id="btn-clear" aria-label="Clear track focus">Clear Focus</button>',
      '  <span id="focus-label" aria-live="polite"></span>',
      '  <span id="selected-count" aria-live="polite"></span>',
      '  <span class="toolbar-sep" role="separator"></span>',
      '  <button id="btn-zoom-out" title="Zoom out (Ctrl+-)" aria-label="Zoom out">&#8722;</button>',
      '  <span id="zoom-level" aria-live="polite">100%</span>',
      '  <button id="btn-zoom-in" title="Zoom in (Ctrl++)" aria-label="Zoom in">+</button>',
      '  <button id="btn-phonemes" disabled title="No phoneme data — re-analyze with Phonemes enabled" aria-label="View phoneme tracks">Phonemes</button>',
      '  <button id="btn-legend" title="Show/hide section color legend">Legend</button>',
      '  <button id="btn-export" disabled>Export Selection</button>',
      '</div>',
      '<div id="main">',
      '  <div id="panel">',
      '    <div id="stem-filter-bar"></div>',
      '    <div id="track-list"></div>',
      '  </div>',
      '  <div id="canvas-wrap">',
      '    <canvas id="bg-canvas"></canvas>',
      '    <canvas id="fg-canvas"></canvas>',
      '  </div>',
      '</div>',
      '<audio id="player" src="/audio" preload="auto"></audio>',
      '<div id="legend-panel"></div>',
      '<div id="status">Loading analysis...</div>',
    ].join('\n');
    return root;
  }

  function mountAnalysisTab() {
    const panel = document.getElementById('panel-analysis');
    if (!panel) return;

    if (window.__xoAnalysisMissing) {
      panel.innerHTML =
        '<div class="workspace-empty-state">' +
        'No analysis available — re-run analysis to populate this tab.' +
        '</div>';
      return;
    }

    // Also link style.css for the timeline — the workspace page doesn't
    // include it by default. Idempotent if already present.
    if (!document.querySelector('link[data-xo-style]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/style.css';
      link.dataset.xoStyle = 'true';
      document.head.appendChild(link);
    }

    const mountRoot = buildTimelineSubtree();
    panel.appendChild(mountRoot);

    const run = () => {
      if (typeof window.createTimeline === 'function') {
        window.createTimeline({ rootEl: mountRoot, hashParam: sourceHash });
      }
    };

    if (typeof window.createTimeline === 'function') {
      run();
      return;
    }

    // Lazy inject /app.js (the timeline factory) if not already loaded.
    const existing = document.querySelector('script[data-xo-timeline-script]');
    if (existing) {
      existing.addEventListener('load', run, { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = '/app.js';
    script.dataset.xoTimelineScript = 'true';
    script.addEventListener('load', run, { once: true });
    document.head.appendChild(script);
  }

  // --- Generate tab: history fetch + re-attach + polling -----------------
  const GENERATE_POLL_MS = 1500;
  let generatePollTimer = null;
  let generateActiveJobId = null;

  async function mountGenerateTab() {
    await applyLayoutGate();
    await loadHistoryAndMaybeReattach();
    bindGenerateButton();
  }

  async function applyLayoutGate() {
    const banner = document.getElementById('generate-layout-banner');
    const btn = document.getElementById('btn-generate');
    try {
      const resp = await fetch('/generate/settings');
      const data = await resp.json();
      if (data.layout_configured) {
        banner.hidden = true;
        btn.disabled = false;
        btn.title = '';
      } else {
        banner.hidden = false;
        banner.innerHTML =
          'Layout setup is required before generating. ' +
          '<a href="/grouper">Configure layout groups</a>.';
        btn.disabled = true;
        btn.title = 'Layout not configured — set up layout groups first.';
      }
    } catch (err) {
      banner.hidden = false;
      banner.textContent = 'Could not verify layout setup.';
      btn.disabled = true;
    }
  }

  async function loadHistoryAndMaybeReattach() {
    if (!sourceHash) return;
    try {
      const resp = await fetch(`/generate/${encodeURIComponent(sourceHash)}/history`);
      if (!resp.ok) return;
      const data = await resp.json();
      const jobs = data.jobs || [];

      renderHistory(jobs);

      const running = jobs.find(j => j.status === 'pending' || j.status === 'running');
      if (running) {
        attachToJob(running.job_id);
      }
    } catch (err) {
      // Non-fatal.
    }
  }

  function renderHistory(jobs) {
    const list = document.getElementById('generate-history');
    list.innerHTML = '';

    const completed = jobs.filter(j => j.status === 'complete');
    if (completed.length === 0) {
      const empty = document.createElement('li');
      empty.className = 'history-meta';
      empty.textContent = 'No previous renders yet.';
      list.appendChild(empty);
      return;
    }

    completed.forEach(j => {
      const li = document.createElement('li');
      li.className = 'status-' + j.status;
      const summary = `${j.genre || 'pop'} / ${j.occasion || 'general'} / ${j.transition_mode || 'subtle'}`;
      li.innerHTML =
        `<span class="history-meta">${fmtTimestamp(j.created_at)} — ${summary}</span>` +
        (j.download_url
          ? ` <a href="${j.download_url}">Download</a>`
          : '');
      list.appendChild(li);
    });
  }

  function bindGenerateButton() {
    const btn = document.getElementById('btn-generate');
    btn.addEventListener('click', startGeneration);
  }

  async function startGeneration() {
    const btn = document.getElementById('btn-generate');
    const errorBox = document.getElementById('generate-error');
    errorBox.hidden = true;

    btn.disabled = true;
    showProgress('Starting…');

    try {
      const resp = await fetch(`/generate/${encodeURIComponent(sourceHash)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),  // use defaults per FR-014
      });
      const data = await resp.json();
      if (!resp.ok) {
        showError(data.error || 'Failed to start generation');
        btn.disabled = false;
        hideProgress();
        return;
      }
      attachToJob(data.job_id);
    } catch (err) {
      showError(String(err));
      btn.disabled = false;
      hideProgress();
    }
  }

  function attachToJob(jobId) {
    generateActiveJobId = jobId;
    const btn = document.getElementById('btn-generate');
    btn.disabled = true;
    showProgress('Running…');
    hideDownload();
    clearGeneratePoll();
    generatePollTimer = setInterval(pollJobStatus, GENERATE_POLL_MS);
    pollJobStatus();
  }

  async function pollJobStatus() {
    if (!generateActiveJobId) return;
    try {
      const resp = await fetch(
        `/generate/${encodeURIComponent(sourceHash)}/status?job_id=${encodeURIComponent(generateActiveJobId)}`
      );
      const data = await resp.json();

      if (data.status === 'complete') {
        clearGeneratePoll();
        hideProgress();
        showDownload(data.job_id);
        document.getElementById('btn-generate').disabled = false;
        // Refresh history so the new entry shows up.
        loadHistoryForRefresh();
      } else if (data.status === 'failed') {
        clearGeneratePoll();
        hideProgress();
        showError(data.error || 'Generation failed.');
        document.getElementById('btn-generate').disabled = false;
      } else {
        showProgress(data.status === 'pending' ? 'Queued…' : 'Running…');
      }
    } catch (err) {
      // keep polling — transient network error.
    }
  }

  async function loadHistoryForRefresh() {
    try {
      const resp = await fetch(`/generate/${encodeURIComponent(sourceHash)}/history`);
      if (!resp.ok) return;
      const data = await resp.json();
      renderHistory(data.jobs || []);
    } catch (err) {
      /* ignore */
    }
  }

  function clearGeneratePoll() {
    if (generatePollTimer) {
      clearInterval(generatePollTimer);
      generatePollTimer = null;
    }
  }

  function showProgress(label) {
    document.getElementById('generate-progress').hidden = false;
    document.getElementById('generate-stage').textContent = label;
  }

  function hideProgress() {
    document.getElementById('generate-progress').hidden = true;
  }

  function showDownload(jobId) {
    const box = document.getElementById('generate-download');
    box.hidden = false;
    box.innerHTML =
      `<a href="/generate/${encodeURIComponent(sourceHash)}/download/${encodeURIComponent(jobId)}">` +
      'Download .xsq</a>';
  }

  function hideDownload() {
    document.getElementById('generate-download').hidden = true;
  }

  function showError(msg) {
    const box = document.getElementById('generate-error');
    box.hidden = false;
    box.textContent = msg;
  }

  // --- Brief tab: lazy-load brief-tab.js + brief-tab.css, then mount -----
  //
  // brief-presets.js is loaded first (it attaches BRIEF_PRESETS to window).
  // brief-tab.js is loaded second (it attaches mountBriefTab to window).
  // brief-tab.css is injected once.

  async function mountBriefTabInWorkspace() {
    const panel = document.getElementById('panel-brief');
    if (!panel) return;

    // Edge case: analysis missing — Brief tab shows disabled state (spec §edge-cases §1)
    if (window.__xoAnalysisMissing) {
      panel.innerHTML =
        '<div class="brief-disabled-banner">' +
        'Analysis required — run Analysis first before editing the Brief.' +
        '</div>';
      // Disable the Brief tab button
      const tabBtn = document.querySelector('[data-tab="brief"]');
      if (tabBtn) {
        tabBtn.disabled = true;
        tabBtn.title = 'Run analysis first to enable the Brief tab.';
      }
      return;
    }

    // Inject CSS once
    if (!document.querySelector('link[data-xo-brief-css]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/brief-tab.css';
      link.dataset.xoBriefCss = 'true';
      document.head.appendChild(link);
    }

    // Load brief-tab.html fragment into the panel
    try {
      const resp = await fetch('/brief-tab.html');
      if (resp.ok) {
        panel.innerHTML = await resp.text();
      }
    } catch (e) {
      // HTML may already be inline from server-side render
    }

    // Helper to load a script and resolve when loaded
    function _loadScript(src, dataAttr) {
      return new Promise((resolve) => {
        if (document.querySelector(`script[${dataAttr}]`)) {
          resolve();
          return;
        }
        const s = document.createElement('script');
        s.src = src;
        s.setAttribute(dataAttr, 'true');
        s.addEventListener('load', resolve, { once: true });
        s.addEventListener('error', resolve, { once: true }); // degrade gracefully
        document.head.appendChild(s);
      });
    }

    await _loadScript('/brief-presets.js', 'data-xo-brief-presets');
    await _loadScript('/brief-tab.js', 'data-xo-brief-tab');

    if (typeof window.mountBriefTab === 'function') {
      window.mountBriefTab(panel, sourceHash);
    }
  }

  // --- Brief tab badge (dirty/clean indicator) ---------------------------

  function _setBriefTabBadge(dirty) {
    const tabBtn = document.querySelector('[data-tab="brief"]');
    if (!tabBtn) return;
    if (dirty) {
      tabBtn.dataset.briefDirty = 'true';
      if (!tabBtn.querySelector('.brief-dirty-dot')) {
        const dot = document.createElement('span');
        dot.className = 'brief-dirty-dot';
        dot.setAttribute('aria-label', 'Unsaved changes');
        tabBtn.appendChild(dot);
      }
    } else {
      delete tabBtn.dataset.briefDirty;
      const dot = tabBtn.querySelector('.brief-dirty-dot');
      if (dot) dot.remove();
    }
  }

  document.addEventListener('brief:dirty', () => _setBriefTabBadge(true));
  document.addEventListener('brief:clean', () => _setBriefTabBadge(false));

  // Allow brief-tab.js to switch the workspace to a different tab
  document.addEventListener('workspace:activateTab', (e) => {
    if (e.detail && e.detail.tab) activateTab(e.detail.tab);
  });

  // --- Preview tab --------------------------------------------------------
  // US5 (in-browser canvas preview) is out of scope for spec 049 and will be
  // picked up in a follow-up spec. The download path is the authoritative P1.

  const PREVIEW_POLL_MS = 500;
  let previewPollTimer = null;
  let previewActiveJobId = null;
  // Track whether the current preview result is stale (Brief changed since last run)
  let previewResultIsStale = false;

  // Populate the section dropdown from analysis hierarchy.
  async function populatePreviewSections() {
    const select = document.getElementById('preview-section-select');
    const btn = document.getElementById('btn-preview');
    if (!select) return;

    try {
      // Load analysis for the song
      const resp = await fetch(`/api/analysis/${encodeURIComponent(sourceHash)}`);
      let sections = [];
      let pickerDefault = 0;

      if (resp.ok) {
        const data = await resp.json();
        const hierarchy = data.hierarchy || data;
        const rawSections = hierarchy.sections || [];

        if (rawSections.length === 0) {
          select.innerHTML = '<option value="" disabled>No sections available</option>';
          btn.disabled = true;
          btn.title = 'No sections available for this song.';
          return;
        }

        // Resolve auto-selected default via server (null section_index)
        // We derive it client-side from picker logic for display purposes.
        sections = rawSections;
        // Build section options
        select.innerHTML = '';
        sections.forEach((sec, i) => {
          const startStr = fmtDurationMs(sec.time_ms !== undefined ? sec.time_ms * 1000 : (sec.start_ms || 0));
          const endStr = fmtDurationMs(sec.end_ms || 0);
          const label = sec.label || sec.role || `Section ${i}`;
          const energy = sec.energy_score !== undefined ? sec.energy_score : '';
          const energyStr = energy !== '' ? ` — energy ${energy}` : '';
          const opt = document.createElement('option');
          opt.value = String(i);
          opt.textContent = `${label} — ${startStr}–${endStr}${energyStr}`;
          select.appendChild(opt);
        });

        // Select index 0 by default; the POST with section_index=null will auto-pick
        select.value = '0';
        btn.disabled = false;
        btn.title = '';
      } else {
        // Analysis fetch failed — use placeholder
        select.innerHTML = '<option value="">Auto-select (default)</option>';
        btn.disabled = false;
      }
    } catch (err) {
      select.innerHTML = '<option value="">Auto-select (default)</option>';
      btn.disabled = false;
    }
  }

  function mountPreviewTab() {
    populatePreviewSections();
    bindPreviewButton();
  }

  function bindPreviewButton() {
    const btn = document.getElementById('btn-preview');
    if (btn) btn.addEventListener('click', startPreview);
    const reBtn = document.getElementById('btn-repreview');
    if (reBtn) reBtn.addEventListener('click', startPreview);
  }

  async function startPreview() {
    const select = document.getElementById('preview-section-select');
    const sectionIndex = select && select.value !== '' ? parseInt(select.value, 10) : null;

    // Clear stale state
    previewResultIsStale = false;
    const staleBanner = document.getElementById('preview-stale-banner');
    if (staleBanner) staleBanner.hidden = true;

    // Hide previous result and error
    const resultPane = document.getElementById('preview-result');
    const errorPane = document.getElementById('preview-error');
    const dlLink = document.getElementById('preview-download-link');
    if (resultPane) resultPane.hidden = true;
    if (errorPane) errorPane.hidden = true;
    if (dlLink) { dlLink.hidden = true; dlLink.href = '#'; }

    // Show progress
    const progressEl = document.getElementById('preview-progress');
    if (progressEl) progressEl.hidden = false;

    // Gather brief (attempt to read from Brief tab form fields if present)
    const brief = _collectBriefValues();

    try {
      const resp = await fetch(`/api/song/${encodeURIComponent(sourceHash)}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section_index: sectionIndex,
          brief: brief,
        }),
      });
      const data = await resp.json();

      if (!resp.ok) {
        if (progressEl) progressEl.hidden = true;
        showPreviewError(data.error || 'Failed to start preview');
        return;
      }

      // Cache hit — result already available
      if (data.cached) {
        if (progressEl) progressEl.hidden = true;
        renderPreviewResult(data.result);
        return;
      }

      // Start polling
      previewActiveJobId = data.job_id;
      clearPreviewPoll();
      previewPollTimer = setInterval(pollPreviewStatus, PREVIEW_POLL_MS);
    } catch (err) {
      if (progressEl) progressEl.hidden = true;
      showPreviewError(String(err));
    }
  }

  async function pollPreviewStatus() {
    if (!previewActiveJobId) return;
    try {
      const resp = await fetch(
        `/api/song/${encodeURIComponent(sourceHash)}/preview/${encodeURIComponent(previewActiveJobId)}`
      );
      const data = await resp.json();

      if (data.status === 'done') {
        clearPreviewPoll();
        document.getElementById('preview-progress').hidden = true;
        renderPreviewResult(data.result);
      } else if (data.status === 'failed') {
        clearPreviewPoll();
        document.getElementById('preview-progress').hidden = true;
        // FR-013: clear any prior result download link on error
        const dlLink = document.getElementById('preview-download-link');
        if (dlLink) { dlLink.hidden = true; dlLink.href = '#'; }
        const resultPane = document.getElementById('preview-result');
        if (resultPane) resultPane.hidden = true;
        showPreviewError(data.error || 'Preview generation failed.');
      } else if (data.status === 'cancelled') {
        // Superseded — a newer job will be polling separately
        clearPreviewPoll();
      }
      // pending / running: keep polling
    } catch (err) {
      // transient network error — keep polling
    }
  }

  function renderPreviewResult(result) {
    if (!result) return;
    const resultPane = document.getElementById('preview-result');
    if (!resultPane) return;

    const sec = result.section || {};
    const sectionLabel = sec.label || 'unknown';
    const startStr = fmtDurationMs(sec.start_ms || 0);
    const endStr = fmtDurationMs(sec.end_ms || 0);
    document.getElementById('preview-meta-section').textContent =
      `${sectionLabel} (${startStr}–${endStr})`;
    document.getElementById('preview-meta-window').textContent =
      result.window_ms ? `${(result.window_ms / 1000).toFixed(1)}s` : '—';
    document.getElementById('preview-meta-theme').textContent = result.theme_name || '—';
    document.getElementById('preview-meta-placements').textContent =
      result.placement_count != null ? String(result.placement_count) : '—';

    // Warnings
    const warnBox = document.getElementById('preview-warnings');
    if (result.warnings && result.warnings.length > 0) {
      warnBox.hidden = false;
      warnBox.innerHTML = result.warnings.map(w => `<p class="preview-warning">⚠ ${w}</p>`).join('');
    } else {
      warnBox.hidden = true;
    }

    // Download link
    const dlLink = document.getElementById('preview-download-link');
    if (dlLink && result.artifact_url) {
      dlLink.href = result.artifact_url;
      dlLink.hidden = false;
    }

    resultPane.hidden = false;
    document.getElementById('preview-error').hidden = true;
  }

  function showPreviewError(msg) {
    const errorPane = document.getElementById('preview-error');
    const msgEl = document.getElementById('preview-error-message');
    if (errorPane) errorPane.hidden = false;
    if (msgEl) msgEl.textContent = msg;
  }

  function clearPreviewPoll() {
    if (previewPollTimer) {
      clearInterval(previewPollTimer);
      previewPollTimer = null;
    }
  }

  // Collect brief values from the Brief tab form if it exists (US4 stale detection).
  function _collectBriefValues() {
    // If the brief form is not present, use "saved" to load persisted brief.
    return 'saved';
  }

  // Brief-change listener for stale marking (SC-005 / US4).
  // Marks the preview result as stale within 500ms of any Brief field edit.
  function _bindBriefChangeWatcher() {
    const briefPanel = document.getElementById('panel-brief');
    if (!briefPanel) return;
    briefPanel.addEventListener('change', () => {
      const resultPane = document.getElementById('preview-result');
      if (resultPane && !resultPane.hidden) {
        previewResultIsStale = true;
        const staleBanner = document.getElementById('preview-stale-banner');
        if (staleBanner) staleBanner.hidden = false;
      }
    });
    briefPanel.addEventListener('input', () => {
      const resultPane = document.getElementById('preview-result');
      if (resultPane && !resultPane.hidden) {
        previewResultIsStale = true;
        const staleBanner = document.getElementById('preview-stale-banner');
        if (staleBanner) staleBanner.hidden = false;
      }
    });
  }

  // --- Boot --------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    bindTabClicks();
    populateHeader();
    _bindBriefChangeWatcher();
    const fragment = (location.hash || '').replace(/^#/, '').toLowerCase();
    activateTab(VALID_TABS.includes(fragment) ? fragment : 'analysis');
  });
})();
