import React from 'react';
import type { Screen } from 'src/store/app';
import type { Song, Folder } from 'src/store/library';
import { About, shortCommit } from '../About/About';
import { Help } from '../Help/Help';
import { useManifestStore } from '../../store/manifest';
import { isBackendStale, isUpdateAvailable } from '../../lib/manifestStaleness';
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
  { id: 'drop', label: 'Import', key: '2' },
  { id: 'analyze', label: 'Analyze', key: '3' },
  { id: 'timeline', label: 'Timeline', key: '4' },
  { id: 'theme', label: 'Theme', key: '5' },
  { id: 'pictures', label: 'Pictures', key: '6' },
  { id: 'export', label: 'Export', key: '7' },
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
  onCreateFolder?: (name: string) => Promise<string | null>;
  onRemoveFolder?: (folderId: string) => void;
}

export function Chrome({ activeScreen, onNavigate, children, songs, folders, activeSongId, onSelectSong, onSongMoved, onRemoveSong, onCreateFolder, onRemoveFolder }: Props) {
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
  const [helpOpen, setHelpOpen] = React.useState(false);

  // Backend code stamp — the Vite build stamp only covers the JS bundle;
  // this shows what commit the server process is actually running.
  const manifest = useManifestStore((s) => s.manifest);
  const loadManifest = useManifestStore((s) => s.load);
  React.useEffect(() => { void loadManifest(); }, [loadManifest]);
  const backendStale = isBackendStale(manifest?.backend_commit, manifest?.repo_head_commit);
  const updateAvailable = isUpdateAvailable(
    manifest?.repo_head_commit, manifest?.origin_main_commit, manifest?.origin_ahead_of_head,
  );

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <span className={styles.wordmark}>xLightsAI</span>
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
          data-testid="help-button"
          onClick={() => setHelpOpen(true)}
          title="Help & FAQ"
          style={{
            marginLeft: 'auto',
            background: 'none',
            border: '1px solid var(--color-border, #444)',
            borderRadius: '50%',
            cursor: 'pointer',
            color: 'var(--color-text-muted, #888)',
            width: 22,
            height: 22,
            fontSize: 12,
            fontWeight: 700,
            lineHeight: 1,
            padding: 0,
          }}
        >
          ?
        </button>
        <button
          data-testid="build-stamp"
          onClick={() => setAboutOpen(true)}
          title={
            (updateAvailable
              ? `origin/main has moved past this checkout (${manifest?.origin_main_commit}) — run "git pull" (then restart) to update. `
              : backendStale
              ? `Backend is running an older commit than HEAD (${manifest?.repo_head_commit}) — restart the server to pick up the latest code. `
              : 'ui = frontend bundle, api = running backend code — click for details')
            + (manifest?.backend_started_at ? ` (backend up since ${fmtBuildTime(manifest.backend_started_at)})` : '')
          }
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            color: (updateAvailable || backendStale) ? 'var(--color-warning, #f59e0b)' : 'var(--color-text-muted, #666)',
            fontSize: 11,
            fontFamily: 'monospace',
            whiteSpace: 'nowrap',
            padding: '0 12px',
            fontWeight: (updateAvailable || backendStale) ? 600 : 'normal',
          }}
        >
          ui {__GIT_COMMIT__} · built {fmtBuildTime(__BUILD_TIME__)}
          {manifest?.backend_commit ? ` · api ${shortCommit(manifest.backend_commit)}` : ''}
          {updateAvailable ? ' ⚠ update available' : backendStale ? ' ⚠ restart needed' : ''}
        </button>
      </header>
      <About open={aboutOpen} onClose={() => setAboutOpen(false)} />
      <Help open={helpOpen} onClose={() => setHelpOpen(false)} />
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
              onCreateFolder={onCreateFolder}
              onRemoveFolder={onRemoveFolder}
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
  onCreateFolder?: (name: string) => Promise<string | null>;
  onRemoveFolder?: (folderId: string) => void;
}

function LibraryRail({ songs, folders, activeSongId, onSelectSong, onSongMoved, onRemoveSong, onCreateFolder, onRemoveFolder }: RailProps) {
  const [collapsedFolders, setCollapsedFolders] = React.useState<Set<string>>(
    () => new Set(folders.filter((f) => f.collapsed).map((f) => (f as any).folder_id ?? (f as any).id)),
  );
  const [dragOverFolder, setDragOverFolder] = React.useState<string | null>(null);
  const [draggingSongId, setDraggingSongId] = React.useState<string | null>(null);
  // Pointer-based drag instead of the HTML5 Drag and Drop API: on Windows,
  // Tauri's native window-level drag-drop capture (tauri.conf.json's
  // dragDropEnabled, needed for importing an audio file dropped from
  // Explorer onto the Drop screen -- see src/lib/nativeDialog.ts's
  // tauri://drag-drop listener) intercepts ALL drag operations ending in a
  // drop on the window, including ones that start on an in-page DOM
  // element -- the browser's own dragstart/dragover/drop events for a song
  // row never fire at all (bug found 2026-07-25: song-to-folder drag
  // silently did nothing in the packaged app). Manual pointer tracking
  // sidesteps the native capture entirely since it's not the OS drag
  // protocol.
  const dragStateRef = React.useRef<{ songId: string; startX: number; startY: number; dragging: boolean } | null>(null);
  const wasDraggedRef = React.useRef(false);

  const handlePointerMove = React.useCallback((e: PointerEvent) => {
    const state = dragStateRef.current;
    if (!state) return;
    const dx = e.clientX - state.startX;
    const dy = e.clientY - state.startY;
    if (!state.dragging && Math.hypot(dx, dy) > 6) {
      state.dragging = true;
      wasDraggedRef.current = true;
      setDraggingSongId(state.songId);
    }
    if (state.dragging) {
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const folderEl = el?.closest<HTMLElement>('[data-folder-drop-id]');
      setDragOverFolder(folderEl?.dataset.folderDropId ?? null);
    }
  }, []);

  const handlePointerUp = React.useCallback((e: PointerEvent) => {
    window.removeEventListener('pointermove', handlePointerMove);
    window.removeEventListener('pointerup', handlePointerUp);
    const state = dragStateRef.current;
    if (state?.dragging) {
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const folderEl = el?.closest<HTMLElement>('[data-folder-drop-id]');
      const targetFolderId = folderEl?.dataset.folderDropId;
      if (targetFolderId && onSongMoved) {
        onSongMoved(state.songId, targetFolderId);
      }
    }
    dragStateRef.current = null;
    setDraggingSongId(null);
    setDragOverFolder(null);
  }, [handlePointerMove, onSongMoved]);

  const handlePointerDown = React.useCallback((songId: string, e: React.PointerEvent) => {
    if (e.button !== 0) return;
    dragStateRef.current = { songId, startX: e.clientX, startY: e.clientY, dragging: false };
    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
  }, [handlePointerMove, handlePointerUp]);
  const [creatingFolder, setCreatingFolder] = React.useState(false);
  const [newFolderName, setNewFolderName] = React.useState('');
  const [createError, setCreateError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);

  async function submitNewFolder() {
    const name = newFolderName.trim();
    if (!name) {
      setCreatingFolder(false);
      setCreateError(null);
      return;
    }
    if (!onCreateFolder) return;
    setCreating(true);
    const errorMessage = await onCreateFolder(name);
    setCreating(false);
    if (errorMessage) {
      setCreateError(errorMessage);
      return;
    }
    setCreatingFolder(false);
    setNewFolderName('');
    setCreateError(null);
  }

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
            data-folder-drop-id={folderId}
            style={{ background: isDragTarget ? 'rgba(74,222,128,0.05)' : undefined }}
          >
            {/* Folder header */}
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <button
                onClick={() => toggleFolder(folderId)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  flex: 1,
                  minWidth: 0,
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
              {onRemoveFolder && folderId !== 'unfiled' && (
                <button
                  data-testid={`remove-folder-${folderId}`}
                  onClick={(e) => { e.stopPropagation(); onRemoveFolder(folderId); }}
                  title="Delete folder"
                  style={{
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    color: 'var(--color-text-muted, #888)',
                    fontSize: 12,
                    padding: '0 12px 0 4px',
                    lineHeight: 1,
                  }}
                >
                  ×
                </button>
              )}
            </div>

            {!isCollapsed && folderSongs.map((song) => (
              <RailSongItem
                key={song.song_id}
                song={song}
                isActive={song.song_id === activeSongId}
                isDragging={draggingSongId === song.song_id}
                onClick={() => {
                  if (wasDraggedRef.current) { wasDraggedRef.current = false; return; }
                  onSelectSong?.(song, targetScreenForStatus(song.status));
                }}
                onPointerDown={(e) => handlePointerDown(song.song_id, e)}
                onRemove={onRemoveSong ? () => onRemoveSong(song) : undefined}
              />
            ))}
          </div>
        );
      })}

      {onCreateFolder && (
        creatingFolder ? (
          <div style={{ padding: '6px 12px' }}>
            <input
              data-testid="new-folder-input"
              autoFocus
              value={newFolderName}
              disabled={creating}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitNewFolder();
                if (e.key === 'Escape') { setCreatingFolder(false); setNewFolderName(''); setCreateError(null); }
              }}
              onBlur={submitNewFolder}
              placeholder="Folder name"
              style={{
                width: '100%',
                background: 'var(--color-surface-2, #1e1e24)',
                border: '1px solid var(--color-accent, #4ade80)',
                borderRadius: 4,
                color: 'var(--color-text, #f5f5f0)',
                fontSize: 12,
                padding: '4px 6px',
              }}
            />
            {createError && (
              <p style={{ color: 'var(--color-error, #ef4444)', fontSize: 11, margin: '4px 0 0' }}>
                {createError}
              </p>
            )}
          </div>
        ) : (
          <button
            data-testid="new-folder-button"
            onClick={() => { setCreatingFolder(true); setCreateError(null); }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              width: '100%',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--color-text-muted, #888)',
              fontSize: 11,
              padding: '6px 12px',
              textAlign: 'left',
            }}
          >
            + New Folder
          </button>
        )
      )}
    </aside>
  );
}

interface RailSongItemProps {
  song: Song;
  isActive: boolean;
  isDragging?: boolean;
  onClick: () => void;
  onPointerDown?: (e: React.PointerEvent) => void;
  onRemove?: () => void;
}

function RailSongItem({ song, isActive, isDragging, onClick, onPointerDown, onRemove }: RailSongItemProps) {
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
      onClick={onClick}
      onPointerDown={onPointerDown}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '6px 12px',
        cursor: 'pointer',
        opacity: isDragging ? 0.4 : 1,
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
