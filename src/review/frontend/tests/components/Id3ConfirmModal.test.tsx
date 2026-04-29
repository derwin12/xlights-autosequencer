/**
 * Tests for Id3ConfirmModal — OpenSpec change
 * `lyric-anchored-boundary-refinement` §6a.4. Covers Confirm / Correct
 * (with optional write-back checkbox) / Skip and the editable form.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Id3ConfirmModal } from '../../src/components/Id3ConfirmModal/Id3ConfirmModal';

describe('Id3ConfirmModal', () => {
  it('renders prefilled title and artist', () => {
    render(<Id3ConfirmModal id3Title="Hello" id3Artist="Adele" onSubmit={() => {}} />);
    expect(screen.getByTestId('id3-modal-title').textContent).toBe('Hello');
    expect(screen.getByTestId('id3-modal-artist').textContent).toBe('Adele');
  });

  it('Confirm submits {response: "confirm"}', () => {
    const onSubmit = vi.fn();
    render(<Id3ConfirmModal id3Title="Hello" id3Artist="Adele" onSubmit={onSubmit} />);
    fireEvent.click(screen.getByTestId('id3-modal-confirm'));
    expect(onSubmit).toHaveBeenCalledWith({ response: 'confirm' });
  });

  it('Skip submits {response: "skip"}', () => {
    const onSubmit = vi.fn();
    render(<Id3ConfirmModal id3Title="Hello" id3Artist="Adele" onSubmit={onSubmit} />);
    fireEvent.click(screen.getByTestId('id3-modal-skip'));
    expect(onSubmit).toHaveBeenCalledWith({ response: 'skip' });
  });

  it('Correct surfaces editable inputs prefilled with current tags', () => {
    render(<Id3ConfirmModal id3Title="Wrong Title" id3Artist="Wrong Artist" onSubmit={() => {}} />);
    fireEvent.click(screen.getByTestId('id3-modal-correct'));
    const titleInput = screen.getByTestId('id3-modal-input-title') as HTMLInputElement;
    const artistInput = screen.getByTestId('id3-modal-input-artist') as HTMLInputElement;
    expect(titleInput.value).toBe('Wrong Title');
    expect(artistInput.value).toBe('Wrong Artist');
  });

  it('Correct → Use Corrected submits override fields and write_back default false', () => {
    const onSubmit = vi.fn();
    render(<Id3ConfirmModal id3Title="Wrong" id3Artist="Wrong" onSubmit={onSubmit} />);
    fireEvent.click(screen.getByTestId('id3-modal-correct'));
    fireEvent.change(screen.getByTestId('id3-modal-input-title'), {
      target: { value: 'Right Title' },
    });
    fireEvent.change(screen.getByTestId('id3-modal-input-artist'), {
      target: { value: 'Right Artist' },
    });
    fireEvent.click(screen.getByTestId('id3-modal-correct-submit'));
    expect(onSubmit).toHaveBeenCalledWith({
      response: 'correct',
      title: 'Right Title',
      artist: 'Right Artist',
      write_back: false,
    });
  });

  it('Correct with write-back checkbox sets write_back: true', () => {
    const onSubmit = vi.fn();
    render(<Id3ConfirmModal id3Title="Wrong" id3Artist="Wrong" onSubmit={onSubmit} />);
    fireEvent.click(screen.getByTestId('id3-modal-correct'));
    fireEvent.change(screen.getByTestId('id3-modal-input-title'), {
      target: { value: 'Right Title' },
    });
    fireEvent.click(screen.getByTestId('id3-modal-write-back'));
    fireEvent.click(screen.getByTestId('id3-modal-correct-submit'));
    expect(onSubmit).toHaveBeenCalledWith({
      response: 'correct',
      title: 'Right Title',
      artist: 'Wrong',
      write_back: true,
    });
  });

  it('Correct with no edits falls back to confirm', () => {
    const onSubmit = vi.fn();
    render(<Id3ConfirmModal id3Title="" id3Artist="" onSubmit={onSubmit} />);
    fireEvent.click(screen.getByTestId('id3-modal-correct'));
    // Title and artist remain blank; clicking Use Corrected should fall
    // through to confirm rather than submitting empty overrides.
    fireEvent.click(screen.getByTestId('id3-modal-correct-submit'));
    expect(onSubmit).toHaveBeenCalledWith({ response: 'confirm' });
  });

  it('Back from Correct returns to confirm view', () => {
    render(<Id3ConfirmModal id3Title="A" id3Artist="B" onSubmit={() => {}} />);
    fireEvent.click(screen.getByTestId('id3-modal-correct'));
    fireEvent.click(screen.getByTestId('id3-modal-correct-cancel'));
    expect(screen.getByTestId('id3-modal-confirm')).toBeTruthy();
  });

  it('shows fallback "(none)" placeholder for empty tags', () => {
    render(<Id3ConfirmModal id3Title="" id3Artist="" onSubmit={() => {}} />);
    expect(screen.getByTestId('id3-modal-title').textContent).toContain('(none)');
    expect(screen.getByTestId('id3-modal-artist').textContent).toContain('(none)');
  });
});
