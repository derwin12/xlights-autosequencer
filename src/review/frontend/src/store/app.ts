import { create } from 'zustand';

export type Screen = 'layout' | 'library' | 'drop' | 'analyze' | 'timeline' | 'theme' | 'pictures' | 'export';

interface AppState {
  screen: Screen;
  selectedSongId: string | null;
  inspectorOpen: boolean;
  tweaksOpen: boolean;

  setScreen: (screen: Screen) => void;
  setSelectedSongId: (id: string | null) => void;
  toggleInspector: () => void;
  toggleTweaks: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  screen: 'library',
  selectedSongId: null,
  inspectorOpen: true,
  tweaksOpen: false,

  setScreen: (screen) => set({ screen }),
  setSelectedSongId: (id) => set({ selectedSongId: id }),
  toggleInspector: () => set((s) => ({ inspectorOpen: !s.inspectorOpen })),
  toggleTweaks: () => set((s) => ({ tweaksOpen: !s.tweaksOpen })),
}));
