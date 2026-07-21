import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PasteLyricsDialog } from '../../src/components/PasteLyricsDialog/PasteLyricsDialog';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('PasteLyricsDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a validation error and does not POST when saving blank text', async () => {
    const onSaved = vi.fn();
    render(<PasteLyricsDialog title="T" artist="A" onSaved={onSaved} onCancel={() => {}} />);
    screen.getByTestId('paste-lyrics-save').click();
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/paste some lyrics text first/i);
    });
    expect(mockFetch).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('POSTs the trimmed text and calls onSaved with the response', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ found: true, reason: null, line_count: 2, preview: ['a', 'b'], source: 'pasted' }),
    });
    const onSaved = vi.fn();
    render(<PasteLyricsDialog title="Song Title" artist="Song Artist" onSaved={onSaved} onCancel={() => {}} />);

    fireEvent.change(screen.getByLabelText('Lyrics text'), { target: { value: '  a\nb  ' } });
    screen.getByTestId('paste-lyrics-save').click();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith('/api/v1/lyrics/paste', expect.objectContaining({
        method: 'POST',
      }));
      const [, opts] = mockFetch.mock.calls[0];
      expect(JSON.parse(opts.body)).toEqual({
        title: 'Song Title', artist: 'Song Artist', lyrics_text: 'a\nb',
      });
      expect(onSaved).toHaveBeenCalledWith({
        found: true, reason: null, line_count: 2, preview: ['a', 'b'], source: 'pasted',
      });
    });
  });

  it('shows an error and does not call onSaved when the request fails', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ error: { message: 'lyrics_text is required' } }),
    });
    const onSaved = vi.fn();
    render(<PasteLyricsDialog title="T" artist="A" onSaved={onSaved} onCancel={() => {}} />);

    fireEvent.change(screen.getByLabelText('Lyrics text'), { target: { value: 'x' } });
    screen.getByTestId('paste-lyrics-save').click();

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/lyrics_text is required/i);
    });
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('calls onCancel without posting', () => {
    const onCancel = vi.fn();
    render(<PasteLyricsDialog title="T" artist="A" onSaved={() => {}} onCancel={onCancel} />);
    screen.getByTestId('paste-lyrics-cancel').click();
    expect(onCancel).toHaveBeenCalled();
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
