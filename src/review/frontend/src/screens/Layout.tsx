import { useEffect, useState } from 'react';
import { LayoutUpload, type ActiveLayout } from '../components/LayoutUpload/LayoutUpload';
import styles from './Layout.module.css';

interface LayoutProps {
  /** Called whenever the active layout changes (upload or revert), so the
   * app-level layoutId/xmlPath state (lifted in App.tsx, shared with the
   * Export screen) stays in sync. */
  onLayoutChange: (layout: ActiveLayout | null) => void;
}

/**
 * Step 1 of the workflow: establish which xLights layout xOnset generates
 * against, before dropping a song. Every prop-tier grouping, effect
 * placement, and the Export screen's bundled layout all key off whatever
 * is active here.
 */
export function LayoutScreen({ onLayoutChange }: LayoutProps) {
  const [layoutInfo, setLayoutInfo] = useState<ActiveLayout | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch('/api/v1/layout')
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        setLayoutInfo(body?.layout_id ? body : null);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  function handleChange(layout: ActiveLayout | null) {
    setLayoutInfo(layout);
    onLayoutChange(layout);
  }

  return (
    <div data-testid="layout-screen" className={styles.root}>
      <h2 className={styles.title}>Layout</h2>
      <p className={styles.intro}>
        Every song exports against this layout — its props drive the 8-tier
        Power Groups (spatial, rhythmic, prop type, compound, heroes) the
        generator places effects on. Set it up here before dropping a song.
      </p>

      {loaded && (
        <div data-testid="layout-current-summary" className={styles.summary}>
          {layoutInfo ? (
            <p>
              Active: <strong>{layoutInfo.display_name ?? layoutInfo.layout_id}</strong>
              {layoutInfo.props ? ` · ${layoutInfo.props.length} props` : ''}
              {layoutInfo.imported_at
                ? ` · as of ${new Date(layoutInfo.imported_at).toLocaleDateString()}`
                : ''}
              {' · '}
              <span className={layoutInfo.is_uploaded ? styles.badgeUploaded : styles.badgeDefault}>
                {layoutInfo.is_uploaded ? 'custom upload' : 'repo default'}
              </span>
            </p>
          ) : (
            <p className={styles.noneActive}>No layout active yet.</p>
          )}
        </div>
      )}

      <LayoutUpload onLayoutChange={handleChange} showRemove={layoutInfo?.is_uploaded === true} />
    </div>
  );
}
