/**
 * Dashboard logic for x-onset unified homepage.
 * Handles: song library table, sort/filter, upload, detail panel, delete.
 */
(function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────────────────────
  let _entries = [];
  let _sortCol = 'analyzed_at';
  let _sortAsc = false;
  let _filterText = '';
  let _expandedHash = null;
  let _selectedFile = null;
  let _deleteHash = null;
  let _lastResultHash = null;

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const tbody = () => document.getElementById('library-tbody');
  const searchInput = () => document.getElementById('search-input');
  const songCount = () => document.getElementById('song-count');
  const emptyState = () => document.getElementById('empty-state');
  const tableWrap = () => document.getElementById('library-table-wrap');
  const filterBar = () => document.querySelector('.filter-bar');

  // ── Formatting helpers ─────────────────────────────────────────────────────
  function fmtDuration(ms) {
    var s = Math.round(ms / 1000);
    var m = Math.floor(s / 60);
    s = s % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  function fmtDate(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  }

  function fmtBpm(bpm) {
    return bpm ? Math.round(bpm) : '—';
  }

  function qualityClass(score) {
    if (score == null) return '';
    if (score >= 0.7) return 'quality-good';
    if (score >= 0.4) return 'quality-mid';
    return 'quality-low';
  }

  // ── Fetch library ──────────────────────────────────────────────────────────
  function fetchLibrary() {
    fetch('/library')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        _entries = data.entries || [];
        renderZoneABanner(_entries);
        renderTable();
      })
      .catch(function () {
        _entries = [];
        renderZoneABanner(_entries);
        renderTable();
      });
  }

  // ── Workflow strip state (spec 045 US1) ──────────────────────────────────
  // Step rules:
  //   1 upload   — complete iff source_file_exists && analysis_exists
  //   2 review   — complete iff step 1 complete
  //   3 story    — complete iff has_story; active when 1–2 complete && !has_story
  //   4 generate — blocked when layout_configured=false; complete when
  //                last_generated_at != null; active when 1–3 complete &&
  //                layout_configured && no generation yet
  function computeStripStates(entry) {
    var step1Complete = !!(entry.source_file_exists && entry.analysis_exists);
    var step2Complete = step1Complete;
    var step3Complete = !!entry.has_story;
    var step4Complete = !!entry.last_generated_at;
    var layoutOk = !!entry.layout_configured;

    var s1 = step1Complete ? 'complete' : 'incomplete';
    var s2 = step2Complete ? 'complete' : 'incomplete';
    var s3;
    if (step3Complete) s3 = 'complete';
    else if (step1Complete && step2Complete) s3 = 'active';
    else s3 = 'incomplete';
    var s4;
    if (!layoutOk) s4 = 'blocked';
    else if (step4Complete) s4 = 'complete';
    else if (step1Complete && step2Complete && step3Complete) s4 = 'active';
    else s4 = 'incomplete';

    return { upload: s1, review: s2, story: s3, generate: s4 };
  }

  var _STRIP_TOOLTIPS = {
    upload: {
      incomplete: 'Upload and analyze this song to continue.',
      complete: 'Upload complete.',
      active: 'Upload is in progress.',
      blocked: ''
    },
    review: {
      incomplete: 'Analysis must finish before you can review the timeline.',
      complete: 'Open the timeline for this song.',
      active: 'Open the timeline for this song.',
      blocked: ''
    },
    story: {
      incomplete: 'Finish analysis before brief & story.',
      active: 'Create the story and brief for this song.',
      complete: 'Open the story review for this song.',
      blocked: ''
    },
    generate: {
      incomplete: 'Complete earlier steps before generating.',
      active: 'Generate a sequence for this song.',
      complete: 'Sequence generated — open the overflow menu to regenerate.',
      blocked: 'Set up your layout before generating sequences.'
    }
  };

  function applyStripState(entry) {
    var states = computeStripStates(entry);
    var steps = document.querySelectorAll('.workflow-step');
    var connectors = document.querySelectorAll('.workflow-connector');
    steps.forEach(function (el) {
      var key = el.dataset.step;
      var state = states[key] || 'incomplete';
      el.dataset.state = state;
      var tip = (_STRIP_TOOLTIPS[key] || {})[state] || '';
      if (tip) el.setAttribute('title', tip);
      else el.removeAttribute('title');
    });
    connectors.forEach(function (c) {
      c.dataset.state = 'neutral';
    });
    // Mark connectors leading into each complete step as complete
    var order = ['upload', 'review', 'story', 'generate'];
    for (var i = 1; i < order.length; i++) {
      var prev = states[order[i - 1]];
      if (prev === 'complete' && connectors[i - 1]) {
        connectors[i - 1].dataset.state = 'complete';
      }
    }
  }

  function resetStripState() {
    document.querySelectorAll('.workflow-step').forEach(function (el) {
      el.dataset.state = 'neutral';
      el.removeAttribute('title');
    });
    document.querySelectorAll('.workflow-connector').forEach(function (c) {
      c.dataset.state = 'neutral';
    });
  }

  function wireStripClicks() {
    document.querySelectorAll('.workflow-step').forEach(function (el) {
      el.addEventListener('click', function () {
        var state = el.dataset.state;
        if (state !== 'complete' && state !== 'active') return; // blocked/incomplete/neutral
        if (!_expandedHash) return;
        var entry = _entries.find(function (e) { return e.source_hash === _expandedHash; });
        if (!entry) return;
        var step = el.dataset.step;
        if (step === 'upload') return; // no destination for step 1
        if (step === 'review') { openSong(entry.source_hash); return; }
        if (step === 'story') {
          if (entry.story_path) {
            window.location.href = '/story-review?path=' + encodeURIComponent(entry.story_path);
          } else {
            window.location.href = '/story-review?hash=' + encodeURIComponent(entry.source_hash);
          }
          return;
        }
        if (step === 'generate') {
          if (document.body.dataset.layoutConfigured !== 'true') return;
          // Open the row detail panel and trigger the inline generate action.
          if (_expandedHash !== entry.source_hash) {
            _expandedHash = entry.source_hash;
            renderTable();
          }
          var detailRow = document.querySelector('tr.detail-row');
          if (detailRow) {
            var genPanel = detailRow.querySelector('.detail-generate');
            if (genPanel) {
              genPanel.style.display = '';
              renderGeneratePanel(entry, genPanel);
            }
          }
        }
      });
    });
  }

  // ── Zone A setup banner (spec 045 US2) ────────────────────────────────────
  function renderZoneABanner(entries) {
    var banner = document.getElementById('zone-a-banner');
    // layout_configured is a global field, the same value on every entry.
    // When the library is empty we still want the banner to appear if layout
    // is missing — but we cannot read layout_configured without an entry.
    // The banner stays hidden in that case (only relevant when at least one
    // song exists because only then is "generate" meaningful).
    var configured = entries.length > 0 ? !!entries[0].layout_configured : true;
    if (banner) {
      banner.hidden = configured;
    }
    document.body.dataset.layoutConfigured = configured ? 'true' : 'false';
  }

  // ── Sort & filter ──────────────────────────────────────────────────────────
  function getFiltered() {
    var q = _filterText.toLowerCase();
    var list = _entries;
    if (q) {
      list = list.filter(function (e) {
        return (e.title || '').toLowerCase().indexOf(q) >= 0 ||
               (e.artist || '').toLowerCase().indexOf(q) >= 0 ||
               (e.album || '').toLowerCase().indexOf(q) >= 0 ||
               (e.genre || '').toLowerCase().indexOf(q) >= 0;
      });
    }
    // Sort
    list = list.slice().sort(function (a, b) {
      var av = a[_sortCol], bv = b[_sortCol];
      if (av == null) av = '';
      if (bv == null) bv = '';
      if (typeof av === 'string') av = av.toLowerCase();
      if (typeof bv === 'string') bv = bv.toLowerCase();
      if (av < bv) return _sortAsc ? -1 : 1;
      if (av > bv) return _sortAsc ? 1 : -1;
      return 0;
    });
    return list;
  }

  // ── Render table ───────────────────────────────────────────────────────────
  function renderTable() {
    var filtered = getFiltered();
    var tb = tbody();
    if (!tb) return;
    tb.innerHTML = '';

    var total = _entries.length;
    var shown = filtered.length;
    var sc = songCount();
    if (sc) {
      sc.textContent = _filterText
        ? shown + ' of ' + total + ' songs'
        : total + ' song' + (total !== 1 ? 's' : '');
    }

    // Show/hide empty state vs table
    var es = emptyState();
    var tw = tableWrap();
    var fb = filterBar();
    if (total === 0) {
      if (es) es.style.display = '';
      if (tw) tw.style.display = 'none';
      if (fb) fb.style.display = 'none';
      return;
    }
    if (es) es.style.display = 'none';
    if (tw) tw.style.display = '';
    if (fb) fb.style.display = '';

    // Auto-expand upload section when library is empty
    var uploadSection = document.getElementById('upload-section');
    if (uploadSection) {
      if (total === 0) {
        uploadSection.classList.remove('collapsed');
      }
    }

    // Update sort indicators
    document.querySelectorAll('.library-table th').forEach(function (th) {
      th.classList.remove('sorted', 'sort-asc', 'sort-desc');
      if (th.dataset.sort === _sortCol) {
        th.classList.add('sorted', _sortAsc ? 'sort-asc' : 'sort-desc');
      }
    });

    filtered.forEach(function (e) {
      var tr = document.createElement('tr');
      var isMissing = e.file_exists === false || e.analysis_exists === false;
      if (isMissing) tr.classList.add('missing');
      if (_expandedHash === e.source_hash) tr.classList.add('expanded');
      tr.dataset.hash = e.source_hash;

      var coverHtml = e.has_cover
        ? '<img class="cover-thumb" src="/library/' + esc(e.source_hash) + '/cover" alt="">'
        : '<span class="cover-placeholder">&#9836;</span>';

      tr.innerHTML =
        '<td class="col-cover">' + coverHtml + '</td>' +
        '<td class="song-title-cell">' + esc(e.title || e.filename) + '</td>' +
        '<td class="song-artist-cell">' + esc(e.artist || '') + '</td>' +
        '<td class="song-album-cell">' + esc(e.album || '') + '</td>' +
        '<td class="song-genre-cell">' + esc(e.genre || '') + '</td>' +
        '<td class="col-num">' + esc(e.year || '') + '</td>' +
        '<td class="col-num">' + fmtDuration(e.duration_ms) + '</td>' +
        '<td class="col-num">' + fmtBpm(e.estimated_tempo_bpm) + '</td>' +
        '<td class="col-num">' + renderQuality(e.quality_score) + '</td>' +
        '<td class="col-badges">' + renderBadges(e) + '</td>' +
        '<td class="col-num">' + fmtDate(e.analyzed_at) + '</td>' +
        '<td class="col-actions"><button class="btn-expand" data-hash="' + esc(e.source_hash) + '">Details</button></td>';

      // Click row to go to story view (but not on buttons)
      tr.addEventListener('click', function (ev) {
        if (ev.target.tagName === 'BUTTON') return;
        openSongTool(e.source_hash, e.has_story ? 'story' : 'timeline', e.story_path);
      });

      tb.appendChild(tr);

      // Detail panel if expanded
      if (_expandedHash === e.source_hash) {
        renderDetail(e, tb);
      }
    });

    // Update workflow strip based on expanded song (spec 045 US1)
    if (_expandedHash) {
      var expanded = _entries.find(function (e) { return e.source_hash === _expandedHash; });
      if (expanded) applyStripState(expanded);
      else resetStripState();
    } else {
      resetStripState();
    }

    // Attach expand button handlers
    tb.querySelectorAll('.btn-expand').forEach(function (btn) {
      btn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var hash = btn.dataset.hash;
        _expandedHash = (_expandedHash === hash) ? null : hash;
        renderTable();
      });
    });
  }

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function renderQuality(score) {
    if (score == null) return '<span class="quality-label">—</span>';
    var pct = Math.round(score * 100);
    var cls = qualityClass(score);
    return '<span class="quality-bar"><span class="quality-fill ' + cls + '" style="width:' + pct + '%"></span></span>' +
           '<span class="quality-label">' + pct + '%</span>';
  }

  function renderBadges(e) {
    var html = '';
    // Spec 045 US4 lifecycle badge: one of Analyzed / Generated / Stale.
    // Only one lifecycle badge is shown per row; Stale replaces Generated
    // replaces Analyzed. The Phase-3 reserved-label slot is deliberately
    // NOT emitted here (FR-011).
    if (e.is_stale) {
      html += '<span class="badge badge-stale">Stale</span>';
    } else if (e.last_generated_at) {
      html += '<span class="badge badge-generated">Generated</span>';
    } else if (e.analysis_exists) {
      html += '<span class="badge badge-analyzed">Analyzed</span>';
    }
    if (e.stem_separation) html += '<span class="badge badge-stems">Stems</span>';
    if (e.has_phonemes) html += '<span class="badge badge-phonemes">Phonemes</span>';
    if (e.has_story) html += '<span class="badge badge-story">Story</span>';
    if (e.file_exists === false || e.analysis_exists === false) {
      html += '<span class="badge badge-missing">Missing</span>';
    }
    return html;
  }

  // ── Detail panel ───────────────────────────────────────────────────────────
  function renderDetail(entry, tb) {
    var tmpl = document.getElementById('detail-template');
    if (!tmpl) return;
    var clone = tmpl.content.cloneNode(true);
    var tr = clone.querySelector('tr');

    // Quality bar
    var qFill = tr.querySelector('.quality-fill');
    var qLabel = tr.querySelector('.detail-quality-label');
    if (entry.quality_score != null) {
      var pct = Math.round(entry.quality_score * 100);
      qFill.style.width = pct + '%';
      qFill.className = 'quality-fill ' + qualityClass(entry.quality_score);
      qLabel.textContent = pct + '% overall';
    } else {
      qLabel.textContent = 'No quality data';
    }

    // Info
    var info = tr.querySelector('.detail-info');
    var lines = [];
    lines.push('Tracks: ' + (entry.track_count || '—'));
    lines.push('Stems: ' + (entry.stem_separation ? 'Yes' : 'No'));
    lines.push('File: ' + esc(entry.filename || ''));
    if (entry.file_exists === false) lines.push('<span style="color:#c44">Source file missing</span>');
    if (entry.analysis_exists === false) lines.push('<span style="color:#c44">Analysis file missing</span>');
    info.innerHTML = lines.join('<br>');

    // Spec 045 US3: single primary Open + overflow-menu actions.
    function handleDetailAction(action) {
      if (action === 'open') openSong(entry.source_hash);
      else if (action === 'preview') window.location.href = '/generation-preview?hash=' + entry.source_hash;
      else if (action === 'story') openSongTool(entry.source_hash, 'story', entry.story_path);
      else if (action === 'phonemes') openSongTool(entry.source_hash, 'phonemes');
      else if (action === 'generate') {
        if (document.body.dataset.layoutConfigured !== 'true') return;
        toggleGeneratePanel(entry, tr);
      }
      else if (action === 'reanalyze') reanalyzeSong(entry);
      else if (action === 'delete') showDeleteDialog(entry);
    }

    var openBtn = tr.querySelector('[data-action="open"]');
    if (openBtn) {
      openBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        handleDetailAction('open');
      });
    }

    var kebab = tr.querySelector('.btn-kebab');
    var menu = tr.querySelector('.overflow-menu');
    if (kebab && menu) {
      kebab.addEventListener('click', function (ev) {
        ev.stopPropagation();
        closeAllOverflowMenus(menu);
        var open = !menu.hidden;
        if (open) {
          menu.hidden = true;
          kebab.setAttribute('aria-expanded', 'false');
        } else {
          menu.hidden = false;
          kebab.setAttribute('aria-expanded', 'true');
        }
      });

      menu.querySelectorAll('.overflow-menu-item').forEach(function (item) {
        item.addEventListener('click', function (ev) {
          ev.stopPropagation();
          var action = item.dataset.action;
          menu.hidden = true;
          kebab.setAttribute('aria-expanded', 'false');
          handleDetailAction(action);
        });
      });
    }

    tb.appendChild(tr);
  }

  // ── Overflow menu dismiss helpers (spec 045 US3, FR-010) ──────────────────
  function closeAllOverflowMenus(keepOpen) {
    document.querySelectorAll('.overflow-menu').forEach(function (m) {
      if (m === keepOpen) return;
      m.hidden = true;
      var owner = m.closest('.overflow-wrap');
      if (owner) {
        var kebab = owner.querySelector('.btn-kebab');
        if (kebab) kebab.setAttribute('aria-expanded', 'false');
      }
    });
  }

  document.addEventListener('click', function (ev) {
    if (ev.target.closest('.overflow-wrap')) return;
    closeAllOverflowMenus();
  });

  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') closeAllOverflowMenus();
  });

  // ── Generate Sequence inline panel ────────────────────────────────────────
  var _genPollInterval = null;

  function toggleGeneratePanel(entry, detailRow) {
    var panel = detailRow.querySelector('.detail-generate');
    if (!panel) return;
    if (panel.style.display !== 'none') {
      panel.style.display = 'none';
      return;
    }
    panel.style.display = '';
    renderGeneratePanel(entry, panel);
  }

  function renderGeneratePanel(entry, panel) {
    if (!entry.analysis_exists) {
      panel.innerHTML = '<div class="gen-inline-notice">Analysis required before generating. Run analysis first.</div>';
      return;
    }

    panel.innerHTML = '<div class="gen-inline-loading">Checking layout configuration…</div>';

    fetch('/generate/settings')
      .then(function (r) { return r.json(); })
      .then(function (settings) {
        if (!settings.layout_configured) {
          panel.innerHTML = '<div class="gen-inline-notice">' +
            'No layout groups configured. ' +
            '<a href="/grouper" target="_blank">Set up layout groups in the grouper</a> ' +
            'and save to enable generation.' +
            '</div>';
          return;
        }

        var knownGenres = ['any', 'pop', 'rock', 'classical'];
        var songGenre = entry.genre && knownGenres.indexOf(entry.genre.toLowerCase()) >= 0
          ? entry.genre.toLowerCase() : 'any';

        function opt(val, label, sel) {
          return '<option value="' + val + '"' + (sel === val ? ' selected' : '') + '>' + label + '</option>';
        }

        panel.innerHTML =
          '<div class="gen-inline-form">' +
            '<label>Genre <select class="gen-inline-select" id="gi-genre-' + esc(entry.source_hash) + '">' +
              opt('any', 'Any', songGenre) +
              opt('pop', 'Pop', songGenre) +
              opt('rock', 'Rock', songGenre) +
              opt('classical', 'Classical', songGenre) +
            '</select></label>' +
            '<label>Occasion <select class="gen-inline-select" id="gi-occasion-' + esc(entry.source_hash) + '">' +
              opt('general', 'General', 'general') +
              opt('christmas', 'Christmas', 'general') +
              opt('halloween', 'Halloween', 'general') +
            '</select></label>' +
            '<label>Transitions <select class="gen-inline-select" id="gi-transition-' + esc(entry.source_hash) + '">' +
              opt('subtle', 'Subtle', 'subtle') +
              opt('none', 'None', 'subtle') +
              opt('dramatic', 'Dramatic', 'subtle') +
            '</select></label>' +
            '<button class="btn btn-small gen-inline-btn" id="gi-btn-' + esc(entry.source_hash) + '">Generate</button>' +
            '<span class="gen-inline-status" id="gi-status-' + esc(entry.source_hash) + '"></span>' +
          '</div>' +
          '<div class="gen-inline-history" id="gi-history-' + esc(entry.source_hash) + '"></div>';

        document.getElementById('gi-btn-' + entry.source_hash)
          .addEventListener('click', function () { startGeneration(entry, panel); });

        loadGenHistory(entry.source_hash);
      })
      .catch(function () {
        panel.innerHTML = '<div class="gen-inline-notice">Could not reach server.</div>';
      });
  }

  function startGeneration(entry, panel) {
    var hash = entry.source_hash;
    var btn = document.getElementById('gi-btn-' + hash);
    var statusEl = document.getElementById('gi-status-' + hash);
    if (!btn || !statusEl) return;

    var genre = (document.getElementById('gi-genre-' + hash) || {}).value || 'any';
    var occasion = (document.getElementById('gi-occasion-' + hash) || {}).value || 'general';
    var transition = (document.getElementById('gi-transition-' + hash) || {}).value || 'subtle';

    btn.disabled = true;
    statusEl.textContent = 'Starting…';
    statusEl.className = 'gen-inline-status gen-inline-status--running';

    fetch('/generate/' + hash, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ genre: genre, occasion: occasion, transition_mode: transition })
    })
      .then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); })
      .then(function (res) {
        if (res.status === 409) {
          statusEl.innerHTML = 'No layout configured. <a href="/grouper" target="_blank">Set up grouper →</a>';
          statusEl.className = 'gen-inline-status gen-inline-status--error';
          btn.disabled = false;
          return;
        }
        if (res.status !== 202) {
          statusEl.textContent = res.data.error || 'Generation failed.';
          statusEl.className = 'gen-inline-status gen-inline-status--error';
          btn.disabled = false;
          return;
        }

        var jobId = res.data.job_id;
        statusEl.textContent = 'Generating…';

        if (_genPollInterval) clearInterval(_genPollInterval);
        _genPollInterval = setInterval(function () {
          fetch('/generate/' + hash + '/status?job_id=' + encodeURIComponent(jobId))
            .then(function (r) { return r.json(); })
            .then(function (d) {
              if (d.status === 'complete') {
                clearInterval(_genPollInterval);
                _genPollInterval = null;
                statusEl.textContent = 'Done! Downloading…';
                statusEl.className = 'gen-inline-status gen-inline-status--done';
                window.location.href = '/generate/' + hash + '/download/' + encodeURIComponent(jobId);
                btn.disabled = false;
                loadGenHistory(hash);
              } else if (d.status === 'failed') {
                clearInterval(_genPollInterval);
                _genPollInterval = null;
                statusEl.textContent = d.error || 'Generation failed.';
                statusEl.className = 'gen-inline-status gen-inline-status--error';
                btn.disabled = false;
              }
            })
            .catch(function () { /* keep polling */ });
        }, 2000);
      })
      .catch(function () {
        statusEl.textContent = 'Network error.';
        statusEl.className = 'gen-inline-status gen-inline-status--error';
        btn.disabled = false;
      });
  }

  function loadGenHistory(hash) {
    var histEl = document.getElementById('gi-history-' + hash);
    if (!histEl) return;
    fetch('/generate/' + hash + '/history')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data.jobs || data.jobs.length === 0) { histEl.innerHTML = ''; return; }
        var rows = data.jobs.map(function (j) {
          var d = new Date(j.created_at * 1000);
          var ts = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          return '<div class="gen-hist-row">' +
            '<span class="gen-hist-ts">' + ts + '</span>' +
            '<span class="gen-hist-opts">' + esc(j.genre) + ' / ' + esc(j.occasion) + '</span>' +
            '<a href="/generate/' + esc(hash) + '/download/' + esc(j.job_id) + '" class="gen-hist-dl">Re-download</a>' +
            '</div>';
        }).join('');
        histEl.innerHTML = '<div class="gen-hist-header">Previous generations</div>' + rows;
      })
      .catch(function () {});
  }

  // ── Navigation helpers ─────────────────────────────────────────────────────
  // Spec 045 centralized the "Open" action; spec 046 retargets it to
  // /song/<hash> — the single per-song workspace — without touching callers.
  function openSong(hash) {
    fetch('/open-from-library?hash=' + hash, { method: 'POST' })
      .then(function () {
        window.location.href = '/song/' + encodeURIComponent(hash);
      });
  }

  // Legacy tool-routing helper retained for the overflow-menu entries that
  // still target specific tools (story, phonemes) and for fallback callers.
  function openSongTool(hash, tool, storyPath) {
    fetch('/open-from-library?hash=' + hash, { method: 'POST' })
      .then(function () {
        if (tool === 'story' && storyPath) {
          window.location.href = '/story-review?path=' + encodeURIComponent(storyPath);
        } else if (tool === 'story') {
          window.location.href = '/story-review?hash=' + hash;
        } else if (tool === 'phonemes') {
          window.location.href = '/phonemes-view?hash=' + hash;
        } else {
          window.location.href = '/timeline?hash=' + hash;
        }
      });
  }

  function reanalyzeSong(entry) {
    // Open upload section and pre-fill
    var section = document.getElementById('upload-section');
    section.classList.remove('collapsed');
    // Could pre-fill with source path in the future; for now just open upload
  }

  // ── Delete ─────────────────────────────────────────────────────────────────
  function showDeleteDialog(entry) {
    _deleteHash = entry.source_hash;
    var dialog = document.getElementById('delete-dialog');
    document.getElementById('delete-song-name').textContent = entry.title || entry.filename;
    document.getElementById('delete-files-check').checked = false;
    dialog.style.display = '';
  }

  function hideDeleteDialog() {
    document.getElementById('delete-dialog').style.display = 'none';
    _deleteHash = null;
  }

  function confirmDelete() {
    if (!_deleteHash) return;
    var deleteFiles = document.getElementById('delete-files-check').checked;
    fetch('/library/' + _deleteHash + '?delete_files=' + deleteFiles, { method: 'DELETE' })
      .then(function (r) { return r.json(); })
      .then(function () {
        hideDeleteDialog();
        if (_expandedHash === _deleteHash) _expandedHash = null;
        fetchLibrary();
      })
      .catch(function () { hideDeleteDialog(); });
  }

  // ── Upload ─────────────────────────────────────────────────────────────────
  function initUpload() {
    var toggle = document.getElementById('upload-toggle');
    var section = document.getElementById('upload-section');
    var dropZone = document.getElementById('drop-zone');
    var fileInput = document.getElementById('file-input');
    var btnAnalyze = document.getElementById('btn-analyze');
    var fileName = document.getElementById('file-name');

    if (toggle) {
      toggle.addEventListener('click', function () {
        section.classList.toggle('collapsed');
      });
    }

    // Empty state upload button
    var btnEmpty = document.getElementById('btn-empty-upload');
    if (btnEmpty) {
      btnEmpty.addEventListener('click', function () {
        section.classList.remove('collapsed');
        section.scrollIntoView({ behavior: 'smooth' });
      });
    }

    // Drop zone
    if (dropZone) {
      dropZone.addEventListener('dragover', function (e) {
        e.preventDefault();
        dropZone.classList.add('drag-over');
      });
      dropZone.addEventListener('dragleave', function () {
        dropZone.classList.remove('drag-over');
      });
      dropZone.addEventListener('drop', function (e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length > 0) {
          selectFile(e.dataTransfer.files[0]);
        }
      });
    }

    if (fileInput) {
      fileInput.addEventListener('change', function () {
        if (fileInput.files.length > 0) selectFile(fileInput.files[0]);
      });
    }

    if (btnAnalyze) {
      btnAnalyze.addEventListener('click', startAnalysis);
    }

    function selectFile(file) {
      if (!file.name.toLowerCase().endsWith('.mp3')) {
        alert('Only .mp3 files are accepted');
        return;
      }
      _selectedFile = file;
      if (fileName) fileName.textContent = file.name;
      if (btnAnalyze) btnAnalyze.disabled = false;

      // Check for duplicate
      var dup = document.getElementById('duplicate-warning');
      var existing = _entries.find(function (e) { return e.filename === file.name; });
      if (existing && dup) {
        dup.style.display = '';
        document.getElementById('btn-go-existing').onclick = function () {
          openSongTool(existing.source_hash, existing.has_story ? 'story' : 'timeline', existing.story_path);
        };
        document.getElementById('btn-reanalyze').onclick = startAnalysis;
      } else if (dup) {
        dup.style.display = 'none';
      }
    }
  }

  function startAnalysis() {
    if (!_selectedFile) return;

    var fd = new FormData();
    fd.append('mp3', _selectedFile);
    fd.append('story', document.getElementById('opt-story').checked ? 'true' : 'false');

    // Show progress section
    var progSection = document.getElementById('progress-section');
    progSection.style.display = '';
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-steps').innerHTML = '';
    document.getElementById('progress-error').style.display = 'none';
    document.getElementById('progress-done').style.display = 'none';
    document.getElementById('genius-prompt').style.display = 'none';
    document.getElementById('progress-label').textContent = 'Starting analysis...';
    document.getElementById('progress-count').textContent = '';

    // Collapse upload section
    document.getElementById('upload-section').classList.add('collapsed');

    fetch('/upload', { method: 'POST', body: fd })
      .then(function (r) {
        if (!r.ok) return r.json().then(function (d) { throw new Error(d.error || 'Upload failed'); });
        return r.json();
      })
      .then(function () {
        listenProgress();
      })
      .catch(function (err) {
        document.getElementById('progress-error').textContent = err.message;
        document.getElementById('progress-error').style.display = '';
      });
  }

  function listenProgress() {
    var es = new EventSource('/progress');
    var steps = document.getElementById('progress-steps');

    es.onmessage = function (ev) {
      var data;
      try { data = JSON.parse(ev.data); } catch (e) { return; }

      if (data.error) {
        es.close();
        document.getElementById('progress-error').textContent = data.error;
        document.getElementById('progress-error').style.display = '';
        return;
      }

      if (data.done) {
        es.close();
        document.getElementById('progress-bar').style.width = '100%';
        document.getElementById('progress-label').textContent = 'Complete';
        _lastResultHash = null;
        // Refresh library
        fetchLibrary();

        // Show analysis summary in the done section
        var doneSec = document.getElementById('progress-done');
        if (doneSec && data.summary) {
          var s = data.summary;
          var summaryHtml = '<div class="analysis-summary">';
          summaryHtml += '<p class="summary-headline">&#10003; Analysis complete!</p>';
          summaryHtml += '<div class="summary-stats">';
          summaryHtml += '<span class="summary-stat">' + (s.track_count || 0) + ' tracks</span>';
          if (s.stems_available && s.stems_available.length > 1) {
            summaryHtml += '<span class="summary-stat">' + (s.stems_available.length - 1) + ' stems</span>';
          }
          if (s.has_phonemes) summaryHtml += '<span class="summary-stat">Phonemes</span>';
          if (s.has_story) summaryHtml += '<span class="summary-stat">Story</span>';
          summaryHtml += '</div>';
          if (s.warnings && s.warnings.length > 0) {
            summaryHtml += '<div class="summary-warnings">';
            s.warnings.forEach(function(w) {
              summaryHtml += '<div class="summary-warning">&#9888; ' + w + '</div>';
            });
            summaryHtml += '</div>';
          }
          summaryHtml += '</div>';
          doneSec.innerHTML = summaryHtml +
            '<button id="btn-view-result" class="btn btn-primary btn-small">View Result</button>';
        }
        doneSec.style.display = '';

        document.getElementById('btn-view-result').onclick = function () {
          if (data.story_path) {
            window.location.href = '/story-review?path=' + encodeURIComponent(data.story_path);
          } else {
            window.location.href = '/timeline';
          }
        };
        return;
      }

      if (data.genius_prompt) {
        var gp = document.getElementById('genius-prompt');
        gp.style.display = '';
        document.getElementById('genius-artist').value = data.guessed_artist || '';
        document.getElementById('genius-title').value = data.guessed_title || '';
        return;
      }

      if (data.stage) {
        document.getElementById('progress-label').textContent = data.label || data.stage;
        return;
      }

      if (data.warning) {
        var warn = document.createElement('div');
        warn.className = 'step';
        warn.style.color = '#c90';
        warn.textContent = '\u26A0 ' + data.warning;
        steps.appendChild(warn);
        return;
      }

      // Progress event
      if (data.idx != null) {
        var pct = Math.round(((data.idx + 1) / data.total) * 100);
        document.getElementById('progress-bar').style.width = pct + '%';
        document.getElementById('progress-count').textContent = (data.idx + 1) + '/' + data.total;

        var step = document.createElement('div');
        step.className = 'step done';
        step.textContent = '\u2713 ' + data.name + (data.mark_count ? ' (' + data.mark_count + ' marks)' : '');
        steps.appendChild(step);
        steps.scrollTop = steps.scrollHeight;
      }
    };
  }

  function initGenius() {
    var btnSubmit = document.getElementById('btn-genius-submit');
    var btnSkip = document.getElementById('btn-genius-skip');

    if (btnSubmit) {
      btnSubmit.addEventListener('click', function () {
        var artist = document.getElementById('genius-artist').value;
        var title = document.getElementById('genius-title').value;
        fetch('/genius-retry', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artist: artist, title: title }),
        });
        document.getElementById('genius-prompt').style.display = 'none';
      });
    }

    if (btnSkip) {
      btnSkip.addEventListener('click', function () {
        fetch('/genius-retry', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ artist: '', title: '__skip__' }),
        });
        document.getElementById('genius-prompt').style.display = 'none';
      });
    }
  }

  // ── State persistence (US3) ────────────────────────────────────────────────
  function saveState() {
    try {
      sessionStorage.setItem('dashboard_sort_col', _sortCol);
      sessionStorage.setItem('dashboard_sort_asc', _sortAsc ? '1' : '0');
      sessionStorage.setItem('dashboard_filter', _filterText);
    } catch (e) { /* ignore */ }
  }

  function restoreState() {
    try {
      var col = sessionStorage.getItem('dashboard_sort_col');
      var asc = sessionStorage.getItem('dashboard_sort_asc');
      var filter = sessionStorage.getItem('dashboard_filter');
      if (col) _sortCol = col;
      if (asc !== null) _sortAsc = asc === '1';
      if (filter) {
        _filterText = filter;
        var si = searchInput();
        if (si) si.value = filter;
      }
    } catch (e) { /* ignore */ }
  }

  // Save state before navigating away
  window.addEventListener('beforeunload', saveState);

  // ── Init ───────────────────────────────────────────────────────────────────
  function init() {
    restoreState();

    // Sort column click
    document.querySelectorAll('.library-table th.sortable').forEach(function (th) {
      th.addEventListener('click', function () {
        var col = th.dataset.sort;
        if (_sortCol === col) {
          _sortAsc = !_sortAsc;
        } else {
          _sortCol = col;
          _sortAsc = true;
        }
        renderTable();
      });
    });

    // Search input
    var si = searchInput();
    if (si) {
      si.addEventListener('input', function () {
        _filterText = si.value;
        renderTable();
      });
    }

    // Delete dialog buttons
    var btnDelCancel = document.getElementById('btn-delete-cancel');
    var btnDelConfirm = document.getElementById('btn-delete-confirm');
    if (btnDelCancel) btnDelCancel.addEventListener('click', hideDeleteDialog);
    if (btnDelConfirm) btnDelConfirm.addEventListener('click', confirmDelete);

    initUpload();
    initGenius();
    wireStripClicks();
    fetchLibrary();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
