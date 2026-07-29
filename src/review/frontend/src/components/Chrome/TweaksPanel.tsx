import React, { useRef, useState } from 'react';
import { usePreferencesStore, Preferences } from 'src/store/preferences';
import { api } from 'src/api/client';
import styles from './TweaksPanel.module.css';

function persistPrefs(patch: Partial<Preferences>): void {
  api.put('/preferences', patch).catch(() => {
    // Network failure is non-fatal; local state already updated.
  });
}

const GENRES: Preferences['genre'][] = ['any', 'pop', 'rock', 'classical'];
const OCCASIONS: Preferences['occasion'][] = ['general', 'christmas', 'halloween'];

export function TweaksPanel() {
  const {
    mode, density, inspector_open, genre, occasion, randomness,
    setMode, setDensity, setPreferences,
  } = usePreferencesStore();

  // Replace-mode double-confirm state
  const [replaceConfirmPending, setReplaceConfirmPending] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);

  function handleMode(value: Preferences['mode']) {
    setMode(value);
    persistPrefs({ mode: value });
  }

  function handleDensity(value: Preferences['density']) {
    setDensity(value);
    persistPrefs({ density: value });
  }

  function handleGenre(value: Preferences['genre']) {
    setPreferences({ genre: value });
    persistPrefs({ genre: value });
  }

  function handleOccasion(value: Preferences['occasion']) {
    setPreferences({ occasion: value });
    persistPrefs({ occasion: value });
  }

  function handleRandomnessChange(value: number) {
    // Live-update the store on every drag tick for a responsive slider, but
    // only persist to the backend on release (handleRandomnessCommit) so
    // dragging doesn't spam PUT /preferences.
    setPreferences({ randomness: value });
  }

  function handleRandomnessCommit() {
    persistPrefs({ randomness: usePreferencesStore.getState().randomness });
  }

  function handleInspectorToggle() {
    const next = !inspector_open;
    setPreferences({ inspector_open: next });
    persistPrefs({ inspector_open: next });
  }

  async function handleExport() {
    const resp = await fetch('/api/v1/library/export', { method: 'POST' });
    if (!resp.ok) return;
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'library.xonset';
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleImportClick() {
    importInputRef.current?.click();
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    const formData = new FormData();
    formData.append('bundle', file);
    formData.append('mode', 'merge');
    await fetch('/api/v1/library/import', { method: 'POST', body: formData });
    // Reload the page to refresh library state
    window.location.reload();
  }

  function handleReplaceClick() {
    if (!replaceConfirmPending) {
      setReplaceConfirmPending(true);
      // Auto-cancel confirm after 5s
      setTimeout(() => setReplaceConfirmPending(false), 5000);
      return;
    }
    // Second click: proceed with replace
    setReplaceConfirmPending(false);
    importInputRef.current?.setAttribute('data-mode', 'replace');
    importInputRef.current?.click();
  }

  async function handleImportFileReplace(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    const formData = new FormData();
    formData.append('bundle', file);
    formData.append('mode', 'replace');
    await fetch('/api/v1/library/import', { method: 'POST', body: formData });
    window.location.reload();
  }

  return (
    <aside className={styles.panel}>
      <div className={styles.row}>
        <span className={styles.label}>Mode</span>
        <div className={styles.segmented}>
          <button
            data-active={String(mode === 'dark')}
            onClick={() => handleMode('dark')}
          >
            Dark
          </button>
          <button
            data-active={String(mode === 'light')}
            onClick={() => handleMode('light')}
          >
            Light
          </button>
        </div>
      </div>
      <div className={styles.row}>
        <span className={styles.label}>Density</span>
        <div className={styles.segmented}>
          <button
            data-active={String(density === 'comfortable')}
            onClick={() => handleDensity('comfortable')}
          >
            Comfortable
          </button>
          <button
            data-active={String(density === 'compact')}
            onClick={() => handleDensity('compact')}
          >
            Compact
          </button>
        </div>
      </div>
      <div className={styles.row}>
        <span className={styles.label}>Genre</span>
        <div className={styles.segmented}>
          {GENRES.map((g) => (
            <button
              key={g}
              data-active={String(genre === g)}
              data-testid={`genre-${g}`}
              onClick={() => handleGenre(g)}
            >
              {g === 'any' ? 'Any' : g.charAt(0).toUpperCase() + g.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <div className={styles.row}>
        <span className={styles.label}>Occasion</span>
        <div className={styles.segmented}>
          {OCCASIONS.map((o) => (
            <button
              key={o}
              data-active={String(occasion === o)}
              data-testid={`occasion-${o}`}
              onClick={() => handleOccasion(o)}
            >
              {o.charAt(0).toUpperCase() + o.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <div className={styles.row}>
        <span className={styles.label}>Randomness</span>
        <div className={styles.sliderRow}>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={Math.round(randomness * 100)}
            data-testid="randomness-slider"
            onChange={(e) => handleRandomnessChange(Number(e.target.value) / 100)}
            onMouseUp={handleRandomnessCommit}
            onTouchEnd={handleRandomnessCommit}
            onKeyUp={handleRandomnessCommit}
          />
          <span className={styles.sliderValue}>{Math.round(randomness * 100)}%</span>
        </div>
      </div>
      <div className={styles.row}>
        <span className={styles.label}>Inspector</span>
        <div className={styles.segmented}>
          <button
            data-active={String(inspector_open)}
            onClick={handleInspectorToggle}
          >
            {inspector_open ? 'Visible' : 'Hidden'}
          </button>
        </div>
      </div>

      {/* Library portability */}
      <div className={styles.row}>
        <span className={styles.label}>Library</span>
        <button
          data-testid="export-library-btn"
          className={styles.actionBtn}
          onClick={handleExport}
        >
          Export library
        </button>
        <button
          data-testid="import-library-btn"
          className={styles.actionBtn}
          onClick={handleImportClick}
        >
          Import (merge)
        </button>
        <button
          data-testid="replace-library-btn"
          className={styles.actionBtn}
          data-danger={String(replaceConfirmPending)}
          onClick={handleReplaceClick}
        >
          {replaceConfirmPending ? 'Confirm replace?' : 'Import (replace)'}
        </button>
      </div>

      {/* Hidden file inputs */}
      <input
        ref={importInputRef}
        type="file"
        accept=".xonset,.zip"
        style={{ display: 'none' }}
        onChange={handleImportFile}
        data-testid="import-file-input"
      />
      <input
        type="file"
        accept=".xonset,.zip"
        style={{ display: 'none' }}
        onChange={handleImportFileReplace}
        data-testid="replace-file-input"
      />
    </aside>
  );
}
