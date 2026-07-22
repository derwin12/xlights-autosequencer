import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { Chrome } from 'src/components/Chrome/Chrome';

describe('Chrome', () => {
  it('renders the wordmark', () => {
    render(<Chrome activeScreen="library"><div /></Chrome>);
    expect(screen.getByText(/xonset/i)).toBeTruthy();
  });

  it('tool strip highlights active tab with accent underline', () => {
    render(<Chrome activeScreen="timeline"><div /></Chrome>);
    const tab = screen.getByRole('tab', { name: /timeline/i });
    expect(tab).toHaveAttribute('data-active', 'true');
  });

  it('renders children inside content area', () => {
    render(
      <Chrome activeScreen="library">
        <div data-testid="child-content">child</div>
      </Chrome>,
    );
    expect(screen.getByTestId('child-content')).toBeTruthy();
  });
});

describe('Chrome LibraryRail (T097)', () => {
  const SONGS = [
    {
      song_id: 'song_a',
      title: 'Song Alpha',
      artist: null,
      duration_ms: 120000,
      bpm: null,
      key: null,
      time_signature: null as [number, number] | null,
      status: 'draft' as const,
      source_paths: [] as string[],
      folder_id: 'unfiled',
      imported_at: '2026-01-01T00:00:00Z',
      last_opened_at: null,
      source_exists: true,
    },
    {
      song_id: 'song_b',
      title: 'Song Beta',
      artist: 'Artist',
      duration_ms: 200000,
      bpm: 120,
      key: 'C major',
      time_signature: [4, 4] as [number, number],
      status: 'themed' as const,
      source_paths: ['/tmp/beta.mp3'],
      folder_id: 'xmas',
      imported_at: '2026-01-01T01:00:00Z',
      last_opened_at: null,
      source_exists: true,
    },
  ];

  const FOLDERS = [
    { folder_id: 'unfiled', name: 'Unfiled', collapsed: false, order: 0 },
    { folder_id: 'xmas', name: 'Christmas', collapsed: false, order: 1 },
  ];

  it('renders library rail when songs and folders provided', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS}>
        <div />
      </Chrome>,
    );
    expect(screen.getByTestId('library-rail')).toBeTruthy();
  });

  it('renders song titles in the rail', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS}>
        <div />
      </Chrome>,
    );
    expect(screen.getByText('Song Alpha')).toBeTruthy();
    expect(screen.getByText('Song Beta')).toBeTruthy();
  });

  it('renders folder names in the rail', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS}>
        <div />
      </Chrome>,
    );
    expect(screen.getByText('Unfiled')).toBeTruthy();
    expect(screen.getByText('Christmas')).toBeTruthy();
  });

  it('renders status chip for each song in the rail', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS}>
        <div />
      </Chrome>,
    );
    expect(screen.getByTestId('rail-status-chip-song_a')).toBeTruthy();
    expect(screen.getByTestId('rail-status-chip-song_b')).toBeTruthy();
  });

  it('highlights the active song', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} activeSongId="song_a">
        <div />
      </Chrome>,
    );
    const item = screen.getByTestId('rail-song-song_a');
    expect(item).toHaveAttribute('data-active', 'true');
  });

  it('non-active song does not have data-active=true', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} activeSongId="song_a">
        <div />
      </Chrome>,
    );
    const item = screen.getByTestId('rail-song-song_b');
    expect(item).toHaveAttribute('data-active', 'false');
  });

  it('calls onSelectSong when a song is clicked in the rail', () => {
    const onSelectSong = vi.fn();
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} onSelectSong={onSelectSong}>
        <div />
      </Chrome>,
    );
    fireEvent.click(screen.getByTestId('rail-song-song_a'));
    expect(onSelectSong).toHaveBeenCalledWith(
      expect.objectContaining({ song_id: 'song_a' }),
      expect.any(String),
    );
  });

  it('does not render library rail when no songs/folders provided', () => {
    render(
      <Chrome activeScreen="library">
        <div />
      </Chrome>,
    );
    expect(screen.queryByTestId('library-rail')).toBeNull();
  });

  it('does not show a New Folder control without an onCreateFolder handler', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS}>
        <div />
      </Chrome>,
    );
    expect(screen.queryByTestId('new-folder-button')).toBeNull();
  });

  it('shows a name input when New Folder is clicked, and creates on Enter', async () => {
    const onCreateFolder = vi.fn().mockResolvedValue(null);
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} onCreateFolder={onCreateFolder}>
        <div />
      </Chrome>,
    );
    fireEvent.click(screen.getByTestId('new-folder-button'));
    const input = screen.getByTestId('new-folder-input');
    fireEvent.change(input, { target: { value: 'Halloween' } });
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }); });

    expect(onCreateFolder).toHaveBeenCalledWith('Halloween');
  });

  it('shows the server error inline when folder creation fails', async () => {
    const onCreateFolder = vi.fn().mockResolvedValue('A folder with this name already exists');
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} onCreateFolder={onCreateFolder}>
        <div />
      </Chrome>,
    );
    fireEvent.click(screen.getByTestId('new-folder-button'));
    const input = screen.getByTestId('new-folder-input');
    fireEvent.change(input, { target: { value: 'Christmas' } });
    await act(async () => { fireEvent.keyDown(input, { key: 'Enter' }); });

    expect(await screen.findByText(/already exists/i)).toBeTruthy();
    // Input stays open so the user can fix the name rather than losing it.
    expect(screen.getByTestId('new-folder-input')).toBeTruthy();
  });

  it('cancels on Escape without calling onCreateFolder', () => {
    const onCreateFolder = vi.fn();
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} onCreateFolder={onCreateFolder}>
        <div />
      </Chrome>,
    );
    fireEvent.click(screen.getByTestId('new-folder-button'));
    const input = screen.getByTestId('new-folder-input');
    fireEvent.change(input, { target: { value: 'Halloween' } });
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(onCreateFolder).not.toHaveBeenCalled();
    expect(screen.getByTestId('new-folder-button')).toBeTruthy();
  });

  it('does not show a delete control on any folder without an onRemoveFolder handler', () => {
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS}>
        <div />
      </Chrome>,
    );
    expect(screen.queryByTestId('remove-folder-xmas')).toBeNull();
  });

  it('shows a delete control on a regular folder and calls onRemoveFolder on click', () => {
    const onRemoveFolder = vi.fn();
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} onRemoveFolder={onRemoveFolder}>
        <div />
      </Chrome>,
    );
    fireEvent.click(screen.getByTestId('remove-folder-xmas'));
    expect(onRemoveFolder).toHaveBeenCalledWith('xmas');
  });

  it('never shows a delete control on the reserved Unfiled folder', () => {
    const onRemoveFolder = vi.fn();
    render(
      <Chrome activeScreen="library" songs={SONGS} folders={FOLDERS} onRemoveFolder={onRemoveFolder}>
        <div />
      </Chrome>,
    );
    expect(screen.queryByTestId('remove-folder-unfiled')).toBeNull();
  });
});
