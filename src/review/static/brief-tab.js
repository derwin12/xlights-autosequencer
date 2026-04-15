'use strict';

// brief-tab.js — Creative Brief form controller (spec 047).
//
// Mounts the Brief form into the per-song workspace shell (spec 046).
// Depends on brief-presets.js being loaded first (BRIEF_PRESETS,
// resolveBriefToPost, detectActivePreset, collectAxisFields on window).
//
// Public API (attached to window):
//   mountBriefTab(root, sourceHash) — called by song-workspace.js on first
//     activation of the Brief tab.

(function () {
  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------

  // Mood smart-default ruleset — Phase 3 client-side only.
  // Phase 4 (spec 048) will wire mood_intent into build_plan() and this object
  // can be deleted then. The values are preset ids (lowercase) matching
  // research.md §2 exactly.
  const MOOD_DEFAULTS = {
    party:     { transitions: 'dramatic', accents: 'strong',  variation: 'varied',  palette: 'full',       duration: 'snappy'  },
    emotional: { transitions: 'subtle',   accents: 'subtle',  variation: 'focused', palette: 'restrained', duration: 'flowing' },
    dramatic:  { transitions: 'dramatic', accents: 'strong',  variation: 'focused', palette: 'restrained', duration: 'flowing' },
    playful:   { transitions: 'subtle',   accents: 'subtle',  variation: 'varied',  palette: 'full',       duration: 'snappy'  },
  };

  // Axes in the order they appear in the form.
  const AXES = ['genre', 'occasion', 'mood_intent', 'variation', 'palette', 'duration', 'accents', 'transitions', 'curves'];

  // ---------------------------------------------------------------------------
  // In-memory brief state
  // ---------------------------------------------------------------------------
  // Each axis: { value: string (preset id), origin: 'default'|'user'|'via-mood' }
  // advanced: { [fieldName]: value }  — raw overrides set via Advanced disclosures
  // per_section_overrides: [{ section_index, theme_slug }]
  // _dirty: bool
  // _sourceHash: string
  // _themes: [{slug, name}]   — catalog fetched from GET /themes + GET /variants

  let _state = null;

  function _defaultBriefState(sourceHash) {
    const axes = {};
    AXES.forEach(axis => {
      axes[axis] = { value: 'auto', origin: 'default' };
    });
    return {
      source_hash: sourceHash,
      brief_schema_version: 1,
      axes,
      advanced: {},
      per_section_overrides: [],
      _dirty: false,
      _sourceHash: sourceHash,
      _themes: [],
      _sections: [],
    };
  }

  function _stateFromBriefJson(json, sourceHash) {
    const state = _defaultBriefState(sourceHash);
    AXES.forEach(axis => {
      const val = json[axis] || 'auto';
      state.axes[axis] = { value: val, origin: 'user' };
    });
    state.advanced = json.advanced || {};
    state.per_section_overrides = (json.per_section_overrides || []).slice();
    return state;
  }

  function _stateToBriefJson(state) {
    const brief = {
      brief_schema_version: 1,
      source_hash: state._sourceHash,
      advanced: Object.assign({}, state.advanced),
      per_section_overrides: state.per_section_overrides.slice(),
    };
    AXES.forEach(axis => {
      brief[axis] = state.axes[axis].value;
    });
    return brief;
  }

  // ---------------------------------------------------------------------------
  // Axis rendering helpers
  // ---------------------------------------------------------------------------

  function _buildAxisFieldset(axisId, axisState) {
    const axisDef = window.BRIEF_PRESETS[axisId];
    if (!axisDef) return null;

    const fs = document.querySelector(`#axis-${axisId}`);
    if (!fs) return null;

    const activePresetId = _state
      ? window.detectActivePreset(axisId, _stateToBriefJson(_state))
      : axisState.value;

    // Legend
    let legend = fs.querySelector('legend');
    if (!legend) {
      legend = document.createElement('legend');
      fs.insertBefore(legend, fs.firstChild);
    }
    legend.textContent = axisDef.label;

    // Status chips container (via-mood / custom)
    let chips = fs.querySelector('.axis-chips');
    if (!chips) {
      chips = document.createElement('span');
      chips.className = 'axis-chips';
      legend.appendChild(chips);
    }
    chips.innerHTML = '';
    if (axisState.origin === 'via-mood') {
      const chip = document.createElement('span');
      chip.className = 'via-mood-chip';
      chip.textContent = 'via Mood';
      chips.appendChild(chip);
    }
    if (activePresetId === 'custom') {
      const chip = document.createElement('span');
      chip.className = 'custom-chip';
      chip.textContent = 'Custom';
      chips.appendChild(chip);
    }

    // Inline error (cleared on re-render)
    const existingErr = fs.querySelector('.inline-error');
    if (existingErr) existingErr.remove();

    // Preset radio group
    let pg = fs.querySelector('.preset-group');
    if (!pg) {
      pg = document.createElement('div');
      pg.className = 'preset-group';
      pg.setAttribute('role', 'radiogroup');
      pg.setAttribute('aria-label', axisDef.label + ' presets');
    } else {
      pg.innerHTML = '';
    }

    axisDef.presets.forEach(preset => {
      const radio = document.createElement('input');
      radio.type = 'radio';
      radio.name = `brief-${axisId}`;
      radio.id = `brief-${axisId}-${preset.id}`;
      radio.value = preset.id;
      radio.checked = (activePresetId === preset.id) || (activePresetId === 'custom' && axisState.value === preset.id);

      const label = document.createElement('label');
      label.htmlFor = radio.id;
      label.className = radio.checked ? 'active' : '';

      const span = document.createElement('span');
      span.textContent = preset.label;
      label.appendChild(radio);
      label.appendChild(span);

      radio.addEventListener('change', () => {
        if (radio.checked) _onPresetChange(axisId, preset.id);
      });

      pg.appendChild(label);
    });

    // Hint paragraph
    let hint = fs.querySelector('p.hint');
    if (!hint) {
      hint = document.createElement('p');
      hint.className = 'hint';
    }
    hint.textContent = axisDef.hint;

    // Advanced disclosure
    let adv = fs.querySelector('details.advanced');
    if (!adv) {
      adv = _buildAdvancedDisclosure(axisId, axisDef);
    } else {
      _refreshAdvancedDisclosure(adv, axisId, axisDef);
    }

    // Assemble if newly built elements
    if (!fs.querySelector('.preset-group')) fs.appendChild(pg);
    if (!fs.querySelector('p.hint')) fs.appendChild(hint);
    if (!fs.querySelector('details.advanced')) fs.appendChild(adv);

    return fs;
  }

  // DOM element templates (string literals for static analysis / test assertions):
  // <details class="advanced"> — Advanced disclosures are closed by default.
  // <p class="hint"> — Hint text is always visible in the DOM (FR-051, US6 AC-1).

  function _buildAdvancedDisclosure(axisId, axisDef) {
    const adv = document.createElement('details');
    adv.className = 'advanced';

    const summary = document.createElement('summary');
    summary.textContent = 'Advanced';
    adv.appendChild(summary);

    _populateAdvancedContent(adv, axisId, axisDef);
    return adv;
  }

  function _refreshAdvancedDisclosure(adv, axisId, axisDef) {
    // Remove old controls but keep the summary
    Array.from(adv.children).forEach(ch => {
      if (ch.tagName !== 'SUMMARY') adv.removeChild(ch);
    });
    _populateAdvancedContent(adv, axisId, axisDef);
  }

  function _populateAdvancedContent(adv, axisId, axisDef) {
    const advHints = window.BRIEF_ADVANCED_HINTS || {};

    // Collect all raw field names this axis touches
    const fields = window.collectAxisFields ? window.collectAxisFields(axisId) : [];

    // For curves axis, add the full 5-way curves_mode selector
    const fieldSet = new Set(fields);
    if (axisId === 'curves') {
      ['all', 'brightness', 'speed', 'color', 'none'].forEach(v => fieldSet.add('curves_mode'));
    }

    // Special handling: for each distinct raw field, build a control
    const seenFields = new Set();
    axisDef.presets.forEach(p => {
      Object.keys(p.raw).forEach(k => seenFields.add(k));
    });
    if (axisId === 'curves') seenFields.add('curves_mode');

    seenFields.forEach(fieldName => {
      const ctrl = document.createElement('div');
      ctrl.className = 'advanced-control';
      ctrl.dataset.field = fieldName;

      const lbl = document.createElement('label');
      lbl.htmlFor = `adv-${axisId}-${fieldName}`;
      lbl.textContent = fieldName;
      ctrl.appendChild(lbl);

      const hintP = document.createElement('p');
      hintP.className = 'hint';
      hintP.textContent = advHints[fieldName] || fieldName;
      ctrl.appendChild(hintP);

      const currentVal = _state
        ? (_state.advanced.hasOwnProperty(fieldName) ? _state.advanced[fieldName] : _getPresetFieldValue(axisId, fieldName))
        : '';

      // Determine input type from known field types
      if (typeof currentVal === 'boolean' || _isBoolField(fieldName)) {
        const inp = document.createElement('input');
        inp.type = 'checkbox';
        inp.id = `adv-${axisId}-${fieldName}`;
        const boolVal = currentVal === true || currentVal === 'true';
        inp.checked = boolVal;
        inp.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, inp.checked));
        ctrl.appendChild(inp);
      } else if (fieldName === 'curves_mode') {
        const sel = document.createElement('select');
        sel.id = `adv-${axisId}-${fieldName}`;
        ['all', 'brightness', 'speed', 'color', 'none'].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          o.selected = (currentVal === opt);
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, sel.value));
        ctrl.appendChild(sel);
      } else if (fieldName === 'duration_feel') {
        const sel = document.createElement('select');
        sel.id = `adv-${axisId}-${fieldName}`;
        ['auto', 'snappy', 'balanced', 'flowing'].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          o.selected = (currentVal === opt || (!currentVal && opt === 'auto'));
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, sel.value));
        ctrl.appendChild(sel);
      } else if (fieldName === 'accent_strength') {
        const sel = document.createElement('select');
        sel.id = `adv-${axisId}-${fieldName}`;
        ['auto', 'subtle', 'strong'].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          o.selected = (currentVal === opt || (!currentVal && opt === 'auto'));
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, sel.value));
        ctrl.appendChild(sel);
      } else if (fieldName === 'transition_mode') {
        const sel = document.createElement('select');
        sel.id = `adv-${axisId}-${fieldName}`;
        ['none', 'subtle', 'dramatic'].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          o.selected = (currentVal === opt);
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, sel.value));
        ctrl.appendChild(sel);
      } else if (fieldName === 'genre') {
        const sel = document.createElement('select');
        sel.id = `adv-${axisId}-${fieldName}`;
        ['any', 'pop', 'rock', 'classical'].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          o.selected = (currentVal === opt);
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, sel.value));
        ctrl.appendChild(sel);
      } else if (fieldName === 'occasion') {
        const sel = document.createElement('select');
        sel.id = `adv-${axisId}-${fieldName}`;
        ['general', 'christmas', 'halloween'].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          o.selected = (currentVal === opt);
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, sel.value));
        ctrl.appendChild(sel);
      } else if (fieldName === 'mood_intent') {
        const sel = document.createElement('select');
        sel.id = `adv-${axisId}-${fieldName}`;
        ['auto', 'party', 'emotional', 'dramatic', 'playful'].forEach(opt => {
          const o = document.createElement('option');
          o.value = opt;
          o.textContent = opt;
          o.selected = (currentVal === opt || (!currentVal && opt === 'auto'));
          sel.appendChild(o);
        });
        sel.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, sel.value));
        ctrl.appendChild(sel);
      } else {
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.id = `adv-${axisId}-${fieldName}`;
        inp.value = currentVal !== undefined && currentVal !== null ? String(currentVal) : '';
        inp.addEventListener('change', () => _onAdvancedChange(axisId, fieldName, inp.value));
        ctrl.appendChild(inp);
      }

      adv.appendChild(ctrl);
    });
  }

  function _isBoolField(fieldName) {
    return ['focused_vocabulary', 'embrace_repetition', 'tier_selection',
            'palette_restraint', 'duration_scaling', 'beat_accent_effects'].includes(fieldName);
  }

  function _getPresetFieldValue(axisId, fieldName) {
    if (!_state) return undefined;
    const axisDef = window.BRIEF_PRESETS[axisId];
    if (!axisDef) return undefined;
    const preset = axisDef.presets.find(p => p.id === _state.axes[axisId].value);
    if (!preset) return undefined;
    return preset.raw[fieldName];
  }

  // ---------------------------------------------------------------------------
  // Per-section overrides table
  // ---------------------------------------------------------------------------

  function _renderPerSectionTable() {
    const tbody = document.getElementById('per-section-tbody');
    if (!tbody || !_state) return;
    tbody.innerHTML = '';

    const sections = _state._sections || [];
    if (sections.length === 0) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 5;
      td.textContent = '(no sections detected)';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    const themes = _state._themes || [];
    const overrideMap = {};
    (_state.per_section_overrides || []).forEach(row => {
      overrideMap[row.section_index] = row.theme_slug;
    });

    sections.forEach(sec => {
      const tr = document.createElement('tr');
      const idx = sec.section_index !== undefined ? sec.section_index : sec.index;

      // # column
      const tdIdx = document.createElement('td');
      tdIdx.textContent = idx;
      tr.appendChild(tdIdx);

      // Section label
      const tdLabel = document.createElement('td');
      tdLabel.textContent = sec.label || '—';
      tr.appendChild(tdLabel);

      // Time range mm:ss – mm:ss
      const tdTime = document.createElement('td');
      tdTime.textContent = `${_fmtMs(sec.start_ms)} – ${_fmtMs(sec.end_ms)}`;
      tr.appendChild(tdTime);

      // Energy
      const tdEnergy = document.createElement('td');
      tdEnergy.textContent = sec.energy_score !== undefined ? sec.energy_score : '—';
      tr.appendChild(tdEnergy);

      // Theme selector
      const tdTheme = document.createElement('td');
      const sel = document.createElement('select');
      sel.setAttribute('aria-label', `Theme override for section ${idx}`);

      const autoOpt = document.createElement('option');
      autoOpt.value = 'auto';
      autoOpt.textContent = 'Auto';
      sel.appendChild(autoOpt);

      const savedSlug = overrideMap[idx];
      let slugStillValid = false;

      themes.forEach(theme => {
        const opt = document.createElement('option');
        opt.value = theme.slug;
        opt.textContent = theme.name || theme.slug;
        if (savedSlug && theme.slug === savedSlug) {
          slugStillValid = true;
          opt.selected = true;
        }
        sel.appendChild(opt);
      });

      // Stale override handling (FR-033 edge case)
      if (savedSlug && savedSlug !== 'auto' && !slugStillValid) {
        const chip = document.createElement('span');
        chip.className = 'stale-chip';
        chip.title = `Theme "${savedSlug}" not found in catalog — will be cleared on next submit.`;
        chip.textContent = '!';
        tdTheme.appendChild(chip);
        // Drop from in-memory state
        _state.per_section_overrides = _state.per_section_overrides.filter(
          r => r.section_index !== idx
        );
      }

      if (!savedSlug || savedSlug === 'auto') {
        sel.value = 'auto';
      }

      sel.addEventListener('change', () => {
        const slug = sel.value;
        // Remove old override for this index
        _state.per_section_overrides = _state.per_section_overrides.filter(
          r => r.section_index !== idx
        );
        if (slug && slug !== 'auto') {
          _state.per_section_overrides.push({ section_index: idx, theme_slug: slug });
        }
        _markDirty();
      });

      tdTheme.appendChild(sel);
      tr.appendChild(tdTheme);

      tbody.appendChild(tr);
    });
  }

  function _fmtMs(ms) {
    if (!ms && ms !== 0) return '?';
    const totalSec = Math.floor(ms / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------

  function _onPresetChange(axisId, presetId) {
    if (!_state) return;
    _state.axes[axisId] = { value: presetId, origin: 'user' };

    // Sync Advanced controls to the preset's raw values (remove axis-specific
    // advanced overrides so the preset is authoritative again).
    const axisDef = window.BRIEF_PRESETS[axisId];
    if (axisDef) {
      const preset = axisDef.presets.find(p => p.id === presetId);
      if (preset) {
        const axisFields = window.collectAxisFields ? window.collectAxisFields(axisId) : [];
        axisFields.forEach(k => {
          if (_state.advanced.hasOwnProperty(k)) {
            delete _state.advanced[k];
          }
        });
        // Set preset raw values (so Advanced reflects them when opened)
        Object.keys(preset.raw).forEach(k => {
          _state.advanced[k] = preset.raw[k];
        });
        // If preset is auto, remove its entries (auto = omit everything)
        if (Object.keys(preset.raw).length === 0) {
          const axisF = window.collectAxisFields ? window.collectAxisFields(axisId) : [];
          axisF.forEach(k => delete _state.advanced[k]);
        }
      }
    }

    // If this is the mood axis, apply smart defaults
    if (axisId === 'mood_intent') {
      _applyMoodDefaults(presetId);
    }

    _markDirty();
    _reRenderAxis(axisId);

    // Re-render siblings that may have been affected by mood
    if (axisId === 'mood_intent') {
      ['transitions', 'accents', 'variation', 'palette', 'duration'].forEach(sibling => {
        _reRenderAxis(sibling);
      });
    }
  }

  function _onAdvancedChange(axisId, fieldName, value) {
    if (!_state) return;
    _state.advanced[fieldName] = value;
    _markDirty();
    // Re-render the axis legend chips (custom detection)
    _reRenderAxis(axisId);
  }

  function _applyMoodDefaults(mood) {
    if (!_state) return;
    if (!MOOD_DEFAULTS[mood]) {
      // mood=auto: revert all "via-mood" siblings back to auto
      AXES.forEach(axis => {
        if (_state.axes[axis].origin === 'via-mood') {
          _state.axes[axis] = { value: 'auto', origin: 'default' };
        }
      });
      return;
    }
    const defaults = MOOD_DEFAULTS[mood];
    Object.keys(defaults).forEach(axis => {
      const origin = _state.axes[axis].origin;
      if (origin === 'default' || origin === 'via-mood') {
        _state.axes[axis] = { value: defaults[axis], origin: 'via-mood' };
      }
    });
  }

  function _markDirty() {
    if (!_state) return;
    _state._dirty = true;
    // Dispatch brief:dirty event so the workspace shell can update tab badge
    document.dispatchEvent(new CustomEvent('brief:dirty'));
  }

  function _markClean() {
    if (!_state) return;
    _state._dirty = false;
    document.dispatchEvent(new CustomEvent('brief:clean'));
  }

  // ---------------------------------------------------------------------------
  // Full re-render of one axis fieldset
  // ---------------------------------------------------------------------------

  function _reRenderAxis(axisId) {
    if (!_state) return;
    _buildAxisFieldset(axisId, _state.axes[axisId]);
  }

  // ---------------------------------------------------------------------------
  // Reset to Auto
  // ---------------------------------------------------------------------------

  function _resetToAuto() {
    if (!_state) return;
    AXES.forEach(axis => {
      _state.axes[axis] = { value: 'auto', origin: 'default' };
    });
    _state.advanced = {};
    _state.per_section_overrides = [];
    _markDirty();
    _renderAllAxes();
    _renderPerSectionTable();
  }

  // ---------------------------------------------------------------------------
  // Full render
  // ---------------------------------------------------------------------------

  function _renderAllAxes() {
    AXES.forEach(axis => {
      _buildAxisFieldset(axis, _state.axes[axis]);
    });
  }

  // ---------------------------------------------------------------------------
  // Generate button logic (Phase 6 — wired here as a generate-and-switch handler)
  // ---------------------------------------------------------------------------

  async function _onGenerateClick() {
    if (!_state) return;

    const btn = document.getElementById('btn-brief-generate');
    const concMsg = document.getElementById('brief-concurrent-message');
    if (btn) btn.disabled = true;

    try {
      // Step 1: PUT /brief/<hash>
      const briefJson = _stateToBriefJson(_state);
      const putResp = await fetch(`/brief/${encodeURIComponent(_state._sourceHash)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(briefJson),
      });

      if (!putResp.ok) {
        const data = await putResp.json().catch(() => ({}));
        if (data.field) {
          _showInlineError(data.field, data.error || 'Invalid value');
        } else {
          _showInlineError(null, data.error || 'Failed to save brief');
        }
        if (btn) btn.disabled = false;
        return;
      }

      _markClean();

      // Step 2: POST /generate/<hash>
      const postBody = window.resolveBriefToPost ? window.resolveBriefToPost(briefJson) : {};
      const genResp = await fetch(`/generate/${encodeURIComponent(_state._sourceHash)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(postBody),
      });
      const genData = await genResp.json().catch(() => ({}));

      if (!genResp.ok) {
        if (genResp.status === 409 && genData.setup_required) {
          // Layout not configured — show non-blocking note
          if (concMsg) {
            concMsg.hidden = false;
            concMsg.textContent = genData.error || 'Layout not configured.';
          }
        } else if (genData.field) {
          _showInlineError(genData.field, genData.error || 'Invalid value');
        } else {
          _showInlineError(null, genData.error || 'Failed to start generation');
        }
        if (btn) btn.disabled = false;
        return;
      }

      // Check if a job was already running (409 from a concurrent-job guard,
      // handled above). A 202 means accepted.
      if (genResp.status === 202 || genData.job_id) {
        // Switch workspace shell to the Generate tab
        document.dispatchEvent(new CustomEvent('workspace:activateTab', { detail: { tab: 'generate' } }));
        // Also try the direct approach: find the Generate tab button and click it
        const generateTabBtn = document.querySelector('[data-tab="generate"]');
        if (generateTabBtn) generateTabBtn.click();
      }

    } catch (err) {
      _showInlineError(null, String(err));
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function _showInlineError(axisId, message) {
    // Remove any existing inline errors first
    document.querySelectorAll('#brief-form .inline-error').forEach(el => el.remove());

    let target;
    if (axisId) {
      // Map field name to axis id (some fields map to axes differently)
      const fieldToAxis = {
        genre: 'genre', occasion: 'occasion', mood_intent: 'mood_intent',
        focused_vocabulary: 'variation', embrace_repetition: 'variation',
        tier_selection: 'variation', palette_restraint: 'palette',
        duration_scaling: 'duration', duration_feel: 'duration',
        beat_accent_effects: 'accents', accent_strength: 'accents',
        transition_mode: 'transitions', curves_mode: 'curves',
      };
      const axis = fieldToAxis[axisId] || axisId;
      target = document.querySelector(`#axis-${axis}`);
    }
    if (!target) target = document.getElementById('brief-form');
    if (!target) return;

    const errEl = document.createElement('p');
    errEl.className = 'inline-error';
    errEl.textContent = message;
    errEl.setAttribute('role', 'alert');
    target.appendChild(errEl);
    errEl.scrollIntoView({ block: 'nearest' });
  }

  // ---------------------------------------------------------------------------
  // Timestamp display
  // ---------------------------------------------------------------------------

  function _renderUpdatedAt(updatedAt) {
    const el = document.getElementById('brief-updated-at');
    if (!el) return;
    if (updatedAt) {
      el.textContent = `Last submitted: ${new Date(updatedAt).toLocaleString()}`;
      el.hidden = false;
    } else {
      el.hidden = true;
    }
  }

  // ---------------------------------------------------------------------------
  // Data fetching helpers
  // ---------------------------------------------------------------------------

  async function _fetchThemeCatalog() {
    const themes = [];
    try {
      // Use JSON API endpoint — /themes/api/list returns themes as JSON objects with .name
      const resp = await fetch('/themes/api/list').catch(() => null);
      if (resp && resp.ok) {
        const data = await resp.json().catch(() => ({}));
        (data.themes || []).forEach(t => {
          const slug = t.slug || (typeof window.slugify === 'function' ? window.slugify(t.name) : t.name);
          themes.push({ slug, name: t.name || slug });
        });
      }
    } catch (e) {
      // Non-fatal — catalog will be empty, per-section dropdowns will only have Auto
    }
    return themes;
  }

  async function _fetchSections(sourceHash) {
    try {
      const resp = await fetch(`/song/${encodeURIComponent(sourceHash)}/sections`);
      if (!resp.ok) return [];
      const data = await resp.json().catch(() => ({}));
      return data.sections || [];
    } catch (e) {
      return [];
    }
  }

  // ---------------------------------------------------------------------------
  // mountBriefTab — public entry point
  // ---------------------------------------------------------------------------

  async function mountBriefTab(root, sourceHash) {
    // Load the brief-tab.html fragment into root if it doesn't already have it
    if (!root.querySelector('#brief-tab')) {
      try {
        const resp = await fetch('/brief-tab.html');
        if (resp.ok) {
          const html = await resp.text();
          root.innerHTML = html;
        }
      } catch (e) {
        // Fragment may already be inline
      }
    }

    // Initialise state with defaults
    _state = _defaultBriefState(sourceHash);

    let persistedUpdatedAt = null;

    // Fetch persisted brief (non-blocking on 404)
    try {
      const resp = await fetch(`/brief/${encodeURIComponent(sourceHash)}`);
      if (resp.ok) {
        const json = await resp.json();
        _state = _stateFromBriefJson(json, sourceHash);
        persistedUpdatedAt = json.updated_at || null;
      }
      // 404 = no brief yet — use defaults (already set above)
    } catch (e) {
      // Network error — use defaults
    }

    // Fetch themes and sections in parallel
    const [themes, sections] = await Promise.all([
      _fetchThemeCatalog(),
      _fetchSections(sourceHash),
    ]);
    _state._themes = themes;
    _state._sections = sections;
    _state._sourceHash = sourceHash;

    // Render timestamp
    _renderUpdatedAt(persistedUpdatedAt);

    // Render all axes
    _renderAllAxes();

    // Render per-section table
    _renderPerSectionTable();

    // Wire Reset button
    const resetBtn = document.getElementById('btn-brief-reset');
    if (resetBtn) {
      resetBtn.addEventListener('click', _resetToAuto);
    }

    // Wire Generate button
    const generateBtn = document.getElementById('btn-brief-generate');
    if (generateBtn) {
      generateBtn.addEventListener('click', _onGenerateClick);
    }

    // Wire Clear overrides button
    const clearBtn = document.getElementById('btn-clear-overrides');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => {
        _state.per_section_overrides = [];
        _markDirty();
        _renderPerSectionTable();
      });
    }

    // Check layout for Generate button disabled state
    try {
      const settingsResp = await fetch('/generate/settings');
      if (settingsResp.ok) {
        const settings = await settingsResp.json();
        if (!settings.layout_configured && generateBtn) {
          generateBtn.disabled = true;
          generateBtn.title = 'Layout not configured — set up layout groups first.';
        }
      }
    } catch (e) {
      // Non-fatal
    }
  }

  // ---------------------------------------------------------------------------
  // Workspace shell tab badge integration
  // ---------------------------------------------------------------------------

  // Listen for tab:show / tab:hide events from song-workspace.js so we can
  // restore keyboard focus.
  let _lastFocusedId = null;
  document.addEventListener('brief:focusSave', () => {
    _lastFocusedId = document.activeElement ? document.activeElement.id : null;
  });
  document.addEventListener('brief:focusRestore', () => {
    if (_lastFocusedId) {
      const el = document.getElementById(_lastFocusedId);
      if (el) el.focus();
    }
  });

  window.mountBriefTab = mountBriefTab;
})();
