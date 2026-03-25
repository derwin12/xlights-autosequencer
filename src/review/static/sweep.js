'use strict';

let allResults = [];
let sortCol = 'quality_score';
let sortAsc = false;
let selected = new Set();  // indices of selected rows for comparison

async function init() {
  try {
    const resp = await fetch('/sweep-report');
    if (!resp.ok) {
      document.getElementById('status').textContent = 'No sweep results found. Run sweep-matrix first.';
      return;
    }
    const report = await resp.json();
    allResults = (report.results || []).filter(r => r.status === 'success');
    renderTable();
    document.getElementById('status').style.display = 'none';
  } catch (e) {
    document.getElementById('status').textContent = `Failed to load: ${e.message}`;
  }
}

function renderTable() {
  const filter = document.getElementById('filter-input').value.toLowerCase();
  let rows = allResults.filter(r => {
    if (!filter) return true;
    const text = `${r.algorithm} ${r.stem} ${r.result_type} ${JSON.stringify(r.parameters)}`.toLowerCase();
    return text.includes(filter);
  });

  // Sort
  rows.sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (typeof va === 'string') {
      return sortAsc ? va.localeCompare(vb) : vb.localeCompare(va);
    }
    return sortAsc ? (va - vb) : (vb - va);
  });

  const tbody = document.getElementById('results-body');
  tbody.innerHTML = '';

  rows.forEach((r, i) => {
    const globalIdx = allResults.indexOf(r);
    const tr = document.createElement('tr');
    if (selected.has(globalIdx)) tr.classList.add('selected');

    const paramStr = Object.entries(r.parameters || {}).map(([k, v]) => `${k}=${v}`).join(', ') || '—';
    const marks = r.result_type === 'timing' ? r.mark_count : `${r.sample_count || 0}s`;
    const avgInt = r.result_type === 'timing' ? `${r.avg_interval_ms}ms` : '—';

    tr.innerHTML = `
      <td class="check-col"><input type="checkbox" data-idx="${globalIdx}" ${selected.has(globalIdx) ? 'checked' : ''}></td>
      <td>${i + 1}</td>
      <td class="score">${r.quality_score.toFixed(2)}</td>
      <td>${r.result_type}</td>
      <td>${r.algorithm}</td>
      <td>${r.stem}</td>
      <td>${marks}</td>
      <td>${avgInt}</td>
      <td style="color:#888;font-size:11px;">${paramStr}</td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById('result-count').textContent = `${rows.length} of ${allResults.length} results`;
  updateCompareBar();
}

// Column sorting
document.querySelector('#results-table thead').addEventListener('click', (e) => {
  const th = e.target.closest('th');
  if (!th || !th.dataset.col) return;
  if (sortCol === th.dataset.col) {
    sortAsc = !sortAsc;
  } else {
    sortCol = th.dataset.col;
    sortAsc = false;
  }
  renderTable();
});

// Filter
document.getElementById('filter-input').addEventListener('input', () => renderTable());

// Checkbox selection
document.getElementById('results-body').addEventListener('change', (e) => {
  if (e.target.type !== 'checkbox') return;
  const idx = parseInt(e.target.dataset.idx);
  if (e.target.checked) {
    if (selected.size >= 2) {
      // Only allow 2 selections
      const first = selected.values().next().value;
      selected.delete(first);
    }
    selected.add(idx);
  } else {
    selected.delete(idx);
  }
  renderTable();
});

function updateCompareBar() {
  const bar = document.getElementById('compare-bar');
  if (selected.size >= 2) {
    bar.style.display = 'flex';
    bar.style.gap = '10px';
    bar.style.alignItems = 'center';
    const items = [...selected].map(i => allResults[i]);
    document.getElementById('compare-info').textContent =
      `Compare: ${items[0].algorithm}/${items[0].stem} vs ${items[1].algorithm}/${items[1].stem}`;
  } else if (selected.size === 1) {
    bar.style.display = 'flex';
    bar.style.gap = '10px';
    bar.style.alignItems = 'center';
    document.getElementById('compare-info').textContent = 'Select one more result to compare';
    document.getElementById('btn-compare').style.display = 'none';
  } else {
    bar.style.display = 'none';
  }
  const btn = document.getElementById('btn-compare');
  if (btn) btn.style.display = selected.size >= 2 ? '' : 'none';
}

function clearSelection() {
  selected.clear();
  renderTable();
}

function openCompare() {
  if (selected.size < 2) return;
  const indices = [...selected];
  const a = allResults[indices[0]];
  const b = allResults[indices[1]];
  // Open comparison in a new query-string view (reuses timeline with two tracks)
  const params = new URLSearchParams({
    a_algo: a.algorithm, a_stem: a.stem, a_params: JSON.stringify(a.parameters),
    b_algo: b.algorithm, b_stem: b.stem, b_params: JSON.stringify(b.parameters),
  });
  alert(`Comparison view: ${a.algorithm}/${a.stem} vs ${b.algorithm}/${b.stem}\n\n(Full timeline comparison coming in next iteration)`);
}

init();
