import React, { useMemo, useState } from 'react';
import styles from './Theme.module.css';
import { ThemeCard } from '../components/ThemeCard/ThemeCard';
import { LightsPreview } from '../components/LightsPreview/LightsPreview';
import { SectionStrip } from '../components/SectionStrip/SectionStrip';
import { Inspector } from '../components/Inspector/Inspector';
import { ParameterSliders, ParameterOverrides } from '../components/ParameterSliders/ParameterSliders';
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
  name: string;
  description: string;
  mood: string;
  occasion: string;
  genre: string;
  palette: string[];
  accent_palette: string[];
  saving: boolean;
  error: string | null;
}

function EditDialog({
  state,
  onChange,
  onSave,
  onClose,
}: {
  state: EditState;
  onChange: (patch: Partial<EditState>) => void;
  onSave: () => void;
  onClose: () => void;
}) {
  return (
    <div className={styles.dialogOverlay} onClick={onClose}>
      <div className={styles.dialog} onClick={(e) => e.stopPropagation()}>
        <div className={styles.dialogHeader}>
          <span className={styles.dialogTitle}>Edit Theme</span>
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

        <label className={styles.fieldLabel}>Palette (one hex per line)</label>
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
            {state.saving ? 'Saving…' : 'Save'}
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

  const currentAssignment = localAssignments.find((a) => a.section_index === selectedSectionIdx);

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

  function openEdit(theme: Theme) {
    setEditState({
      theme,
      name: theme.name,
      description: theme.description,
      mood: theme.mood ?? 'structural',
      occasion: theme.occasion ?? 'general',
      genre: theme.genre ?? 'any',
      palette: theme.swatches.slice(0, 4),
      accent_palette: [theme.accent],
      saving: false,
      error: null,
    });
  }

  async function handleSaveEdit() {
    if (!editState) return;
    setEditState((s) => s ? { ...s, saving: true, error: null } : s);
    try {
      const res = await fetch(`/api/v1/themes/${editState.theme.theme_id}`, {
        method: 'PUT',
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
              onClick={() => handleThemeSelect(theme.theme_id)}
              onEdit={theme.editable ? () => openEdit(theme) : undefined}
            />
          ))}
        </div>

        <div className={styles.preview}>
          <LightsPreview
            n={20}
            label={sections[selectedSectionIdx]?.label ?? ''}
            accent={currentAssignment?.theme_id
              ? (themes.find((t) => t.theme_id === currentAssignment.theme_id)?.accent ?? '#4ade80')
              : '#555'
            }
            energyPulse={0.6 * liveOverrides.brightness}
          />
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
          onClose={() => setEditState(null)}
        />
      )}
    </div>
  );
}
