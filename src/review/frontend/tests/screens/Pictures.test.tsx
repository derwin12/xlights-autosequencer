import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
});
