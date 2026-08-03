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
});
