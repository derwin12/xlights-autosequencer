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
        onThemeSaved={() => {}}
        onThemeDeleted={() => {}}
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
        onThemeSaved={() => {}}
        onThemeDeleted={() => {}}
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
        onThemeSaved={() => {}}
        onThemeDeleted={() => {}}
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
        onThemeSaved={() => {}}
        onThemeDeleted={() => {}}
      />
    );

    const acceptBtn = screen.getByRole('button', { name: /^accept$/i });
    fireEvent.click(acceptBtn);

    await waitFor(() => {
      expect(onThemed).toHaveBeenCalled();
    });
  });

  describe('New Theme', () => {
    it('opens a blank create dialog and POSTs a new theme on save', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ theme: { theme_id: 'my-new-theme', name: 'My New Theme' } }),
      });

      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /new theme/i }));
      const dialogTitle = screen.getByText('New Theme');
      const dialog = dialogTitle.closest('div')?.parentElement as HTMLElement;

      // The Name field is the dialog's first <input> (Mood/Occasion are
      // <select>, Genre is a later <input>). Scoped to the dialog
      // specifically — the page also has unrelated <input>s outside it
      // (ParameterSliders' range inputs) that a page-wide query would
      // match first.
      const nameInput = Array.from(dialog.querySelectorAll('input'))[0] as HTMLInputElement;
      fireEvent.change(nameInput, { target: { value: 'My New Theme' } });
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          '/api/v1/themes',
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('My New Theme'),
          }),
        );
      });
    });

    it('shows an error instead of saving when the name is blank', () => {
      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /new theme/i }));
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      expect(screen.getByText(/name is required/i)).toBeTruthy();
      expect(mockFetch).not.toHaveBeenCalled();
    });
  });

  describe('AI palette prompt', () => {
    function openEditDialog() {
      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );
      fireEvent.click(screen.getByRole('button', { name: /new theme/i }));
      const dialogTitle = screen.getByText('New Theme');
      const dialog = dialogTitle.closest('div')?.parentElement as HTMLElement;
      return dialog;
    }

    function pasteInto(textarea: HTMLTextAreaElement, text: string) {
      fireEvent.paste(textarea, { clipboardData: { getData: () => text } });
    }

    it('asks for a base + accent group, not one flat array', () => {
      openEditDialog();
      fireEvent.click(screen.getByRole('button', { name: /suggest with ai/i }));
      const promptTextarea = Array.from(document.querySelectorAll('textarea')).find((t) => t.readOnly);
      expect(promptTextarea?.value).toContain('"base"');
      expect(promptTextarea?.value).toContain('"accent"');
    });

    it('pasting the AI JSON reply into Palette extracts only the base colors', () => {
      const dialog = openEditDialog();
      const [, paletteTextarea] = Array.from(dialog.querySelectorAll('textarea'));
      pasteInto(
        paletteTextarea as HTMLTextAreaElement,
        '{"base":["#2E1065","#00A8E8"],"accent":["#C71585","#FFB703"]}',
      );
      expect((paletteTextarea as HTMLTextAreaElement).value).toBe('#2E1065\n#00A8E8');
    });

    it('pasting the same AI JSON reply into Accent Palette extracts only the accent colors', () => {
      const dialog = openEditDialog();
      const [, , accentTextarea] = Array.from(dialog.querySelectorAll('textarea'));
      pasteInto(
        accentTextarea as HTMLTextAreaElement,
        '{"base":["#2E1065","#00A8E8"],"accent":["#C71585","#FFB703"]}',
      );
      expect((accentTextarea as HTMLTextAreaElement).value).toBe('#C71585\n#FFB703');
    });

    it('falls back to flat hex extraction for a non-JSON paste (e.g. old-style array string)', () => {
      const dialog = openEditDialog();
      const [, paletteTextarea] = Array.from(dialog.querySelectorAll('textarea'));
      pasteInto(paletteTextarea as HTMLTextAreaElement, '["#2E1065","#00A8E8","#C71585","#FFB703"]');
      expect((paletteTextarea as HTMLTextAreaElement).value).toBe(
        '#2E1065\n#00A8E8\n#C71585\n#FFB703',
      );
    });
  });

  describe('New Theme dialog backdrop', () => {
    it('does not close when a text-selection drag starts inside the dialog and releases on the backdrop', () => {
      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );
      fireEvent.click(screen.getByRole('button', { name: /new theme/i }));
      const dialogTitle = screen.getByText('New Theme');
      const dialog = dialogTitle.closest('div')?.parentElement as HTMLElement;
      const overlay = dialog.parentElement as HTMLElement;
      const [descriptionTextarea] = Array.from(dialog.querySelectorAll('textarea'));

      fireEvent.mouseDown(descriptionTextarea);
      fireEvent.mouseUp(overlay);

      expect(screen.getByText('New Theme')).toBeTruthy();
    });

    it('closes on a genuine click directly on the backdrop', () => {
      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );
      fireEvent.click(screen.getByRole('button', { name: /new theme/i }));
      const dialogTitle = screen.getByText('New Theme');
      const dialog = dialogTitle.closest('div')?.parentElement as HTMLElement;
      const overlay = dialog.parentElement as HTMLElement;

      fireEvent.mouseDown(overlay);
      fireEvent.mouseUp(overlay);

      expect(screen.queryByText('New Theme')).toBeNull();
    });
  });

  describe('theme list stays in sync without a reload', () => {
    const editableThemes = [
      ...themes,
      {
        theme_id: 'test-theme',
        name: 'test',
        description: 'test',
        accent: '#1e1b4b',
        swatches: ['#1e1b4b', '#7dd3fc'],
        default_for_kinds: ['verse'],
        editable: true,
      },
    ];

    it('calls onThemeSaved with the created theme so it appears in the grid immediately', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: async () => ({ theme: { theme_id: 'my-new-theme', name: 'My New Theme', editable: true } }),
      });
      const onThemeSaved = vi.fn();

      render(
        <Theme
          song={song}
          themes={themes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={onThemeSaved}
          onThemeDeleted={() => {}}
        />
      );

      fireEvent.click(screen.getByRole('button', { name: /new theme/i }));
      const dialogTitle = screen.getByText('New Theme');
      const dialog = dialogTitle.closest('div')?.parentElement as HTMLElement;
      const nameInput = Array.from(dialog.querySelectorAll('input'))
        .find((el) => el.type !== 'file') as HTMLInputElement;
      fireEvent.change(nameInput, { target: { value: 'My New Theme' } });
      fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

      await waitFor(() => {
        expect(onThemeSaved).toHaveBeenCalledWith(
          expect.objectContaining({ theme_id: 'my-new-theme', name: 'My New Theme' }),
        );
      });
    });

    it('Delete button only appears for existing editable themes, not built-ins or New Theme', () => {
      render(
        <Theme
          song={song}
          themes={editableThemes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );

      // Built-in theme: no edit affordance at all.
      expect(screen.queryByLabelText('Edit Shimmer Wash')).toBeNull();

      // Custom theme: edit opens a dialog with a Delete button.
      fireEvent.click(screen.getByLabelText('Edit test'));
      expect(screen.getByRole('button', { name: /^delete$/i })).toBeTruthy();
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

      // New Theme dialog: no theme to delete yet.
      fireEvent.click(screen.getByRole('button', { name: /new theme/i }));
      expect(screen.queryByRole('button', { name: /^delete$/i })).toBeNull();
    });

    it('deletes the theme after confirmation and calls onThemeDeleted', async () => {
      vi.stubGlobal('confirm', vi.fn(() => true));
      mockFetch.mockResolvedValue({ ok: true, json: async () => ({ theme_id: 'test-theme' }) });
      const onThemeDeleted = vi.fn();

      render(
        <Theme
          song={song}
          themes={editableThemes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={onThemeDeleted}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit test'));
      fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith('/api/v1/themes/test-theme', { method: 'DELETE' });
        expect(onThemeDeleted).toHaveBeenCalledWith('test-theme');
      });
      expect(screen.queryByText('Edit Theme')).toBeNull();
    });

    it('does not delete when the confirmation is declined', () => {
      vi.stubGlobal('confirm', vi.fn(() => false));

      render(
        <Theme
          song={song}
          themes={editableThemes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit test'));
      fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

      expect(mockFetch).not.toHaveBeenCalled();
      expect(screen.getByText('Edit Theme')).toBeTruthy();
    });

    it('shows an in-use error from the API without closing the dialog', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        json: async () => ({ error: { code: 'theme_in_use', message: 'Theme is still assigned in: Test Song' } }),
      });
      vi.stubGlobal('confirm', vi.fn(() => true));

      render(
        <Theme
          song={song}
          themes={editableThemes}
          sections={sections}
          assignments={assignments}
          onThemed={() => {}}
          onAssignmentChange={() => {}}
          onThemeSaved={() => {}}
          onThemeDeleted={() => {}}
        />
      );

      fireEvent.click(screen.getByLabelText('Edit test'));
      fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));

      await waitFor(() => {
        expect(screen.getByText(/still assigned in: Test Song/i)).toBeTruthy();
      });
      expect(screen.getByText('Edit Theme')).toBeTruthy();
    });
  });
});
