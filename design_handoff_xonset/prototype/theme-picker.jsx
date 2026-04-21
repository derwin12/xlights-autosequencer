// Theme picker — the north-star interactive screen.
// Layout: header → section strip (click to select) → current section inspector
// → theme grid (click to assign) → live lights preview → timeline strip.
const { useApp, Chrome, THEMES, THEMES_BY_ID, LightsPreview, MiniLights, fmt } = window;

const KIND_GLYPH = { intro: '○', verse: '▮', chorus: '▲', solo: '◆', bridge: '◈', outro: '◌' };

function ThemePicker() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const selIdx = app.selectedSection;
  const sec = app.sections[selIdx];
  const selThemeId = app.sectionThemes[selIdx];
  const selTheme = THEMES_BY_ID[selThemeId];

  const inspector = (
    <div style={{
      width: 300, background: t.bg1, borderLeft: `1px solid ${t.line}`,
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div style={{
        padding: '10px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3,
        letterSpacing: 1, borderBottom: `1px solid ${t.line}`,
      }}>SECTION · {selIdx + 1} / {app.sections.length}</div>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: -0.2, marginBottom: 2 }}>{sec.label}</div>
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>
          {fmt.timeShort(sec.start)} – {fmt.timeShort(sec.end)} · {Math.round(sec.end - sec.start)}s
        </div>
      </div>
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>DETECTED</div>
        {[
          ['kind',       sec.kind],
          ['confidence', '66.7%'],
          ['bars',       Math.round((sec.end - sec.start) / 2.02).toString()],
          ['beats',      Math.round((sec.end - sec.start) / 0.52).toString()],
        ].map(([k, v], i) => (
          <div key={i} style={{ display: 'flex', fontFamily: t.mono, fontSize: 11, marginBottom: 4 }}>
            <span style={{ flex: 1, color: t.ink3 }}>{k}</span>
            <span style={{ color: t.ink }}>{v}</span>
          </div>
        ))}
      </div>
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>CURRENT THEME</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <i style={{ width: 12, height: 12, background: selTheme.accent, display: 'block' }}/>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{selTheme.name}</div>
            <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>{selTheme.desc}</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 3, marginBottom: 10 }}>
          {selTheme.swatches.map((c, i) => (
            <i key={i} style={{ flex: 1, height: 22, background: c, border: `1px solid ${t.line2}` }}/>
          ))}
        </div>
        <LightsPreview height={30} cells={32} compact label={null}/>
      </div>
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>PARAMETERS</div>
        {[
          ['brightness',  0.78],
          ['hit strength', 0.92],
          ['dwell time',  0.45],
          ['color shift', 0.30],
        ].map(([k, v], i) => (
          <div key={i} style={{ marginBottom: 6 }}>
            <div style={{ display: 'flex', fontFamily: t.mono, fontSize: 10, color: t.ink3, marginBottom: 2 }}>
              <span style={{ flex: 1 }}>{k}</span>
              <span style={{ color: t.ink2 }}>{v.toFixed(2)}</span>
            </div>
            <div style={{ height: 3, background: t.bg3, position: 'relative' }}>
              <i style={{ display: 'block', height: '100%', width: `${v * 100}%`, background: selTheme.accent }}/>
            </div>
          </div>
        ))}
      </div>
      <div style={{ flex: 1 }}/>
      <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.line}`, display: 'flex', gap: 6 }}>
        <button onClick={() => app.seekTo(sec.start)} style={{
          flex: 1, background: 'transparent', color: t.ink2,
          border: `1px solid ${t.line2}`, padding: '7px 8px',
          fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
        }}>⇤ jump</button>
        <button onClick={() => { app.seekTo(sec.start); if (!app.playing) app.togglePlay(); }} style={{
          flex: 1, background: t.accent, color: t.accentInk,
          border: 'none', padding: '7px 8px',
          fontFamily: t.mono, fontSize: 11, fontWeight: 600, cursor: 'pointer',
        }}>▶ preview</button>
      </div>
    </div>
  );

  return (
    <Chrome inspector={inspector} statusExtra={<span>section {selIdx + 1} · {selTheme.name}</span>}>
      {/* Header band */}
      <div style={{
        padding: '14px 20px 12px', display: 'flex', alignItems: 'baseline',
        gap: 14, borderBottom: `1px solid ${t.line}`, flexShrink: 0,
      }}>
        <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.3 }}>{song.title}</div>
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>
          {song.artist} · {song.bpm} BPM · {song.key} · {fmt.timeShort(song.duration)}
        </div>
        <div style={{ flex: 1 }}/>
        <button onClick={() => { app.setScreen('timeline'); app.setSectionsMode(true); }} style={{
          padding: '6px 12px', background: 'transparent', color: t.ink2,
          border: `1px solid ${t.line2}`, fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
        }}>✎ edit sections</button>
        <button onClick={() => app.setScreen('timeline')} style={{
          padding: '6px 12px', background: 'transparent', color: t.ink2,
          border: `1px solid ${t.line2}`, fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
        }}>open in timeline →</button>
        <button onClick={() => app.setScreen('export')} style={{
          padding: '6px 12px', background: t.accent, color: t.accentInk,
          border: 'none', fontFamily: t.mono, fontSize: 11, fontWeight: 600, cursor: 'pointer',
        }}>export ⌘E</button>
      </div>

      {/* Section strip */}
      <SectionStrip/>

      {/* Theme grid */}
      <div style={{ padding: '16px 20px', flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'baseline', marginBottom: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 600, letterSpacing: -0.1 }}>
              Pick theme for <span style={{ color: selTheme.accent }}>{sec.label}</span>
            </div>
            <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3, marginLeft: 10 }}>
              · {THEMES.length} themes available
            </div>
            <div style={{ flex: 1 }}/>
            <button onClick={() => {
              // reset selected section to default
              const def = app.sections[selIdx].defaultTheme;
              app.setSectionTheme(selIdx, def);
            }} style={{
              background: 'transparent', color: t.ink3, border: `1px solid ${t.line2}`,
              padding: '4px 10px', fontFamily: t.mono, fontSize: 10, cursor: 'pointer',
            }}>reset to auto</button>
            <div style={{ width: 6 }}/>
            <button onClick={() => {
              // auto-assign all by default
              app.sections.forEach((s, i) => app.setSectionTheme(i, s.defaultTheme));
            }} style={{
              background: 'transparent', color: t.ink3, border: `1px solid ${t.line2}`,
              padding: '4px 10px', fontFamily: t.mono, fontSize: 10, cursor: 'pointer', marginLeft: 0,
            }}>auto-assign all</button>
          </div>

          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 10,
          }}>
            {THEMES.map(theme => {
              const active = theme.id === selThemeId;
              return (
                <button key={theme.id}
                  onClick={() => app.setSectionTheme(selIdx, theme.id)}
                  style={{
                    textAlign: 'left', padding: 0, cursor: 'pointer',
                    background: active ? t.bg3 : t.bg1,
                    border: `1px solid ${active ? theme.accent : t.line}`,
                    outline: active ? `1px solid ${theme.accent}` : 'none',
                    outlineOffset: -2,
                    fontFamily: t.sans, color: t.ink,
                    transition: 'background 120ms, border 120ms',
                  }}>
                  <div style={{ display: 'flex', height: 48 }}>
                    {theme.swatches.map((c, i) => (
                      <i key={i} style={{ flex: 1, background: c }}/>
                    ))}
                  </div>
                  <div style={{ padding: '8px 10px 10px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, flex: 1 }}>{theme.name}</div>
                      {active && <span style={{ fontFamily: t.mono, fontSize: 9, color: theme.accent, letterSpacing: 0.6 }}>● ASSIGNED</span>}
                    </div>
                    <div style={{ fontSize: 11, color: t.ink3, marginBottom: 6, minHeight: 28, lineHeight: 1.4 }}>{theme.desc}</div>
                    <MiniLights themeId={theme.id} kind={sec.kind} height={18}/>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Live preview */}
        <div style={{
          border: `1px solid ${t.line}`, background: t.bg1, padding: 12,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flex: 1 }}>
              LIVE LIGHTS · {selTheme.name.toUpperCase()} · on {sec.label}
            </span>
            <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>4 props · 512 px</span>
          </div>
          <LightsPreview height={80} cells={64} label="FRONT YARD"/>
          <div style={{ display: 'flex', gap: 10, marginTop: 10, fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
            <span>● mega tree (300px)</span>
            <span>● tree L (70px)</span>
            <span>● tree R (70px)</span>
            <span>● arch (72px)</span>
            <div style={{ flex: 1 }}/>
            <span>{app.playing ? `▶ ${fmt.time(app.time)}` : 'paused'}</span>
          </div>
        </div>

        {/* Full timeline strip */}
        <TimelineStrip/>
      </div>
    </Chrome>
  );
}

// A row of sections the user can click to select. Each shows its theme swatch + a micro-wave.
function SectionStrip() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  return (
    <div style={{
      background: t.bg1, borderBottom: `1px solid ${t.line}`, padding: '10px 14px',
      display: 'flex', gap: 6, overflowX: 'auto', flexShrink: 0,
    }}>
      {app.sections.map((s, i) => {
        const th = THEMES_BY_ID[app.sectionThemes[i]];
        const active = i === app.selectedSection;
        const playing = app.time >= s.start && app.time < s.end;
        const w = Math.max(90, (s.end - s.start) / song.duration * 1200);
        return (
          <button key={i}
            onClick={() => app.setSelectedSection(i)}
            onDoubleClick={() => { app.seekTo(s.start); if (!app.playing) app.togglePlay(); }}
            style={{
              width: w, padding: 0, cursor: 'pointer',
              background: active ? t.bg3 : t.bg0,
              border: `1px solid ${active ? th.accent : t.line}`,
              outline: active ? `1px solid ${th.accent}` : 'none',
              outlineOffset: -2,
              flexShrink: 0,
              fontFamily: t.sans, color: t.ink,
              textAlign: 'left',
              position: 'relative',
            }}>
            <div style={{ height: 6, background: `linear-gradient(90deg, ${th.accent}, ${th.swatches[th.swatches.length - 1]})` }}/>
            <div style={{ padding: '6px 8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 2 }}>
                <span style={{ fontFamily: t.mono, fontSize: 9, color: t.ink3 }}>{String(i + 1).padStart(2, '0')}</span>
                <span style={{ fontSize: 11, color: t.ink, fontWeight: 600, flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {KIND_GLYPH[s.kind]} {s.label}
                </span>
                {playing && <span style={{ fontFamily: t.mono, fontSize: 8, color: t.accent, letterSpacing: 0.5 }}>▶</span>}
              </div>
              <div style={{ fontFamily: t.mono, fontSize: 9, color: t.ink3, marginBottom: 4 }}>
                {fmt.timeShort(s.start)}–{fmt.timeShort(s.end)} · {th.name}
              </div>
              <MiniLights themeId={app.sectionThemes[i]} kind={s.kind} height={12}/>
            </div>
            {playing && (
              <div style={{
                position: 'absolute', bottom: -1, left: 0, right: 0, height: 2, background: t.accent,
              }}/>
            )}
          </button>
        );
      })}
    </div>
  );
}

// A thin timeline strip at the bottom of the theme picker.
// Shows section bars + playhead + transport.
function TimelineStrip() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const [hover, setHover] = React.useState(null);
  const wrapRef = React.useRef(null);

  const onScrub = (e) => {
    const r = wrapRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    app.seekTo(pct * song.duration);
  };
  const onMove = (e) => {
    const r = wrapRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
    setHover(pct * song.duration);
  };
  const pct = (app.time / song.duration) * 100;

  return (
    <div style={{ border: `1px solid ${t.line}`, background: t.bg1 }}>
      {/* transport */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 14px', gap: 10, borderBottom: `1px solid ${t.line}` }}>
        <button onClick={() => app.seekTo(0)} style={transportBtn(t)}>⏮</button>
        <button onClick={() => app.seekTo(app.time - 5)} style={transportBtn(t)}>◀</button>
        <button onClick={app.togglePlay} style={{
          ...transportBtn(t),
          background: app.playing ? t.accent : t.bg3,
          color: app.playing ? t.accentInk : t.ink,
          width: 40, fontWeight: 700,
        }}>{app.playing ? '❚❚' : '▶'}</button>
        <button onClick={() => app.seekTo(app.time + 5)} style={transportBtn(t)}>▶</button>
        <button onClick={() => app.seekTo(song.duration - 0.5)} style={transportBtn(t)}>⏭</button>
        <div style={{ fontFamily: t.mono, fontSize: 15, fontWeight: 600, color: t.ink, letterSpacing: 0.5, fontVariantNumeric: 'tabular-nums', marginLeft: 6 }}>
          {fmt.time(app.time)}
        </div>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>/ {fmt.time(song.duration)}</div>
        <div style={{ flex: 1 }}/>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
          bar {app.curBeat?.bar ?? 0} · beat {(app.curBeat?.beat ?? 0) + 1}
        </div>
      </div>

      {/* scrubber with section bands */}
      <div
        ref={wrapRef}
        onClick={onScrub}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        style={{
          height: 40, position: 'relative', cursor: 'pointer',
          background: '#000',
        }}>
        {/* section bands */}
        <div style={{ position: 'absolute', inset: 0, display: 'flex' }}>
          {app.sections.map((s, i) => {
            const th = THEMES_BY_ID[app.sectionThemes[i]];
            const w = (s.end - s.start) / song.duration * 100;
            return (
              <div key={i} style={{
                width: `${w}%`,
                background: `linear-gradient(180deg, ${th.accent}88, ${th.accent}22)`,
                borderRight: i < app.sections.length - 1 ? `1px solid rgba(0,0,0,0.5)` : 'none',
                display: 'flex', alignItems: 'center', padding: '0 6px',
                overflow: 'hidden',
              }}>
                <span style={{ fontFamily: t.mono, fontSize: 9, color: '#fff', letterSpacing: 0.5, whiteSpace: 'nowrap' }}>
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
        {/* hover line */}
        {hover != null && (
          <div style={{
            position: 'absolute', top: 0, bottom: 0,
            left: `${(hover / song.duration) * 100}%`, width: 1,
            background: 'rgba(255,255,255,0.4)',
          }}/>
        )}
        {/* playhead */}
        <div style={{
          position: 'absolute', top: 0, bottom: 0,
          left: `${pct}%`, width: 2, background: '#fff',
          boxShadow: '0 0 6px rgba(255,255,255,0.8)',
        }}/>
        <div style={{
          position: 'absolute', top: -6, left: `${pct}%`, transform: 'translateX(-50%)',
          width: 10, height: 10, background: '#fff', borderRadius: 2,
        }}/>
      </div>
      <div style={{ padding: '6px 14px', fontFamily: t.mono, fontSize: 10, color: t.ink3, display: 'flex' }}>
        <span style={{ flex: 1 }}>
          ↑↓ click to scrub · double-click a section above to jump+play · space to play/pause
        </span>
        <span>{hover != null ? `hover ${fmt.timeShort(hover)}` : ''}</span>
      </div>
    </div>
  );
}

function transportBtn(t) {
  return {
    width: 28, height: 28, background: t.bg3, color: t.ink2,
    border: `1px solid ${t.line2}`,
    fontFamily: t.mono, fontSize: 11,
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', padding: 0,
  };
}

Object.assign(window, { ThemePicker, SectionStrip, TimelineStrip });
