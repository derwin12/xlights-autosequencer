import { create } from 'zustand';

export interface Preferences {
  mode: 'dark' | 'light';
  density: 'comfortable' | 'compact';
  inspector_open: boolean;
  tweaks_open: boolean;
  last_song_id: string | null;
  last_screen: string;
  last_playhead_ms_by_song: Record<string, number>;
  layout_id: string | null;
  library_state_version: number;
  genre: 'any' | 'pop' | 'rock' | 'classical';
  occasion: 'general' | 'christmas' | 'halloween';
  randomness: number;
}

interface PreferencesState extends Preferences {
  setMode: (mode: Preferences['mode']) => void;
  setDensity: (density: Preferences['density']) => void;
  setPreferences: (prefs: Partial<Preferences>) => void;
}

const DEFAULTS: Preferences = {
  mode: 'dark',
  density: 'comfortable',
  inspector_open: true,
  tweaks_open: false,
  last_song_id: null,
  last_screen: 'library',
  last_playhead_ms_by_song: {},
  layout_id: null,
  library_state_version: 0,
  genre: 'any',
  occasion: 'general',
  randomness: 0,
};

function applyDataMode(mode: Preferences['mode']) {
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-mode', mode);
  }
}

function applyDensity(density: Preferences['density']) {
  if (typeof document !== 'undefined') {
    document.documentElement.style.setProperty('--density', density);
  }
}

export const usePreferencesStore = create<PreferencesState>((set) => ({
  ...DEFAULTS,

  setMode: (mode) => {
    applyDataMode(mode);
    set({ mode });
  },

  setDensity: (density) => {
    applyDensity(density);
    set({ density });
  },

  setPreferences: (prefs) => {
    if (prefs.mode) applyDataMode(prefs.mode);
    if (prefs.density) applyDensity(prefs.density);
    set((s) => ({ ...s, ...prefs }));
  },
}));
