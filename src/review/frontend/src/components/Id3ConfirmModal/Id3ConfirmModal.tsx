import { useEffect, useState } from 'react';
import styles from './Id3ConfirmModal.module.css';

export interface Id3ConfirmResponse {
  response: 'confirm' | 'correct' | 'skip';
  /** Replacement title — only set when response === 'correct'. */
  title?: string;
  /** Replacement artist — only set when response === 'correct'. */
  artist?: string;
  /** Whether to atomically rewrite the MP3's ID3 tags. Only meaningful with 'correct'. */
  write_back?: boolean;
}

interface Id3ConfirmModalProps {
  /** Title read from the MP3's ID3 tags (may be empty). */
  id3Title: string;
  /** Artist read from the MP3's ID3 tags (may be empty). */
  id3Artist: string;
  /** Submit the user's choice. Resolves the modal. */
  onSubmit: (response: Id3ConfirmResponse) => void;
}

/**
 * Modal shown before Genius lookup so the user can confirm, correct, or
 * skip the song's title/artist. Per OpenSpec change
 * `lyric-anchored-boundary-refinement` §6a.
 */
export function Id3ConfirmModal({ id3Title, id3Artist, onSubmit }: Id3ConfirmModalProps) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(id3Title);
  const [artist, setArtist] = useState(id3Artist);
  const [writeBack, setWriteBack] = useState(false);

  // Keep editable fields in sync if the parent re-shows the modal with new tags
  // (e.g. user cancelled and we re-prompt with refreshed values).
  useEffect(() => {
    setTitle(id3Title);
    setArtist(id3Artist);
  }, [id3Title, id3Artist]);

  function handleConfirm() {
    onSubmit({ response: 'confirm' });
  }

  function handleCorrectStart() {
    setEditing(true);
  }

  function handleCorrectSubmit() {
    const t = title.trim();
    const a = artist.trim();
    if (!t && !a) {
      // Nothing changed — treat as confirm.
      onSubmit({ response: 'confirm' });
      return;
    }
    onSubmit({ response: 'correct', title: t, artist: a, write_back: writeBack });
  }

  function handleSkip() {
    onSubmit({ response: 'skip' });
  }

  return (
    <div className={styles.overlay}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Confirm song title and artist"
        className={styles.dialog}
        data-testid="id3-confirm-modal"
      >
        <h2 className={styles.title}>Confirm song info</h2>
        <p className={styles.subtitle}>
          The analyzer will look up lyric segmentation on Genius using the title and artist.
          If the tags below are wrong, correct them so Genius hits the right song.
        </p>

        {!editing ? (
          <>
            <div className={styles.tagsRow}>
              <span className={styles.tagLabel}>Title</span>
              <span className={styles.tagValue} data-testid="id3-modal-title">
                {id3Title || <em style={{ opacity: 0.6 }}>(none)</em>}
              </span>
              <span className={styles.tagLabel}>Artist</span>
              <span className={styles.tagValue} data-testid="id3-modal-artist">
                {id3Artist || <em style={{ opacity: 0.6 }}>(none)</em>}
              </span>
            </div>
            <div className={styles.actions}>
              <button
                className={styles.btn}
                data-testid="id3-modal-skip"
                onClick={handleSkip}
              >
                Skip Genius
              </button>
              <button
                className={styles.btn}
                data-testid="id3-modal-correct"
                onClick={handleCorrectStart}
              >
                Correct
              </button>
              <button
                className={`${styles.btn} ${styles.btnPrimary}`}
                data-testid="id3-modal-confirm"
                onClick={handleConfirm}
              >
                Confirm
              </button>
            </div>
          </>
        ) : (
          <>
            <div className={styles.tagsRow}>
              <span className={styles.tagLabel}>Title</span>
              <input
                className={styles.input}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                data-testid="id3-modal-input-title"
                autoFocus
              />
              <span className={styles.tagLabel}>Artist</span>
              <input
                className={styles.input}
                value={artist}
                onChange={(e) => setArtist(e.target.value)}
                data-testid="id3-modal-input-artist"
              />
            </div>
            <label className={styles.checkboxRow}>
              <input
                type="checkbox"
                checked={writeBack}
                onChange={(e) => setWriteBack(e.target.checked)}
                data-testid="id3-modal-write-back"
              />
              Save corrected tags back to the MP3 (creates a .bak)
            </label>
            <div className={styles.actions}>
              <button
                className={styles.btn}
                data-testid="id3-modal-correct-cancel"
                onClick={() => {
                  setEditing(false);
                  setTitle(id3Title);
                  setArtist(id3Artist);
                  setWriteBack(false);
                }}
              >
                Back
              </button>
              <button
                className={`${styles.btn} ${styles.btnPrimary}`}
                data-testid="id3-modal-correct-submit"
                onClick={handleCorrectSubmit}
              >
                Use Corrected
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
