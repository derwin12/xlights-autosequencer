// Editable sections UI — inline handles on the strip/waveform + Sections mode.
const { useApp, THEMES_BY_ID, fmt } = window;

const SECTION_KINDS = ['intro', 'verse', 'pre-chorus', 'chorus', 'bridge', 'solo', 'breakdown', 'outro'];

function nearestBarSec(t) {
  const bars = window.HIGHWAY.bars;
  let best = t, bd = Infinity;
  for (const b of bars) { const d = Math.abs(b - t); if (d < bd) { bd = d; best = b; } }
  return best;
}

// ---------------------------------------------------------------------------
// Inline editable SECTION STRIP — replaces SectionsRow when on timeline
// Handles: drag edges, right-click context menu, double-click rename, kind dot cycles.
// ---------------------------------------------------------------------------
function EditableSectionStrip({ tall = false }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const wrapRef = React.useRef(null);
  const [drag, setDrag] = React.useState(null); // {sectionIdx, edge: 'start'|'end', snap: bool}
  const [menu, setMenu] = React.useState(null); // {x,y,sectionIdx,atT}
  const [editing, setEditing] = React.useState(null); // {idx, value}

  const pctFromEvent = (e) => {
    const r = wrapRef.current.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  };
  const tFromEvent = (e) => pctFromEvent(e) * song.duration;

  // drag
  React.useEffect(() => {
    if (!drag) return;
    const onMove = (e) => {
      let nt = tFromEvent(e);
      if (e.shiftKey === false) nt = nearestBarSec(nt);
      const secs = app.sections;
      const s = secs[drag.sectionIdx];
      const prevS = secs[drag.sectionIdx - 1];
      const nextS = secs[drag.sectionIdx + 1];
      if (drag.edge === 'start') {
        const minT = (prevS?.start ?? 0) + 0.5;
        const maxT = s.end - 0.5;
        nt = Math.max(minT, Math.min(maxT, nt));
        app.updateSection(drag.sectionIdx, { start: nt });
        if (prevS) app.updateSection(drag.sectionIdx - 1, { end: nt });
      } else {
        const minT = s.start + 0.5;
        const maxT = (nextS?.end ?? song.duration) - 0.5;
        nt = Math.max(minT, Math.min(maxT, nt));
        app.updateSection(drag.sectionIdx, { end: nt });
        if (nextS) app.updateSection(drag.sectionIdx + 1, { start: nt });
      }
    };
    const onUp = () => setDrag(null);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [drag, app.sections]);

  // close menu on outside click
  React.useEffect(() => {
    if (!menu) return;
    const off = () => setMenu(null);
    window.addEventListener('click', off);
    return () => window.removeEventListener('click', off);
  }, [menu]);

  const height = tall ? 60 : 28;

  return (
    <div ref={wrapRef} style={{
      height, display: 'flex', position: 'relative',
      borderBottom: `1px solid ${t.line}`, flexShrink: 0,
      background: t.bg1,
    }}>
      {app.sections.map((s, i) => {
        const w = ((s.end - s.start) / song.duration) * 100;
        const th = THEMES_BY_ID[app.sectionThemes[i]];
        const active = i === app.curSectionIdx;
        const selected = i === app.selectedSection;
        const isEditing = editing?.idx === i;
        const lowConf = (s.conf ?? 1) < 0.55;
        return (
          <div key={s.id}
            onClick={(e) => {
              if (drag) return;
              app.setSelectedSection(i);
              app.seekTo(s.start + 0.1);
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              setMenu({ x: e.clientX, y: e.clientY, sectionIdx: i, atT: tFromEvent(e) });
            }}
            onDoubleClick={(e) => {
              e.stopPropagation();
              setEditing({ idx: i, value: s.label });
            }}
            style={{
              width: `${w}%`,
              padding: tall ? '8px 10px' : '5px 8px',
              fontFamily: t.mono, fontSize: tall ? 12 : 10,
              color: t.ink,
              display: 'flex', alignItems: 'center', gap: 8,
              background: `linear-gradient(180deg, ${th.accent}${active ? 'aa' : selected ? '66' : '33'}, ${th.accent}${active ? '44' : '18'})`,
              borderRight: i < app.sections.length - 1 ? `1px solid ${t.line2}` : 'none',
              position: 'relative',
              cursor: 'pointer',
              boxShadow: selected ? `inset 0 0 0 1.5px ${t.accent}` : 'none',
              minWidth: 0,
            }}>
            {/* kind dot — click to cycle */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                const idx = SECTION_KINDS.indexOf(s.kind);
                const next = SECTION_KINDS[(idx + 1) % SECTION_KINDS.length];
                app.updateSection(i, { kind: next });
              }}
              style={{
                width: tall ? 10 : 7, height: tall ? 10 : 7,
                background: th.accent, border: 'none', padding: 0,
                flexShrink: 0, cursor: 'pointer',
              }}
              title={`${s.kind} · click to cycle`}
            />
            {lowConf && <span style={{ color: t.warn, fontSize: tall ? 12 : 10, lineHeight: 1 }}>⚠</span>}
            {/* label or input */}
            {isEditing ? (
              <input
                autoFocus
                value={editing.value}
                onChange={e => setEditing({ ...editing, value: e.target.value })}
                onKeyDown={e => {
                  if (e.key === 'Enter') { app.updateSection(i, { label: editing.value }); setEditing(null); }
                  if (e.key === 'Escape') setEditing(null);
                }}
                onBlur={() => { app.updateSection(i, { label: editing.value }); setEditing(null); }}
                onClick={e => e.stopPropagation()}
                style={{
                  flex: 1, background: t.bg0, color: t.ink, border: `1px solid ${t.accent}`,
                  fontFamily: t.mono, fontSize: tall ? 12 : 10, padding: '1px 4px', outline: 'none',
                  minWidth: 0,
                }}
              />
            ) : (
              <span style={{
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                flex: 1, minWidth: 0,
              }}>
                {s.label}
                {tall && <span style={{ color: t.ink3 }}> · {th.name}</span>}
              </span>
            )}
            {tall && (
              <span style={{ fontFamily: t.mono, fontSize: 9, color: t.ink3, flexShrink: 0 }}>
                {fmt.timeShort(s.start)}
              </span>
            )}
          </div>
        );
      })}

      {/* Draggable edge handles (absolute, over the strip) */}
      {app.sections.slice(0, -1).map((s, i) => {
        const boundaryT = s.end;
        const left = (boundaryT / song.duration) * 100;
        const isDragging = drag && drag.sectionIdx === i && drag.edge === 'end';
        const conf = app.sections[i + 1]?.conf ?? 1;
        const low = conf < 0.55;
        return (
          <div key={'h' + i}
            onMouseDown={(e) => {
              e.stopPropagation();
              setDrag({ sectionIdx: i, edge: 'end' });
            }}
            style={{
              position: 'absolute', left: `${left}%`, top: 0, bottom: 0,
              width: 12, transform: 'translateX(-50%)',
              cursor: 'ew-resize', zIndex: 2,
            }}
            title={`boundary · ${fmt.time(boundaryT)}${low ? ' · low confidence' : ''}`}>
            <div style={{
              position: 'absolute', left: '50%', top: 0, bottom: 0,
              width: isDragging ? 2 : 1,
              background: isDragging ? t.accent : low ? t.warn : t.line2,
              borderLeft: low && !isDragging ? `1px dashed ${t.warn}` : 'none',
              transform: 'translateX(-50%)',
              pointerEvents: 'none',
              opacity: isDragging ? 1 : 0.85,
            }}/>
            <div style={{
              position: 'absolute', top: '50%', left: '50%',
              width: 6, height: Math.max(14, height / 2),
              transform: 'translate(-50%, -50%)',
              background: isDragging ? t.accent : t.bg3,
              border: `1px solid ${isDragging ? t.accent : t.line2}`,
              pointerEvents: 'none',
            }}/>
          </div>
        );
      })}

      {/* Context menu */}
      {menu && (
        <SectionContextMenu
          menu={menu}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
}

function SectionContextMenu({ menu, onClose }) {
  const app = useApp();
  const t = app.theme;
  const s = app.sections[menu.sectionIdx];
  if (!s) return null;
  const items = [
    { label: `split at ${fmt.time(menu.atT)}`, onClick: () => app.splitSection(menu.sectionIdx, menu.atT) },
    { label: 'merge with next', onClick: () => app.mergeWithNext(menu.sectionIdx), disabled: menu.sectionIdx >= app.sections.length - 1 },
    { label: 'delete', onClick: () => app.deleteSection(menu.sectionIdx), disabled: app.sections.length <= 1 },
    { sep: true },
    ...SECTION_KINDS.map(k => ({
      label: (k === s.kind ? '● ' : '  ') + k,
      mono: true,
      onClick: () => app.updateSection(menu.sectionIdx, { kind: k }),
    })),
  ];
  return (
    <div
      style={{
        position: 'fixed', left: menu.x, top: menu.y,
        background: t.bg1, border: `1px solid ${t.line2}`,
        padding: 4, zIndex: 100, minWidth: 180,
        boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        fontFamily: t.mono, fontSize: 11,
      }}
      onClick={e => e.stopPropagation()}
      onContextMenu={e => e.preventDefault()}
    >
      {items.map((it, i) => it.sep ? (
        <div key={i} style={{ height: 1, background: t.line, margin: '3px 0' }}/>
      ) : (
        <div key={i}
          onClick={() => { if (!it.disabled) { it.onClick(); onClose(); } }}
          style={{
            padding: '5px 10px',
            color: it.disabled ? t.ink3 : t.ink,
            cursor: it.disabled ? 'default' : 'pointer',
            fontFamily: it.mono ? t.mono : t.sans,
            opacity: it.disabled ? 0.5 : 1,
          }}
          onMouseEnter={e => !it.disabled && (e.currentTarget.style.background = t.bg3)}
          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
        >
          {it.label}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SECTIONS MODE — taller strip + right panel listing all sections
// ---------------------------------------------------------------------------
function SectionsModePanel() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  return (
    <div style={{
      width: 340, background: t.bg1, borderLeft: `1px solid ${t.line}`,
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div style={{
        padding: '10px 14px', borderBottom: `1px solid ${t.line}`,
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <span style={{ fontFamily: t.mono, fontSize: 10, color: t.accent, letterSpacing: 1, flex: 1 }}>
          ✎ EDITING SECTIONS
        </span>
        <button onClick={() => app.setSectionsMode(false)} style={{
          background: 'transparent', color: t.ink2, border: `1px solid ${t.line2}`,
          padding: '3px 8px', fontFamily: t.mono, fontSize: 10, cursor: 'pointer',
        }}>done · esc</button>
      </div>

      <div style={{
        padding: '8px 14px', borderBottom: `1px solid ${t.line}`,
        fontFamily: t.mono, fontSize: 10, color: t.ink3, lineHeight: 1.5,
      }}>
        drag edges to nudge · snaps to bars (hold shift to bypass)<br/>
        double-click to rename · right-click for split / merge / delete
      </div>

      <div style={{ padding: '8px 14px', borderBottom: `1px solid ${t.line}`, display: 'flex', gap: 6 }}>
        <button onClick={app.resetSections} style={{
          flex: 1, background: 'transparent', color: t.ink2, border: `1px solid ${t.line2}`,
          padding: '6px 8px', fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
        }}>↺ reset to detected</button>
        <button onClick={() => app.splitSection(app.curSectionIdx, app.time)} style={{
          flex: 1, background: 'transparent', color: t.ink2, border: `1px solid ${t.line2}`,
          padding: '6px 8px', fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
        }}>✂ split at playhead</button>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        <div style={{ padding: '8px 14px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1 }}>
          SECTIONS · {app.sections.length}
        </div>
        {app.sections.map((s, i) => {
          const dur = s.end - s.start;
          const tooLong = dur > 30 && s.kind === 'verse';
          const lowConf = (s.conf ?? 1) < 0.55;
          const active = i === app.curSectionIdx;
          const th = THEMES_BY_ID[app.sectionThemes[i]];
          return (
            <div key={s.id}
              onClick={() => { app.setSelectedSection(i); app.seekTo(s.start + 0.1); }}
              style={{
                padding: '8px 14px',
                borderBottom: `1px solid ${t.line}`,
                background: active ? t.bg3 : 'transparent',
                borderLeft: active ? `2px solid ${t.accent}` : '2px solid transparent',
                cursor: 'pointer',
              }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
                <i style={{ width: 8, height: 8, background: th.accent, flexShrink: 0 }}/>
                <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, width: 22 }}>{String(i + 1).padStart(2, '0')}</span>
                <span style={{ flex: 1, fontSize: 12, color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.label}</span>
                <span style={{ fontFamily: t.mono, fontSize: 9, color: t.ink3, letterSpacing: 0.5 }}>{s.kind}</span>
              </div>
              <div style={{ display: 'flex', gap: 8, fontFamily: t.mono, fontSize: 10, color: t.ink3, paddingLeft: 16 }}>
                <span>{fmt.timeShort(s.start)}–{fmt.timeShort(s.end)}</span>
                <span style={{ color: tooLong ? t.warn : t.ink3 }}>
                  {Math.round(dur)}s{tooLong ? ' · long' : ''}
                </span>
                <div style={{ flex: 1 }}/>
                {lowConf && <span style={{ color: t.warn }}>⚠ {(s.conf ?? 0).toFixed(2)}</span>}
                <span
                  onClick={(e) => { e.stopPropagation(); app.splitSection(i, (s.start + s.end) / 2); }}
                  style={{ cursor: 'pointer', color: t.accent }}
                  title="split in half"
                >split</span>
                <span
                  onClick={(e) => { e.stopPropagation(); app.mergeWithNext(i); }}
                  style={{ cursor: i < app.sections.length - 1 ? 'pointer' : 'default', color: i < app.sections.length - 1 ? t.accent : t.ink3 }}
                  title="merge with next"
                >merge→</span>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ borderTop: `1px solid ${t.line}`, padding: '8px 14px' }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 6 }}>
          ALTERNATE BOUNDARIES · detected but unused
        </div>
        {app.altBoundaries.length === 0 && (
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>none</div>
        )}
        {app.altBoundaries.map((b, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0', fontFamily: t.mono, fontSize: 10 }}>
            <span style={{ color: t.ink3, width: 50 }}>{fmt.timeShort(b.t)}</span>
            <span style={{ color: t.ink2, flex: 1 }}>{b.kind}</span>
            <span style={{ color: b.conf < 0.5 ? t.ink3 : t.warn }}>{b.conf.toFixed(2)}</span>
            <button onClick={() => app.promoteAlt(b.t)} style={{
              background: 'transparent', color: t.accent, border: `1px solid ${t.line2}`,
              padding: '2px 6px', fontFamily: t.mono, fontSize: 10, cursor: 'pointer',
            }}>promote</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// Ghost marks drawn over the waveform in sections mode
function GhostBoundaries() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  if (!app.sectionsMode) return null;
  return (
    <>
      {app.altBoundaries.map((b, i) => {
        const x = (b.t / song.duration) * 100;
        return (
          <div key={i}
            title={`alt · ${fmt.timeShort(b.t)} · conf ${b.conf.toFixed(2)}`}
            onClick={() => app.promoteAlt(b.t)}
            style={{
              position: 'absolute', left: `${x}%`, top: 0, bottom: 0,
              width: 1, background: t.warn,
              borderLeft: `1px dashed ${t.warn}`,
              opacity: 0.5,
              pointerEvents: 'auto', cursor: 'pointer',
              zIndex: 1,
            }}/>
        );
      })}
    </>
  );
}

Object.assign(window, { EditableSectionStrip, SectionsModePanel, GhostBoundaries, SECTION_KINDS });
