// The 4 other screens — Library, Drop, Analyze, Export.
// Lighter fidelity than the theme picker + timeline, but fully reachable via nav.
const { useApp, Chrome, THEMES_BY_ID, fmt, LightsPreview } = window;

// ============================================================================
// LIBRARY
// ============================================================================
function LibraryScreen() {
  const app = useApp();
  const t = app.theme;
  const rows = [
    { n: 'Highway to Hell',     a: 'AC/DC',           dur: '3:28', bpm: 115, key: 'A maj',  st: 'themed',   pct: 100, theme: 'punchy',  upd: '2h ago',   current: true },
    { n: 'Thunderstruck',       a: 'AC/DC',           dur: '4:52', bpm: 135, key: 'B min',  st: 'analyzed', pct: 55,  theme: '—',       upd: '3h ago' },
    { n: 'Enter Sandman',       a: 'Metallica',       dur: '5:31', bpm: 123, key: 'E min',  st: 'themed',   pct: 100, theme: 'storm',   upd: '1d ago' },
    { n: 'Zombie',              a: 'The Cranberries', dur: '5:06', bpm: 166, key: 'E min',  st: 'draft',    pct: 15,  theme: '—',       upd: '1d ago' },
    { n: 'Toxic',               a: 'Britney Spears',  dur: '3:20', bpm: 143, key: 'C min',  st: 'themed',   pct: 100, theme: 'bright',  upd: '2d ago' },
    { n: 'Spooky Scary Skel.',  a: 'Andrew Gold',     dur: '2:48', bpm: 180, key: 'A maj',  st: 'analyzed', pct: 60,  theme: '—',       upd: '2d ago' },
    { n: 'Thriller',            a: 'Michael Jackson', dur: '5:57', bpm: 118, key: 'F# min', st: 'draft',    pct: 0,   theme: '—',       upd: '3d ago' },
    { n: 'Bad Moon Rising',     a: 'CCR',             dur: '2:20', bpm: 180, key: 'D maj',  st: 'draft',    pct: 0,   theme: '—',       upd: '3d ago' },
  ];
  const stColor = { themed: t.ok, analyzed: t.warn, draft: t.ink3 };

  const inspector = (
    <div style={{ width: 300, background: t.bg1, borderLeft: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      <div style={{ padding: '10px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, borderBottom: `1px solid ${t.line}` }}>SHOW</div>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 2, letterSpacing: -0.2 }}>Halloween 2026</div>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>8 songs · 28:14 · 3 themed</div>
      </div>
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>PROGRESS</div>
        {[['themed', 3, t.ok], ['analyzed', 2, t.warn], ['draft', 3, t.ink3]].map(([k, n, c], i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5, fontFamily: t.mono, fontSize: 11 }}>
            <i style={{ width: 8, height: 8, background: c }}/>
            <span style={{ flex: 1, color: t.ink2 }}>{k}</span>
            <span style={{ color: t.ink }}>{n}</span>
          </div>
        ))}
        <div style={{ height: 5, background: t.bg3, marginTop: 10, display: 'flex' }}>
          <i style={{ width: '38%', background: t.ok }}/>
          <i style={{ width: '25%', background: t.warn }}/>
        </div>
      </div>
      <div style={{ padding: '10px 14px' }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>XLIGHTS TARGET</div>
        <div style={{ fontSize: 12, color: t.ink, marginBottom: 2 }}>~/xLights/Shows/Halloween 2026</div>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>last sync 12m ago</div>
      </div>
      <div style={{ flex: 1 }}/>
      <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.line}` }}>
        <button style={{ width: '100%', background: t.accent, color: t.accentInk, border: 'none', padding: '8px 10px', fontFamily: t.mono, fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>▶ batch render show</button>
      </div>
    </div>
  );

  return (
    <Chrome inspector={inspector} statusExtra={<span>8 songs · 3 themed · 2 analyzed · 3 draft</span>}>
      <div style={{ height: 38, background: t.bg1, borderBottom: `1px solid ${t.line}`, display: 'flex', alignItems: 'center', padding: '0 14px', gap: 10, flexShrink: 0 }}>
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink }}>halloween 2026</div>
        <div style={{ color: t.ink3 }}>·</div>
        <div style={{ fontSize: 12, color: t.ink2 }}>8 songs</div>
        <div style={{ flex: 1 }}/>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: t.bg2, padding: '4px 10px' }}>
          <span style={{ color: t.ink3, fontFamily: t.mono, fontSize: 11 }}>⌕</span>
          <span style={{ color: t.ink3, fontSize: 12 }}>filter songs…</span>
        </div>
        <button onClick={() => app.setScreen('drop')} style={{ background: t.accent, color: t.accentInk, border: 'none', padding: '6px 12px', fontFamily: t.mono, fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>+ add song</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '28px 2.4fr 70px 60px 80px 90px 1.2fr 120px 90px', padding: '6px 14px', background: t.bg1, borderBottom: `1px solid ${t.line}`, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flexShrink: 0 }}>
        <span></span>
        <span>SONG ↓</span><span>DUR</span><span>BPM</span><span>KEY</span><span>STATUS</span><span>PROGRESS</span><span>THEME</span>
        <span style={{ textAlign: 'right' }}>UPDATED</span>
      </div>

      <div style={{ flex: 1, overflow: 'auto' }}>
        {rows.map((r, i) => (
          <div key={i}
            onClick={() => r.current && app.setScreen('theme')}
            style={{
              display: 'grid',
              gridTemplateColumns: '28px 2.4fr 70px 60px 80px 90px 1.2fr 120px 90px',
              alignItems: 'center', padding: '8px 14px',
              borderBottom: `1px solid ${t.line}`, fontSize: 12,
              background: r.current ? t.bg3 : i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.015)',
              borderLeft: r.current ? `2px solid ${t.accent}` : '2px solid transparent',
              cursor: r.current ? 'pointer' : 'default',
            }}>
            <div style={{ width: 20, height: 20, background: t.bg2, display: 'flex', alignItems: 'center', justifyContent: 'center', color: t.ink3, fontFamily: t.mono, fontSize: 10 }}>{String(i + 1).padStart(2, '0')}</div>
            <div style={{ minWidth: 0 }}>
              <div style={{ color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.n}</div>
              <div style={{ fontSize: 10, fontFamily: t.mono, color: t.ink3 }}>{r.a}</div>
            </div>
            <span style={{ fontFamily: t.mono, color: t.ink2, fontVariantNumeric: 'tabular-nums' }}>{r.dur}</span>
            <span style={{ fontFamily: t.mono, color: t.ink2, fontVariantNumeric: 'tabular-nums' }}>{r.bpm}</span>
            <span style={{ fontFamily: t.mono, color: t.ink2 }}>{r.key}</span>
            <span style={{ fontFamily: t.mono, fontSize: 10, color: stColor[r.st], letterSpacing: 0.6 }}>● {r.st}</span>
            <div style={{ height: 4, background: t.bg3, position: 'relative', marginRight: 20 }}>
              <i style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${r.pct}%`, background: stColor[r.st] }}/>
            </div>
            <span style={{ fontFamily: t.mono, fontSize: 11, color: r.theme === '—' ? t.ink3 : t.ink }}>{r.theme}</span>
            <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, textAlign: 'right' }}>{r.upd}</span>
          </div>
        ))}
      </div>
    </Chrome>
  );
}

// ============================================================================
// DROP MP3
// ============================================================================
function DropScreen() {
  const app = useApp();
  const t = app.theme;
  const [dragOver, setDragOver] = React.useState(false);

  const doDrop = () => {
    app.setScreen('analyze');
  };

  return (
    <Chrome statusExtra={<span>drag a file, or click to browse</span>}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}>
        <div style={{ width: 600, textAlign: 'center' }}>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); doDrop(); }}
            onClick={doDrop}
            style={{
              border: `2px dashed ${dragOver ? t.accent : t.line2}`,
              padding: '80px 30px 70px',
              background: dragOver ? `${t.accent}11` : `linear-gradient(180deg, ${t.bg1} 0%, ${t.bg0} 100%)`,
              cursor: 'pointer',
              transition: 'border 120ms, background 120ms',
            }}>
            <div style={{ fontSize: 52, color: dragOver ? t.accent : t.ink3, marginBottom: 18, fontFamily: t.mono, transition: 'color 120ms' }}>↓</div>
            <div style={{ fontSize: 24, fontWeight: 600, color: t.ink, marginBottom: 10, letterSpacing: -0.3 }}>Drop an MP3</div>
            <div style={{ fontSize: 13, color: t.ink2, marginBottom: 24 }}>
              or <span style={{ color: t.accent, textDecoration: 'underline' }}>browse your files</span>
            </div>
            <div style={{ display: 'inline-flex', gap: 16, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 0.5 }}>
              <span>.mp3</span><span>·</span><span>.wav</span><span>·</span><span>.m4a</span><span>·</span><span>.flac</span>
            </div>
          </div>
          <div style={{ marginTop: 16, fontSize: 12, color: t.ink3 }}>
            <span style={{ fontFamily: t.mono }}>⌘V</span> paste path ·{' '}
            <span style={{ fontFamily: t.mono }}>⌘⇧O</span> browse ·{' '}
            <span style={{ fontFamily: t.mono }}>⌘D</span> demo song
          </div>

          <div style={{ marginTop: 36, textAlign: 'left', background: t.bg1, border: `1px solid ${t.line}`, padding: '14px 18px' }}>
            <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>RECENTS</div>
            {[
              ['Highway to Hell — AC_DC.mp3', '/Downloads · 8.4 MB · 3 days ago'],
              ['thunderstruck_remaster.wav',   '/Music · 54 MB · 1 week ago'],
              ['stairway_demo.mp3',            '/Downloads · 12 MB · 2 weeks ago'],
            ].map(([n, meta], i) => (
              <div key={i} onClick={doDrop} style={{ padding: '6px 0', display: 'flex', alignItems: 'center', gap: 10, borderBottom: i < 2 ? `1px solid ${t.line}` : 'none', cursor: 'pointer' }}>
                <div style={{ width: 22, height: 22, background: t.bg2, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>♪</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{n}</div>
                  <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>{meta}</div>
                </div>
                <span style={{ fontFamily: t.mono, fontSize: 10, color: t.accent }}>open →</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Chrome>
  );
}

// ============================================================================
// ANALYZING
// ============================================================================
function AnalyzeScreen() {
  const app = useApp();
  const t = app.theme;
  const [progress, setProgress] = React.useState(0);
  const [done, setDone] = React.useState(false);

  React.useEffect(() => {
    setProgress(0); setDone(false);
    let p = 0;
    const id = setInterval(() => {
      p += 2 + Math.random() * 3;
      if (p >= 100) {
        setProgress(100);
        setDone(true);
        clearInterval(id);
        // auto-advance after brief pause
        setTimeout(() => app.setScreen('theme'), 1400);
      } else {
        setProgress(p);
      }
    }, 120);
    return () => clearInterval(id);
  }, []);

  const tasks = [
    ['decode audio',                 28],
    ['beat tracking · madmom',       80],
    ['bar detection · qm_bars',      72],
    ['onsets · librosa HFC',         62],
    ['onsets · aubio complex',       55],
    ['kick drum · demucs stem',      42],
    ['chord progression · chordino', 32],
    ['vocals · phoneme align',       20],
    ['bass onset · Essentia',        14],
    ['song structure · MSA',          8],
    ['key + tempo · Essentia',        4],
    ['spectral flux',                 0],
  ];

  const doneCount = tasks.filter(([, p]) => progress >= p).length;

  return (
    <Chrome statusExtra={<span>{done ? `done · opening theme picker…` : `analyzing · ${doneCount}/${tasks.length} complete · ${Math.floor(100 - progress)}% remaining`}</span>}>
      <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16, overflow: 'hidden', flex: 1 }}>
        <div style={{ background: t.bg1, border: `1px solid ${t.line}`, padding: 20 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14 }}>
            <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: -0.2 }}>
              {done ? 'Analysis complete' : 'Analyzing Highway to Hell'}
            </div>
            <div style={{ flex: 1 }}/>
            <div style={{ fontFamily: t.mono, fontSize: 13, color: t.ink }}>{doneCount} <span style={{ color: t.ink3 }}>/ {tasks.length}</span></div>
            <div style={{ fontFamily: t.mono, fontSize: 13, color: t.ink2 }}>· {Math.floor(progress)}%</div>
          </div>
          <div style={{ height: 6, background: t.bg3 }}>
            <i style={{ display: 'block', height: '100%', width: `${progress}%`, background: done ? t.ok : t.accent, transition: 'width 120ms linear' }}/>
          </div>
          <div style={{ height: 70, marginTop: 16, position: 'relative', background: '#000', border: `1px solid ${t.line}` }}>
            <svg width="100%" height="100%" preserveAspectRatio="none" viewBox="0 0 520 70">
              {window.WAVE.map((v, i) => {
                const h = v * 58;
                const scanned = i / 520 * 100 < progress;
                return <rect key={i} x={i} y={35 - h / 2} width={0.9} height={h}
                             fill={scanned ? t.accent : t.ink3}
                             opacity={scanned ? 0.9 : 0.3}/>;
              })}
              <line x1={progress / 100 * 520} x2={progress / 100 * 520} y1={0} y2={70} stroke="#fff" strokeWidth={1.5}/>
            </svg>
            <div style={{ position: 'absolute', bottom: 4, left: 8, fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
              {fmt.timeShort(progress / 100 * 208)} / 3:28 · scanning
            </div>
          </div>
        </div>

        <div style={{ flex: 1, background: t.bg1, border: `1px solid ${t.line}`, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '8px 16px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, borderBottom: `1px solid ${t.line}`, display: 'grid', gridTemplateColumns: '20px 1fr 80px 90px' }}>
            <span></span><span>TASK</span><span>STATUS</span><span style={{ textAlign: 'right' }}>TIME</span>
          </div>
          <div style={{ flex: 1, overflow: 'auto' }}>
            {tasks.map((tk, i) => {
              const reached = progress >= tk[1];
              const running = !reached && progress >= tk[1] - 15;
              const status = reached ? 'done' : running ? 'running' : 'queued';
              const col = status === 'done' ? t.ok : status === 'running' ? t.accent : t.ink3;
              const glyph = status === 'done' ? '✓' : status === 'running' ? '●' : '○';
              return (
                <div key={i} style={{
                  padding: '7px 16px', display: 'grid',
                  gridTemplateColumns: '20px 1fr 80px 90px',
                  alignItems: 'center', fontFamily: t.mono, fontSize: 11,
                  borderBottom: i < tasks.length - 1 ? `1px solid ${t.line}` : 'none',
                }}>
                  <span style={{ color: col }}>{glyph}</span>
                  <span style={{ color: status === 'queued' ? t.ink3 : t.ink }}>{tk[0]}</span>
                  <span style={{ color: col, letterSpacing: 0.5 }}>{status}</span>
                  <span style={{ color: t.ink2, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {reached ? `${(1 + Math.random() * 10).toFixed(1)}s` : running ? `${Math.round((progress - tk[1] + 15) / 15 * 100)}%` : '—'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </Chrome>
  );
}

// ============================================================================
// EXPORT
// ============================================================================
function ExportScreen() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const [exporting, setExporting] = React.useState(false);
  const [exportDone, setExportDone] = React.useState(false);
  const [progress, setProgress] = React.useState(0);

  const doExport = () => {
    setExporting(true);
    setExportDone(false);
    setProgress(0);
    let p = 0;
    const id = setInterval(() => {
      p += 4 + Math.random() * 6;
      if (p >= 100) { p = 100; clearInterval(id); setExportDone(true); setExporting(false); }
      setProgress(p);
    }, 80);
  };

  const inspector = (
    <div style={{ width: 300, background: t.bg1, borderLeft: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      <div style={{ padding: '10px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, borderBottom: `1px solid ${t.line}` }}>EXPORT SUMMARY</div>
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: t.ink, letterSpacing: -0.2 }}>{song.title}</div>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>{fmt.timeShort(song.duration)} · {app.sections.length} sections · {song.beats.length} beats · 4 props</div>
      </div>
      <div style={{ padding: '12px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 10 }}>WILL PRODUCE</div>
        {[
          ['effects',       '142'],
          ['color curves',  String(app.sections.length)],
          ['audio track',   '1'],
          ['model refs',    '4'],
          ['timing marks',  String(song.beats.length)],
        ].map(([k, v], i) => (
          <div key={i} style={{ display: 'flex', fontFamily: t.mono, fontSize: 11, marginBottom: 5 }}>
            <span style={{ flex: 1, color: t.ink2 }}>{k}</span>
            <span style={{ color: t.ink, fontVariantNumeric: 'tabular-nums' }}>{v}</span>
          </div>
        ))}
      </div>
      <div style={{ padding: '10px 14px' }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>OUTPUT</div>
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink, lineHeight: 1.5 }}>
          Highway to Hell.xsq<br/>
          <span style={{ color: t.ink3 }}>+ Highway to Hell.mp3</span><br/>
          <span style={{ color: t.ink3 }}>+ theme-metadata.json</span>
        </div>
      </div>
      <div style={{ flex: 1 }}/>
      <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button onClick={doExport} disabled={exporting}
          style={{
            background: exportDone ? t.ok : t.accent, color: '#000',
            border: 'none', padding: '10px 12px',
            fontFamily: t.mono, fontSize: 12, fontWeight: 700, letterSpacing: 0.5,
            cursor: exporting ? 'wait' : 'pointer',
            opacity: exporting ? 0.7 : 1,
          }}>
          {exportDone ? '✓ EXPORTED · ⌘R to repeat' : exporting ? `EXPORTING… ${Math.floor(progress)}%` : '▶ EXPORT TO XLIGHTS · ⌘E'}
        </button>
        <button style={{ background: 'transparent', color: t.ink2, border: `1px solid ${t.line2}`, padding: '7px 12px', fontFamily: t.mono, fontSize: 11, cursor: 'pointer' }}>
          export dry-run…
        </button>
      </div>
    </div>
  );

  return (
    <Chrome inspector={inspector} statusExtra={exportDone ? <span style={{ color: t.ok }}>● exported to ~/xLights/Shows/Halloween 2026</span> : <span style={{ color: t.ok }}>ready to export · all checks passed</span>}>
      <div style={{ padding: '18px 24px 10px', display: 'flex', alignItems: 'baseline', gap: 16, borderBottom: `1px solid ${t.line}`, flexShrink: 0 }}>
        <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.3 }}>Export to xLights</div>
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>{song.title} · v0.4.1</div>
      </div>

      <div style={{ padding: '14px 0 0', flexShrink: 0 }}>
        <div style={{ padding: '0 14px 8px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1 }}>PREVIEW · full song</div>
        <div style={{ height: 38, background: '#000', border: `1px solid ${t.line}`, display: 'flex', margin: '0 14px 14px' }}>
          {app.sections.map((s, i) => {
            const w = (s.end - s.start) / song.duration * 100;
            const th = THEMES_BY_ID[app.sectionThemes[i]];
            return (
              <div key={i} style={{
                width: `${w}%`,
                background: `linear-gradient(90deg, ${th.accent}aa, ${th.accent}55)`,
                borderRight: i < app.sections.length - 1 ? '1px solid rgba(0,0,0,0.5)' : 'none',
                padding: '4px 6px',
                fontFamily: t.mono, fontSize: 9, color: '#fff',
                display: 'flex', alignItems: 'flex-end',
                letterSpacing: 0.3,
              }}>
                {s.label}
              </div>
            );
          })}
        </div>
      </div>

      {exporting && (
        <div style={{ padding: '0 24px 14px', flexShrink: 0 }}>
          <div style={{ height: 4, background: t.bg3 }}>
            <i style={{ display: 'block', height: '100%', width: `${progress}%`, background: t.accent, transition: 'width 80ms linear' }}/>
          </div>
        </div>
      )}

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', minHeight: 0, borderTop: `1px solid ${t.line}`, overflow: 'hidden' }}>
        <div style={{ borderRight: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
          <div style={{ padding: '10px 14px', background: t.bg1, borderBottom: `1px solid ${t.line}`, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flexShrink: 0 }}>
            PRE-FLIGHT · 7/7 passed
          </div>
          {[
            ['ok',   'All sections have a theme',   `${app.sections.length} / ${app.sections.length} sections · 0 drafts`],
            ['ok',   'Audio file present',          `Highway to Hell.mp3 · 8.4 MB · embedded`],
            ['ok',   'xLights install detected',    `v2024.22 · /Applications/xLights.app`],
            ['ok',   'Layout file valid',           `4 props · 512 px`],
            ['ok',   'No clashing timing marks',    `${song.beats.length} beats · all within tolerance`],
            ['warn', 'Solo section is quieter',     `'bright' theme pulls avg lumens down 22%`],
            ['ok',   'Destination writable',        `48 GB free`],
          ].map(([s, label, detail], i) => {
            const col = s === 'ok' ? t.ok : s === 'warn' ? t.warn : t.err;
            const gl = s === 'ok' ? '✓' : s === 'warn' ? '!' : '✕';
            return (
              <div key={i} style={{ display: 'flex', gap: 10, padding: '8px 14px', borderBottom: `1px solid ${t.line}` }}>
                <span style={{ color: col, fontFamily: t.mono, fontSize: 13, fontWeight: 700, width: 14, textAlign: 'center' }}>{gl}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: t.ink }}>{label}</div>
                  <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, marginTop: 2 }}>{detail}</div>
                </div>
              </div>
            );
          })}
          <div style={{ padding: '14px', borderTop: `1px solid ${t.line}` }}>
            <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 10 }}>DESTINATION</div>
            <div style={{ background: t.bg1, border: `1px solid ${t.line2}`, padding: '10px 12px' }}>
              <div style={{ fontFamily: t.mono, fontSize: 12, color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>~/xLights/Shows/Halloween 2026/</div>
              <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>48 GB free · xLights default</div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={{ padding: '10px 14px', background: t.bg1, borderBottom: `1px solid ${t.line}`, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flexShrink: 0 }}>
            CHANNEL MAP · 4 props · 512 px
          </div>
          {[
            ['Mega Tree',   '1–300',   '300', 'color wash + strobe'],
            ['Tree Left',   '301–370', '70',  'chase + pulse'],
            ['Tree Right',  '371–440', '70',  'chase + pulse'],
            ['Arch',        '441–512', '72',  'sweep'],
          ].map(([n, ch, px, eff], i) => (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '30px 1.6fr 80px 70px 1.2fr 70px', padding: '8px 14px', alignItems: 'center', borderBottom: `1px solid ${t.line}`, fontSize: 12 }}>
              <i style={{ width: 14, height: 14, background: t.bg3, border: `1px solid ${t.line2}` }}/>
              <div>
                <div style={{ color: t.ink }}>{n}</div>
                <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>/halloween2026/{n.toLowerCase().replace(/\s/g, '_')}.xmodel</div>
              </div>
              <span style={{ fontFamily: t.mono, color: t.ink2, fontVariantNumeric: 'tabular-nums' }}>{ch}</span>
              <span style={{ fontFamily: t.mono, color: t.ink2, fontVariantNumeric: 'tabular-nums' }}>{px}</span>
              <span style={{ fontFamily: t.mono, fontSize: 11, color: t.ink2 }}>{eff}</span>
              <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ok }}>● mapped</span>
            </div>
          ))}
          <div style={{ padding: 14, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>
              LIVE OUT · what xLights will play
            </div>
            <LightsPreview height={120} cells={80} label="4 PROPS · 512 PX"/>
          </div>
        </div>
      </div>
    </Chrome>
  );
}

Object.assign(window, { LibraryScreen, DropScreen, AnalyzeScreen, ExportScreen });
