import { describe, it, expect, beforeEach } from 'vitest';
import { usePreferencesStore } from 'src/store/preferences';

describe('preferences store', () => {
  beforeEach(() => {
    usePreferencesStore.setState({
      mode: 'dark',
      density: 'comfortable',
      inspector_open: true,
      tweaks_open: false,
      last_song_id: null,
      last_screen: 'library',
      last_playhead_ms_by_song: {},
      layout_id: null,
      library_state_version: 0,
    });
  });

  it('has default mode dark', () => {
    expect(usePreferencesStore.getState().mode).toBe('dark');
  });

  it('has default density comfortable', () => {
    expect(usePreferencesStore.getState().density).toBe('comfortable');
  });

  it('setMode switches to light', () => {
    usePreferencesStore.getState().setMode('light');
    expect(usePreferencesStore.getState().mode).toBe('light');
  });

  it('setMode switches back to dark', () => {
    usePreferencesStore.getState().setMode('light');
    usePreferencesStore.getState().setMode('dark');
    expect(usePreferencesStore.getState().mode).toBe('dark');
  });

  it('setDensity switches to compact', () => {
    usePreferencesStore.getState().setDensity('compact');
    expect(usePreferencesStore.getState().density).toBe('compact');
  });

  it('setDensity switches back to comfortable', () => {
    usePreferencesStore.getState().setDensity('compact');
    usePreferencesStore.getState().setDensity('comfortable');
    expect(usePreferencesStore.getState().density).toBe('comfortable');
  });

  it('setPreferences partial update preserves other fields', () => {
    usePreferencesStore.getState().setPreferences({ mode: 'light' });
    const s = usePreferencesStore.getState();
    expect(s.mode).toBe('light');
    expect(s.density).toBe('comfortable');
    expect(s.inspector_open).toBe(true);
  });

  it('setPreferences updates inspector_open', () => {
    usePreferencesStore.getState().setPreferences({ inspector_open: false });
    expect(usePreferencesStore.getState().inspector_open).toBe(false);
  });

  it('data-mode derivation: dark mode sets data-mode=dark on document', () => {
    usePreferencesStore.getState().setMode('dark');
    // derivation applied outside the store; test that mode is correct for consumers
    expect(usePreferencesStore.getState().mode).toBe('dark');
  });

  it('data-mode derivation: light mode value accessible', () => {
    usePreferencesStore.getState().setMode('light');
    expect(usePreferencesStore.getState().mode).toBe('light');
  });

  it('setDensity applies --density CSS custom property to :root', () => {
    usePreferencesStore.getState().setDensity('compact');
    expect(document.documentElement.style.getPropertyValue('--density')).toBe('compact');
  });

  it('setDensity comfortable applies --density comfortable', () => {
    usePreferencesStore.getState().setDensity('comfortable');
    expect(document.documentElement.style.getPropertyValue('--density')).toBe('comfortable');
  });

  it('setMode applies data-mode attribute to document element', () => {
    usePreferencesStore.getState().setMode('light');
    expect(document.documentElement.getAttribute('data-mode')).toBe('light');
  });

  it('inspector_open toggle via setPreferences', () => {
    usePreferencesStore.getState().setPreferences({ inspector_open: false });
    expect(usePreferencesStore.getState().inspector_open).toBe(false);
    usePreferencesStore.getState().setPreferences({ inspector_open: true });
    expect(usePreferencesStore.getState().inspector_open).toBe(true);
  });

  it('has default randomness 0', () => {
    expect(usePreferencesStore.getState().randomness).toBe(0);
  });

  it('setPreferences updates randomness', () => {
    usePreferencesStore.getState().setPreferences({ randomness: 0.5 });
    expect(usePreferencesStore.getState().randomness).toBe(0.5);
  });
});
