import React, { useRef, useState, useCallback } from 'react';
import styles from './Drop.module.css';

interface Song {
  song_id: string;
  title: string;
  status: string;
  duration_ms: number;
  folder_id: string;
  imported_at: string;
  source_paths: string[];
  video_path?: string | null;
}

interface DropProps {
  /**
   * Called after a successful import response (either /api/v1/import or
   * /api/v1/import-video).
   *
   * `created` is the server's "this is a new library entry" flag. When
   * `created: false` the user dropped a file that's already in the library
   * (deduplicated by SHA-256 of the audio) and the returned song is the
   * existing record. Callers can use this to decide whether to force a
   * re-analysis rather than just showing the cached result.
   */
  onSongImported: (song: Song, created: boolean) => void;
}

const ALLOWED_AUDIO_EXTS = new Set(['.mp3', '.wav', '.flac', '.aiff', '.aif']);
const ALLOWED_VIDEO_EXTS = new Set(['.mp4', '.mov', '.avi', '.mkv', '.webm']);
const ALL_ALLOWED_EXTS = new Set([...ALLOWED_AUDIO_EXTS, ...ALLOWED_VIDEO_EXTS]);

type ImportMode = 'audio' | 'video';

function getExt(filename: string): string {
  const i = filename.lastIndexOf('.');
  return i >= 0 ? filename.slice(i).toLowerCase() : '';
}

// The audio/video extension sets are disjoint, so the file itself tells us
// which import path to take -- no need to make the user pick a mode first.
function detectMode(ext: string): ImportMode | null {
  if (ALLOWED_AUDIO_EXTS.has(ext)) return 'audio';
  if (ALLOWED_VIDEO_EXTS.has(ext)) return 'video';
  return null;
}

export function Drop({ onSongImported }: DropProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<ImportMode | null>(null);

  async function handleFile(file: File) {
    const ext = getExt(file.name);
    const mode = detectMode(ext);
    if (!mode) {
      setError(`Unsupported file type: ${ext}. Supported: ${[...ALL_ALLOWED_EXTS].join(', ')}`);
      return;
    }

    setError(null);
    setLoading(mode);

    try {
      const formData = new FormData();
      const endpoint = mode === 'audio' ? '/api/v1/import' : '/api/v1/import-video';
      formData.append(mode, file);

      const res = await fetch(endpoint, {
        method: 'POST',
        body: formData,
      });

      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Import failed');
        return;
      }

      // `created` is truthy only when this is a fresh library entry.
      // Dropping a file that's already imported returns created: false.
      onSongImported(body.song, Boolean(body?.created));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
    } finally {
      setLoading(null);
    }
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  const handleDrop = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
  }, []);

  const acceptAttr = [...ALL_ALLOWED_EXTS].join(',');

  return (
    <div className={styles.root}>
      <div
        data-testid="drop-target"
        className={styles.dropZone}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onClick={() => inputRef.current?.click()}
      >
        <input
          data-testid="file-input"
          ref={inputRef}
          type="file"
          accept={acceptAttr}
          style={{ display: 'none' }}
          onChange={handleChange}
        />
        {loading ? (
          <p className={styles.hint}>
            {loading === 'audio' ? 'Importing audio…' : 'Importing video, extracting its audio track…'}
          </p>
        ) : (
          <>
            <p className={styles.hint}>Drop an audio or video file here, or click to browse</p>
            <p className={styles.sub}>
              Audio: MP3, WAV, FLAC, AIFF — analyzed directly.<br />
              Video: MP4, MOV, AVI, MKV, WEBM — its audio track drives the
              sequence, and the video itself can be placed on a matrix with
              the Video effect. Detected automatically from the file type.
            </p>
          </>
        )}
      </div>

      {error && (
        <p data-testid="error-message" className={styles.error}>{error}</p>
      )}
    </div>
  );
}
