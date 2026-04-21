// Review timeline screen — scrub, play, raw detector tracks.
const { useApp, Chrome, THEMES_BY_ID, LightsPreview, ALGOS, fmt, WAVE } = window;

function ReviewTimeline() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const sec = app.sections[app.curSectionIdx];
  const selThemeId = app.sectionThemes[app.curSectionIdx];
  const selTheme = THEMES_BY_ID[selThemeId];

  // Current beat + confidence
  const beat = app.curBeat;

  const inspector = (
    <div style={{
      width: 300, background: t.bg1, borderLeft: `1px solid ${t.line}`,
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div style={{
        padding: '10px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3,
        letterSpacing: 1, borderBottom: `1px solid ${t.line}`,
      }}>PLAYHEAD</div>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, marginBottom: 4 }}>NOW</div>
        <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.3, fontFamily: t.mono, color: t.ink, marginBottom: 2, fontVariantNumeric: 'tabular-nums' }}>
          {fmt.time(app.time)}
        </div>
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>
          bar {beat?.bar ?? 0} · beat {(beat?.beat ?? 0) + 1} of 4
        </div>
      </div>
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>CURRENT SECTION</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <i style={{ width: 10, height: 10, background: selTheme.accent }}/>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{sec.label}</div>
            <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>{selTheme.name}</div>
          </div>
        </div>
      </div>
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>CONFIDENCE</div>
        {[
          ['librosa_beats', 0.91, t.ok],
          ['qm_bars',       0.83, t.ok],
          ['energy impact', 0.72, t.warn],
          ['chord change',  0.64, t.warn],
        ].map(([lib, c, col], i) => (
          <div key={i} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', fontFamily: t.mono, fontSize: 11, marginBottom: 2 }}>
              <span style={{ flex: 1, color: t.ink2 }}>{lib}</span>
              <span style={{ color: t.ink, fontVariantNumeric: 'tabular-nums' }}>{c.toFixed(2)}</span>
            </div>
            <div style={{ height: 3, background: t.bg3 }}>
              <i style={{ display: 'block', height: '100%', width: `${c * 100}%`, background: col }}/>
            </div>
          </div>
        ))}
      </div>
      <div style={{ padding: '10px 14px' }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>LIGHTS OUT</div>
        <LightsPreview height={36} cells={32} compact/>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, marginTop: 6 }}>
          RGB {selTheme.swatches[2]} · theme "{selTheme.name}" · all 4 props
        </div>
      </div>
      <div style={{ flex: 1 }}/>
      <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.line}`, display: 'flex', gap: 6 }}>
        <button onClick={() => app.seekTo(app.time - 0.01)} style={nudgeBtn(t)}>nudge -10ms</button>
        <button onClick={() => app.seekTo(app.time + 0.01)} style={nudgeBtn(t)}>nudge +10ms</button>
      </div>
    </div>
  );

  const transportExtra = (
    <>
      <span>{fmt.time(app.time)} / {fmt.time(song.duration)}</span>
      <span>bar {beat?.bar ?? 0} · beat {(beat?.beat ?? 0) + 1}</span>
    </>
  );

  const { EditableSectionStrip, SectionsModePanel } = window;
  return (
    <Chrome inspector={app.sectionsMode ? <SectionsModePanel/> : inspector} statusExtra={transportExtra}>
      <TransportBar/>
      <Ruler/>
      <EditableSectionStrip tall={app.sectionsMode}/>
      <div style={{ borderBottom: `1px solid ${t.line}` }}>
        <LightsPreview height={40} cells={72}/>
      </div>
      <WavePane/>

      {/* Raw tracks drawer */}
      <div style={{ flex: 1, background: t.bg0, display: 'flex', flexDirection: 'column', minHeight: 0, borderTop: `1px solid ${t.line}` }}>
        <div style={{
          height: 30, background: t.bg1, borderBottom: `1px solid ${t.line}`,
          display: 'flex', alignItems: 'center', padding: '0 14px', gap: 12, flexShrink: 0,
        }}>
          <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink, letterSpacing: 1 }}>▾ RAW ALGORITHM TRACKS</span>
          <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
            {ALGOS.filter(a => app.algoStates[a.id]).length} / {ALGOS.length} visible
          </span>
          <div style={{ flex: 1 }}/>
          <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>conf ≥ 0.50</span>
          <span style={{ fontFamily: t.mono, fontSize: 10, color: t.accent, cursor: 'pointer' }}>+ add detector</span>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {ALGOS.map((a, i) => <AlgoTrack key={a.id} a={a} rowIdx={i}/>)}
        </div>
      </div>
    </Chrome>
  );
}

function TransportBar() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  return (
    <div style={{
      height: 44, background: t.bg1, borderBottom: `1px solid ${t.line}`,
      display: 'flex', alignItems: 'center', padding: '0 14px', gap: 12, flexShrink: 0,
    }}>
      <div style={{ fontSize: 14, fontWeight: 600, color: t.ink }}>{song.title}</div>
      <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>{song.bpm} BPM · {song.key} · {fmt.timeShort(song.duration)}</div>
      <div style={{ flex: 1 }}/>
      <div style={{ display: 'flex', gap: 4 }}>
        <button onClick={() => app.seekTo(0)} style={transportStyle(t)}>⏮</button>
        <button onClick={() => app.seekTo(app.time - 5)} style={transportStyle(t)}>◀◀</button>
        <button onClick={app.togglePlay} style={{
          ...transportStyle(t),
          background: app.playing ? t.accent : t.bg3,
          color: app.playing ? t.accentInk : t.ink,
          width: 36, fontWeight: 700,
        }}>{app.playing ? '❚❚' : '▶'}</button>
        <button onClick={() => app.seekTo(app.time + 5)} style={transportStyle(t)}>▶▶</button>
        <button onClick={() => app.seekTo(song.duration - 0.5)} style={transportStyle(t)}>⏭</button>
      </div>
      <div style={{ fontFamily: t.mono, fontSize: 20, fontWeight: 600, color: t.ink, letterSpacing: 0.5, fontVariantNumeric: 'tabular-nums', minWidth: 120, textAlign: 'right' }}>
        {fmt.time(app.time)}
      </div>
    </div>
  );
}

function Ruler() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const ticks = [];
  for (let s = 0; s <= song.duration; s += 20) ticks.push(s);
  const pct = (app.time / song.duration) * 100;
  const wrapRef = React.useRef(null);
  const onClick = (e) => {
    const r = wrapRef.current.getBoundingClientRect();
    const p = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    app.seekTo(p * song.duration);
  };
  return (
    <div ref={wrapRef} onClick={onClick} style={{
      height: 22, background: t.bg1, borderBottom: `1px solid ${t.line}`,
      position: 'relative', cursor: 'pointer', flexShrink: 0,
    }}>
      {ticks.map((s, i) => {
        const x = (s / song.duration) * 100;
        const m = Math.floor(s / 60), sec = s % 60;
        return (
          <div key={i} style={{
            position: 'absolute', left: `${x}%`, top: 0, bottom: 0,
            borderLeft: `1px solid ${t.line2}`, padding: '4px 4px',
            fontFamily: t.mono, fontSize: 9, color: t.ink3,
          }}>
            {m}:{String(sec).padStart(2, '0')}
          </div>
        );
      })}
      <div style={{
        position: 'absolute', left: `${pct}%`, transform: 'translateX(-50%)',
        top: 2, background: t.accent, color: t.accentInk,
        fontFamily: t.mono, fontSize: 9, fontWeight: 600, padding: '1px 5px',
        letterSpacing: 0.5, whiteSpace: 'nowrap',
      }}>{fmt.time(app.time)}</div>
    </div>
  );
}

function SectionsRow() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  return (
    <div style={{
      height: 26, display: 'flex', position: 'relative',
      borderBottom: `1px solid ${t.line}`, flexShrink: 0,
    }}>
      {app.sections.map((s, i) => {
        const w = ((s.end - s.start) / song.duration) * 100;
        const th = THEMES_BY_ID[app.sectionThemes[i]];
        const active = i === app.curSectionIdx;
        return (
          <div key={i}
            onClick={() => { app.setSelectedSection(i); app.seekTo(s.start); }}
            style={{
              width: `${w}%`,
              borderRight: i < app.sections.length - 1 ? `1px solid ${t.line2}` : 'none',
              padding: '5px 8px', fontFamily: t.mono, fontSize: 10,
              color: t.ink, display: 'flex', alignItems: 'center', gap: 6,
              background: `linear-gradient(90deg, ${th.accent}${active ? '88' : '44'}, ${th.accent}${active ? '33' : '18'})`,
              position: 'relative', cursor: 'pointer',
            }}>
            <i style={{ width: 6, height: 6, background: th.accent, display: 'inline-block', flexShrink: 0 }}/>
            <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {s.label} · {th.name}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function WavePane() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const wrapRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);

  const pctFromEvent = (e) => {
    const r = wrapRef.current.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  };
  const onMouseDown = (e) => {
    setDragging(true);
    app.seekTo(pctFromEvent(e) * song.duration);
  };
  React.useEffect(() => {
    if (!dragging) return;
    const onMove = (e) => app.seekTo(pctFromEvent(e) * song.duration);
    const onUp = () => setDragging(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [dragging]);

  const pct = (app.time / song.duration) * 100;

  // Visible beats (just bars, for perf)
  const bars = song.bars;

  return (
    <div ref={wrapRef} onMouseDown={onMouseDown} style={{
      height: 120, position: 'relative', background: '#000',
      borderBottom: `1px solid ${t.line}`, cursor: 'ew-resize', flexShrink: 0,
    }}>
      <svg width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 520 120" style={{ display: 'block' }}>
        {/* section tints behind wave */}
        {app.sections.map((s, i) => {
          const x = (s.start / song.duration) * 520;
          const w = ((s.end - s.start) / song.duration) * 520;
          const th = THEMES_BY_ID[app.sectionThemes[i]];
          return <rect key={'b' + i} x={x} y={0} width={w} height={120} fill={th.accent} opacity={0.08}/>;
        })}
        {/* waveform */}
        {WAVE.map((v, i) => {
          const h = v * 100;
          return <rect key={i} x={i} y={60 - h / 2} width={0.9} height={h} fill={t.ink2} opacity={0.75}/>;
        })}
        {/* played-through overlay */}
        <rect x={0} y={0} width={pct / 100 * 520} height={120} fill={t.accent} opacity={0.08}/>
        {/* bars */}
        {bars.map((b, i) => {
          const x = (b / song.duration) * 520;
          return <line key={'bar' + i} x1={x} x2={x} y1={0} y2={120} stroke={t.accent} strokeWidth={0.35} opacity={0.3}/>;
        })}
        {/* playhead */}
        <line x1={pct / 100 * 520} x2={pct / 100 * 520} y1={0} y2={120} stroke="#fff" strokeWidth={1.2}/>
        <circle cx={pct / 100 * 520} cy={8} r={3.5} fill="#fff"/>
      </svg>
      <div style={{ position: 'absolute', top: 4, left: 8, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 0.5 }}>
        WAVEFORM · {bars.length} bars · {song.beats.length} beats
      </div>
      <div style={{ position: 'absolute', top: 4, right: 8, fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>zoom 1× · drag to scrub</div>
      {window.GhostBoundaries && <window.GhostBoundaries/>}
    </div>
  );
}

// Raw detector row
function AlgoTrack({ a, rowIdx }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const on = app.algoStates[a.id];

  // pick points based on algo id
  const pts = React.useMemo(() => {
    if (a.id === 'beats') return song.beats.map(b => ({ t: b.t, v: 0.85 }));
    if (a.id === 'bars')  return song.bars.map(t0 => ({ t: t0, v: 1 }));
    if (a.id === 'kick')  return song.impacts.map(i => ({ t: i.t, v: 0.5 + i.conf * 0.5 }));
    if (a.id === 'drop')  return song.drops.map(i => ({ t: i.t, v: 0.5 + i.conf * 0.5 }));
    if (a.id === 'onsets') {
      // generate deterministic extras
      const out = [];
      for (let i = 0; i < song.bars.length; i++) {
        out.push({ t: song.bars[i] + 0.12, v: 0.5 });
        out.push({ t: song.bars[i] + 0.6, v: 0.6 });
        out.push({ t: song.bars[i] + 1.2, v: 0.4 });
      }
      return out;
    }
    if (a.id === 'chord') {
      // one per 2 bars
      return song.bars.filter((_, i) => i % 4 === 0).map(t0 => ({ t: t0, v: 0.8 }));
    }
    if (a.id === 'bass') return song.bars.map((t0, i) => ({ t: t0 + (i % 2 === 0 ? 0 : 0.5), v: 0.7 }));
    if (a.id === 'voc')  return song.bars.filter((_, i) => i > 6 && i < 50 && i % 3 === 0).map(t0 => ({ t: t0 + 0.3, v: 0.5 }));
    return [];
  }, [a.id]);

  const pct = (app.time / song.duration) * 100;

  return (
    <div style={{
      display: 'flex', height: 28, borderBottom: `1px solid ${t.line}`,
      opacity: on ? 1 : 0.4,
    }}>
      <div style={{
        width: 220, padding: '0 10px', display: 'flex', alignItems: 'center', gap: 8,
        background: t.bg1, borderRight: `1px solid ${t.line}`, flexShrink: 0,
      }}>
        <button
          onClick={() => app.toggleAlgo(a.id)}
          style={{
            background: 'transparent', border: 'none', color: on ? t.ink : t.ink3,
            fontFamily: t.mono, fontSize: 11, cursor: 'pointer', padding: 0, width: 16,
          }}>{on ? '●' : '○'}</button>
        <i style={{ width: 8, height: 8, background: a.color, flexShrink: 0 }}/>
        <span style={{
          fontFamily: t.mono, fontSize: 11, color: on ? t.ink : t.ink3,
          flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>{a.name}</span>
        <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>{pts.length}</span>
      </div>
      <div style={{
        flex: 1, position: 'relative',
        background: rowIdx % 2 === 0 ? t.bg0 : 'rgba(255,255,255,0.01)',
      }}>
        <svg width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 520 28" style={{ display: 'block' }}>
          {pts.map((p, i) => {
            const x = (p.t / song.duration) * 520;
            const h = p.v * 22;
            const live = Math.abs(p.t - app.time) < 0.15 && app.playing;
            return <rect key={i} x={x - 0.5} y={14 - h / 2} width={1} height={h}
                         fill={live ? '#fff' : a.color} opacity={live ? 1 : 0.85}/>;
          })}
          <line x1={pct / 100 * 520} x2={pct / 100 * 520} y1={0} y2={28} stroke="#fff" strokeWidth={1} opacity={0.9}/>
        </svg>
      </div>
    </div>
  );
}

function transportStyle(t) {
  return {
    width: 30, height: 26, background: t.bg2, color: t.ink2,
    border: `1px solid ${t.line2}`, fontFamily: t.mono, fontSize: 11,
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', padding: 0,
  };
}
function nudgeBtn(t) {
  return {
    flex: 1, background: 'transparent', color: t.ink2,
    border: `1px solid ${t.line2}`, padding: '6px 8px',
    fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
  };
}

Object.assign(window, { ReviewTimeline });
