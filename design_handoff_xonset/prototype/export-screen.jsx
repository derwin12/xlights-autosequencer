// Export screen — dry-run first, commit second. Staged pipeline, per-section render,
// files-as-they-write, streaming log. Distinct phases: idle → running → done.
const { useApp, Chrome, THEMES_BY_ID, fmt, LightsPreview } = window;

const PHASES = [
  { id: 'timing',   label: 'write timing marks',    unit: 'beats',    detail: 'librosa onsets → xLights timing track' },
  { id: 'sections', label: 'render section effects', unit: 'sections', detail: 'per-section theme → effect envelopes' },
  { id: 'audio',    label: 'pack audio',             unit: 'MB',       detail: 'copy + embed highway.mp3' },
  { id: 'xsq',      label: 'write .xsq',             unit: 'bytes',    detail: 'serialize xml · 4 props · 512 px' },
  { id: 'validate', label: 'validate output',        unit: 'checks',   detail: 'open in xLights headless · roundtrip' },
];

function ExportScreenV2() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;

  // mode: 'idle' | 'running' | 'done' | 'error'
  const [state, setState] = React.useState('idle');
  const [mode, setMode] = React.useState('dry'); // 'dry' | 'commit'
  const [phase, setPhase] = React.useState(0);
  const [phaseP, setPhaseP] = React.useState(0); // 0..1 for current phase
  const [sectionIdx, setSectionIdx] = React.useState(-1);
  const [log, setLog] = React.useState([]);
  const [writtenFiles, setWrittenFiles] = React.useState(new Set());
  const tickRef = React.useRef(null);

  const overallP = ((phase + phaseP) / PHASES.length) * 100;

  const addLog = (line, kind = 'info') => {
    setLog(l => [...l, { line, kind, t: Date.now() }].slice(-80));
  };

  const reset = () => {
    setState('idle'); setPhase(0); setPhaseP(0); setSectionIdx(-1);
    setLog([]); setWrittenFiles(new Set());
    if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
  };

  const start = (runMode) => {
    reset();
    setMode(runMode);
    setState('running');
    addLog(`$ xo-export ${runMode === 'dry' ? '--dry-run' : '--commit'} "${song.title}"`, 'cmd');
    addLog(`› target: ~/xLights/Shows/Halloween 2026/`, 'info');
    addLog(`› ${runMode === 'dry' ? 'DRY-RUN · no files will be written' : 'COMMIT · files will be written to disk'}`,
      runMode === 'dry' ? 'warn' : 'ok');

    let ph = 0;
    let localP = 0;
    let secI = -1;

    const step = () => {
      const curPhase = PHASES[ph];
      // speed varies per phase
      const inc = curPhase.id === 'sections' ? 0.04 : curPhase.id === 'audio' ? 0.06 : 0.12;
      localP += inc + Math.random() * inc * 0.6;

      if (curPhase.id === 'sections') {
        const newSec = Math.min(app.sections.length - 1, Math.floor(localP * app.sections.length));
        if (newSec !== secI) {
          secI = newSec;
          setSectionIdx(secI);
          const s = app.sections[secI];
          const th = THEMES_BY_ID[app.sectionThemes[secI]];
          addLog(`› render ${s.label.padEnd(12)} · ${th.name.padEnd(14)} · ${Math.round((s.end - s.start))}s`, 'section', th.accent);
        }
      }

      if (localP >= 1) {
        // phase done
        const done = PHASES[ph];
        addLog(`✓ ${done.label} complete`, 'ok');
        if (done.id === 'xsq') {
          if (runMode === 'commit') {
            setWrittenFiles(prev => new Set([...prev, 'xsq', 'mp3', 'json']));
            addLog(`  wrote Highway to Hell.xsq · 284 KB`, 'file');
            addLog(`  wrote Highway to Hell.mp3 · 8.4 MB`, 'file');
            addLog(`  wrote theme-metadata.json · 12 KB`, 'file');
          } else {
            addLog(`  would write 3 files · 8.7 MB total`, 'file');
          }
        }
        ph++;
        localP = 0;
        if (ph >= PHASES.length) {
          clearInterval(tickRef.current); tickRef.current = null;
          setPhase(PHASES.length - 1);
          setPhaseP(1);
          addLog(`✓ done in 2.8s · ${runMode === 'dry' ? '0 files written (dry-run)' : '3 files written'}`, 'ok');
          setState('done');
          return;
        }
        setPhase(ph);
        setPhaseP(0);
        return;
      }
      setPhase(ph);
      setPhaseP(localP);
    };
    tickRef.current = setInterval(step, 80);
  };

  React.useEffect(() => () => { if (tickRef.current) clearInterval(tickRef.current); }, []);

  // ---------------- UI ----------------
  const inspector = (
    <ExportInspector
      state={state} mode={mode}
      overallP={overallP}
      phase={phase} phaseP={phaseP}
      sectionIdx={sectionIdx}
      writtenFiles={writtenFiles}
      start={start} reset={reset}
    />
  );

  const statusExtra = state === 'done'
    ? <span style={{ color: t.ok }}>
        ● {mode === 'commit' ? 'committed' : 'dry-run passed'} · ~/xLights/Shows/Halloween 2026
      </span>
    : state === 'running'
    ? <span style={{ color: t.accent }}>● {mode === 'dry' ? 'dry-running' : 'committing'} · phase {phase + 1}/{PHASES.length}</span>
    : <span style={{ color: t.ok }}>ready · 7 / 7 checks passed</span>;

  return (
    <Chrome inspector={inspector} statusExtra={statusExtra}>
      <ExportHeader state={state} mode={mode} start={start} reset={reset}/>
      <SongBanner state={state} sectionIdx={sectionIdx}/>

      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', minHeight: 0, borderTop: `1px solid ${t.line}`, overflow: 'hidden' }}>
        <PipelineColumn state={state} phase={phase} phaseP={phaseP} sectionIdx={sectionIdx} log={log} mode={mode}/>
        <OutputColumn state={state} mode={mode} writtenFiles={writtenFiles} phase={phase} phaseP={phaseP}/>
      </div>
    </Chrome>
  );
}

// ---------------- Header ----------------
function ExportHeader({ state, mode, start, reset }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  return (
    <div style={{
      padding: '14px 20px 12px', display: 'flex', alignItems: 'baseline',
      gap: 14, borderBottom: `1px solid ${t.line}`, flexShrink: 0,
    }}>
      <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.3 }}>Export to xLights</div>
      <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>{song.title} · v0.4.1</div>
      <div style={{ flex: 1 }}/>

      {state === 'idle' && (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            fontFamily: t.mono, fontSize: 11, color: t.ink3,
          }}>
            <span>7 / 7 pre-flight passed</span>
          </div>
          <button onClick={() => start('dry')} style={{
            padding: '7px 14px', background: 'transparent', color: t.ink,
            border: `1px solid ${t.line2}`, fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
            fontWeight: 600,
          }}>▸ dry-run</button>
          <button onClick={() => start('commit')} style={{
            padding: '7px 14px', background: t.accent, color: t.accentInk,
            border: 'none', fontFamily: t.mono, fontSize: 11, fontWeight: 700,
            cursor: 'pointer', letterSpacing: 0.3,
          }}>▶ commit · ⌘E</button>
        </>
      )}
      {state === 'running' && (
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.accent }}>
          {mode === 'dry' ? 'DRY-RUN' : 'COMMIT'} IN PROGRESS…
        </div>
      )}
      {state === 'done' && (
        <>
          <span style={{ fontFamily: t.mono, fontSize: 11, color: t.ok, letterSpacing: 0.4 }}>
            ✓ {mode === 'dry' ? 'DRY-RUN PASSED' : 'COMMITTED'}
          </span>
          {mode === 'dry' && (
            <button onClick={() => start('commit')} style={{
              padding: '7px 14px', background: t.accent, color: t.accentInk,
              border: 'none', fontFamily: t.mono, fontSize: 11, fontWeight: 700,
              cursor: 'pointer', letterSpacing: 0.3,
            }}>▶ commit for real · ⌘E</button>
          )}
          <button onClick={reset} style={{
            padding: '7px 14px', background: 'transparent', color: t.ink2,
            border: `1px solid ${t.line2}`, fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
          }}>↺ run again</button>
        </>
      )}
    </div>
  );
}

// ---------------- Song banner / section strip ----------------
function SongBanner({ state, sectionIdx }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  return (
    <div style={{ padding: '14px 0 0', flexShrink: 0 }}>
      <div style={{ padding: '0 14px 8px', display: 'flex', alignItems: 'center' }}>
        <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flex: 1 }}>
          TIMELINE · {app.sections.length} sections · {song.beats.length} beats · 142 effects
        </span>
        {state === 'running' && sectionIdx >= 0 && (
          <span style={{ fontFamily: t.mono, fontSize: 10, color: t.accent, letterSpacing: 0.5 }}>
            ▶ rendering {app.sections[sectionIdx].label}
          </span>
        )}
      </div>
      <div style={{ height: 44, background: '#000', border: `1px solid ${t.line}`, display: 'flex', margin: '0 14px 14px', position: 'relative' }}>
        {app.sections.map((s, i) => {
          const w = (s.end - s.start) / song.duration * 100;
          const th = THEMES_BY_ID[app.sectionThemes[i]];
          const active = state === 'running' && i === sectionIdx;
          const done = state === 'running' && i < sectionIdx;
          const fullyDone = state === 'done';
          return (
            <div key={i} style={{
              width: `${w}%`,
              background: `linear-gradient(90deg, ${th.accent}${active || fullyDone ? 'cc' : done ? '88' : '33'}, ${th.accent}${active || fullyDone ? '66' : done ? '44' : '14'})`,
              borderRight: i < app.sections.length - 1 ? '1px solid rgba(0,0,0,0.6)' : 'none',
              padding: '4px 6px',
              fontFamily: t.mono, fontSize: 9, color: '#fff',
              display: 'flex', alignItems: 'flex-end',
              letterSpacing: 0.3,
              position: 'relative',
              outline: active ? `1.5px solid ${t.accent}` : 'none',
              outlineOffset: -1,
            }}>
              {s.label}
              {done && <span style={{ position: 'absolute', top: 3, right: 5, color: t.ok, fontSize: 10 }}>✓</span>}
              {active && <span style={{ position: 'absolute', top: 3, right: 5, color: '#fff', fontSize: 10 }}>●</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------- Left column: pipeline + log ----------------
function PipelineColumn({ state, phase, phaseP, sectionIdx, log, mode }) {
  const app = useApp();
  const t = app.theme;
  const logRef = React.useRef(null);
  React.useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [log]);

  return (
    <div style={{ borderRight: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', background: t.bg1, borderBottom: `1px solid ${t.line}`, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flexShrink: 0 }}>
        PIPELINE · {state === 'idle' ? `${PHASES.length} phases` : state === 'done' ? `${PHASES.length}/${PHASES.length} complete` : `${phase + 1}/${PHASES.length}`}
      </div>

      {/* Phase list */}
      <div style={{ padding: '4px 0', flexShrink: 0 }}>
        {PHASES.map((p, i) => {
          const isDone = state === 'done' || i < phase;
          const isActive = state === 'running' && i === phase;
          const isPending = !isDone && !isActive;
          const innerP = isActive ? phaseP : isDone ? 1 : 0;
          const unitLabel = p.id === 'sections' && isActive
            ? `${Math.min(sectionIdx + 1, app.sections.length)} / ${app.sections.length} ${p.unit}`
            : isActive
            ? `${Math.round(innerP * 100)}%`
            : isDone
            ? `done` : 'pending';
          return (
            <div key={p.id} style={{
              padding: '8px 14px', borderBottom: `1px solid ${t.line}`,
              background: isActive ? t.bg3 : 'transparent',
              opacity: isPending ? 0.5 : 1,
              borderLeft: isActive ? `2px solid ${t.accent}` : '2px solid transparent',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                <span style={{
                  fontFamily: t.mono, fontSize: 11, fontWeight: 700,
                  width: 18, textAlign: 'center',
                  color: isDone ? t.ok : isActive ? t.accent : t.ink3,
                }}>
                  {isDone ? '✓' : isActive ? '●' : String(i + 1).padStart(2, '0')}
                </span>
                <span style={{ fontSize: 12, color: t.ink, flex: 1, fontWeight: isActive ? 600 : 400 }}>{p.label}</span>
                <span style={{ fontFamily: t.mono, fontSize: 10, color: isActive ? t.accent : t.ink3 }}>
                  {unitLabel}
                </span>
              </div>
              <div style={{ paddingLeft: 28 }}>
                <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, marginBottom: 4 }}>{p.detail}</div>
                <div style={{ height: 2, background: t.bg3 }}>
                  <i style={{
                    display: 'block', height: '100%', width: `${innerP * 100}%`,
                    background: isDone ? t.ok : t.accent,
                    transition: 'width 80ms linear',
                  }}/>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Streaming log */}
      <div style={{ padding: '10px 14px 6px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, borderTop: `1px solid ${t.line}`, background: t.bg1, flexShrink: 0 }}>
        LOG · {state === 'idle' ? 'idle' : log.length + ' lines'}
      </div>
      <div ref={logRef} style={{
        flex: 1, minHeight: 80,
        background: '#050507',
        padding: '8px 14px',
        fontFamily: t.mono, fontSize: 11, color: '#a8a8b0',
        overflow: 'auto', lineHeight: 1.55,
        borderBottomLeftRadius: 0,
      }}>
        {log.length === 0 && (
          <div style={{ color: '#4a4a55', fontStyle: 'italic' }}>
            waiting · press "dry-run" to preview or "commit" to write files
          </div>
        )}
        {log.map((l, i) => {
          const col = l.kind === 'cmd' ? '#f5f5f0'
            : l.kind === 'ok' ? '#4ade80'
            : l.kind === 'warn' ? '#f5a623'
            : l.kind === 'err' ? '#d43a2f'
            : l.kind === 'file' ? '#d97757'
            : l.kind === 'section' ? (l[3] || '#a8a8b0')
            : '#a8a8b0';
          return (
            <div key={i} style={{ color: col, whiteSpace: 'pre' }}>
              {l.line}
            </div>
          );
        })}
        {state === 'running' && (
          <div style={{ color: '#d97757', animation: 'blink 0.8s step-end infinite' }}>▋</div>
        )}
      </div>
      <style>{`@keyframes blink { 50% { opacity: 0; } }`}</style>
    </div>
  );
}

// ---------------- Right column: output files tree ----------------
function OutputColumn({ state, mode, writtenFiles, phase, phaseP }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;

  const files = [
    { name: 'Highway to Hell.xsq',          size: '284 KB', kind: 'xsq',  produced: 'sections+timing+xsq', important: true, icon: '◆' },
    { name: 'Highway to Hell.mp3',          size: '8.4 MB', kind: 'mp3',  produced: 'audio',               icon: '♪' },
    { name: 'theme-metadata.json',          size: '12 KB',  kind: 'json', produced: 'xsq',                 icon: '{}' },
    { name: '.xo-cache/effects.bin',        size: '96 KB',  kind: 'bin',  produced: 'sections',            icon: '▦' },
    { name: '.xo-cache/timing.marks',       size: '4 KB',   kind: 'bin',  produced: 'timing',              icon: '▦' },
  ];

  const fileState = (f) => {
    if (state === 'idle') return 'pending';
    if (state === 'done') return mode === 'dry' ? 'dry' : 'written';
    // running: written once that phase finished
    const producedPhaseIdx = PHASES.findIndex(p => f.produced.includes(p.id));
    if (phase > producedPhaseIdx) return mode === 'dry' ? 'dry' : 'written';
    return 'pending';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', background: t.bg1, borderBottom: `1px solid ${t.line}`, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flexShrink: 0, display: 'flex', alignItems: 'center' }}>
        <span style={{ flex: 1 }}>DESTINATION</span>
        <span>{state === 'done' && mode === 'commit' ? `${files.length} files written` : state === 'done' ? `${files.length} files · dry-run` : state === 'running' ? 'writing…' : 'preview'}</span>
      </div>

      {/* Destination path */}
      <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}`, flexShrink: 0 }}>
        <div style={{ background: t.bg1, border: `1px solid ${t.line2}`, padding: '8px 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>▸</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: t.mono, fontSize: 12, color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              ~/xLights/Shows/Halloween 2026/
            </div>
            <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>48 GB free · xLights default · writable</div>
          </div>
          <button style={{ background: 'transparent', color: t.ink3, border: `1px solid ${t.line2}`, padding: '3px 8px', fontFamily: t.mono, fontSize: 10, cursor: 'pointer' }}>change…</button>
        </div>
      </div>

      {/* File list */}
      <div style={{ padding: '4px 0', overflow: 'auto', flex: 1 }}>
        {files.map((f, i) => {
          const fs = fileState(f);
          const col = fs === 'written' ? t.ok : fs === 'dry' ? t.warn : t.ink3;
          const glyph = fs === 'written' ? '✓' : fs === 'dry' ? '◌' : '·';
          return (
            <div key={i} style={{
              display: 'grid', gridTemplateColumns: '18px 20px 1fr 80px 24px',
              padding: '7px 14px', alignItems: 'center',
              borderBottom: `1px solid ${t.line}`, fontSize: 12,
              opacity: fs === 'pending' ? 0.55 : 1,
              transition: 'opacity 300ms',
              background: fs === 'written' && f.important ? `${t.ok}0c` : 'transparent',
            }}>
              <span style={{ color: col, fontFamily: t.mono, fontSize: 12, fontWeight: 700, textAlign: 'center' }}>{glyph}</span>
              <span style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3, textAlign: 'center' }}>{f.icon}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: f.important ? 600 : 400 }}>{f.name}</div>
                <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
                  {fs === 'pending' ? 'not written' : fs === 'dry' ? 'would write' : `written · ${fs === 'written' ? 'crc ok' : ''}`}
                </div>
              </div>
              <span style={{ fontFamily: t.mono, color: t.ink2, fontVariantNumeric: 'tabular-nums', fontSize: 11, textAlign: 'right' }}>{f.size}</span>
              <span style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>↗</span>
            </div>
          );
        })}
      </div>

      {/* Live out */}
      <div style={{ padding: '12px 14px', borderTop: `1px solid ${t.line}`, flexShrink: 0 }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 6, display: 'flex' }}>
          <span style={{ flex: 1 }}>LIVE OUT · what xLights will play</span>
          <span>4 props · 512 px</span>
        </div>
        <LightsPreview height={70} cells={64} label={null}/>
      </div>
    </div>
  );
}

// ---------------- Right inspector ----------------
function ExportInspector({ state, mode, overallP, phase, phaseP, sectionIdx, writtenFiles, start, reset }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;

  return (
    <div style={{ width: 300, background: t.bg1, borderLeft: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      <div style={{ padding: '10px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, borderBottom: `1px solid ${t.line}`, display: 'flex' }}>
        <span style={{ flex: 1 }}>EXPORT</span>
        <span style={{ color: state === 'done' ? t.ok : state === 'running' ? t.accent : t.ink3 }}>
          {state === 'done' ? (mode === 'dry' ? '◌ DRY-RUN' : '✓ COMMITTED')
            : state === 'running' ? `● ${mode === 'dry' ? 'DRY' : 'COMMIT'}`
            : '○ IDLE'}
        </span>
      </div>

      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: t.ink, letterSpacing: -0.2 }}>{song.title}</div>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>{fmt.timeShort(song.duration)} · {app.sections.length} sections · {song.beats.length} beats · 4 props</div>
      </div>

      {/* Progress summary */}
      {state !== 'idle' && (
        <div style={{ padding: '12px 14px', borderBottom: `1px solid ${t.line}` }}>
          <div style={{ display: 'flex', fontFamily: t.mono, fontSize: 10, color: t.ink3, marginBottom: 6 }}>
            <span style={{ flex: 1 }}>OVERALL</span>
            <span style={{ color: t.ink, fontVariantNumeric: 'tabular-nums' }}>{Math.floor(overallP)}%</span>
          </div>
          <div style={{ height: 4, background: t.bg3, marginBottom: 10 }}>
            <i style={{ display: 'block', height: '100%', width: `${overallP}%`, background: state === 'done' ? t.ok : t.accent, transition: 'width 80ms linear' }}/>
          </div>
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
            phase {phase + 1} · {PHASES[phase].label}
          </div>
          {state === 'running' && sectionIdx >= 0 && PHASES[phase].id === 'sections' && (
            <div style={{ fontFamily: t.mono, fontSize: 10, color: t.accent, marginTop: 4 }}>
              ▶ {app.sections[sectionIdx].label}
            </div>
          )}
        </div>
      )}

      {/* Pre-flight (idle only) */}
      {state === 'idle' && (
        <div style={{ padding: '10px 14px', borderBottom: `1px solid ${t.line}` }}>
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 8 }}>PRE-FLIGHT · 7 / 7</div>
          {[
            ['ok',  'themes assigned',        `${app.sections.length}/${app.sections.length}`],
            ['ok',  'audio embedded',         '8.4 MB'],
            ['ok',  'xLights detected',       'v2024.22'],
            ['ok',  'layout valid',           '4 props · 512 px'],
            ['ok',  'timing clean',           `${song.beats.length} beats`],
            ['warn','solo is quiet',          '-22% lumens'],
            ['ok',  'destination writable',   '48 GB free'],
          ].map(([s, l, d], i) => {
            const col = s === 'ok' ? t.ok : t.warn;
            const g = s === 'ok' ? '✓' : '!';
            return (
              <div key={i} style={{ display: 'flex', fontFamily: t.mono, fontSize: 10, marginBottom: 4, gap: 6 }}>
                <span style={{ color: col, width: 10 }}>{g}</span>
                <span style={{ flex: 1, color: t.ink2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{l}</span>
                <span style={{ color: t.ink3 }}>{d}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Success CTAs */}
      {state === 'done' && (
        <div style={{ padding: '12px 14px', borderBottom: `1px solid ${t.line}` }}>
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 10 }}>
            {mode === 'dry' ? 'DRY-RUN RESULT' : 'COMMITTED'}
          </div>
          {mode === 'commit' && (
            <>
              <button style={{ width: '100%', background: t.accent, color: t.accentInk, border: 'none', padding: '8px 10px', fontFamily: t.mono, fontSize: 11, fontWeight: 700, cursor: 'pointer', marginBottom: 6 }}>
                ↗ open in xLights
              </button>
              <button style={{ width: '100%', background: 'transparent', color: t.ink2, border: `1px solid ${t.line2}`, padding: '7px 10px', fontFamily: t.mono, fontSize: 11, cursor: 'pointer', marginBottom: 6 }}>
                ▸ reveal in Finder
              </button>
            </>
          )}
          {mode === 'dry' && (
            <button onClick={() => start('commit')} style={{ width: '100%', background: t.accent, color: t.accentInk, border: 'none', padding: '8px 10px', fontFamily: t.mono, fontSize: 11, fontWeight: 700, cursor: 'pointer', marginBottom: 6 }}>
              ▶ commit for real
            </button>
          )}
          <button onClick={() => app.setScreen('library')} style={{ width: '100%', background: 'transparent', color: t.ink2, border: `1px solid ${t.line2}`, padding: '7px 10px', fontFamily: t.mono, fontSize: 11, cursor: 'pointer' }}>
            ⇤ export next song
          </button>
        </div>
      )}

      <div style={{ flex: 1 }}/>

      {/* Action buttons (idle) */}
      {state === 'idle' && (
        <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button onClick={() => start('dry')} style={{
            background: 'transparent', color: t.ink, border: `1px solid ${t.line2}`,
            padding: '9px 10px', fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
            fontWeight: 600,
          }}>
            ▸ DRY-RUN · no disk writes
          </button>
          <button onClick={() => start('commit')} style={{
            background: t.accent, color: t.accentInk, border: 'none',
            padding: '10px 10px', fontFamily: t.mono, fontSize: 12, fontWeight: 700,
            cursor: 'pointer', letterSpacing: 0.5,
          }}>
            ▶ COMMIT · ⌘E
          </button>
          <div style={{ fontFamily: t.mono, fontSize: 9, color: t.ink3, textAlign: 'center', marginTop: 2 }}>
            dry-run first if anything changed
          </div>
        </div>
      )}

      {state === 'running' && (
        <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.line}` }}>
          <button onClick={reset} style={{
            width: '100%', background: 'transparent', color: t.err, border: `1px solid ${t.err}`,
            padding: '8px 10px', fontFamily: t.mono, fontSize: 11, cursor: 'pointer',
          }}>
            ✕ cancel export
          </button>
        </div>
      )}
    </div>
  );
}

Object.assign(window, { ExportScreenV2 });
