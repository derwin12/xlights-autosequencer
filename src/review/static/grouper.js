/**
 * Layout Group Editor — vanilla JS frontend
 *
 * Communicates with Flask routes:
 *   GET  /grouper/layout?path=<layout_path>
 *   POST /grouper/move
 *   POST /grouper/group/create
 *   POST /grouper/group/delete
 *   POST /grouper/group/rename
 *   POST /grouper/save
 *   POST /grouper/reset
 *   POST /grouper/export
 */

// ── Module state ──────────────────────────────────────────────────────────────

let _state = {
  layoutPath: null,
  layoutMd5: null,
  props: [],           // [{name, display_as, pixel_count, norm_x, norm_y}]
  tiers: [],           // [{tier, label, prefix, groups, ungrouped}]
  hasEdits: false,
  editedProps: new Set(),
  activeTier: 1,
  selectedProps: new Set(),   // currently selected prop names
  dragging: null,             // {propName, sourceTier, sourceGroup}
};

function esc(s) {
  var d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

// ── Initialization ────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  var path = params.get("path");
  // Fall back to last-used layout path from localStorage
  if (!path) {
    path = localStorage.getItem("xlight_layout_path") || "";
  }
  if (!path) {
    showFilePicker();
    return;
  }
  _state.layoutPath = path;
  localStorage.setItem("xlight_layout_path", path);
  loadLayout(path);

  // Wire header buttons
  document.getElementById("btn-save").addEventListener("click", saveEdits);
  document.getElementById("btn-reset").addEventListener("click", resetEdits);
  document.getElementById("btn-export").addEventListener("click", exportGrouping);

  // Wire new-group form
  document.getElementById("btn-new-group").addEventListener("click", showNewGroupForm);
  document.getElementById("btn-new-group-cancel").addEventListener("click", hideNewGroupForm);
  document.getElementById("btn-new-group-confirm").addEventListener("click", createGroup);
  document.getElementById("new-group-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") createGroup();
    if (e.key === "Escape") hideNewGroupForm();
  });

  // Wire tier tabs
  document.getElementById("tier-tabs").addEventListener("click", (e) => {
    const tab = e.target.closest(".tier-tab");
    if (tab) switchTier(parseInt(tab.dataset.tier, 10));
  });
});

// ── API calls ─────────────────────────────────────────────────────────────────

async function loadLayout(layoutPath) {
  showLoading(true);
  try {
    const res = await fetch(`/grouper/layout?path=${encodeURIComponent(layoutPath)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      showError(err.error || "Failed to load layout");
      return;
    }
    const data = await res.json();
    applyLayoutData(data);
  } catch (err) {
    showError("Network error: " + err.message);
  } finally {
    showLoading(false);
  }
}

async function postMove(moves) {
  const res = await fetch("/grouper/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layout_md5: _state.layoutMd5, moves }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || "Move failed");
  }
  return res.json();
}

async function saveEdits() {
  const res = await fetch("/grouper/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layout_md5: _state.layoutMd5 }),
  });
  const data = await res.json();
  if (data.success) {
    setEditStatus("Saved ✓", "saved");
    setTimeout(() => setEditStatus("", ""), 3000);
  }
}

async function resetEdits() {
  if (!confirm("Discard all manual edits and return to the original auto-generated grouping?")) return;
  const res = await fetch("/grouper/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layout_md5: _state.layoutMd5 }),
  });
  const data = await res.json();
  if (data.success) {
    setEditStatus("Reset to original", "saved");
    setTimeout(() => setEditStatus("", ""), 3000);
    await loadLayout(_state.layoutPath);
  }
}

async function exportGrouping() {
  const res = await fetch("/grouper/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layout_md5: _state.layoutMd5 }),
  });
  const data = await res.json();
  if (data.success) {
    showError(""); // clear error
    alert(`Exported ${data.group_count} groups to:\n${data.export_path}`);
  } else {
    showError(data.error || "Export failed");
  }
}

async function apiCreateGroup(name) {
  const res = await fetch("/grouper/group/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layout_md5: _state.layoutMd5, tier: _state.activeTier, name }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Create failed");
  return data;
}

async function apiDeleteGroup(groupName) {
  const res = await fetch("/grouper/group/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layout_md5: _state.layoutMd5, group_name: groupName }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Delete failed");
  return data;
}

async function apiRenameGroup(oldName, newName) {
  const res = await fetch("/grouper/group/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ layout_md5: _state.layoutMd5, old_name: oldName, new_name: newName }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Rename failed");
  return data;
}

// ── State management ──────────────────────────────────────────────────────────

function applyLayoutData(data) {
  _state.layoutMd5 = data.layout_md5;
  _state.props = data.props || [];
  _state.tiers = data.tiers || [];
  _state.hasEdits = data.has_edits || false;
  _state.editedProps = new Set(data.edited_props || []);
  _state.selectedProps = new Set();

  document.getElementById("tier-tabs").style.display = "";
  document.getElementById("tier-content").style.display = "";

  if (_state.props.length === 0) {
    document.getElementById("empty-banner").style.display = "";
  } else {
    document.getElementById("empty-banner").style.display = "none";
  }

  document.getElementById("btn-save").disabled = false;
  document.getElementById("btn-reset").disabled = !_state.hasEdits;
  document.getElementById("btn-export").disabled = false;

  updateExcludedBanner();
  renderTierTab(_state.activeTier);
}

function updateExcludedBanner() {
  // Find props in no group across all tiers
  const inAnyGroup = new Set();
  for (const tier of _state.tiers) {
    for (const grp of tier.groups) {
      for (const m of grp.members) inAnyGroup.add(m);
    }
  }
  const excluded = _state.props.map(p => p.name).filter(n => !inAnyGroup.has(n));
  const banner = document.getElementById("excluded-banner");
  if (excluded.length > 0) {
    document.getElementById("excluded-list").textContent = excluded.join(", ");
    banner.style.display = "";
  } else {
    banner.style.display = "none";
  }
}

function switchTier(tierNum) {
  _state.activeTier = tierNum;
  _state.selectedProps = new Set();

  document.querySelectorAll(".tier-tab").forEach(tab => {
    tab.classList.toggle("active", parseInt(tab.dataset.tier, 10) === tierNum);
  });

  hideNewGroupForm();
  renderTierTab(tierNum);
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function renderTierTab(tierNum) {
  const tierData = _state.tiers.find(t => t.tier === tierNum);
  const container = document.getElementById("groups-container");
  const ungroupedList = document.getElementById("ungrouped-list");
  const tierLabel = document.getElementById("tier-label");

  if (!tierData) {
    container.innerHTML = '<p style="color:#666;font-size:12px">No data for this tier.</p>';
    ungroupedList.innerHTML = '<span class="ungrouped-empty-hint">No ungrouped props in this tier.</span>';
    return;
  }

  tierLabel.textContent = `Tier ${tierNum}: ${tierData.label}`;

  // Render groups
  container.innerHTML = "";
  for (const grp of tierData.groups) {
    container.appendChild(renderGroupCard(grp, tierNum));
  }

  // Render ungrouped
  ungroupedList.innerHTML = "";
  ungroupedList.dataset.tier = tierNum;
  if (tierData.ungrouped.length === 0) {
    ungroupedList.innerHTML = '<span class="ungrouped-empty-hint">No ungrouped props in this tier.</span>';
  } else {
    for (const propName of tierData.ungrouped) {
      const propMeta = _state.props.find(p => p.name === propName);
      ungroupedList.appendChild(renderPropItem(propName, propMeta, tierNum, null));
    }
  }
}

function renderGroupCard(grp, tierNum) {
  const card = document.createElement("div");
  card.className = "group-card";
  card.dataset.groupName = grp.name;
  card.dataset.tier = tierNum;

  // Header
  const header = document.createElement("div");
  header.className = "group-card-header";

  const nameEl = document.createElement("span");
  nameEl.className = "group-name";
  nameEl.textContent = grp.name;

  const actions = document.createElement("div");
  actions.className = "group-card-actions";

  const renameBtn = document.createElement("button");
  renameBtn.className = "group-action-btn rename";
  renameBtn.title = "Rename";
  renameBtn.textContent = "✏";
  renameBtn.addEventListener("click", () => startRenameGroup(card, grp.name, nameEl));

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "group-action-btn delete";
  deleteBtn.title = "Delete group";
  deleteBtn.textContent = "✕";
  deleteBtn.addEventListener("click", () => deleteGroup(grp.name));

  actions.appendChild(renameBtn);
  actions.appendChild(deleteBtn);
  header.appendChild(nameEl);
  header.appendChild(actions);

  // Prop list (drop target)
  const propList = document.createElement("div");
  propList.className = "prop-list";
  propList.dataset.group = grp.name;
  propList.dataset.tier = tierNum;

  propList.addEventListener("dragover", handleDragOver);
  propList.addEventListener("drop", handleDrop);
  propList.addEventListener("dragleave", handleDragLeave);

  for (const memberName of grp.members) {
    const propMeta = _state.props.find(p => p.name === memberName);
    propList.appendChild(renderPropItem(memberName, propMeta, tierNum, grp.name));
  }

  card.appendChild(header);
  card.appendChild(propList);
  return card;
}

function renderPropItem(propName, propMeta, tierNum, groupName) {
  const item = document.createElement("div");
  item.className = "prop-item";
  item.draggable = true;
  item.dataset.propName = propName;
  item.dataset.tier = tierNum;
  item.dataset.group = groupName || "__ungrouped__";

  if (_state.editedProps.has(propName)) {
    const dot = document.createElement("span");
    dot.className = "prop-edited-dot";
    dot.title = "Manually moved";
    item.appendChild(dot);
  }

  const nameEl = document.createElement("span");
  nameEl.className = "prop-name";
  nameEl.textContent = propName;
  item.appendChild(nameEl);

  if (propMeta) {
    const meta = document.createElement("span");
    meta.className = "prop-meta";
    meta.textContent = `${propMeta.pixel_count}px`;
    item.appendChild(meta);
  }

  // Drag events
  item.addEventListener("dragstart", (e) => handleDragStart(e, propName, tierNum, groupName));
  item.addEventListener("dragend", handleDragEnd);

  // Click to select/deselect
  item.addEventListener("click", (e) => {
    if (e.shiftKey || e.ctrlKey || e.metaKey) {
      togglePropSelection(item, propName);
    } else {
      clearSelection();
      togglePropSelection(item, propName);
    }
  });

  if (_state.selectedProps.has(propName)) {
    item.classList.add("selected");
  }

  return item;
}

// ── Drag and drop ─────────────────────────────────────────────────────────────

function handleDragStart(e, propName, tierNum, groupName) {
  // If dragging a non-selected item, clear selection and select just this one
  if (!_state.selectedProps.has(propName)) {
    clearSelection();
    _state.selectedProps.add(propName);
    e.target.classList.add("selected");
  }

  _state.dragging = { tierNum, sourceGroup: groupName };
  e.target.classList.add("dragging");
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", propName);
}

function handleDragEnd(e) {
  e.target.classList.remove("dragging");
  document.querySelectorAll(".drag-over").forEach(el => el.classList.remove("drag-over"));
}

function handleDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
  const target = e.currentTarget;
  target.classList.add("drag-over");
}

function handleDragLeave(e) {
  e.currentTarget.classList.remove("drag-over");
}

async function handleDrop(e) {
  e.preventDefault();
  e.currentTarget.classList.remove("drag-over");

  const toGroup = e.currentTarget.dataset.group === "__ungrouped__"
    ? null
    : e.currentTarget.dataset.group;
  const tierNum = parseInt(e.currentTarget.dataset.tier, 10);
  const { tierNum: fromTier, sourceGroup } = _state.dragging || {};

  if (fromTier !== tierNum) return; // cross-tier drops not allowed

  // Build moves for all selected props
  const propsToMove = [..._state.selectedProps];
  if (propsToMove.length === 0) return;

  const moves = propsToMove
    .filter(pn => {
      // Skip if already in target group
      const tierData = _state.tiers.find(t => t.tier === tierNum);
      if (!tierData) return false;
      if (toGroup === null) {
        return !tierData.ungrouped.includes(pn);
      }
      const grp = tierData.groups.find(g => g.name === toGroup);
      return grp && !grp.members.includes(pn);
    })
    .map(pn => {
      // Find current group for this prop in this tier
      const tierData = _state.tiers.find(t => t.tier === tierNum);
      let fromGroup = null;
      if (tierData) {
        for (const grp of tierData.groups) {
          if (grp.members.includes(pn)) { fromGroup = grp.name; break; }
        }
      }
      return { prop_name: pn, tier: tierNum, from_group: fromGroup, to_group: toGroup };
    });

  if (moves.length === 0) return;

  try {
    const data = await postMove(moves);
    // Update local state for the tier
    const tierIdx = _state.tiers.findIndex(t => t.tier === tierNum);
    if (tierIdx >= 0) {
      _state.tiers[tierIdx].groups = data.groups;
      _state.tiers[tierIdx].ungrouped = data.ungrouped;
    }
    for (const pn of data.edited_props || []) _state.editedProps.add(pn);
    _state.hasEdits = true;
    document.getElementById("btn-reset").disabled = false;
    clearSelection();
    updateExcludedBanner();
    renderTierTab(tierNum);
    setEditStatus("Unsaved changes", "unsaved");
  } catch (err) {
    showError(err.message);
  }
}

// ── Selection ─────────────────────────────────────────────────────────────────

function togglePropSelection(item, propName) {
  if (_state.selectedProps.has(propName)) {
    _state.selectedProps.delete(propName);
    item.classList.remove("selected");
  } else {
    _state.selectedProps.add(propName);
    item.classList.add("selected");
  }
}

function clearSelection() {
  _state.selectedProps = new Set();
  document.querySelectorAll(".prop-item.selected").forEach(el => el.classList.remove("selected"));
}

// ── Group CRUD ────────────────────────────────────────────────────────────────

function showNewGroupForm() {
  const form = document.getElementById("new-group-form");
  const input = document.getElementById("new-group-name");
  const tierData = _state.tiers.find(t => t.tier === _state.activeTier);
  if (tierData) input.placeholder = `e.g. ${tierData.prefix}MyGroup`;
  form.style.display = "";
  input.value = "";
  input.focus();
}

function hideNewGroupForm() {
  document.getElementById("new-group-form").style.display = "none";
  document.getElementById("new-group-name").value = "";
}

async function createGroup() {
  const name = document.getElementById("new-group-name").value.trim();
  if (!name) return;
  try {
    const data = await apiCreateGroup(name);
    hideNewGroupForm();
    // Add new group to local tier state
    const tierIdx = _state.tiers.findIndex(t => t.tier === _state.activeTier);
    if (tierIdx >= 0) {
      _state.tiers[tierIdx].groups.push({ name: data.group.name, members: [], is_user_created: true });
    }
    _state.hasEdits = true;
    document.getElementById("btn-reset").disabled = false;
    renderTierTab(_state.activeTier);
    setEditStatus("Unsaved changes", "unsaved");
  } catch (err) {
    showError(err.message);
  }
}

async function deleteGroup(groupName) {
  if (!confirm(`Delete group "${groupName}"? Its members will move to Ungrouped.`)) return;
  try {
    const data = await apiDeleteGroup(groupName);
    // Update local tier state
    const tierIdx = _state.tiers.findIndex(t => t.tier === _state.activeTier);
    if (tierIdx >= 0) {
      _state.tiers[tierIdx].groups = _state.tiers[tierIdx].groups.filter(g => g.name !== groupName);
      for (const pn of data.displaced_props || []) {
        if (!_state.tiers[tierIdx].ungrouped.includes(pn)) {
          _state.tiers[tierIdx].ungrouped.push(pn);
        }
      }
    }
    _state.hasEdits = true;
    document.getElementById("btn-reset").disabled = false;
    updateExcludedBanner();
    renderTierTab(_state.activeTier);
    setEditStatus("Unsaved changes", "unsaved");
  } catch (err) {
    showError(err.message);
  }
}

function startRenameGroup(card, oldName, nameEl) {
  const input = document.createElement("input");
  input.className = "group-name-input";
  input.value = oldName;
  nameEl.replaceWith(input);
  input.focus();
  input.select();

  const finish = async () => {
    const newName = input.value.trim();
    if (!newName || newName === oldName) {
      input.replaceWith(nameEl);
      return;
    }
    try {
      const data = await apiRenameGroup(oldName, newName);
      nameEl.textContent = data.group.name;
      input.replaceWith(nameEl);
      card.dataset.groupName = data.group.name;
      // Update local state
      const tierIdx = _state.tiers.findIndex(t => t.tier === _state.activeTier);
      if (tierIdx >= 0) {
        const grp = _state.tiers[tierIdx].groups.find(g => g.name === oldName);
        if (grp) grp.name = data.group.name;
      }
      _state.hasEdits = true;
      document.getElementById("btn-reset").disabled = false;
      renderTierTab(_state.activeTier);
      setEditStatus("Unsaved changes", "unsaved");
    } catch (err) {
      input.replaceWith(nameEl);
      showError(err.message);
    }
  };

  input.addEventListener("blur", finish);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); finish(); }
    if (e.key === "Escape") { input.replaceWith(nameEl); }
  });
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function showLoading(visible) {
  document.getElementById("loading-banner").style.display = visible ? "" : "none";
}

// ── File picker ──────────────────────────────────────────────────────────────

function showFilePicker() {
  document.getElementById("layout-picker").style.display = "";
  // Fetch starting roots
  fetch("/grouper/browse")
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.roots) {
        renderPickerRoots(data.roots);
      }
    })
    .catch(function() {
      document.getElementById("picker-list").innerHTML =
        '<div class="picker-error">Could not load directories.</div>';
    });
}

function renderPickerRoots(roots) {
  var list = document.getElementById("picker-list");
  var bc = document.getElementById("picker-breadcrumb");
  bc.innerHTML = '<span class="picker-breadcrumb-seg" style="color:#888;cursor:default">Choose a starting location</span>';
  list.innerHTML = "";
  roots.forEach(function(r) {
    var item = document.createElement("div");
    item.className = "picker-item picker-item-dir";
    item.innerHTML =
      '<span class="picker-item-icon">&#128193;</span>' +
      '<span class="picker-item-name">' + esc(r.name) + '</span>' +
      '<span class="picker-item-hint">' + esc(r.path) + '</span>';
    item.addEventListener("click", function() { browseDir(r.path); });
    list.appendChild(item);
  });
}

function browseDir(dirPath) {
  var list = document.getElementById("picker-list");
  list.innerHTML = '<div class="picker-loading">Loading\u2026</div>';

  fetch("/grouper/browse?dir=" + encodeURIComponent(dirPath))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.error) {
        list.innerHTML = '<div class="picker-error">' + esc(data.error) + '</div>';
        return;
      }
      renderPickerBreadcrumb(data.current);
      renderPickerContents(data);
    })
    .catch(function() {
      list.innerHTML = '<div class="picker-error">Could not browse directory.</div>';
    });
}

function renderPickerBreadcrumb(currentPath) {
  var bc = document.getElementById("picker-breadcrumb");
  bc.innerHTML = "";
  // Split path into segments and build clickable breadcrumb
  var parts = currentPath.split("/");
  var built = "";
  parts.forEach(function(part, i) {
    if (i === 0 && part === "") {
      // Root "/"
      built = "/";
      var seg = document.createElement("span");
      seg.className = "picker-breadcrumb-seg";
      seg.textContent = "/";
      seg.addEventListener("click", function() { browseDir("/"); });
      bc.appendChild(seg);
      return;
    }
    if (!part) return;
    built += (built.endsWith("/") ? "" : "/") + part;
    var sep = document.createElement("span");
    sep.className = "picker-breadcrumb-sep";
    sep.textContent = " / ";
    bc.appendChild(sep);
    var seg = document.createElement("span");
    seg.className = "picker-breadcrumb-seg";
    seg.textContent = part;
    var target = built;
    seg.addEventListener("click", function() { browseDir(target); });
    bc.appendChild(seg);
  });
}

function renderPickerContents(data) {
  var list = document.getElementById("picker-list");
  list.innerHTML = "";

  // Parent directory link
  if (data.parent) {
    var up = document.createElement("div");
    up.className = "picker-item picker-item-dir";
    up.innerHTML =
      '<span class="picker-item-icon">\u2191</span>' +
      '<span class="picker-item-name">..</span>' +
      '<span class="picker-item-hint">Parent directory</span>';
    up.addEventListener("click", function() { browseDir(data.parent); });
    list.appendChild(up);
  }

  // Directories
  data.dirs.forEach(function(d) {
    var item = document.createElement("div");
    item.className = "picker-item picker-item-dir";
    item.innerHTML =
      '<span class="picker-item-icon">&#128193;</span>' +
      '<span class="picker-item-name">' + esc(d.name) + '</span>';
    item.addEventListener("click", function() { browseDir(d.path); });
    list.appendChild(item);
  });

  // XML files
  data.files.forEach(function(f) {
    var item = document.createElement("div");
    item.className = "picker-item picker-item-xml";
    var isLayout = f.name.toLowerCase().indexOf("rgbeffects") >= 0;
    item.innerHTML =
      '<span class="picker-item-icon">\u2B25</span>' +
      '<span class="picker-item-name">' + esc(f.name) + '</span>' +
      (isLayout ? '<span class="picker-item-hint" style="color:var(--xo-accent)">layout file</span>' : '');
    item.addEventListener("click", function() { selectLayoutFile(f.path); });
    list.appendChild(item);
  });

  if (data.dirs.length === 0 && data.files.length === 0) {
    list.innerHTML += '<div class="picker-empty">No folders or XML files in this directory.</div>';
  }
}

function selectLayoutFile(filePath) {
  _state.layoutPath = filePath;
  localStorage.setItem("xlight_layout_path", filePath);
  document.getElementById("layout-picker").style.display = "none";
  loadLayout(filePath);
  // Wire header buttons that were skipped during init
  document.getElementById("btn-save").addEventListener("click", saveEdits);
  document.getElementById("btn-reset").addEventListener("click", resetEdits);
  document.getElementById("btn-export").addEventListener("click", exportGrouping);
  document.getElementById("btn-new-group").addEventListener("click", showNewGroupForm);
  document.getElementById("btn-new-group-cancel").addEventListener("click", hideNewGroupForm);
  document.getElementById("btn-new-group-confirm").addEventListener("click", createGroup);
  document.getElementById("new-group-name").addEventListener("keydown", function(e) {
    if (e.key === "Enter") createGroup();
    if (e.key === "Escape") hideNewGroupForm();
  });
  document.getElementById("tier-tabs").addEventListener("click", function(e) {
    var tab = e.target.closest(".tier-tab");
    if (tab) switchTier(parseInt(tab.dataset.tier, 10));
  });
}

function showError(msg) {
  const el = document.getElementById("error-banner");
  if (msg) {
    el.textContent = msg;
    el.style.display = "";
  } else {
    el.style.display = "none";
  }
}

function setEditStatus(msg, cls) {
  const el = document.getElementById("edit-status");
  el.textContent = msg;
  el.className = "edit-status" + (cls ? " " + cls : "");
}

// ── Background drop → ungrouped ──────────────────────────────────────────────
// Dropping a prop onto the background (outside any group card or ungrouped list)
// moves it to ungrouped.

document.addEventListener("DOMContentLoaded", () => {
  const tierContent = document.getElementById("tier-content");
  if (!tierContent) return;

  tierContent.addEventListener("dragover", (e) => {
    // Only act if the drop target is the background, not a child .prop-list
    if (e.target.closest(".prop-list")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  });

  tierContent.addEventListener("drop", (e) => {
    if (e.target.closest(".prop-list")) return;
    e.preventDefault();

    // Delegate to the ungrouped list's drop handler
    const ungroupedList = document.getElementById("ungrouped-list");
    if (ungroupedList) {
      // Synthesize drop on the ungrouped list
      const synth = new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer: e.dataTransfer,
      });
      // handleDrop reads e.currentTarget.dataset, so call it directly
      // with ungrouped-list as the context
      const fakeEvent = {
        preventDefault() {},
        currentTarget: ungroupedList,
        dataTransfer: e.dataTransfer,
      };
      handleDrop(fakeEvent);
    }
  });
});

// Expose drop handlers to HTML (needed for ungrouped section's inline ondrop attribute)
window.handleDragOver = handleDragOver;
window.handleDrop = handleDrop;
