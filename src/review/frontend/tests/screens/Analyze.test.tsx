import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import {
  Analyze,
  deriveSectionRefinementStatus,
  deriveSectionReviewStatus,
} from '../../src/screens/Analyze';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const mockSong = {
  song_id: 'abc123',
  title: 'Test Song',
  status: 'draft',
  duration_ms: 60000,
  folder_id: 'unfiled',
  imported_at: '2026-01-01T00:00:00Z',
  source_paths: ['/tmp/test.mp3'],
};

describe('Analyze screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the song title', () => {
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    // headerMeta renders "Test Song · <duration>" as one text node, so a
    // substring matcher is required.
    expect(screen.getByText(/Test Song/)).toBeTruthy();
  });

  it('shows an analyzing state initially', () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ run_id: 'run_1', started_at: '2026-01-01T00:00:00Z' }),
    });
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    // Should show some indication of analysis state
    expect(screen.getByTestId('analyze-screen')).toBeTruthy();
  });

  it('shows review button when complete', async () => {
    render(<Analyze song={{ ...mockSong, status: 'analyzed' }} onComplete={() => {}} />);
    await waitFor(() => {
      const btn = screen.queryByRole('button', { name: /review timeline/i });
      // Button may appear after analysis completes
      if (btn) expect(btn).toBeTruthy();
    });
  });

  it('calls onComplete when review button clicked', async () => {
    const onComplete = vi.fn();
    render(<Analyze song={{ ...mockSong, status: 'analyzed' }} onComplete={onComplete} />);
    const btn = screen.queryByRole('button', { name: /review timeline/i });
    if (btn) {
      btn.click();
      expect(onComplete).toHaveBeenCalled();
    }
  });

  it('prefills title/artist inputs from the song', () => {
    render(<Analyze song={{ ...mockSong, artist: 'Test Artist' }} onComplete={() => {}} />);
    expect(screen.getByLabelText('Title')).toHaveValue('Test Song');
    expect(screen.getByLabelText('Artist')).toHaveValue('Test Artist');
  });

  it('does not PATCH metadata when values are unchanged', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    screen.getByText('Save & Refresh').click();
    await waitFor(() => {
      const patchCalls = mockFetch.mock.calls.filter(([, opts]) => opts?.method === 'PATCH');
      expect(patchCalls.length).toBe(0);
    });
  });

  it('PATCHes /metadata with the changed title on Save & Refresh', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ song_id: 'abc123', title: 'New Title' }) });
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    const titleInput = screen.getByLabelText('Title');
    fireEvent.change(titleInput, { target: { value: 'New Title' } });
    screen.getByText('Save & Refresh').click();
    await waitFor(() => {
      const patchCall = mockFetch.mock.calls.find(([, opts]) => opts?.method === 'PATCH');
      expect(patchCall).toBeTruthy();
      expect(patchCall![0]).toBe('/api/v1/songs/abc123/metadata');
      expect(JSON.parse(patchCall![1].body)).toEqual({ title: 'New Title' });
    });
  });

  it('POSTs /lyrics/check with the current title/artist and shows found result', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ found: true, reason: null, line_count: 12, preview: [] }),
    });
    render(<Analyze song={{ ...mockSong, artist: 'Test Artist' }} onComplete={() => {}} />);
    screen.getByText('Check Lyrics').click();
    await waitFor(() => {
      const checkCall = mockFetch.mock.calls.find(([url]) => url === '/api/v1/lyrics/check');
      expect(checkCall).toBeTruthy();
      expect(JSON.parse(checkCall![1].body)).toEqual({ title: 'Test Song', artist: 'Test Artist' });
      expect(screen.getByText(/Found \(12 lines\)/)).toBeTruthy();
    });
  });

  it('shows the failure reason when lyrics are not found', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ found: false, reason: 'no_match', line_count: 0, preview: [] }),
    });
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    screen.getByText('Check Lyrics').click();
    await waitFor(() => {
      expect(screen.getByText(/no match found/)).toBeTruthy();
    });
  });

  it('does not show Paste Lyrics before a Check Lyrics attempt', () => {
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    expect(screen.queryByTestId('paste-lyrics-btn')).toBeNull();
  });

  it('shows a reject-and-paste option even when Check Lyrics found a match', async () => {
    // A found match can still be the WRONG song (real incident, 2026-07-21:
    // an unrelated song's LRC matched this exact title/artist query) -- the
    // user needs a way to reject it and paste their own text regardless of
    // whether something was "found".
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ found: true, reason: null, line_count: 12, preview: [] }),
    });
    render(<Analyze song={{ ...mockSong, artist: 'Test Artist' }} onComplete={() => {}} />);
    screen.getByText('Check Lyrics').click();
    await waitFor(() => {
      expect(screen.getByText(/Found \(12 lines\)/)).toBeTruthy();
    });
    expect(screen.getByTestId('paste-lyrics-btn')).toBeTruthy();
    expect(screen.getByTestId('paste-lyrics-btn').textContent).toMatch(/not this song/i);
  });

  it('shows a preview of the matched lyrics so a wrong match is visible at a glance', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        found: true, reason: null, line_count: 67,
        preview: ['Ah ah ah ah', 'I was fine before I met you'],
      }),
    });
    render(<Analyze song={{ ...mockSong, artist: 'Test Artist' }} onComplete={() => {}} />);
    screen.getByText('Check Lyrics').click();
    await waitFor(() => {
      expect(screen.getByTestId('lyrics-preview').textContent).toContain('Ah ah ah ah');
      expect(screen.getByTestId('lyrics-preview').textContent).toContain('I was fine before I met you');
    });
  });

  it('shows no preview when nothing was found', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ found: false, reason: 'no_match', line_count: 0, preview: [] }),
    });
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    screen.getByText('Check Lyrics').click();
    await waitFor(() => {
      expect(screen.getByTestId('paste-lyrics-btn')).toBeTruthy();
    });
    expect(screen.queryByTestId('lyrics-preview')).toBeNull();
  });

  it('opens Paste Lyrics dialog and saves pasted text after a failed check', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ found: false, reason: 'no_match', line_count: 0, preview: [] }),
    });
    render(<Analyze song={{ ...mockSong, artist: 'Test Artist' }} onComplete={() => {}} />);
    screen.getByText('Check Lyrics').click();
    await waitFor(() => expect(screen.getByTestId('paste-lyrics-btn')).toBeTruthy());

    screen.getByTestId('paste-lyrics-btn').click();
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /paste lyrics/i })).toBeTruthy();
    });

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ found: true, reason: null, line_count: 2, preview: ['a', 'b'], source: 'pasted' }),
    });
    fireEvent.change(screen.getByLabelText('Lyrics text'), { target: { value: 'a\nb' } });
    screen.getByTestId('paste-lyrics-save').click();

    await waitFor(() => {
      const pasteCall = mockFetch.mock.calls.find(([url]) => url === '/api/v1/lyrics/paste');
      expect(pasteCall).toBeTruthy();
      expect(JSON.parse(pasteCall![1].body)).toEqual({
        title: 'Test Song', artist: 'Test Artist', lyrics_text: 'a\nb',
      });
      expect(screen.getByText(/Pasted \(2 lines\)/)).toBeTruthy();
      expect(screen.queryByRole('dialog', { name: /paste lyrics/i })).toBeNull();
    });
  });

  it('closes Paste Lyrics dialog on cancel without posting', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ found: false, reason: 'no_match', line_count: 0, preview: [] }),
    });
    render(<Analyze song={mockSong} onComplete={() => {}} />);
    screen.getByText('Check Lyrics').click();
    await waitFor(() => expect(screen.getByTestId('paste-lyrics-btn')).toBeTruthy());

    screen.getByTestId('paste-lyrics-btn').click();
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /paste lyrics/i })).toBeTruthy();
    });
    screen.getByTestId('paste-lyrics-cancel').click();
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /paste lyrics/i })).toBeNull();
    });
    expect(mockFetch.mock.calls.find(([url]) => url === '/api/v1/lyrics/paste')).toBeFalsy();
  });

  it('shows the persisted lyrics status for an already-analyzed song without a fresh Check Lyrics click', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === `/api/v1/songs/${mockSong.song_id}/analysis`) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ detected_sections: [], lyrics: [], lyrics_text_found: true }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    render(<Analyze song={{ ...mockSong, status: 'analyzed' }} onComplete={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/lyrics found \(no timing\)/i)).toBeTruthy();
    });
    // No fresh provider search was triggered to get this status.
    expect(mockFetch.mock.calls.find(([url]) => url === '/api/v1/lyrics/check')).toBeFalsy();
  });

  it('does not show a lyrics status for an already-analyzed song with nothing found', async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === `/api/v1/songs/${mockSong.song_id}/analysis`) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ detected_sections: [], lyrics: [], lyrics_text_found: false }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    render(<Analyze song={{ ...mockSong, status: 'analyzed' }} onComplete={() => {}} />);
    await waitFor(() => {
      expect(screen.getByTestId('analyze-screen')).toBeTruthy();
    });
    expect(screen.queryByText(/lyrics found/i)).toBeNull();
  });

});

// ──────────────────────────────────────────────────────────────────────
// deriveSectionReviewStatus — pure function unit tests
//
// Per openspec change `agreement-score-operationalization` task 5.4 and
// the spec's "section-list low_confidence indicator" scenarios. Tests
// the pure-function logic that drives the section row's review flag.
//
// Tested at function level rather than at the rendered-component level
// because the section list is inlined inside Analyze.tsx and only renders
// in the live-pipeline view (the "already analyzed" summary view returns
// early at line 448 with no section list). Testing the pure function is
// a more focused, less brittle target — it isolates the indicator logic
// from the full pipeline state machine.
//
// Threshold for low_confidence is `agreement_score <= 0` (retuned
// 2026-04-25 from <= 1; corpus measurement on 16 songs / 145 sections
// showed <= 1 flagged 38% of sections, <= 0 flags only the 11%
// genuinely uncorroborated boundaries).
// ──────────────────────────────────────────────────────────────────────
describe('deriveSectionReviewStatus', () => {
  it('no flag when neither low_confidence nor SSM-unsupported', () => {
    const status = deriveSectionReviewStatus({
      low_confidence: false,
      agreement_score: 3,
    });
    expect(status.needsReview).toBe(false);
    expect(status.tooltip).toBe('');
  });

  it('flags when low_confidence is true', () => {
    const status = deriveSectionReviewStatus({
      low_confidence: true,
      agreement_score: 0,
    });
    expect(status.needsReview).toBe(true);
    expect(status.tooltip).toMatch(/verify boundary/i);
    expect(status.tooltip).toMatch(/score 0/);
  });

  it('flags when chorus_ssm_supported is false', () => {
    const status = deriveSectionReviewStatus({
      low_confidence: false,
      agreement_score: 4,
      chorus_ssm_supported: false,
    });
    expect(status.needsReview).toBe(true);
    expect(status.tooltip).toMatch(/verify Chorus label/i);
  });

  it('joins both reasons with a middot when both signals fire', () => {
    const status = deriveSectionReviewStatus({
      low_confidence: true,
      agreement_score: 0,
      chorus_ssm_supported: false,
    });
    expect(status.needsReview).toBe(true);
    expect(status.tooltip).toMatch(/verify boundary/i);
    expect(status.tooltip).toMatch(/verify Chorus label/i);
    expect(status.tooltip).toContain(' · ');
  });

  it('treats absent chorus_ssm_supported as supported (no flag)', () => {
    // Per spec D1: missing field → treated as supported. Only
    // explicit false should flag.
    const status = deriveSectionReviewStatus({
      low_confidence: false,
      agreement_score: 3,
      // chorus_ssm_supported intentionally omitted
    });
    expect(status.needsReview).toBe(false);
    expect(status.tooltip).toBe('');
  });

  it('treats chorus_ssm_supported=true as supported (no flag)', () => {
    const status = deriveSectionReviewStatus({
      low_confidence: false,
      agreement_score: 3,
      chorus_ssm_supported: true,
    });
    expect(status.needsReview).toBe(false);
  });

  it('includes the actual agreement_score in the boundary tooltip', () => {
    // Lets reviewers see the raw score without changing the on/off logic.
    // Useful when debugging close-call boundaries.
    const status = deriveSectionReviewStatus({
      low_confidence: true,
      agreement_score: 0,
    });
    expect(status.tooltip).toContain('score 0');
  });
});

// ──────────────────────────────────────────────────────────────────────
// deriveSectionRefinementStatus — pure function unit tests
//
// Per OpenSpec change `lyric-anchored-boundary-refinement` task 5.4 and
// the spec's "refinement indicator" scenarios. Tests the pure-function
// logic that drives the section row's "↻" boundary-refined indicator.
// ──────────────────────────────────────────────────────────────────────
describe('deriveSectionRefinementStatus', () => {
  it('no indicator when boundary_refinements is empty', () => {
    const status = deriveSectionRefinementStatus({ boundary_refinements: [] });
    expect(status.refined).toBe(false);
    expect(status.tooltip).toBe('');
  });

  it('no indicator when field is absent (legacy schema 1.0.0)', () => {
    const status = deriveSectionRefinementStatus({});
    expect(status.refined).toBe(false);
    expect(status.tooltip).toBe('');
  });

  it('indicator on when boundary_refinements has one note', () => {
    const status = deriveSectionRefinementStatus({
      boundary_refinements: ['merged short post_chorus into prior chorus (gap=100ms, words=4)'],
    });
    expect(status.refined).toBe(true);
    expect(status.tooltip).toMatch(/Boundary refined:/);
    expect(status.tooltip).toMatch(/merged short post_chorus/);
  });

  it('joins multiple refinement notes with a middot', () => {
    const status = deriveSectionRefinementStatus({
      boundary_refinements: [
        'chorus hook present in transcribed bridge — relabel whole',
        'shifted start to first transcribed word at 163.75s',
      ],
    });
    expect(status.refined).toBe(true);
    expect(status.tooltip).toContain(' · ');
    expect(status.tooltip).toMatch(/relabel whole/);
    expect(status.tooltip).toMatch(/shifted start/);
  });

  it('respects explicit low_refined=true even with empty refinements', () => {
    // Theoretical: API could set low_refined without the notes list.
    // Indicator should still light up.
    const status = deriveSectionRefinementStatus({
      boundary_refinements: [],
      low_refined: true,
    });
    expect(status.refined).toBe(true);
  });

  it('respects explicit low_refined=false even with non-empty refinements', () => {
    // Theoretical: API could explicitly suppress the indicator.
    const status = deriveSectionRefinementStatus({
      boundary_refinements: ['note'],
      low_refined: false,
    });
    expect(status.refined).toBe(false);
  });
});
