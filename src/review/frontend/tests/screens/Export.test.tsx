import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { Export } from '../../src/screens/Export';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

const song = {
  song_id: 'abc123',
  title: 'Test Song',
  status: 'themed',
  duration_ms: 60000,
};

describe('Export screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: any unstubbed fetch (e.g. the layout-summary GET /api/v1/layout
    // that fires whenever a layoutId is present) resolves harmlessly.
    mockFetch.mockResolvedValue({ ok: false, json: async () => ({}) });
  });

  it('shows layout-required block when the committed layout is missing', () => {
    render(<Export song={song} layoutId={null} />);
    expect(screen.getByTestId('layout-required')).toBeTruthy();
  });

  it('shows layout-required block when layout has no xml_path', () => {
    render(<Export song={song} layoutId="layout_abc123" layoutXmlPath={null} />);
    expect(screen.getByTestId('layout-required')).toBeTruthy();
  });

  it('shows export form when layout is present', () => {
    render(<Export song={song} layoutId="layout_abc123" layoutXmlPath="/tmp/layout_abc123.xml" />);
    expect(screen.queryByTestId('layout-required')).toBeNull();
    expect(screen.getByTestId('export-form')).toBeTruthy();
  });

  it('render button triggers export API', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ export_id: 'exp_1', started_at: '2026-01-01T00:00:00Z' }),
    });

    render(<Export song={song} layoutId="layout_abc123" layoutXmlPath="/tmp/layout_abc123.xml" />);
    const btn = screen.getByRole('button', { name: /render/i });
    btn.click();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/export'),
        expect.any(Object),
      );
    });
  });

  it('shows incomplete_theming message when not themed', () => {
    render(<Export song={{ ...song, status: 'analyzed' }} layoutId="layout_abc123" layoutXmlPath="/tmp/layout_abc123.xml" />);
    expect(screen.getByTestId('incomplete-theming')).toBeTruthy();
  });

  describe('Save Bundle', () => {
    // Consolidated save (user request 2026-08-04): replaces the old Theme
    // screen's assignments-only Save Mappings with one button here that
    // captures title/artist + theme assignments + every session extra.

    it('triggers a download of the save-bundle endpoint', () => {
      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
      let hrefUsed: string | null = null;
      vi.spyOn(HTMLAnchorElement.prototype, 'href', 'set').mockImplementation(function (this: HTMLAnchorElement, v: string) {
        hrefUsed = v;
      });

      render(<Export song={song} layoutId="layout_abc123" layoutXmlPath="/tmp/layout_abc123.xml" />);
      screen.getByTestId('save-bundle-button').click();

      expect(clickSpy).toHaveBeenCalled();
      expect(hrefUsed).toBe(`/api/v1/songs/${song.song_id}/save-bundle`);
      clickSpy.mockRestore();
    });
  });
});
