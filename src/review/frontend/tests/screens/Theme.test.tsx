import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Theme } from '../../src/screens/Theme';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const themes = [
  {
    theme_id: 'shimmer-wash',
    name: 'Shimmer Wash',
    description: 'Slow color drift.',
    accent: '#4ade80',
    swatches: ['#4ade80', '#7eebd1', '#f5f5f0', '#1a1a20'],
    default_for_kinds: ['intro'],
  },
  {
    theme_id: 'peak-flash',
    name: 'Peak Flash',
    description: 'High-contrast hits.',
    accent: '#facc15',
    swatches: ['#facc15', '#fb923c', '#f5f5f0', '#0d0d10'],
    default_for_kinds: ['chorus'],
  },
];

const song = {
  song_id: 'abc123',
  title: 'Test Song',
  status: 'analyzed',
  duration_ms: 60000,
};

const sections = [
  { index: 0, start_ms: 0, end_ms: 30000, kind: 'intro', label: 'Intro' },
];

const assignments = [
  { section_index: 0, theme_id: 'shimmer-wash', overrides: {}, user_confirmed: false },
];

describe('Theme screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders theme grid', () => {
    render(
      <Theme
        song={song}
        themes={themes}
        sections={sections}
        assignments={assignments}
        onThemed={() => {}}
        onAssignmentChange={() => {}}
      />
    );
    expect(screen.getByText('Shimmer Wash')).toBeTruthy();
    expect(screen.getByText('Peak Flash')).toBeTruthy();
  });

  it('shows assigned theme marked', () => {
    render(
      <Theme
        song={song}
        themes={themes}
        sections={sections}
        assignments={assignments}
        onThemed={() => {}}
        onAssignmentChange={() => {}}
      />
    );
    // Shimmer Wash is assigned — should show ASSIGNED pill
    expect(screen.getByText(/assigned/i)).toBeTruthy();
  });

  it('shows every section using a theme as a chip on its card', () => {
    const twoSections = [
      { index: 0, start_ms: 0, end_ms: 30000, kind: 'intro', label: 'Intro' },
      { index: 1, start_ms: 30000, end_ms: 60000, kind: 'verse', label: 'Verse' },
    ];
    const twoAssignments = [
      { section_index: 0, theme_id: 'shimmer-wash', overrides: {}, user_confirmed: false },
      { section_index: 1, theme_id: 'shimmer-wash', overrides: {}, user_confirmed: false },
    ];
    render(
      <Theme
        song={song}
        themes={themes}
        sections={twoSections}
        assignments={twoAssignments}
        onThemed={() => {}}
        onAssignmentChange={() => {}}
      />
    );
    const rows = screen.getAllByTestId('assigned-sections');
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain('Intro');
    expect(rows[0].textContent).toContain('Verse');
  });

  it('accept-all button fires API and calls onThemed', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ song_status: 'themed', confirmed_count: 1 }),
    });

    const onThemed = vi.fn();
    render(
      <Theme
        song={song}
        themes={themes}
        sections={sections}
        assignments={assignments}
        onThemed={onThemed}
        onAssignmentChange={() => {}}
      />
    );

    const acceptBtn = screen.getByRole('button', { name: /accept all/i });
    fireEvent.click(acceptBtn);

    await waitFor(() => {
      expect(onThemed).toHaveBeenCalled();
    });
  });
});
