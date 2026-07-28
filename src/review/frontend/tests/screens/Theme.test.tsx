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

  describe('Save/Load theme mappings', () => {
    // User request (2026-07-28): a manual export/import round-trip for
    // theme assignments, since the session JSON they normally live in can
    // be wiped by environment resets (e.g. an ephemeral devcontainer home
    // dir) between visits.

    it('Save Mappings triggers a JSON file download', () => {
      const createObjectURL = vi.fn(() => 'blob:mock-url');
      const revokeObjectURL = vi.fn();
      vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL });
      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

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

      fireEvent.click(screen.getByRole('button', { name: /save mappings/i }));

      expect(createObjectURL).toHaveBeenCalled();
      expect(clickSpy).toHaveBeenCalled();
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
      clickSpy.mockRestore();
    });

    it('Load Mappings applies each section via PUT and calls onAssignmentChange', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          assignment: { section_index: 0, theme_id: 'peak-flash', overrides: {}, user_confirmed: true },
        }),
      });
      const onAssignmentChange = vi.fn();

      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={onAssignmentChange}
        />
      );

      const fileContents = JSON.stringify({
        schema_version: 1,
        assignments: [{ section_index: 0, theme_id: 'peak-flash', overrides: {} }],
      });
      const file = new File([fileContents], 'mappings.json', { type: 'application/json' });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(onAssignmentChange).toHaveBeenCalledWith(
          expect.objectContaining({ section_index: 0, theme_id: 'peak-flash' }),
        );
      });
      expect(mockFetch).toHaveBeenCalledWith(
        `/api/v1/songs/${song.song_id}/assignments/0`,
        expect.objectContaining({ method: 'PUT' }),
      );
    });

    it('Load Mappings skips sections not present in this song', async () => {
      const onAssignmentChange = vi.fn();
      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={onAssignmentChange}
        />
      );

      const fileContents = JSON.stringify({
        assignments: [{ section_index: 99, theme_id: 'peak-flash', overrides: {} }],
      });
      const file = new File([fileContents], 'mappings.json', { type: 'application/json' });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/no matching sections/i)).toBeTruthy();
      });
      expect(mockFetch).not.toHaveBeenCalled();
      expect(onAssignmentChange).not.toHaveBeenCalled();
    });

    it('Load Mappings shows an error for invalid JSON', async () => {
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

      const file = new File(['not json'], 'mappings.json', { type: 'application/json' });
      const input = document.querySelector('input[type="file"]') as HTMLInputElement;
      fireEvent.change(input, { target: { files: [file] } });

      await waitFor(() => {
        expect(screen.getByText(/not valid json/i)).toBeTruthy();
      });
    });
  });
});
