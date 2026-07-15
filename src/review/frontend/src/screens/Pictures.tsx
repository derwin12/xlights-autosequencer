import React, { useState } from 'react';
import styles from './Pictures.module.css';

interface ImageSuggestion {
  word: string;
  start_ms: number;
  end_ms: number;
  matched_file: string;
  matched_tag: string;
  score: number;
}

interface ImageTopic {
  word: string;
  start_ms: number;
  end_ms: number;
}

interface Song {
  song_id: string;
  title: string;
}

interface PicturesScreenProps {
  song: Song;
  imageSuggestions: ImageSuggestion[];
  imageTopics: ImageTopic[];
  onContinue: () => void;
}

function formatTimestamp(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function Pictures({ song, imageSuggestions, imageTopics, onContinue }: PicturesScreenProps) {
  const [uploaded, setUploaded] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleUpload(topic: ImageTopic, file: File) {
    setUploading(topic.word);
    setError(null);
    try {
      const form = new FormData();
      form.append('image', file);
      form.append('tag', topic.word.toLowerCase());
      const res = await fetch('/api/v1/images', { method: 'POST', body: form });
      const body = await res.json();
      if (!res.ok) {
        setError(body?.error?.message ?? 'Upload failed');
        return;
      }
      setUploaded((prev) => new Set(prev).add(topic.word));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error');
    } finally {
      setUploading(null);
    }
  }

  const remainingTopics = imageTopics.filter((t) => !uploaded.has(t.word));

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <h2 className={styles.title}>{song.title}</h2>
        <button className={styles.continueBtn} onClick={onContinue}>
          Continue to Export
        </button>
      </div>

      <p className={styles.intro}>
        Pictures effects cycle through your uploaded image library on Matrix and Mega Tree props.
        The library is shared across every song — an image you upload here for one song's lyrics
        is automatically suggested again for any future song that mentions the same word.
      </p>

      {error && <p className={styles.error}>{error}</p>}

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Suggested topics</h3>
        <p className={styles.sectionHint}>
          These lyric words don't have a matching image in your library yet. Upload one to make
          it available for this song (and any future song mentioning the same word).
        </p>
        {remainingTopics.length === 0 ? (
          <p className={styles.empty}>No unmatched topics — nothing to upload.</p>
        ) : (
          <ul className={styles.topicList}>
            {remainingTopics.map((t) => (
              <li key={`${t.word}-${t.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(t.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{t.word}&rdquo;</span>
                <label className={styles.uploadLabel}>
                  {uploading === t.word ? 'Uploading…' : 'Choose image'}
                  <input
                    type="file"
                    accept=".gif,.png,.bmp,.jpg,.jpeg"
                    className={styles.uploadInput}
                    disabled={uploading === t.word}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file) handleUpload(t, file);
                      e.target.value = '';
                    }}
                  />
                </label>
              </li>
            ))}
          </ul>
        )}
      </section>

      {(imageSuggestions.length > 0 || uploaded.size > 0) && (
        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Already matched</h3>
          <ul className={styles.topicList}>
            {imageSuggestions.map((s, i) => (
              <li key={`matched-${s.word}-${s.start_ms}-${i}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(s.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{s.word}&rdquo;</span>
                <span className={styles.matchedArrow}>&rarr;</span>
                <span className={styles.matchedFile}>{s.matched_file}</span>
              </li>
            ))}
            {imageTopics.filter((t) => uploaded.has(t.word)).map((t) => (
              <li key={`uploaded-${t.word}-${t.start_ms}`} className={styles.topicItem}>
                <span className={styles.topicTime}>{formatTimestamp(t.start_ms)}</span>
                <span className={styles.topicWord}>&ldquo;{t.word}&rdquo;</span>
                <span className={styles.matchedArrow}>&rarr;</span>
                <span className={styles.matchedFile}>uploaded</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
