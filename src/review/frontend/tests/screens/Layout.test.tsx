import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { LayoutScreen } from '../../src/screens/Layout';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('Layout screen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows "no layout active" when nothing is set yet', async () => {
    mockFetch.mockResolvedValue({ ok: false, json: async () => ({}) });
    render(<LayoutScreen onLayoutChange={() => {}} />);
    await waitFor(() => {
      expect(screen.getByTestId('layout-current-summary')).toBeTruthy();
    });
    expect(screen.getByText(/no layout active yet/i)).toBeTruthy();
  });

  it('shows the active layout summary when one is set', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        layout_id: 'layout_abc123',
        display_name: 'xlights_rgbeffects.xml',
        props: [{ name: 'Arch 1' }, { name: 'Arch 2' }],
        is_uploaded: true,
      }),
    });
    render(<LayoutScreen onLayoutChange={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/2 props/i)).toBeTruthy();
    });
    expect(screen.getByText(/custom upload/i)).toBeTruthy();
  });

  it('always renders the upload form', () => {
    mockFetch.mockResolvedValue({ ok: false, json: async () => ({}) });
    render(<LayoutScreen onLayoutChange={() => {}} />);
    expect(screen.getByTestId('layout-upload')).toBeTruthy();
    expect(screen.getByTestId('layout-upload-submit')).toBeTruthy();
  });
});
