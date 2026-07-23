import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SingerLane, distinctSingers, type AttrWord } from '../../src/components/SingerLane/SingerLane';

const WORDS: AttrWord[] = [
  { label: 'A', start_ms: 0, end_ms: 400, singers: ['Blake'], backing: false },
  { label: 'B', start_ms: 500, end_ms: 900, singers: ['Gwen'], backing: false },
  { label: 'C', start_ms: 1000, end_ms: 1400, singers: ['Blake', 'Gwen'], backing: false },
  { label: 'OOH', start_ms: 1500, end_ms: 1900, singers: [], backing: true },
];

describe('distinctSingers', () => {
  it('returns names in first-appearance order, excluding backing', () => {
    expect(distinctSingers(WORDS)).toEqual(['Blake', 'Gwen']);
  });
});

describe('SingerLane', () => {
  it('renders one chip per word with singer data', () => {
    render(<SingerLane words={WORDS} durationMs={2000} onCommit={() => {}} />);
    const chips = screen.getAllByTestId('singer-word');
    expect(chips).toHaveLength(4);
    expect(chips[2].getAttribute('data-singers')).toBe('Blake|Gwen');
    expect(chips[3].getAttribute('data-singers')).toBe('Backing');
  });

  it('shows a relabel toolbar only after selecting', () => {
    render(<SingerLane words={WORDS} durationMs={2000} onCommit={() => {}} />);
    expect(screen.queryByTestId('singer-toolbar')).toBeNull();
    fireEvent.click(screen.getAllByTestId('singer-word')[1]); // select B
    expect(screen.getByTestId('singer-toolbar')).toBeInTheDocument();
  });

  it('relabels the selected word to a single singer and commits', () => {
    const onCommit = vi.fn();
    render(<SingerLane words={WORDS} durationMs={2000} onCommit={onCommit} />);
    fireEvent.click(screen.getAllByTestId('singer-word')[0]); // select A (Blake)
    fireEvent.click(screen.getByTestId('relabel-Gwen'));
    expect(onCommit).toHaveBeenCalledTimes(1);
    const next = onCommit.mock.calls[0][0] as AttrWord[];
    expect(next[0].singers).toEqual(['Gwen']);
    expect(next[0].backing).toBe(false);
  });

  it('sets Both on selection', () => {
    const onCommit = vi.fn();
    render(<SingerLane words={WORDS} durationMs={2000} onCommit={onCommit} />);
    fireEvent.click(screen.getAllByTestId('singer-word')[0]); // A
    fireEvent.click(screen.getByTestId('relabel-both'));
    const next = onCommit.mock.calls[0][0] as AttrWord[];
    expect(new Set(next[0].singers)).toEqual(new Set(['Blake', 'Gwen']));
  });

  it('sets Backing on selection', () => {
    const onCommit = vi.fn();
    render(<SingerLane words={WORDS} durationMs={2000} onCommit={onCommit} />);
    fireEvent.click(screen.getAllByTestId('singer-word')[0]); // A
    fireEvent.click(screen.getByTestId('relabel-backing'));
    const next = onCommit.mock.calls[0][0] as AttrWord[];
    expect(next[0].backing).toBe(true);
    expect(next[0].singers).toEqual([]);
  });

  it('applies to multiple selected words at once', () => {
    const onCommit = vi.fn();
    render(<SingerLane words={WORDS} durationMs={2000} onCommit={onCommit} />);
    fireEvent.click(screen.getAllByTestId('singer-word')[0]); // A
    fireEvent.click(screen.getAllByTestId('singer-word')[1]); // B
    fireEvent.click(screen.getByTestId('relabel-Blake'));
    const next = onCommit.mock.calls[0][0] as AttrWord[];
    expect(next[0].singers).toEqual(['Blake']);
    expect(next[1].singers).toEqual(['Blake']);
  });
});
