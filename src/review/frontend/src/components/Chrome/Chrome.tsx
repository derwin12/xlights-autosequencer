import React from 'react';
import type { Screen } from 'src/store/app';
import type { Song, Folder } from 'src/store/library';
import { About } from '../About/About';
import styles from './Chrome.module.css';

function fmtBuildTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

const TABS: { id: Screen; label: string; key: string }[] = [
  { id: 'library', label: 'Library', key: '1' },
  { id: 'drop', label: 'Drop', key: '2' },
  { id: 'analyze', label: 'Analyze', key: '3' },
  { id: 'timeline', label: 'Timeline', key: '4' },
  { id: 'theme', label: 'Theme', key: '5' },
  { id: 'export', label: 'Export', key: '6' },
];

// Which screen to route to based on song status
function targetScreenForStatus(status: Song['status']): string {
  switch (status) {
    case 'themed':
      return 'theme';
    case 'analyzed':
      return 'timeline';
    case 'draft':
    default:
      return 'analyze';
  }
}

interface Props {
  activeScreen: Screen;
  onNavigate?: (screen: Screen) => void;
  children: React.ReactNode;
  // LibraryRail props (T097, T098, T099)
  songs?: Song[];
  folders?: Folder[];
  activeSongId?: string | null;
  onSelectSong?: (song: Song, screen: string) => void;
  onSongMoved?: (songId: string, targetFolderId: string) => void;
  onRemoveSong?: (song: Song) => void;
}

export function Chrome({ activeScreen, onNavigate, children, songs, folders, activeSongId, onSelectSong, onSongMoved, onRemoveSong }: Props) {
  const showRail = songs && folders && songs.length > 0;
  const [railCollapsed, setRailCollapsed] = React.useState<boolean>(() => {
    try { return localStorage.getItem('xonset.railCollapsed') === '1'; }
    catch { return false; }
  });

  const toggleRail = () => {
    setRailCollapsed((prev) => {
      const next = !prev;
      try { localStorage.setItem('xonset.railCollapsed', next ? '1' : '0'); } catch {}
      return next;
    });
  };

  const [aboutOpen, setAboutOpen] = React.useState(false);

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <span className={styles.wordmark}>xOnset</span>
        <nav role="tablist" className={styles.toolStrip}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-label={tab.label}
              data-active={String(activeScreen === tab.id)}
              className={styles.tab}
              onClick={() => onNavigate?.(tab.id)}
            >
              <span className={styles.tabKey}>{tab.key}</span>
              {tab.label}
            </button>
          ))}
        </nav>
        <button
          data-testid="build-stamp"
          onClick={() => setAboutOpen(true)}
          title="Frontend build — click for details"
          style={{
            marginLeft: 'auto',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--color-text-muted, #666)',
            fontSize: 11,
            fontFamily: 'monospace',
            whiteSpace: 'nowrap',
            padding: '0 12px',
          }}
        >
          {__GIT_COMMIT__} · built {fmtBuildTime(__BUILD_TIME__)}
        </button>
      </header>
      <About open={aboutOpen} onClose={() => setAboutOpen(false)} />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {showRail && railCollapsed && (
          <div
            className={styles.railCollapsed}
            onClick={toggleRail}
            title="Expand library rail"
          >
            <span className={styles.railCollapsedLabel}>▸ LIBRARY</span>
          </div>
        )}
        {showRail && !railCollapsed && (
          <div style={{ position: 'relative', display: 'flex' }}>
            <button
              className={styles.railCollapseBtn}
              onClick={toggleRail}
              title="Collapse library rail"
            >
              ◂
            </button>
            <LibraryRail
              songs={songs!}
              folders={folders!}
              activeSongId={activeSongId ?? null}
              onSelectSong={onSelectSong}
              onSongMoved={onSongMoved}
              onRemoveSong={onRemoveSong}
            />
          </div>
        )}
        <main className={styles.content}>{children}</main>
      </div>
      <footer className={styles.statusBar} />
    </div>
  );
}

// ─── LibraryRail ─────────────────────────────────────────────────────────────

interface RailProps {
  songs: Song[];
  folders: Folder[];
  activeSongId: string | null;
  onSelectSong?: (song: Song, screen: string) => void;
  onSongMoved?: (songId: string, targetFolderId: string) => void;
  onRemoveSong?: (song: Song) => void;
}

function LibraryRail({ songs, folders, activeSongId, onSelectSong, onSongMoved, onRemoveSong }: RailProps) {
  const [collapsedFolders, setCollapsedFolders] = React.useState<Set<string>>(
    () => new Set(folders.filter((f) => f.collapsed).map((f) => (f as any).folder_id ?? (f as any).id)),
  );
  const [dragOverFolder, setDragOverFolder] = React.useState<string | null>(null);
  const dragSongId = React.useRef<string | null>(null);

  // Build folder → songs map
  const songsByFolder = React.useMemo(() => {
    const map = new Map<string, Song[]>();
    for (const song of songs) {
      const fid = song.folder_id || 'unfiled';
      if (!map.has(fid)) map.set(fid, []);
      map.get(fid)!.push(song);
    }
    return map;
  }, [songs]);

  function toggleFolder(folderId: string) {
    setCollapsedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(folderId)) {
        next.delete(folderId);
      } else {
        next.add(folderId);
      }
      return next;
    });
  }

  function handleDragStart(songId: string) {
    dragSongId.current = songId;
  }

  function handleDrop(targetFolderId: string) {
    const songId = dragSongId.current;
    if (songId && onSongMoved) {
      onSongMoved(songId, targetFolderId);
    }
    dragSongId.current = null;
    setDragOverFolder(null);
  }

  return (
    <aside
      data-testid="library-rail"
      style={{
        width: 220,
        flexShrink: 0,
        overflowY: 'auto',
        borderRight: '1px solid var(--color-border, #333)',
        padding: '12px 0',
        background: 'var(--color-bg, #111)',
      }}
    >
      {folders.map((folder) => {
        const folderId = (folder as any).folder_id ?? (folder as any).id;
        const folderSongs = songsByFolder.get(folderId) ?? [];
        const isCollapsed = collapsedFolders.has(folderId) || folder.collapsed;
        const isDragTarget = dragOverFolder === folderId;

        return (
          <div
            key={folderId}
            onDragOver={(e) => { e.preventDefault(); setDragOverFolder(folderId); }}
            onDragLeave={() => setDragOverFolder(null)}
            onDrop={() => handleDrop(folderId)}
            style={{ background: isDragTarget ? 'rgba(74,222,128,0.05)' : undefined }}
          >
            {/* Folder header */}
            <button
              onClick={() => toggleFolder(folderId)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                width: '100%',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: 'var(--color-text-muted, #888)',
                fontWeight: 600,
                fontSize: 11,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                padding: '6px 12px',
                textAlign: 'left',
              }}
            >
              <span style={{ fontSize: 9 }}>{isCollapsed ? '▶' : '▼'}</span>
              {folder.name}
            </button>

            {!isCollapsed && folderSongs.map((song) => (
              <RailSongItem
                key={song.song_id}
                song={song}
                isActive={song.song_id === activeSongId}
                onClick={() => onSelectSong?.(song, targetScreenForStatus(song.status))}
                onDragStart={() => handleDragStart(song.song_id)}
                onRemove={onRemoveSong ? () => onRemoveSong(song) : undefined}
              />
            ))}
          </div>
        );
      })}
    </aside>
  );
}

interface RailSongItemProps {
  song: Song;
  isActive: boolean;
  onClick: () => void;
  onDragStart?: () => void;
  onRemove?: () => void;
}

function RailSongItem({ song, isActive, onClick, onDragStart, onRemove }: RailSongItemProps) {
  const STATUS_COLORS: Record<string, string> = {
    draft: '#888',
    analyzed: '#4ade80',
    themed: '#60a5fa',
    source_missing: '#ef4444',
  };

  return (
    <div
      data-testid={`rail-song-${song.song_id}`}
      data-active={String(isActive)}
      draggable={!!onDragStart}
      onClick={onClick}
      onDragStart={onDragStart}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '6px 12px',
        cursor: 'pointer',
        background: isActive ? 'var(--color-accent-muted, rgba(74,222,128,0.1))' : 'transparent',
        borderLeft: isActive ? '2px solid var(--color-accent, #4ade80)' : '2px solid transparent',
      }}
    >
      <span
        style={{
          fontSize: 13,
          color: 'var(--color-text, #f5f5f0)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          flex: 1,
        }}
      >
        {song.title}
      </span>
      <span
        data-testid={`rail-status-chip-${song.song_id}`}
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: STATUS_COLORS[song.status] ?? '#888',
          flexShrink: 0,
          marginLeft: 6,
        }}
        title={song.status}
      />
      {onRemove && (
        <button
          data-testid={`rail-remove-${song.song_id}`}
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          title="Remove from library"
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--color-text-muted, #888)',
            fontSize: 12,
            padding: '0 4px',
            lineHeight: 1,
          }}
        >
          ×
        </button>
      )}
    </div>
  );
}
