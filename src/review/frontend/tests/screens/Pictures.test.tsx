import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { Pictures } from '../../src/screens/Pictures';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const song = { song_id: 'abc123', title: 'Dream On' };

// Two occurrences of the same word, mirroring the reported real-world case
// (multiple "DREAM" rows in one song, each independently mapped/unmapped).
const imageSuggestions = [
  { word: 'DREAM', start_ms: 182000, end_ms: 182400, matched_file: 'dream2.png', matched_tag: 'dream', score: 1 },
  { word: 'DREAM', start_ms: 183000, end_ms: 183400, matched_file: 'dream2.png', matched_tag: 'dream', score: 1 },
];

function defaultFetchImpl(url: string) {
  if (url.endsWith('/ignored-images')) {
    return Promise.resolve({ ok: true, json: async () => ({ occurrences: [] }) });
  }
  if (url.endsWith('/shadow-words')) {
    return Promise.resolve({ ok: true, json: async () => ({ occurrences: [] }) });
  }
  if (url.endsWith('/moving-head-keywords')) {
    return Promise.resolve({ ok: true, json: async () => ({ keywords: {} }) });
  }
  return Promise.resolve({ ok: true, json: async () => ({}) });
}

describe('Pictures screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetch.mockImplementation(defaultFetchImpl);
  });

  it('renders one row per occurrence, not deduped by word', async () => {
    render(
      <Pictures song={song} imageSuggestions={imageSuggestions} imageTopics={[]} onContinue={() => {}} />
    );
    await waitFor(() => {
      expect(screen.getAllByText(/DREAM/)).toHaveLength(2);
    });
  });

  it('unmapping one occurrence sends its start_ms and leaves the sibling occurrence mapped', async () => {
    mockFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === `/api/v1/songs/${song.song_id}/ignored-images` && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ occurrences: [{ word: 'dream', start_ms: 182000 }] }),
        });
      }
      return defaultFetchImpl(url);
    });

    render(
      <Pictures song={song} imageSuggestions={imageSuggestions} imageTopics={[]} onContinue={() => {}} />
    );
    await waitFor(() => expect(screen.getAllByText(/DREAM/)).toHaveLength(2));

    const unmapButtons = screen.getAllByRole('button', { name: /^unmap$/i });
    expect(unmapButtons).toHaveLength(2);
    fireEvent.click(unmapButtons[0]);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/v1/songs/${song.song_id}/ignored-images`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ word: 'dream', start_ms: 182000 }),
        }),
      );
    });

    await waitFor(() => {
      // Only one "DREAM" row remains under "Already matched" / Unmap-able.
      expect(screen.getAllByRole('button', { name: /^unmap$/i })).toHaveLength(1);
      // The unmapped occurrence's row still exists (moved to "Suggested
      // topics" with a "Restore match" action), not disappeared entirely.
      expect(screen.getByRole('button', { name: /restore match/i })).toBeTruthy();
    });
  });

  it('unmapping an occurrence with a standing override clears it locally too', async () => {
    // Regression for a 2026-08-09 user report: an occurrence pinned via
    // "Choose image" to a different library entry kept firing that
    // override at export even after being unmapped on this screen, because
    // the ignore and the override were two independent flags and only the
    // ignore got cleared. The backend now clears both together; this test
    // guards the frontend actually reflects that instead of keeping the
    // stale override in local state until a full reload.
    mockFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === `/api/v1/songs/${song.song_id}/image-overrides` && !opts) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            overrides: [{ word: 'dream', start_ms: 182000, image_id: 'override-id' }],
          }),
        });
      }
      if (url === '/api/v1/images') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ images: [{ id: 'override-id', filename: 'override.png' }] }),
        });
      }
      if (url === `/api/v1/songs/${song.song_id}/ignored-images` && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            occurrences: [{ word: 'dream', start_ms: 182000 }],
            overrides: [],
          }),
        });
      }
      return defaultFetchImpl(url);
    });

    render(
      <Pictures song={song} imageSuggestions={imageSuggestions} imageTopics={[]} onContinue={() => {}} />
    );
    // Before unmapping: the overridden filename shows instead of the
    // row's normal matched_file.
    await waitFor(() => expect(screen.getByText('override.png')).toBeTruthy());

    const unmapButtons = screen.getAllByRole('button', { name: /^unmap$/i });
    fireEvent.click(unmapButtons[0]);

    await waitFor(() => {
      // Row moved to "Suggested topics"; its "unmapped from" note uses the
      // ORIGINAL matched_file, not the override, since it's a fixed label.
      expect(screen.getByText(/unmapped from dream2\.png/i)).toBeTruthy();
    });

    // Restoring the match should now fall back to the normal matched_file,
    // not silently resurrect the cleared override.
    mockFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes('/ignored-images/') && opts?.method === 'DELETE') {
        return Promise.resolve({ ok: true, json: async () => ({ occurrences: [] }) });
      }
      return defaultFetchImpl(url);
    });
    fireEvent.click(screen.getByRole('button', { name: /restore match/i }));

    await waitFor(() => {
      expect(screen.getByText('dream2.png')).toBeTruthy();
      expect(screen.queryByText('override.png')).toBeNull();
    });
  });

  it('adds a manual Moving Head trigger at a typed mm:ss timestamp', async () => {
    mockFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === `/api/v1/songs/${song.song_id}/moving-head-timestamps` && opts?.method === 'PUT') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ triggers: [{ start_ms: 46675, motion: 'shake' }] }),
        });
      }
      return defaultFetchImpl(url);
    });

    render(
      <Pictures song={song} imageSuggestions={[]} imageTopics={[]} onContinue={() => {}} />
    );
    await waitFor(() => expect(screen.getByLabelText(/time for manual moving head trigger/i)).toBeTruthy());

    fireEvent.change(screen.getByLabelText(/time for manual moving head trigger/i), {
      target: { value: '0:46.675' },
    });
    fireEvent.click(screen.getByRole('button', { name: /add manual trigger/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/v1/songs/${song.song_id}/moving-head-timestamps`,
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ start_ms: 46675, motion: 'shake' }),
        }),
      );
    });
    await waitFor(() => {
      const row = screen.getByText('0:46').closest('li');
      expect(row).toBeTruthy();
      expect(within(row as HTMLElement).getByText('shake')).toBeTruthy();
    });
  });

  it('rejects an unparseable manual trigger timestamp without calling the API', async () => {
    render(
      <Pictures song={song} imageSuggestions={[]} imageTopics={[]} onContinue={() => {}} />
    );
    await waitFor(() => expect(screen.getByLabelText(/time for manual moving head trigger/i)).toBeTruthy());

    fireEvent.change(screen.getByLabelText(/time for manual moving head trigger/i), {
      target: { value: 'not-a-time' },
    });
    mockFetch.mockClear();
    fireEvent.click(screen.getByRole('button', { name: /add manual trigger/i }));

    await waitFor(() => expect(screen.getByText(/enter a time as m:ss/i)).toBeTruthy());
    expect(mockFetch).not.toHaveBeenCalledWith(
      expect.stringContaining('/moving-head-timestamps'),
      expect.anything(),
    );
  });

  it('removes a manual Moving Head trigger', async () => {
    mockFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === `/api/v1/songs/${song.song_id}/moving-head-timestamps`) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ triggers: [{ start_ms: 46675, motion: 'shake' }] }),
        });
      }
      if (url === `/api/v1/songs/${song.song_id}/moving-head-timestamps/46675` && opts?.method === 'DELETE') {
        return Promise.resolve({ ok: true, json: async () => ({ triggers: [] }) });
      }
      return defaultFetchImpl(url);
    });

    render(
      <Pictures song={song} imageSuggestions={[]} imageTopics={[]} onContinue={() => {}} />
    );
    await waitFor(() => expect(screen.getByRole('button', { name: /remove manual trigger/i })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /remove manual trigger/i }));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/v1/songs/${song.song_id}/moving-head-timestamps/46675`,
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
  });

  it('uploads and pins a manual Pictures occurrence at a typed mm:ss timestamp', async () => {
    mockFetch.mockImplementation((url: string, opts?: RequestInit) => {
      if (url === '/api/v1/images' && opts?.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ image: { id: 'manual-img-1', filename: 'sunset.png' } }),
        });
      }
      if (url === `/api/v1/songs/${song.song_id}/image-manual-occurrences` && opts?.method === 'PUT') {
        return Promise.resolve({
          ok: true,
          json: async () => ({ occurrences: [{ start_ms: 46675, image_id: 'manual-img-1' }] }),
        });
      }
      return defaultFetchImpl(url);
    });

    render(
      <Pictures song={song} imageSuggestions={[]} imageTopics={[]} onContinue={() => {}} />
    );
    await waitFor(() => expect(screen.getByLabelText(/time for manual picture/i)).toBeTruthy());

    fireEvent.change(screen.getByLabelText(/time for manual picture/i), { target: { value: '0:46.675' } });
    const file = new File(['bytes'], 'sunset.png', { type: 'image/png' });
    const fileInput = screen.getByLabelText(/choose image/i) as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/v1/songs/${song.song_id}/image-manual-occurrences`,
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ start_ms: 46675, image_id: 'manual-img-1' }),
        }),
      );
    });
    await waitFor(() => expect(screen.getByText('sunset.png')).toBeTruthy());
  });
});
