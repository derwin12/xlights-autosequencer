import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { Drop } from '../../src/screens/Drop';

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('Drop screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a drop target', () => {
    render(<Drop onSongImported={() => {}} />);
    expect(screen.getByTestId('drop-target')).toBeTruthy();
  });

  it('rejects unsupported extensions pre-flight', async () => {
    render(<Drop onSongImported={() => {}} />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    const file = new File(['fake'], 'song.txt', { type: 'text/plain' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByTestId('error-message')).toBeTruthy();
    });
    // fetch not called for unsupported type
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('shows server error message when import returns 400 (e.g. malformed audio)', async () => {
    // Backend rejects malformed/empty/short/silent audio at the
    // /api/v1/import boundary with a structured 400.
    mockFetch.mockResolvedValue({
      ok: false,
      json: async () => ({
        error: {
          code: 'audio_too_short',
          message: 'Audio is too short (1.00s). Minimum supported length is 5s.',
        },
      }),
    });

    const onImported = vi.fn();
    render(<Drop onSongImported={onImported} />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    const file = new File(['fake'], 'short.mp3', { type: 'audio/mpeg' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      const err = screen.getByTestId('error-message');
      expect(err.textContent).toContain('too short');
    });
    // Caller is NOT notified — the import didn't succeed.
    expect(onImported).not.toHaveBeenCalled();
  });

  it('calls import API on valid file', async () => {
    const songData = {
      song_id: 'abc123',
      title: 'Test',
      status: 'draft',
      duration_ms: 60000,
      folder_id: 'unfiled',
      imported_at: '2026-01-01T00:00:00Z',
      source_paths: [],
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ created: true, song: songData }),
    });

    const onImported = vi.fn();
    render(<Drop onSongImported={onImported} />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    const file = new File(['fake'], 'song.mp3', { type: 'audio/mpeg' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      // New signature: onSongImported(song, created). Asserting both args
      // here so future callers keep passing `created` through from the
      // server response.
      expect(onImported).toHaveBeenCalledWith(
        expect.objectContaining({ song_id: 'abc123' }),
        true,
      );
    });
  });

  it('shows a type-specific status while a video import is in flight', async () => {
    let resolveFetch: (value: unknown) => void;
    mockFetch.mockReturnValue(new Promise((resolve) => { resolveFetch = resolve; }));

    render(<Drop onSongImported={() => {}} />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;

    const file = new File(['fake'], 'clip.mp4', { type: 'video/mp4' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(screen.getByText(/importing video/i)).toBeTruthy();
    });

    await act(async () => {
      resolveFetch!({ ok: true, json: async () => ({ created: true, song: { song_id: 'x' } }) });
    });
  });

  it('imports via video endpoint when a video extension is dropped', async () => {
    const songData = {
      song_id: 'vid123',
      title: 'Video Song',
      status: 'draft',
      duration_ms: 180000,
      folder_id: 'unfiled',
      imported_at: '2026-01-01T00:00:00Z',
      source_paths: [],
      video_path: '/some/path/clip.mp4',
    };
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ created: true, song: songData }),
    });

    const onImported = vi.fn();
    render(<Drop onSongImported={onImported} />);

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const file = new File(['fake'], 'clip.mp4', { type: 'video/mp4' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/v1/import-video',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(onImported).toHaveBeenCalledWith(
        expect.objectContaining({ song_id: 'vid123' }),
        true,
      );
    });
  });

  it('shows server error message when video import fails', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      json: async () => ({
        error: { code: 'video_audio_extraction_failed', message: 'Could not extract audio from video' },
      }),
    });

    const onImported = vi.fn();
    render(<Drop onSongImported={onImported} />);

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const file = new File(['fake'], 'clip.mp4', { type: 'video/mp4' });
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);

    await waitFor(() => {
      const err = screen.getByTestId('error-message');
      expect(err.textContent).toContain('Could not extract audio');
    });
    expect(onImported).not.toHaveBeenCalled();
  });
});
