import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { LyricTrack } from '../../src/components/LyricTrack/LyricTrack';

const lines = [
  { t_ms: 1000, duration_ms: 2000, text: 'la la placeholder line one' },
  { t_ms: 3000, duration_ms: 2000, text: 'la la placeholder line two' },
];

describe('LyricTrack', () => {
  it('renders one block per lyric line', () => {
    render(<LyricTrack lines={lines} durationMs={10000} />);
    expect(screen.getAllByTestId('lyric-line').length).toBe(2);
  });

  it('shows the empty-state placeholder when no lyrics were found', () => {
    render(<LyricTrack lines={[]} durationMs={10000} />);
    expect(screen.getByTestId('lyric-track-empty')).toBeTruthy();
    expect(screen.getByText(/no synced lyrics found/i)).toBeTruthy();
  });

  it('line block position/width is proportional to time within the view window', () => {
    const { container } = render(<LyricTrack lines={lines} durationMs={10000} />);
    const blocks = container.querySelectorAll('[data-testid="lyric-line"]');
    const first = (blocks[0] as HTMLElement).style.left;
    const second = (blocks[1] as HTMLElement).style.left;
    expect(first).toBe('10%'); // 1000ms / 10000ms
    expect(second).toBe('30%'); // 3000ms / 10000ms
  });

  it('clips lines outside the visible viewStart/viewEnd window', () => {
    render(<LyricTrack lines={lines} durationMs={10000} viewStartMs={0} viewEndMs={2000} />);
    // Only the first line overlaps [0, 2000); the second starts at 3000.
    expect(screen.getAllByTestId('lyric-line').length).toBe(1);
  });
});
