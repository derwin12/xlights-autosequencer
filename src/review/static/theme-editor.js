/* Theme Editor — xLight AutoSequencer */
'use strict';

// ── State ───────────────────────────────────────────────────────────────────
const state = {
  themes: [],
  effects: [],
  blendModes: [],
  moods: [],
  occasions: [],
  genres: [],
  selectedTheme: null,
  editMode: false,
  dirty: false,
  editOriginalName: null,
  filterMood: '',
  filterOccasion: '',
  filterGenre: '',
  searchText: '',
};

// ── DOM refs ────────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// ── Init ────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  showLoading(true);
  await loadThemes();
  await loadEffects();
  showLoading(false);
  populateFilters();
  renderThemeList();
  bindFilterEvents();
  bindKeyboard();
  bindNewThemeButton();
  handleDeepLink();
});

function showLoading(on) {
  const list = $('#theme-list');
  if (on) {
    list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-dim)">Loading themes...</div>';
  }
}

function bindKeyboard() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.editMode) {
      handleCancel();
    }
  });
}

// ── Data Loading ────────────────────────────────────────────────────────────
async function loadThemes() {
  try {
    const resp = await fetch('/themes/api/list');
    const data = await resp.json();
    state.themes = data.themes || [];
    state.moods = data.moods || [];
    state.occasions = data.occasions || [];
    state.genres = data.genres || [];
  } catch (err) {
    console.error('Failed to load themes:', err);
    showNotification('Failed to load themes. Is the server running?', 'error');
  }
}

async function loadEffects() {
  try {
    const resp = await fetch('/themes/api/effects');
    const data = await resp.json();
    state.effects = data.effects || [];
    state.blendModes = data.blend_modes || [];
  } catch (err) {
    console.error('Failed to load effects:', err);
  }
}

// ── Filter Dropdowns ────────────────────────────────────────────────────────
function populateFilters() {
  const moodSel = $('#filter-mood');
  const occSel = $('#filter-occasion');
  const genreSel = $('#filter-genre');
  state.moods.forEach(m => {
    moodSel.appendChild(new Option(m, m));
  });
  state.occasions.forEach(o => {
    occSel.appendChild(new Option(o, o));
  });
  state.genres.forEach(g => {
    genreSel.appendChild(new Option(g, g));
  });
}

function bindFilterEvents() {
  let searchTimer = null;
  $('#search').addEventListener('input', (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.searchText = e.target.value.trim().toLowerCase();
      renderThemeList();
      updateClearButton();
    }, 150);
  });
  // Prevent form submission on Enter
  $('#search').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') e.preventDefault();
  });
  $('#filter-mood').addEventListener('change', (e) => {
    state.filterMood = e.target.value;
    renderThemeList();
    updateClearButton();
  });
  $('#filter-occasion').addEventListener('change', (e) => {
    state.filterOccasion = e.target.value;
    renderThemeList();
    updateClearButton();
  });
  $('#filter-genre').addEventListener('change', (e) => {
    state.filterGenre = e.target.value;
    renderThemeList();
    updateClearButton();
  });
  $('#btn-clear-filters').addEventListener('click', () => {
    state.searchText = '';
    state.filterMood = '';
    state.filterOccasion = '';
    state.filterGenre = '';
    $('#search').value = '';
    $('#filter-mood').value = '';
    $('#filter-occasion').value = '';
    $('#filter-genre').value = '';
    renderThemeList();
    updateClearButton();
  });
}

function updateClearButton() {
  const active = state.searchText || state.filterMood || state.filterOccasion || state.filterGenre;
  $('#btn-clear-filters').style.display = active ? '' : 'none';
}

// ── Theme List Rendering ────────────────────────────────────────────────────
function getFilteredThemes() {
  return state.themes.filter(t => {
    if (state.filterMood && t.mood !== state.filterMood) return false;
    if (state.filterOccasion && t.occasion !== state.filterOccasion) return false;
    if (state.filterGenre && t.genre !== state.filterGenre && t.genre !== 'any') return false;
    if (state.searchText) {
      const hay = (t.name + ' ' + t.intent).toLowerCase();
      if (!hay.includes(state.searchText)) return false;
    }
    return true;
  });
}

function renderThemeList() {
  const container = $('#theme-list');
  container.innerHTML = '';
  const filtered = getFilteredThemes();

  // Group by mood
  const groups = {};
  for (const mood of state.moods) {
    groups[mood] = [];
  }
  for (const t of filtered) {
    if (!groups[t.mood]) groups[t.mood] = [];
    groups[t.mood].push(t);
  }

  for (const mood of state.moods) {
    const themes = groups[mood];
    if (!themes || themes.length === 0) continue;

    // Sort alphabetically
    themes.sort((a, b) => a.name.localeCompare(b.name));

    const group = document.createElement('div');
    group.className = 'theme-group';

    const header = document.createElement('div');
    header.className = 'group-header';
    header.innerHTML = `<span class="chevron">&#9660;</span> ${mood} <span class="group-count">(${themes.length})</span>`;
    header.addEventListener('click', () => {
      group.classList.toggle('collapsed');
      header.querySelector('.chevron').innerHTML = group.classList.contains('collapsed') ? '&#9654;' : '&#9660;';
    });
    group.appendChild(header);

    const list = document.createElement('div');
    list.className = 'group-themes';
    for (const t of themes) {
      const item = document.createElement('div');
      item.className = 'theme-item' + (state.selectedTheme && state.selectedTheme.name === t.name ? ' selected' : '');
      item.dataset.name = t.name;

      let badges = '';
      if (t.is_custom) badges += '<span class="badge badge-custom">Custom</span>';
      if (t.occasion !== 'general') badges += `<span class="badge badge-occasion">${esc(t.occasion)}</span>`;
      if (t.genre !== 'any') badges += `<span class="badge badge-genre">${esc(t.genre)}</span>`;

      let swatches = '';
      for (const color of (t.palette || []).slice(0, 6)) {
        swatches += `<span class="mini-swatch" style="background:${escColor(color)}"></span>`;
      }

      item.innerHTML = `
        <div class="theme-item-name">${esc(t.name)}${badges}</div>
        <div class="theme-item-swatches">${swatches}</div>
      `;
      item.addEventListener('click', () => selectTheme(t.name));
      list.appendChild(item);
    }
    group.appendChild(list);
    container.appendChild(group);
  }
}

// ── Theme Selection ─────────────────────────────────────────────────────────
function selectTheme(name) {
  if (state.dirty) {
    if (!confirm('You have unsaved changes. Discard and continue?')) return;
    state.dirty = false;
  }
  state.editMode = false;
  const theme = state.themes.find(t => t.name === name);
  if (!theme) return;
  state.selectedTheme = theme;
  renderDetailView(theme);
  renderThemeList(); // update selection highlight
  updateUrl();
}

// ── Detail View (Read-Only) ─────────────────────────────────────────────────
function renderDetailView(theme) {
  const placeholder = $('#detail-placeholder');
  const content = $('#detail-content');
  placeholder.style.display = 'none';
  content.style.display = '';
  state.editMode = false;

  const showDelete = theme.is_custom;
  let html = '<div class="detail-toolbar">';
  html += `<button id="btn-edit" class="btn-primary">Edit</button>`;
  html += `<button id="btn-duplicate" class="btn-secondary">Duplicate</button>`;
  html += showDelete ? `<button id="btn-delete" class="btn-danger">Delete</button>` : '';
  html += '</div>';

  html += `<h2 class="detail-name">${esc(theme.name)}</h2>`;

  // Badges
  html += '<div class="detail-badges">';
  html += `<span class="badge badge-mood">${esc(theme.mood)}</span>`;
  if (theme.occasion !== 'general') html += `<span class="badge badge-occasion">${esc(theme.occasion)}</span>`;
  if (theme.genre !== 'any') html += `<span class="badge badge-genre">${esc(theme.genre)}</span>`;
  if (theme.is_custom) html += '<span class="badge badge-custom">Custom</span>';
  html += '</div>';

  // Intent
  html += `<div class="detail-section"><h3>Intent</h3><p>${esc(theme.intent)}</p></div>`;

  // Palette
  html += '<div class="detail-section"><h3>Palette</h3><div class="palette-row">';
  for (const color of theme.palette || []) {
    html += `<div class="swatch"><span class="swatch-color" style="background:${escColor(color)}"></span><span class="swatch-label">${esc(color)}</span></div>`;
  }
  html += '</div></div>';

  // Accent palette
  if (theme.accent_palette && theme.accent_palette.length > 0) {
    html += '<div class="detail-section"><h3>Accent Palette</h3><div class="palette-row">';
    for (const color of theme.accent_palette) {
      html += `<div class="swatch"><span class="swatch-color" style="background:${escColor(color)}"></span><span class="swatch-label">${esc(color)}</span></div>`;
    }
    html += '</div></div>';
  }

  // Layers
  html += '<div class="detail-section"><h3>Layers</h3><ol class="layer-list">';
  for (const layer of theme.layers || []) {
    const overrideCount = Object.keys(layer.parameter_overrides || {}).length;
    const overrideNote = overrideCount > 0 ? ` <span class="text-dim">(${overrideCount} override${overrideCount > 1 ? 's' : ''})</span>` : '';
    html += `<li><strong>${esc(layer.effect)}</strong> — ${esc(layer.blend_mode)}${overrideNote}</li>`;
  }
  html += '</ol></div>';

  // Variants
  if (theme.variants && theme.variants.length > 0) {
    html += '<div class="detail-section"><h3>Variants</h3>';
    theme.variants.forEach((v, i) => {
      html += `<div class="variant-block"><h4>Variant ${i + 1}</h4><ol class="layer-list">`;
      for (const layer of v.layers || []) {
        html += `<li><strong>${esc(layer.effect)}</strong> — ${esc(layer.blend_mode)}</li>`;
      }
      html += '</ol></div>';
    });
    html += '</div>';
  }

  content.innerHTML = html;

  // Bind buttons
  $('#btn-edit').addEventListener('click', () => enterEditMode(theme));
  $('#btn-duplicate').addEventListener('click', () => duplicateTheme(theme));
  if ($('#btn-delete')) {
    $('#btn-delete').addEventListener('click', () => deleteTheme(theme));
  }
}

// ── Duplicate ───────────────────────────────────────────────────────────────
function duplicateTheme(theme) {
  if (state.dirty) {
    if (!confirm('You have unsaved changes. Discard and continue?')) return;
  }
  const copy = JSON.parse(JSON.stringify(theme));
  let newName = theme.name + ' Copy';
  let counter = 2;
  while (state.themes.some(t => t.name.toLowerCase() === newName.toLowerCase())) {
    newName = theme.name + ' Copy ' + counter++;
  }
  copy.name = newName;
  copy.is_custom = false;
  copy.has_builtin_override = false;
  state.selectedTheme = null;
  state.editOriginalName = null;
  state.editMode = true;
  state.dirty = false;
  renderEditForm(copy);
  renderThemeList();
  updateUrl();
}

// ── Delete ──────────────────────────────────────────────────────────────────
async function deleteTheme(theme) {
  if (!confirm(`Delete theme '${theme.name}'? This action cannot be undone.`)) return;
  try {
    const resp = await fetch('/themes/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: theme.name }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showNotification(data.error, 'error');
      return;
    }
    state.selectedTheme = null;
    state.editMode = false;
    state.dirty = false;
    $('#detail-content').style.display = 'none';
    $('#detail-placeholder').style.display = '';
    await reloadThemes();
    updateUrl();
    showNotification(`Theme '${theme.name}' deleted`, 'info');
  } catch (err) {
    showNotification(`Delete failed: ${err.message}`, 'error');
  }
}

// ── Edit Form ───────────────────────────────────────────────────────────────
function enterEditMode(theme) {
  state.editMode = true;
  state.editOriginalName = theme ? theme.name : null;
  state.dirty = false;
  const data = theme ? JSON.parse(JSON.stringify(theme)) : defaultTheme();
  renderEditForm(data);
  updateUrl();
}

function defaultTheme() {
  return {
    name: '',
    mood: 'ethereal',
    occasion: 'general',
    genre: 'any',
    intent: '',
    layers: [{ effect: 'Color Wash', blend_mode: 'Normal', parameter_overrides: {} }],
    palette: ['#FFFFFF', '#FFFFFF'],
    accent_palette: [],
    variants: [],
    is_custom: false,
    has_builtin_override: false,
  };
}

function renderEditForm(theme) {
  const content = $('#detail-content');
  const placeholder = $('#detail-placeholder');
  placeholder.style.display = 'none';
  content.style.display = '';

  const isBuiltinEdit = state.editOriginalName && !theme.is_custom;
  const isOverride = theme.has_builtin_override;
  const nameReadonly = isBuiltinEdit ? 'readonly' : '';

  let html = '<div class="edit-form">';

  // Override notice
  if (isBuiltinEdit && !isOverride) {
    html += '<div class="override-notice">Editing a built-in theme will create a custom override. You can restore the original later.</div>';
  }
  if (isOverride) {
    html += '<div class="override-notice">This is a custom override of a built-in theme. <button id="btn-restore" class="btn-secondary" style="margin-left:8px">Restore Defaults</button></div>';
  }

  // Validation errors container
  html += '<div id="form-errors" class="validation-errors" style="display:none"></div>';

  // Name
  html += `<div class="form-group"><label>Name</label><input type="text" id="edit-name" value="${esc(theme.name)}" ${nameReadonly}></div>`;

  // Mood / Occasion / Genre row
  html += '<div style="display:flex;gap:8px">';
  html += `<div class="form-group" style="flex:1"><label>Mood</label><select id="edit-mood">${state.moods.map(m => `<option ${m === theme.mood ? 'selected' : ''}>${m}</option>`).join('')}</select></div>`;
  html += `<div class="form-group" style="flex:1"><label>Occasion</label><select id="edit-occasion">${state.occasions.map(o => `<option ${o === theme.occasion ? 'selected' : ''}>${o}</option>`).join('')}</select></div>`;
  html += `<div class="form-group" style="flex:1"><label>Genre</label><select id="edit-genre">${state.genres.map(g => `<option ${g === theme.genre ? 'selected' : ''}>${g}</option>`).join('')}</select></div>`;
  html += '</div>';

  // Intent
  html += `<div class="form-group"><label>Intent</label><textarea id="edit-intent">${esc(theme.intent)}</textarea></div>`;

  // Palette
  html += '<div class="form-group"><label>Palette (min 2 colors)</label><div id="palette-editor" class="palette-editor"></div></div>';

  // Accent Palette
  html += '<div class="form-group"><label>Accent Palette (optional)</label><div id="accent-palette-editor" class="palette-editor"></div></div>';

  // Layers
  html += '<div class="form-group"><label>Layers</label><div id="layer-editor" class="layer-editor"></div></div>';

  // Variants
  html += '<div class="form-group"><label>Variants</label><div id="variant-editor"></div></div>';

  // Actions
  html += '<div class="form-actions">';
  html += '<button id="btn-save" class="btn-primary">Save</button>';
  html += '<button id="btn-cancel" class="btn-secondary">Cancel</button>';
  html += '</div>';

  html += '</div>';
  content.innerHTML = html;

  // Initialize sub-components
  renderPaletteEditor('palette-editor', theme.palette || ['#FFFFFF', '#FFFFFF'], 2);
  renderPaletteEditor('accent-palette-editor', theme.accent_palette || [], 0);
  renderLayerEditor(theme.layers || []);
  renderVariantEditor(theme.variants || []);

  // Bind events
  bindFormDirtyTracking();
  $('#btn-save').addEventListener('click', handleSave);
  $('#btn-cancel').addEventListener('click', handleCancel);
  if ($('#btn-restore')) {
    $('#btn-restore').addEventListener('click', handleRestore);
  }
}

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

function escColor(color) {
  return /^#[0-9a-fA-F]{3,8}$/.test(color) ? color : '#000000';
}

function bindFormDirtyTracking() {
  const inputs = $$('#detail-content input, #detail-content select, #detail-content textarea');
  inputs.forEach(el => {
    el.addEventListener('input', () => { state.dirty = true; });
    el.addEventListener('change', () => { state.dirty = true; });
  });
}

// ── Palette Editor Component ────────────────────────────────────────────────
function renderPaletteEditor(containerId, colors, minColors) {
  const container = document.getElementById(containerId);
  container.dataset.minColors = minColors;
  container.innerHTML = '';

  colors.forEach((color, i) => {
    container.appendChild(createPaletteRow(color, i, colors.length, minColors));
  });

  const addBtn = document.createElement('button');
  addBtn.className = 'btn-secondary';
  addBtn.textContent = '+ Add Color';
  addBtn.style.marginTop = '4px';
  addBtn.addEventListener('click', () => {
    const current = getPaletteColors(containerId);
    current.push('#FFFFFF');
    renderPaletteEditor(containerId, current, minColors);
    state.dirty = true;
  });
  container.appendChild(addBtn);
}

function createPaletteRow(color, index, total, minColors) {
  const row = document.createElement('div');
  row.className = 'palette-editor-row';

  const swatch = document.createElement('span');
  swatch.className = 'swatch-color';
  swatch.style.background = color;

  const picker = document.createElement('input');
  picker.type = 'color';
  picker.value = color;
  picker.addEventListener('input', () => {
    hex.value = picker.value;
    swatch.style.background = picker.value;
    state.dirty = true;
  });

  const hex = document.createElement('input');
  hex.type = 'text';
  hex.value = color;
  hex.maxLength = 7;
  hex.addEventListener('input', () => {
    if (/^#[0-9a-fA-F]{6}$/.test(hex.value)) {
      picker.value = hex.value;
      swatch.style.background = hex.value;
    }
    state.dirty = true;
  });

  // Up/down reorder
  const upBtn = document.createElement('button');
  upBtn.className = 'btn-reorder';
  upBtn.textContent = '\u25B2';
  upBtn.disabled = index === 0;
  upBtn.addEventListener('click', () => {
    const containerId = row.parentElement.id;
    const colors = getPaletteColors(containerId);
    [colors[index - 1], colors[index]] = [colors[index], colors[index - 1]];
    renderPaletteEditor(containerId, colors, minColors);
    state.dirty = true;
  });

  const downBtn = document.createElement('button');
  downBtn.className = 'btn-reorder';
  downBtn.textContent = '\u25BC';
  downBtn.disabled = index === total - 1;
  downBtn.addEventListener('click', () => {
    const containerId = row.parentElement.id;
    const colors = getPaletteColors(containerId);
    [colors[index], colors[index + 1]] = [colors[index + 1], colors[index]];
    renderPaletteEditor(containerId, colors, minColors);
    state.dirty = true;
  });

  const removeBtn = document.createElement('button');
  removeBtn.className = 'btn-remove btn-danger';
  removeBtn.textContent = '\u00D7';
  // For accent palette (minColors=0): can remove all, but can't leave exactly 1
  const canRemove = minColors > 0 ? total > minColors : (total !== 2);
  removeBtn.disabled = !canRemove;
  removeBtn.addEventListener('click', () => {
    const containerId = row.parentElement.id;
    const colors = getPaletteColors(containerId);
    colors.splice(index, 1);
    // If accent palette would have exactly 1 color, remove it too
    if (minColors === 0 && colors.length === 1) {
      colors.splice(0, 1);
    }
    renderPaletteEditor(containerId, colors, minColors);
    state.dirty = true;
  });

  row.append(swatch, picker, hex, upBtn, downBtn, removeBtn);
  return row;
}

function getPaletteColors(containerId) {
  const rows = document.querySelectorAll(`#${containerId} .palette-editor-row`);
  return Array.from(rows).map(r => r.querySelector('input[type="text"]').value);
}

// ── Layer Stack Editor Component ────────────────────────────────────────────
function renderLayerEditor(layers) {
  const container = $('#layer-editor');
  container.innerHTML = '';

  layers.forEach((layer, i) => {
    container.appendChild(createLayerRow(layer, i, layers.length));
  });

  const addBtn = document.createElement('button');
  addBtn.className = 'btn-secondary';
  addBtn.textContent = '+ Add Layer';
  addBtn.style.marginTop = '4px';
  addBtn.addEventListener('click', () => {
    const current = getLayerData();
    current.push({ effect: '', blend_mode: 'Normal', parameter_overrides: {} });
    renderLayerEditor(current);
    state.dirty = true;
  });
  container.appendChild(addBtn);
}

function createLayerRow(layer, index, total) {
  const row = document.createElement('div');
  row.className = 'layer-editor-row';

  // Header: effect select, blend mode select, reorder, remove
  const header = document.createElement('div');
  header.className = 'layer-editor-header';

  const isBottom = index === 0;

  // Effect select
  const effectSel = document.createElement('select');
  effectSel.innerHTML = '<option value="">-- Select effect --</option>';
  const standaloneEffects = state.effects.filter(e => {
    if (isBottom) return e.layer_role !== 'modifier';
    return true;
  });
  standaloneEffects.forEach(e => {
    const opt = document.createElement('option');
    opt.value = e.name;
    opt.textContent = `${e.name} (${e.category})`;
    if (e.name === layer.effect) opt.selected = true;
    effectSel.appendChild(opt);
  });
  effectSel.addEventListener('change', () => {
    state.dirty = true;
    refreshLayerParams(row, effectSel.value, {});
  });

  // Blend mode select
  const blendSel = document.createElement('select');
  state.blendModes.forEach(bm => {
    const opt = document.createElement('option');
    opt.value = bm;
    opt.textContent = bm;
    if (bm === layer.blend_mode) opt.selected = true;
    blendSel.appendChild(opt);
  });
  if (isBottom) {
    blendSel.value = 'Normal';
    blendSel.disabled = true;
    blendSel.title = 'Bottom layer must use Normal blend mode';
  }
  blendSel.addEventListener('change', () => { state.dirty = true; });

  // Label
  const label = document.createElement('span');
  label.textContent = isBottom ? 'L1 (base)' : `L${index + 1}`;
  label.style.cssText = 'min-width:50px;color:var(--text-dim);font-size:11px';

  // Reorder buttons
  const upBtn = document.createElement('button');
  upBtn.className = 'btn-reorder';
  upBtn.textContent = '\u25B2';
  upBtn.disabled = index === 0;
  upBtn.addEventListener('click', () => {
    const layers = getLayerData();
    [layers[index - 1], layers[index]] = [layers[index], layers[index - 1]];
    renderLayerEditor(layers);
    state.dirty = true;
  });

  const downBtn = document.createElement('button');
  downBtn.className = 'btn-reorder';
  downBtn.textContent = '\u25BC';
  downBtn.disabled = index === total - 1;
  downBtn.addEventListener('click', () => {
    const layers = getLayerData();
    [layers[index], layers[index + 1]] = [layers[index + 1], layers[index]];
    renderLayerEditor(layers);
    state.dirty = true;
  });

  const removeBtn = document.createElement('button');
  removeBtn.className = 'btn-remove btn-danger';
  removeBtn.textContent = '\u00D7';
  removeBtn.disabled = total <= 1;
  removeBtn.addEventListener('click', () => {
    const layers = getLayerData();
    layers.splice(index, 1);
    renderLayerEditor(layers);
    state.dirty = true;
  });

  header.append(label, effectSel, blendSel, upBtn, downBtn, removeBtn);
  row.appendChild(header);

  // Parameter section
  const params = document.createElement('div');
  params.className = 'layer-params';
  row.appendChild(params);
  refreshLayerParams(row, layer.effect, layer.parameter_overrides || {});

  return row;
}

function refreshLayerParams(layerRow, effectName, overrides) {
  const paramsDiv = layerRow.querySelector('.layer-params');
  paramsDiv.innerHTML = '';
  if (!effectName) return;

  const effectDef = state.effects.find(e => e.name === effectName);
  if (!effectDef || !effectDef.parameters.length) return;

  effectDef.parameters.forEach(p => {
    const paramRow = document.createElement('div');
    paramRow.className = 'param-row';
    paramRow.dataset.storageName = p.storage_name;

    const label = document.createElement('label');
    label.textContent = p.name;

    const value = overrides[p.storage_name] !== undefined ? overrides[p.storage_name] : p.default;

    let input;
    if (p.widget_type === 'slider' && p.min !== null && p.max !== null) {
      input = document.createElement('input');
      input.type = 'range';
      input.min = p.min;
      input.max = p.max;
      input.step = p.value_type === 'float' ? '0.1' : '1';
      input.value = value;
      const valSpan = document.createElement('span');
      valSpan.className = 'param-value';
      valSpan.textContent = value;
      input.addEventListener('input', () => {
        valSpan.textContent = input.value;
        state.dirty = true;
      });
      paramRow.append(label, input, valSpan);
    } else if (p.widget_type === 'checkbox') {
      input = document.createElement('input');
      input.type = 'checkbox';
      input.checked = !!value;
      input.addEventListener('change', () => { state.dirty = true; });
      paramRow.append(label, input);
    } else if (p.widget_type === 'choice' && p.choices) {
      input = document.createElement('select');
      p.choices.forEach(c => {
        const opt = new Option(c, c);
        if (c === String(value)) opt.selected = true;
        input.appendChild(opt);
      });
      input.addEventListener('change', () => { state.dirty = true; });
      paramRow.append(label, input);
    } else {
      input = document.createElement('input');
      input.type = 'text';
      input.value = value;
      input.addEventListener('input', () => { state.dirty = true; });
      paramRow.append(label, input);
    }

    paramsDiv.appendChild(paramRow);
  });
}

function getLayerData() {
  const rows = $$('#layer-editor .layer-editor-row');
  return Array.from(rows).map(row => {
    const effectSel = row.querySelector('.layer-editor-header select:first-of-type');
    const blendSel = row.querySelector('.layer-editor-header select:nth-of-type(2)');
    const effectName = effectSel ? effectSel.value : '';
    const overrides = collectParamOverrides(row, effectName);

    return {
      effect: effectName,
      blend_mode: blendSel ? blendSel.value : 'Normal',
      parameter_overrides: overrides,
    };
  });
}

function collectParamOverrides(layerRow, effectName) {
  const overrides = {};
  const effectDef = state.effects.find(e => e.name === effectName);
  layerRow.querySelectorAll('.param-row').forEach(pr => {
    const storageName = pr.dataset.storageName;
    const input = pr.querySelector('input, select');
    if (!input || !storageName) return;

    let value;
    if (input.type === 'checkbox') {
      value = input.checked;
    } else if (input.type === 'range') {
      value = Number(input.value);
    } else {
      const v = input.value;
      value = isNaN(Number(v)) ? v : Number(v);
    }

    // Only include if different from default
    if (effectDef) {
      const paramDef = effectDef.parameters.find(p => p.storage_name === storageName);
      if (paramDef && value === paramDef.default) return;
    }
    overrides[storageName] = value;
  });
  return overrides;
}

// ── Variant Editor Component ────────────────────────────────────────────────
function renderVariantEditor(variants) {
  const container = $('#variant-editor');
  container.innerHTML = '';

  variants.forEach((v, i) => {
    const block = document.createElement('div');
    block.className = 'variant-block';

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:6px';
    const title = document.createElement('h4');
    title.textContent = `Variant ${i + 1}`;
    title.style.margin = '0';
    const removeBtn = document.createElement('button');
    removeBtn.className = 'btn-remove btn-danger';
    removeBtn.textContent = '\u00D7';
    removeBtn.addEventListener('click', () => {
      const data = getVariantData();
      data.splice(i, 1);
      renderVariantEditor(data);
      state.dirty = true;
    });
    header.append(title, removeBtn);
    block.appendChild(header);

    const layerContainer = document.createElement('div');
    layerContainer.className = 'layer-editor';
    layerContainer.id = `variant-layers-${i}`;
    block.appendChild(layerContainer);
    container.appendChild(block);

    // Render layers within variant
    renderVariantLayers(layerContainer, v.layers || []);
  });

  const addBtn = document.createElement('button');
  addBtn.className = 'btn-secondary';
  addBtn.textContent = '+ Add Variant';
  addBtn.style.marginTop = '4px';
  addBtn.addEventListener('click', () => {
    const data = getVariantData();
    data.push({ layers: [{ effect: 'Color Wash', blend_mode: 'Normal', parameter_overrides: {} }] });
    renderVariantEditor(data);
    state.dirty = true;
  });
  container.appendChild(addBtn);
}

function renderVariantLayers(container, layers) {
  container.innerHTML = '';
  layers.forEach((layer, i) => {
    container.appendChild(createLayerRow(layer, i, layers.length));
  });
  const addBtn = document.createElement('button');
  addBtn.className = 'btn-secondary';
  addBtn.textContent = '+ Add Layer';
  addBtn.style.marginTop = '4px';
  addBtn.addEventListener('click', () => {
    const currentLayers = getLayerDataFromContainer(container);
    currentLayers.push({ effect: '', blend_mode: 'Normal', parameter_overrides: {} });
    renderVariantLayers(container, currentLayers);
    state.dirty = true;
  });
  container.appendChild(addBtn);
}

function getLayerDataFromContainer(container) {
  const rows = container.querySelectorAll('.layer-editor-row');
  return Array.from(rows).map(row => {
    const effectSel = row.querySelector('.layer-editor-header select:first-of-type');
    const blendSel = row.querySelector('.layer-editor-header select:nth-of-type(2)');
    const effectName = effectSel ? effectSel.value : '';
    const overrides = collectParamOverrides(row, effectName);
    return {
      effect: effectName,
      blend_mode: blendSel ? blendSel.value : 'Normal',
      parameter_overrides: overrides,
    };
  });
}

function getVariantData() {
  const blocks = $$('#variant-editor .variant-block');
  return Array.from(blocks).map(block => {
    const layerContainer = block.querySelector('.layer-editor');
    return { layers: getLayerDataFromContainer(layerContainer) };
  });
}

// ── Save / Cancel / Restore ─────────────────────────────────────────────────
async function handleSave() {
  const errEl = $('#form-errors');
  if (errEl) errEl.style.display = 'none';

  const btn = $('#btn-save');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  const themeData = collectFormData();
  const body = { theme: themeData };

  // If renaming (name changed from original)
  if (state.editOriginalName && state.editOriginalName !== themeData.name) {
    body.original_name = state.editOriginalName;
  }

  try {
    const resp = await fetch('/themes/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showFormErrors(data.validation_errors || [data.error]);
      return;
    }

    state.dirty = false;
    state.editMode = false;
    await reloadThemes();
    const saved = state.themes.find(t => t.name === themeData.name);
    if (saved) {
      state.selectedTheme = saved;
      renderDetailView(saved);
      renderThemeList();
      updateUrl();
    }
    showNotification(`Theme '${themeData.name}' saved`, 'info');
  } catch (err) {
    showFormErrors([`Network error: ${err.message}`]);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save';
  }
}

function handleCancel() {
  if (state.dirty) {
    if (!confirm('Discard unsaved changes?')) return;
  }
  state.dirty = false;
  state.editMode = false;
  if (state.selectedTheme) {
    renderDetailView(state.selectedTheme);
  } else {
    $('#detail-content').style.display = 'none';
    $('#detail-placeholder').style.display = '';
  }
  updateUrl();
}

async function handleRestore() {
  const name = state.editOriginalName || (state.selectedTheme && state.selectedTheme.name);
  if (!name) return;
  if (!confirm(`Restore built-in defaults for '${name}'? Your custom override will be removed.`)) return;

  try {
    const resp = await fetch('/themes/api/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showNotification(data.error, 'error');
      return;
    }
    state.dirty = false;
    await reloadThemes();
    const restored = state.themes.find(t => t.name === name);
    if (restored) {
      state.selectedTheme = restored;
      renderDetailView(restored);
      renderThemeList();
    }
    showNotification(`Built-in '${name}' restored`, 'info');
  } catch (err) {
    showNotification(`Restore failed: ${err.message}`, 'error');
  }
}

function collectFormData() {
  return {
    name: ($('#edit-name') || {}).value || '',
    mood: ($('#edit-mood') || {}).value || 'ethereal',
    occasion: ($('#edit-occasion') || {}).value || 'general',
    genre: ($('#edit-genre') || {}).value || 'any',
    intent: ($('#edit-intent') || {}).value || '',
    palette: getPaletteColors('palette-editor'),
    accent_palette: getPaletteColors('accent-palette-editor'),
    layers: getLayerData(),
    variants: getVariantData(),
  };
}

function showFormErrors(errors) {
  const el = $('#form-errors');
  if (!el || !errors || errors.length === 0) return;
  el.style.display = '';
  el.innerHTML = '<strong>Validation errors:</strong><ul>' +
    errors.map(e => `<li>${esc(String(e))}</li>`).join('') + '</ul>';
}

// ── New Theme Button ────────────────────────────────────────────────────────
function bindNewThemeButton() {
  const btn = $('#btn-new-theme');
  if (btn) {
    btn.disabled = false;
    btn.addEventListener('click', () => {
      if (state.dirty) {
        if (!confirm('You have unsaved changes. Discard and continue?')) return;
      }
      state.selectedTheme = null;
      state.editOriginalName = null;
      enterEditMode(null);
      renderThemeList();
    });
  }
}

// ── Unsaved Changes Guard ───────────────────────────────────────────────────
window.addEventListener('beforeunload', (e) => {
  if (state.dirty) {
    e.preventDefault();
    e.returnValue = '';
  }
});

// ── Deep Link Handling ──────────────────────────────────────────────────────
function handleDeepLink() {
  const params = new URLSearchParams(window.location.search);
  const themeName = params.get('theme');
  const mode = params.get('mode');
  if (themeName) {
    const theme = state.themes.find(t => t.name.toLowerCase() === themeName.toLowerCase());
    if (theme) {
      selectTheme(theme.name);
      scrollToTheme(theme.name);
      if (mode === 'edit') {
        enterEditMode(theme);
      }
    } else {
      showNotification(`Theme '${themeName}' not found`, 'warning');
    }
  }
}

function scrollToTheme(name) {
  const item = document.querySelector(`.theme-item[data-name="${name}"]`);
  if (item) item.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ── URL Management ──────────────────────────────────────────────────────────
function updateUrl() {
  const params = new URLSearchParams();
  if (state.selectedTheme) {
    params.set('theme', state.selectedTheme.name);
    if (state.editMode) params.set('mode', 'edit');
  }
  const url = params.toString() ? `/themes?${params}` : '/themes';
  history.replaceState(null, '', url);
}

// ── Notifications ───────────────────────────────────────────────────────────
function showNotification(message, type = 'info') {
  // Remove existing
  const existing = $('.notification');
  if (existing) existing.remove();

  const el = document.createElement('div');
  el.className = `notification notification-${type}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 5000);
}

// ── Reload theme list from server ───────────────────────────────────────────
async function reloadThemes() {
  await loadThemes();
  renderThemeList();
}
