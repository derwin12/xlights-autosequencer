import React, { useMemo, useState } from 'react';
import styles from './Theme.module.css';
import { ThemeCard } from '../components/ThemeCard/ThemeCard';
import { LightsPreview } from '../components/LightsPreview/LightsPreview';
import { SectionStrip } from '../components/SectionStrip/SectionStrip';
import { Inspector } from '../components/Inspector/Inspector';
import { ParameterSliders, ParameterOverrides } from '../components/ParameterSliders/ParameterSliders';
import { MiniLights } from '../components/MiniLights/MiniLights';
import { hueShiftHex, hueShiftPalette } from '../lib/hueShift';
import type { Assignment } from 'src/store/assignments';

interface Theme {
  theme_id: string;
  name: string;
  description: string;
  accent: string;
  swatches: string[];
  default_for_kinds: string[];
  mood?: string;
  occasion?: string;
  genre?: string;
  editable?: boolean;
}

interface Section {
  index: number;
  start_ms: number;
  end_ms: number;
  kind: string;
  label: string;
}

interface Song {
  song_id: string;
  title: string;
  status: string;
  duration_ms: number;
}

interface ThemeScreenProps {
  song: Song;
  themes: Theme[];
  sections: Section[];
  assignments: Assignment[];
  onThemed: () => void;
  onAssignmentChange: (assignment: Assignment) => void;
}

const DEFAULT_OVERRIDES: ParameterOverrides = {
  brightness: 1.0,
  hit_strength: 1.0,
  dwell_time: 1.0,
  color_shift: 0.0,
};

interface EditState {
  theme: Theme;
  isNew: boolean;
  name: string;
  description: string;
  mood: string;
  occasion: string;
  genre: string;
  palette: string[];
  accent_palette: string[];
  saving: boolean;
  suggesting: boolean;
  error: string | null;
}

const BLANK_THEME: Theme = {
  theme_id: '',
  name: '',
  description: '',
  accent: '#ffffff',
  swatches: [],
  default_for_kinds: [],
  editable: true,
};

function EditDialog({
  state,
  onChange,
  onSave,
  onSuggest,
  onClose,
}: {
  state: EditState;
  onChange: (patch: Partial<EditState>) => void;
  onSave: () => void;
  onSuggest: () => void;
  onClose: () => void;
}) {
  return (
    <div className={styles.dialogOverlay} onClick={onClose}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <div className={styles.dialogHeader}>
          <span className={styles.dialogTitle}>{state.isNew ? 'New Theme' : 'Edit Theme'}</span>
          <button className={styles.dialogClose} onClick={onClose}>✕</button>
        </div>

        {state.error && <p className={styles.error}>{state.error}</p>}

        <label className={styles.fieldLabel}>Name</label>
        <input
          className={styles.fieldInput}
          value={state.name}
          onChange={(e) => onChange({ name: e.target.value })}
        />

        <label className={styles.fieldLabel}>Description / Intent</label>
        <textarea
          className={styles.fieldTextarea}
          value={state.description}
          rows={3}
          onChange={(e) => onChange({ description: e.target.value })}
        />

        <div className={styles.fieldRow}>
          <div className={styles.fieldCol}>
            <label className={styles.fieldLabel}>Mood</label>
            <select
              className={styles.fieldSelect}
              value={state.mood}
              onChange={(e) => onChange({ mood: e.target.value })}
            >
              {['ethereal', 'aggressive', 'dark', 'structural'].map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div className={styles.fieldCol}>
            <label className={styles.fieldLabel}>Occasion</label>
            <select
              className={styles.fieldSelect}
              value={state.occasion}
              onChange={(e) => onChange({ occasion: e.target.value })}
            >
              {['general', 'christmas', 'halloween'].map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          </div>
          <div className={styles.fieldCol}>
            <label className={styles.fieldLabel}>Genre</label>
            <input
              className={styles.fieldInput}
              value={state.genre}
              onChange={(e) => onChange({ genre: e.target.value })}
            />
          </div>
        </div>

        <div className={styles.fieldLabelRow}>
          <label className={styles.fieldLabel}>Palette (one hex per line)</label>
          <button
            type="button"
            className={styles.suggestBtn}
            onClick={onSuggest}
            disabled={state.suggesting}
          >
            {state.suggesting ? 'Suggesting…' : '✨ Suggest with AI'}
          </button>
        </div>
        <textarea
          className={styles.fieldTextarea}
          value={state.palette.join('\n')}
          rows={4}
          onChange={(e) =>
            onChange({ palette: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })
          }
        />

        <label className={styles.fieldLabel}>Accent Palette (one hex per line)</label>
        <textarea
          className={styles.fieldTextarea}
          value={state.accent_palette.join('\n')}
          rows={2}
          onChange={(e) =>
            onChange({ accent_palette: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean) })
          }
        />

        <div className={styles.dialogActions}>
          <button className={styles.cancelBtn} onClick={onClose}>Cancel</button>
          <button className={styles.saveBtn} onClick={onSave} disabled={state.saving}>
            {state.saving ? (state.isNew ? 'Creating…' : 'Saving…') : (state.isNew ? 'Create' : 'Save')}
          </button>
        </div>
      </div>
    </div>
  );
}

export function Theme({
  song,
  themes,
  sections,
  assignments,
  onThemed,
  onAssignmentChange,
}: ThemeScreenProps) {
  const [selectedSectionIdx, setSelectedSectionIdx] = useState(0);
  const [localAssignments, setLocalAssignments] = useState(assignments);
  const [error, setError] = useState<string | null>(null);
  const [liveOverrides, setLiveOverrides] = useState<ParameterOverrides>(DEFAULT_OVERRIDES);
  const [editState, setEditState] = useState<EditState | null>(null);
  const [resetting, setResetting] = useState(false);
  const [importing, setImporting] = useState(false);
  const importInputRef = React.useRef<HTMLInputElement>(null);

  const currentAssignment = localAssignments.find((a) => a.section_index === selectedSectionIdx);
  const currentTheme = currentAssignment?.theme_id
    ? themes.find((t) => t.theme_id === currentAssignment.theme_id)
    : undefined;

  // Reverse lookup for the theme grid: which section(s) currently use each
  // theme, so the assignment is visible without clicking through every
  // section tab. Derived from live localAssignments/sections state (not a
  // stale/wrong list — see bug-355) so it stays in sync with edits.
  const sectionLabelsByTheme = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const section of sections) {
      const assignment = localAssignments.find((a) => a.section_index === section.index);
      if (!assignment?.theme_id) continue;
      const labels = map.get(assignment.theme_id) ?? [];
      labels.push(section.label);
      map.set(assignment.theme_id, labels);
    }
    return map;
  }, [sections, localAssignments]);

  // Holiday (occasion) first — general-purpose themes sort last since
  // holiday-specific ones are the special case worth surfacing together —
  // then category (mood), then alphabetical by name (user request 2026-07-18).
  const sortedThemes = useMemo(() => {
    return [...themes].sort((a, b) => {
      const aOccasion = a.occasion ?? 'general';
      const bOccasion = b.occasion ?? 'general';
      const aIsGeneral = aOccasion === 'general' ? 1 : 0;
      const bIsGeneral = bOccasion === 'general' ? 1 : 0;
      if (aIsGeneral !== bIsGeneral) return aIsGeneral - bIsGeneral;
      if (aOccasion !== bOccasion) return aOccasion.localeCompare(bOccasion);
      const aMood = a.mood ?? '';
      const bMood = b.mood ?? '';
      if (aMood !== bMood) return aMood.localeCompare(bMood);
      return a.name.localeCompare(b.name);
    });
  }, [themes]);

  async function handleThemeSelect(themeId: string) {
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/assignments/${selectedSectionIdx}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ theme_id: themeId }),
        }
      );
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to assign theme');
        return;
      }
      const updated = localAssignments.map((a) =>
        a.section_index === selectedSectionIdx
          ? { ...body.assignment }
          : a
      );
      setLocalAssignments(updated);
      setLiveOverrides(body.assignment.overrides ?? DEFAULT_OVERRIDES);
      onAssignmentChange(body.assignment);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  async function handleAcceptAll() {
    setError(null);
    try {
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/assignments/accept-all`,
        { method: 'POST' }
      );
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to accept all');
        return;
      }
      if (body.song_status === 'themed') {
        onThemed();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    }
  }

  async function handleResetDefaults() {
    setError(null);
    setResetting(true);
    try {
      // Recomputing smart defaults rebuilds the song story (section-role
      // classification + lyric-anchored boundary refinement), which can
      // take a while on a real song -- not a quick local operation, hence
      // the loading state rather than an instant round-trip.
      const res = await fetch(
        `/api/v1/songs/${song.song_id}/assignments/reset-defaults`,
        { method: 'POST' }
      );
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Failed to reset to defaults');
        return;
      }
      const updated: Assignment[] = body.assignments;
      setLocalAssignments(updated);
      const current = updated.find((a) => a.section_index === selectedSectionIdx);
      setLiveOverrides(current?.overrides ?? DEFAULT_OVERRIDES);
      updated.forEach((a) => onAssignmentChange(a));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setResetting(false);
    }
  }

  function handleExportAssignments() {
    // User request 2026-07-28: theme assignments live only in the session
    // JSON under the app's state dir, which some environments (e.g. this
    // devcontainer's ephemeral home dir) wipe on restart -- a manual
    // export/import round-trip is a user-controlled backup independent of
    // that.
    const payload = {
      schema_version: 1,
      exported_at: new Date().toISOString(),
      song_id: song.song_id,
      song_title: song.title,
      assignments: localAssignments,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const safeName = song.title.replace(/[^a-z0-9]+/gi, '_').toLowerCase() || 'song';
    link.download = `${safeName}-theme-assignments.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  async function handleImportAssignments(file: File) {
    setError(null);
    setImporting(true);
    try {
      const text = await file.text();
      let parsed: unknown;
      try {
        parsed = JSON.parse(text);
      } catch {
        setError('That file is not valid JSON.');
        return;
      }
      const imported: Assignment[] | undefined = Array.isArray(parsed)
        ? (parsed as Assignment[])
        : (parsed as { assignments?: Assignment[] })?.assignments;
      if (!Array.isArray(imported)) {
        setError('Invalid file: expected an "assignments" array.');
        return;
      }

      let updated = localAssignments;
      const existingIndices = new Set(updated.map((a) => a.section_index));
      let applied = 0;
      for (const a of imported) {
        // Only apply to sections that actually exist in THIS song --
        // a mapping exported from a differently-structured song shouldn't
        // silently create phantom assignments.
        if (typeof a?.section_index !== 'number' || !existingIndices.has(a.section_index)) {
          continue;
        }
        const res = await fetch(
          `/api/v1/songs/${song.song_id}/assignments/${a.section_index}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme_id: a.theme_id, overrides: a.overrides ?? {} }),
          },
        );
        const body = await res.json();
        if (!res.ok) {
          setError(body?.error?.message ?? `Failed to apply section ${a.section_index}`);
          continue;
        }
        applied += 1;
        updated = updated.map((existing) =>
          existing.section_index === a.section_index ? { ...body.assignment } : existing
        );
        onAssignmentChange(body.assignment);
      }

      setLocalAssignments(updated);
      const current = updated.find((a) => a.section_index === selectedSectionIdx);
      setLiveOverrides(current?.overrides ?? DEFAULT_OVERRIDES);
      if (applied === 0) {
        setError('No matching sections found in that file for this song.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error importing assignments');
    } finally {
      setImporting(false);
    }
  }

  function openEdit(theme: Theme) {
    setEditState({
      theme,
      isNew: false,
      name: theme.name,
      description: theme.description,
      mood: theme.mood ?? 'structural',
      occasion: theme.occasion ?? 'general',
      genre: theme.genre ?? 'any',
      palette: theme.swatches.slice(0, 4),
      accent_palette: [theme.accent],
      saving: false,
      suggesting: false,
      error: null,
    });
  }

  function openCreate() {
    setEditState({
      theme: BLANK_THEME,
      isNew: true,
      name: '',
      description: '',
      mood: 'structural',
      occasion: 'general',
      genre: 'any',
      palette: [],
      accent_palette: [],
      saving: false,
      suggesting: false,
      error: null,
    });
  }

  async function handleSuggestPalette() {
    if (!editState) return;
    setEditState((s) => s ? { ...s, suggesting: true, error: null } : s);
    try {
      const res = await fetch(`/api/v1/songs/${song.song_id}/theme-suggest-palette`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ genre: editState.genre, occasion: editState.occasion }),
      });
      const body = await res.json();
      if (!res.ok || body?.error) {
        setEditState((s) => s ? {
          ...s, suggesting: false,
          error: body?.error?.message ?? 'AI suggestion unavailable',
        } : s);
        return;
      }
      setEditState((s) => s ? { ...s, suggesting: false, palette: body.palette } : s);
    } catch (err) {
      setEditState((s) => s ? {
        ...s, suggesting: false,
        error: err instanceof Error ? err.message : 'AI suggestion unavailable',
      } : s);
    }
  }

  async function handleSaveEdit() {
    if (!editState) return;
    if (editState.isNew && !editState.name.trim()) {
      setEditState((s) => s ? { ...s, error: 'Name is required' } : s);
      return;
    }
    setEditState((s) => s ? { ...s, saving: true, error: null } : s);
    try {
      const url = editState.isNew
        ? '/api/v1/themes'
        : `/api/v1/themes/${editState.theme.theme_id}`;
      const res = await fetch(url, {
        method: editState.isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editState.name,
          intent: editState.description,
          mood: editState.mood,
          occasion: editState.occasion,
          genre: editState.genre,
          palette: editState.palette,
          accent_palette: editState.accent_palette,
        }),
      });
      const body = await res.json();
      if (!res.ok) {
        setEditState((s) => s ? { ...s, saving: false, error: body?.error?.message ?? 'Save failed' } : s);
        return;
      }
      // Theme saved — close dialog (parent will re-fetch themes on next load)
      setEditState(null);
    } catch (err) {
      setEditState((s) => s ? { ...s, saving: false, error: err instanceof Error ? err.message : 'Error' } : s);
    }
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>{song.title}</h2>
        <div className={styles.headerActions}>
          <button className={styles.resetBtn} onClick={openCreate}>
            + New Theme
          </button>
          <button className={styles.resetBtn} onClick={handleExportAssignments}>
            Save Mappings
          </button>
          <button
            className={styles.resetBtn}
            onClick={() => importInputRef.current?.click()}
            disabled={importing}
          >
            {importing ? 'Loading…' : 'Load Mappings'}
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleImportAssignments(file);
              e.target.value = '';
            }}
          />
          <button
            className={styles.resetBtn}
            onClick={handleResetDefaults}
            disabled={resetting}
          >
            {resetting ? 'Resetting…' : 'Reset'}
          </button>
          <button className={styles.acceptBtn} onClick={handleAcceptAll}>
            Accept
          </button>
        </div>
      </div>

      <SectionStrip
        sections={sections}
        assignments={localAssignments}
        themes={themes}
        durationMs={song.duration_ms}
        selectedIndex={selectedSectionIdx}
        onSelect={(idx) => {
          setSelectedSectionIdx(idx);
          const a = localAssignments.find((a) => a.section_index === idx);
          setLiveOverrides(
            a?.overrides && Object.keys(a.overrides).length > 0
              ? a.overrides
              : DEFAULT_OVERRIDES
          );
        }}
      />

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.body}>
        <div className={styles.themeGrid}>
          {sortedThemes.map((theme) => (
            <ThemeCard
              key={theme.theme_id}
              theme={theme}
              assigned={currentAssignment?.theme_id === theme.theme_id}
              assignedSections={sectionLabelsByTheme.get(theme.theme_id) ?? []}
              onClick={() => handleThemeSelect(theme.theme_id)}
              onEdit={theme.editable ? () => openEdit(theme) : undefined}
            />
          ))}
        </div>

        <div className={styles.preview}>
          <LightsPreview
            n={20}
            label={sections[selectedSectionIdx]?.label ?? ''}
            accent={currentTheme
              ? hueShiftHex(currentTheme.accent, liveOverrides.color_shift)
              : '#555'
            }
            energyPulse={0.6 * liveOverrides.brightness}
          />
          {currentTheme && currentTheme.swatches.length > 0 && (
            <MiniLights
              themeId={currentTheme.theme_id}
              kind="color-shift-preview"
              swatches={hueShiftPalette(currentTheme.swatches, liveOverrides.color_shift)}
            />
          )}
        </div>

        <Inspector title="Section Parameters">
          {currentAssignment?.theme_id && (
            <ParameterSliders
              songId={song.song_id}
              sectionIdx={selectedSectionIdx}
              themeId={currentAssignment.theme_id}
              overrides={
                currentAssignment.overrides && Object.keys(currentAssignment.overrides).length > 0
                  ? currentAssignment.overrides
                  : DEFAULT_OVERRIDES
              }
              onOverridesChange={(updated) => {
                setLiveOverrides(updated);
                const next = localAssignments.map((a) =>
                  a.section_index === selectedSectionIdx
                    ? { ...a, overrides: updated }
                    : a
                );
                setLocalAssignments(next);
              }}
            />
          )}
        </Inspector>
      </div>

      {editState && (
        <EditDialog
          state={editState}
          onChange={(patch) => setEditState((s) => s ? { ...s, ...patch } : s)}
          onSave={handleSaveEdit}
          onSuggest={handleSuggestPalette}
          onClose={() => setEditState(null)}
        />
      )}
    </div>
  );
}
