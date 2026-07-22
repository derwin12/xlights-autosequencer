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

  it('links to the Layout tab when no layout is active', () => {
    const onNavigateToLayout = vi.fn();
    render(<Export song={song} layoutId={null} onNavigateToLayout={onNavigateToLayout} />);
    const btn = screen.getByRole('button', { name: /go to layout/i });
    btn.click();
    expect(onNavigateToLayout).toHaveBeenCalled();
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

  it('manage-layout link on the export form navigates to the Layout tab', () => {
    const onNavigateToLayout = vi.fn();
    render(
      <Export
        song={song}
        layoutId="layout_abc123"
        layoutXmlPath="/tmp/layout_abc123.xml"
        onNavigateToLayout={onNavigateToLayout}
      />,
    );
    screen.getByTestId('manage-layout-link').click();
    expect(onNavigateToLayout).toHaveBeenCalled();
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
});
