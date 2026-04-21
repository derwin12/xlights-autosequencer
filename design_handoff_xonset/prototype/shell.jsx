// Chrome: header, tool strip (nav), library rail, status bar, tweaks panel.
const { useApp, fmt } = window;

const SCREENS = [
  { id: 'library',  label: 'LIB',      title: 'library' },
  { id: 'drop',     label: 'DROP',     title: 'drop mp3' },
  { id: 'analyze',  label: 'ANALYZE',  title: 'analyzing' },
  { id: 'timeline', label: 'TIMELINE', title: 'review timeline' },
  { id: 'theme',    label: 'THEME',    title: 'theme picker' },
  { id: 'export',   label: 'EXPORT',   title: 'export' },
];

function Chrome({ children, inspector = null, statusExtra = null }) {
  const app = useApp();
  const t = app.theme;
  const show = app.inspectorOpen && inspector;
  return (
    <div style={{
      width: '100%', height: '100%',
      background: t.bg0, color: t.ink, fontFamily: t.sans, fontSize: 12,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
    }}>
      <Header/>
      <ToolStrip/>
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <LibraryRail/>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: t.bg0 }}>
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>{children}</div>
          <StatusBar extra={statusExtra}/>
        </div>
        {show && inspector}
      </div>
      {app.tweaksOpen && <TweaksPanel/>}
    </div>
  );
}

function Header() {
  const app = useApp();
  const t = app.theme;
  return (
    <div style={{
      height: 40, background: t.bg1, borderBottom: `1px solid ${t.line}`,
      display: 'flex', alignItems: 'center', padding: '0 14px', gap: 14, flexShrink: 0,
    }}>
      <div style={{ display: 'flex', gap: 6 }}>
        <i style={{ width: 11, height: 11, borderRadius: 6, background: '#ff5f57' }}/>
        <i style={{ width: 11, height: 11, borderRadius: 6, background: '#febc2e' }}/>
        <i style={{ width: 11, height: 11, borderRadius: 6, background: '#28c840' }}/>
      </div>
      <div style={{ fontFamily: t.mono, fontWeight: 600, letterSpacing: 1, fontSize: 11, color: t.ink2 }}>X—ONSET</div>
      <div style={{ width: 1, height: 16, background: t.line }}/>
      <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>project / Halloween 2026</div>
      <div style={{ flex: 1 }}/>
      <button onClick={() => app.setTweaksOpen(v => !v)} style={{
        background: app.tweaksOpen ? t.accent : 'transparent',
        color: app.tweaksOpen ? t.accentInk : t.ink2,
        border: `1px solid ${app.tweaksOpen ? t.accent : t.line2}`,
        padding: '4px 10px', fontFamily: t.mono, fontSize: 10,
        letterSpacing: 0.6, cursor: 'pointer',
      }}>◐ tweaks</button>
      <div style={{ display: 'flex', gap: 0, fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
        <span style={{ padding: '4px 10px', borderLeft: `1px solid ${t.line}` }}>CPU 12%</span>
        <span style={{ padding: '4px 10px', borderLeft: `1px solid ${t.line}` }}>xLights 2024.22</span>
        <span style={{ padding: '4px 10px', borderLeft: `1px solid ${t.line}`, color: t.ok }}>● connected</span>
      </div>
    </div>
  );
}

function ToolStrip() {
  const app = useApp();
  const t = app.theme;
  return (
    <div style={{
      height: 32, background: t.bg1, borderBottom: `1px solid ${t.line}`,
      display: 'flex', padding: '0 8px', gap: 2, flexShrink: 0,
      fontFamily: t.mono, fontSize: 11,
    }}>
      {SCREENS.map((s) => {
        const active = s.id === app.screen;
        return (
          <button
            key={s.id}
            onClick={() => app.setScreen(s.id)}
            style={{
              display: 'flex', alignItems: 'center', padding: '0 12px',
              background: 'transparent',
              color: active ? t.ink : t.ink3,
              border: 'none',
              borderBottom: active ? `2px solid ${t.accent}` : '2px solid transparent',
              letterSpacing: 0.6,
              cursor: 'pointer',
              fontFamily: t.mono, fontSize: 11,
            }}
          >{s.label}</button>
        );
      })}
      <div style={{ flex: 1 }}/>
      {['undo','redo','snap','grid: 1/4','zoom','fit'].map((x, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '0 10px', color: t.ink3, borderLeft: `1px solid ${t.line}` }}>{x}</div>
      ))}
      <button onClick={() => app.setInspectorOpen(v => !v)} style={{
        padding: '0 10px', borderLeft: `1px solid ${t.line}`, border: 'none',
        borderBottomColor: 'transparent', background: 'transparent',
        color: app.inspectorOpen ? t.ink : t.ink3, fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
      }}>▸ inspector</button>
    </div>
  );
}

function LibraryRail() {
  const app = useApp();
  const t = app.theme;
  const songs = [
    { n: 'Highway to Hell',     a: 'AC/DC',           dur: '3:28', st: 'themed',    active: true },
    { n: 'Thunderstruck',       a: 'AC/DC',           dur: '4:52', st: 'analyzed',  active: false },
    { n: 'Enter Sandman',       a: 'Metallica',       dur: '5:31', st: 'themed',    active: false },
    { n: 'Zombie',              a: 'The Cranberries', dur: '5:06', st: 'draft',     active: false },
    { n: 'Toxic',               a: 'Britney Spears',  dur: '3:20', st: 'themed',    active: false },
    { n: 'Thriller',            a: 'Michael Jackson', dur: '5:57', st: 'draft',     active: false },
  ];
  const stColor = { themed: t.ok, analyzed: t.warn, draft: t.ink3 };
  return (
    <div style={{
      width: 220, background: t.bg1, borderRight: `1px solid ${t.line}`,
      display: 'flex', flexDirection: 'column', flexShrink: 0,
    }}>
      <div style={{ padding: '10px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, borderBottom: `1px solid ${t.line}` }}>LIBRARY · 8</div>
      <div style={{ padding: '8px 10px 4px', fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>▾ HALLOWEEN 2026</div>
      {songs.map((s, i) => (
        <div key={i} style={{
          padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 8,
          background: s.active ? t.bg3 : 'transparent',
          borderLeft: s.active ? `2px solid ${t.accent}` : '2px solid transparent',
          cursor: 'pointer',
        }}>
          <div style={{ width: 22, height: 22, background: t.bg2, borderRadius: 2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: t.mono, fontSize: 9, color: t.ink3 }}>♪</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 12, color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.n}</div>
            <div style={{ fontSize: 10, color: t.ink3, fontFamily: t.mono }}>{s.a} · {s.dur}</div>
          </div>
          <div style={{ fontFamily: t.mono, fontSize: 9, color: stColor[s.st], letterSpacing: 0.5 }}>{s.st}</div>
        </div>
      ))}
      <div style={{ padding: '8px 10px 4px', fontFamily: t.mono, fontSize: 10, color: t.ink3, marginTop: 6 }}>▸ CHRISTMAS 2025</div>
      <div style={{ padding: '4px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>12 songs</div>
      <div style={{ flex: 1 }}/>
      <div style={{ padding: 10, borderTop: `1px solid ${t.line}` }}>
        <button onClick={() => app.setScreen('drop')} style={{
          border: `1px dashed ${t.line2}`, padding: '10px', width: '100%',
          textAlign: 'center', fontFamily: t.mono, fontSize: 10, color: t.ink3,
          background: 'transparent', cursor: 'pointer',
        }}>+ drop mp3</button>
      </div>
    </div>
  );
}

function StatusBar({ extra }) {
  const app = useApp();
  const t = app.theme;
  return (
    <div style={{
      height: 22, background: t.bg1, borderTop: `1px solid ${t.line}`,
      display: 'flex', alignItems: 'center', padding: '0 12px',
      fontFamily: t.mono, fontSize: 10, color: t.ink3, gap: 14, flexShrink: 0,
    }}>
      <span style={{ color: app.playing ? t.accent : t.ink3 }}>
        {app.playing ? '● playing' : '○ paused'} · {fmt.time(app.time)}
      </span>
      {extra}
      <div style={{ flex: 1 }}/>
      <span>{window.HIGHWAY.bpm} BPM</span>
      <span>4 / 4</span>
      <span>A major</span>
      <span>44.1 kHz · 16-bit</span>
      <span>v0.4.1</span>
    </div>
  );
}

// Tweaks panel (slides in from right bottom)
function TweaksPanel() {
  const app = useApp();
  const t = app.theme;
  return (
    <div style={{
      position: 'fixed', right: 16, bottom: 32, width: 280,
      background: t.bg1, border: `1px solid ${t.line2}`, zIndex: 50,
      fontFamily: t.sans, boxShadow: '0 12px 32px rgba(0,0,0,0.5)',
    }}>
      <div style={{
        padding: '8px 12px', borderBottom: `1px solid ${t.line}`,
        display: 'flex', alignItems: 'center',
        fontFamily: t.mono, fontSize: 10, letterSpacing: 1, color: t.ink3,
      }}>
        <span style={{ flex: 1 }}>TWEAKS</span>
        <button onClick={() => app.setTweaksOpen(false)} style={{ background: 'transparent', color: t.ink3, border: 'none', cursor: 'pointer', fontFamily: t.mono, fontSize: 14 }}>×</button>
      </div>
      <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 0.8, marginBottom: 6 }}>APPEARANCE</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {['dark','light'].map(m => (
              <button key={m} onClick={() => app.setMode(m)} style={{
                flex: 1, padding: '6px 10px',
                background: app.mode === m ? t.accent : t.bg2,
                color: app.mode === m ? t.accentInk : t.ink2,
                border: 'none', fontFamily: t.mono, fontSize: 11, cursor: 'pointer', textTransform: 'lowercase',
              }}>{m}</button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 0.8, marginBottom: 6 }}>DENSITY</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {['compact','comfortable'].map(d => (
              <button key={d} onClick={() => app.setDensity(d)} style={{
                flex: 1, padding: '6px 10px',
                background: app.density === d ? t.accent : t.bg2,
                color: app.density === d ? t.accentInk : t.ink2,
                border: 'none', fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
              }}>{d}</button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 0.8, marginBottom: 6 }}>INSPECTOR</div>
          <button onClick={() => app.setInspectorOpen(v => !v)} style={{
            width: '100%', padding: '6px 10px', background: t.bg2, color: t.ink2,
            border: 'none', fontFamily: t.mono, fontSize: 11, cursor: 'pointer', textAlign: 'left',
          }}>{app.inspectorOpen ? '● visible' : '○ hidden'}</button>
        </div>
        <div style={{ borderTop: `1px solid ${t.line}`, paddingTop: 10, fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
          <div style={{ marginBottom: 4 }}>keyboard</div>
          <div>space · play/pause</div>
          <div>← → · nudge 1s</div>
          <div>⇧← ⇧→ · jump section</div>
          <div>1-6 · switch screens</div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Chrome, Header, ToolStrip, LibraryRail, StatusBar, TweaksPanel, SCREENS });
