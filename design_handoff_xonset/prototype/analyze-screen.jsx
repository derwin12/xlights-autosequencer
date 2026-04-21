// Analyze screen v2 — feels like the tool is actually finding things.
// Phased pipeline: decode → beats → bars → key/tempo → sections → themes.
// Findings stream in on the right. Waveform fills as it scans. Skip when ready.
const { useApp, Chrome, THEMES_BY_ID, fmt } = window;

// One phase per column in the findings panel. Ordered by what happens first.
const AZ_PHASES = [
  { id: 'decode',   label: 'decoding waveform',     detail: 'fluidsynth · 44.1 kHz · stereo → mono',  dur: 14 },
  { id: 'beats',    label: 'tracking beats',        detail: 'madmom DBN · tempo hypothesis tree',      dur: 22 },
  { id: 'bars',     label: 'finding bars',          detail: 'qm_bars downbeat tracker',                dur: 12 },
  { id: 'tempo',    label: 'estimating key + tempo',detail: 'essentia keydetector · tempoCNN',         dur: 8  },
  { id: 'impacts',  label: 'detecting impacts',     detail: 'demucs → spectral flux → peak pick',      dur: 14 },
  { id: 'sections', label: 'segmenting structure',  detail: 'MSA · novelty-peaks · SSM',               dur: 18 },
  { id: 'themes',   label: 'auto-assigning themes', detail: 'matching section kind → theme heuristic', dur: 12 },
];

function AnalyzeScreenV2() {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const [elapsed, setElapsed] = React.useState(0);
  const totalDur = AZ_PHASES.reduce((s, p) => s + p.dur, 0);
  const [done, setDone] = React.useState(false);
  const timerRef = React.useRef(null);

  React.useEffect(() => {
    setElapsed(0); setDone(false);
    const t0 = Date.now();
    timerRef.current = setInterval(() => {
      const e = (Date.now() - t0) / 1000 * 6; // 6x speed for demo
      if (e >= totalDur) {
        setElapsed(totalDur); setDone(true);
        clearInterval(timerRef.current); timerRef.current = null;
      } else setElapsed(e);
    }, 60);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  // Current phase progress
  const phaseInfo = React.useMemo(() => {
    let acc = 0;
    for (let i = 0; i < AZ_PHASES.length; i++) {
      const p = AZ_PHASES[i];
      if (elapsed < acc + p.dur) {
        return { idx: i, p: (elapsed - acc) / p.dur, acc };
      }
      acc += p.dur;
    }
    return { idx: AZ_PHASES.length - 1, p: 1, acc: totalDur - AZ_PHASES[AZ_PHASES.length - 1].dur };
  }, [elapsed, totalDur]);

  // How far through the waveform we've scanned (0..1). Decode makes it fill,
  // rest of phases re-scan with different markers.
  const decodePct = Math.min(1, elapsed / AZ_PHASES[0].dur);
  const overallPct = (elapsed / totalDur);

  // Findings — computed based on elapsed. Streams in.
  const findings = React.useMemo(() => computeFindings(elapsed, song), [elapsed]);

  return (
    <Chrome
      inspector={<AZInspector done={done} elapsed={elapsed} totalDur={totalDur} findings={findings} phaseInfo={phaseInfo}/>}
      statusExtra={done
        ? <span style={{ color: t.ok }}>● analysis complete · opening review timeline</span>
        : <span style={{ color: t.accent }}>● {AZ_PHASES[phaseInfo.idx].label} · {Math.floor(overallPct * 100)}%</span>
      }>
      {/* Header */}
      <div style={{
        padding: '14px 20px 12px', display: 'flex', alignItems: 'baseline', gap: 14,
        borderBottom: `1px solid ${t.line}`, flexShrink: 0,
      }}>
        <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: -0.3 }}>
          {done ? 'Analysis complete' : 'Analyzing'}
        </div>
        <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>
          {song.title} · {song.artist} · {fmt.timeShort(song.duration)}
        </div>
        <div style={{ flex: 1 }}/>
        {!done && (
          <>
            <div style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3 }}>
              {elapsed.toFixed(1)}s / {totalDur}s
            </div>
            <button onClick={() => app.setScreen('timeline')} disabled={overallPct < 0.4} style={{
              background: 'transparent', color: overallPct < 0.4 ? t.ink3 : t.ink2,
              border: `1px solid ${t.line2}`, padding: '6px 12px',
              fontFamily: t.mono, fontSize: 11, cursor: overallPct < 0.4 ? 'not-allowed' : 'pointer',
              opacity: overallPct < 0.4 ? 0.4 : 1,
            }}
              title={overallPct < 0.4 ? 'wait for sections to detect' : 'skip to review timeline'}
            >skip to timeline →</button>
          </>
        )}
        {done && (
          <button onClick={() => app.setScreen('timeline')} style={{
            background: t.accent, color: t.accentInk, border: 'none',
            padding: '7px 14px', fontFamily: t.mono, fontSize: 11, fontWeight: 700,
            cursor: 'pointer', letterSpacing: 0.3,
          }}>▶ review timeline →</button>
        )}
      </div>

      {/* BIG live waveform panel */}
      <div style={{ padding: '14px 14px 0', flexShrink: 0 }}>
        <AZWaveform elapsed={elapsed} decodePct={decodePct} phaseIdx={phaseInfo.idx} findings={findings} totalDur={totalDur}/>
      </div>

      {/* Phase strip */}
      <div style={{ padding: '12px 14px 4px', flexShrink: 0 }}>
        <PhaseTimeline phaseIdx={phaseInfo.idx} phaseP={phaseInfo.p} elapsed={elapsed}/>
      </div>

      {/* Detector list + log */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', borderTop: `1px solid ${t.line}`, minHeight: 0, overflow: 'hidden' }}>
        <DetectorList elapsed={elapsed}/>
        <ConsoleLog elapsed={elapsed} findings={findings} phaseIdx={phaseInfo.idx}/>
      </div>
    </Chrome>
  );
}

// ---------------- Waveform that reveals itself ----------------
function AZWaveform({ elapsed, decodePct, phaseIdx, findings, totalDur }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  // Stage: when beat tracking starts, layer beats on top of wave. When bar phase, layer bars. etc.
  const showBeats   = phaseIdx >= 1;
  const showBars    = phaseIdx >= 2;
  const showImpacts = phaseIdx >= 4;
  const showSections = phaseIdx >= 5;
  const showThemes   = phaseIdx >= 6;

  // Progressive reveal within each phase: once the phase starts, show its findings partially
  const beatCount = findings.beats;
  const barCount = findings.bars;
  const impactCount = findings.impacts;
  const sectionCount = findings.sections.length;

  return (
    <div style={{ background: '#000', border: `1px solid ${t.line}`, padding: 10, position: 'relative' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8, gap: 14 }}>
        <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1 }}>WAVEFORM · {song.title.toUpperCase()}</span>
        <span style={{ fontFamily: t.mono, fontSize: 10, color: t.accent }}>
          {phaseIdx === 0 ? `scanning ${Math.floor(decodePct * 100)}%` :
           phaseIdx === 1 ? `tracking beats · ${beatCount} found` :
           phaseIdx === 2 ? `finding bars · ${barCount} found` :
           phaseIdx === 3 ? `estimating key + tempo` :
           phaseIdx === 4 ? `detecting impacts · ${impactCount} found` :
           phaseIdx === 5 ? `segmenting · ${sectionCount} sections` :
           phaseIdx === 6 ? `assigning themes` : 'done'}
        </span>
        <div style={{ flex: 1 }}/>
        <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3 }}>
          {fmt.timeShort(decodePct * song.duration)} / {fmt.timeShort(song.duration)}
        </span>
      </div>

      <svg width="100%" height="210" preserveAspectRatio="none" viewBox="0 0 1040 210" style={{ display: 'block' }}>
        {/* section bands, fade in */}
        {showSections && findings.sections.map((s, i) => {
          const x = (s.start / song.duration) * 1040;
          const w = ((s.end - s.start) / song.duration) * 1040;
          const themeId = showThemes ? s.defaultTheme : null;
          const col = themeId ? THEMES_BY_ID[themeId].accent : t.accent;
          return (
            <g key={'sec' + i}>
              <rect x={x} y={0} width={w} height={210} fill={col}
                    opacity={showThemes ? 0.16 : 0.08}/>
              {showThemes && (
                <text x={x + 6} y={16} fill={col} fontFamily="'JetBrains Mono', monospace" fontSize="10" opacity={0.95}>
                  {s.label}
                </text>
              )}
            </g>
          );
        })}

        {/* waveform */}
        {window.WAVE.map((v, i) => {
          const wx = i / window.WAVE.length * 1040;
          const h = v * 150;
          const pct = i / window.WAVE.length;
          const decoded = pct <= decodePct;
          const col = decoded ? t.ink2 : t.ink3;
          return <rect key={i} x={wx} y={105 - h / 2} width={1.4} height={h}
                       fill={col} opacity={decoded ? 0.85 : 0.18}/>;
        })}

        {/* beat marks */}
        {showBeats && song.beats.slice(0, beatCount).map((b, i) => {
          const x = (b.t / song.duration) * 1040;
          const isDownbeat = b.beat === 0;
          return <line key={'bt' + i} x1={x} x2={x}
                       y1={isDownbeat ? 185 : 190} y2={200}
                       stroke={isDownbeat ? '#d43a2f' : t.warn}
                       strokeWidth={isDownbeat ? 1 : 0.7}
                       opacity={isDownbeat ? 0.9 : 0.6}/>;
        })}

        {/* bar markers */}
        {showBars && song.bars.slice(0, barCount).map((t0, i) => {
          const x = (t0 / song.duration) * 1040;
          return <line key={'br' + i} x1={x} x2={x} y1={0} y2={210}
                       stroke="#2f5ad4" strokeWidth={0.4} opacity={0.3}/>;
        })}

        {/* impacts */}
        {showImpacts && song.impacts.slice(0, impactCount).map((im, i) => {
          const x = (im.t / song.duration) * 1040;
          return <circle key={'im' + i} cx={x} cy={105} r={3}
                         fill="#e87a3a" opacity={0.9}/>;
        })}

        {/* section divider lines */}
        {showSections && findings.sections.map((s, i) => {
          const x = (s.start / song.duration) * 1040;
          if (i === 0) return null;
          return <line key={'sdiv' + i} x1={x} x2={x} y1={0} y2={210}
                       stroke="#fff" strokeWidth={0.8} opacity={0.4}/>;
        })}

        {/* scan sweep */}
        {phaseIdx < AZ_PHASES.length - 1 && (() => {
          // Each phase sweeps 0→100% of the waveform
          const elapsedInPhase = AZ_PHASES.slice(0, phaseIdx).reduce((s, p) => s + p.dur, 0);
          const phaseP = (elapsed - elapsedInPhase) / AZ_PHASES[phaseIdx].dur;
          const x = phaseP * 1040;
          const col = phaseIdx === 0 ? t.accent : phaseIdx === 1 ? t.warn : phaseIdx === 2 ? '#2f5ad4' : phaseIdx === 4 ? '#e87a3a' : phaseIdx === 5 ? '#4aa8ff' : t.accent;
          return (
            <>
              <line x1={x} x2={x} y1={0} y2={210} stroke="#fff" strokeWidth={1} opacity={0.8}/>
              <rect x={x - 40} y={0} width={40} height={210}
                    fill={col} opacity={0.06}/>
            </>
          );
        })()}
      </svg>
      <div style={{ display: 'flex', gap: 14, marginTop: 6, fontFamily: t.mono, fontSize: 9, color: t.ink3 }}>
        <span style={{ color: showBeats ? '#d43a2f' : t.ink3 }}>● downbeats</span>
        <span style={{ color: showBeats ? t.warn : t.ink3 }}>● beats</span>
        <span style={{ color: showBars ? '#2f5ad4' : t.ink3 }}>● bars</span>
        <span style={{ color: showImpacts ? '#e87a3a' : t.ink3 }}>● impacts</span>
        <span style={{ color: showSections ? '#fff' : t.ink3 }}>● sections</span>
        <div style={{ flex: 1 }}/>
        <span>{window.WAVE.length} px · 44.1 kHz · mono</span>
      </div>
    </div>
  );
}

// ---------------- Horizontal phase timeline ----------------
function PhaseTimeline({ phaseIdx, phaseP, elapsed }) {
  const app = useApp();
  const t = app.theme;
  return (
    <div style={{
      display: 'flex', gap: 4, background: t.bg1, padding: 3,
      border: `1px solid ${t.line}`,
    }}>
      {AZ_PHASES.map((p, i) => {
        const isDone = i < phaseIdx;
        const isActive = i === phaseIdx;
        const isPending = i > phaseIdx;
        const innerP = isActive ? phaseP : isDone ? 1 : 0;
        return (
          <div key={p.id} style={{
            flex: p.dur, background: isActive ? t.bg3 : isDone ? `${t.ok}22` : t.bg0,
            padding: '8px 10px', position: 'relative', overflow: 'hidden',
            border: isActive ? `1px solid ${t.accent}` : `1px solid ${t.line}`,
            opacity: isPending ? 0.55 : 1,
            minWidth: 0,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <span style={{
                fontFamily: t.mono, fontSize: 10, fontWeight: 700,
                color: isDone ? t.ok : isActive ? t.accent : t.ink3,
                width: 14,
              }}>{isDone ? '✓' : isActive ? '●' : String(i + 1).padStart(2, '0')}</span>
              <span style={{
                fontSize: 11, color: isPending ? t.ink3 : t.ink,
                fontWeight: isActive ? 600 : 400,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', flex: 1,
              }}>{p.label}</span>
            </div>
            <div style={{ fontFamily: t.mono, fontSize: 9, color: t.ink3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginBottom: 5 }}>
              {p.detail}
            </div>
            <div style={{ height: 2, background: t.bg3 }}>
              <i style={{
                display: 'block', height: '100%', width: `${innerP * 100}%`,
                background: isDone ? t.ok : t.accent, transition: 'width 80ms linear',
              }}/>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------- Detector list on the left ----------------
const DETECTORS = [
  { id: 'decoder',    name: 'libsndfile decoder',        startAt: 0,   dur: 14, items: 0 },
  { id: 'madmom',     name: 'madmom · beat DBN',         startAt: 14,  dur: 22, items: 312 },
  { id: 'qm_bars',    name: 'qm_bars · downbeats',       startAt: 32,  dur: 12, items: 78 },
  { id: 'librosa',    name: 'librosa · HFC onsets',      startAt: 20,  dur: 16, items: 487 },
  { id: 'aubio',      name: 'aubio · complex onsets',    startAt: 22,  dur: 14, items: 412 },
  { id: 'essentia_k', name: 'essentia · key detector',   startAt: 44,  dur: 4,  items: 1 },
  { id: 'essentia_t', name: 'essentia · tempoCNN',       startAt: 46,  dur: 2,  items: 1 },
  { id: 'demucs',     name: 'demucs · stem separation',  startAt: 42,  dur: 14, items: 4 },
  { id: 'spectral',   name: 'spectral flux · peak pick', startAt: 54,  dur: 8,  items: 96 },
  { id: 'msa',        name: 'MSA · structural segment',  startAt: 58,  dur: 18, items: 9 },
  { id: 'ssm',        name: 'self-similarity matrix',    startAt: 60,  dur: 14, items: 1 },
  { id: 'themer',     name: 'theme heuristic',           startAt: 76,  dur: 12, items: 9 },
];

function DetectorList({ elapsed }) {
  const app = useApp();
  const t = app.theme;
  return (
    <div style={{ borderRight: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', background: t.bg1, borderBottom: `1px solid ${t.line}`, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flexShrink: 0 }}>
        DETECTORS · {DETECTORS.filter(d => elapsed >= d.startAt + d.dur).length} / {DETECTORS.length} done
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {DETECTORS.map((d, i) => {
          const done = elapsed >= d.startAt + d.dur;
          const running = elapsed >= d.startAt && !done;
          const pending = elapsed < d.startAt;
          const p = running ? (elapsed - d.startAt) / d.dur : done ? 1 : 0;
          const col = done ? t.ok : running ? t.accent : t.ink3;
          const glyph = done ? '✓' : running ? '●' : '○';
          const count = done ? d.items : running ? Math.floor(d.items * p) : 0;
          return (
            <div key={d.id} style={{
              padding: '7px 14px', borderBottom: `1px solid ${t.line}`,
              opacity: pending ? 0.55 : 1,
              background: running ? `${t.accent}08` : 'transparent',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                <span style={{ color: col, fontFamily: t.mono, fontSize: 11, width: 12, textAlign: 'center', fontWeight: 700 }}>{glyph}</span>
                <span style={{ fontSize: 12, color: pending ? t.ink3 : t.ink, flex: 1, fontFamily: t.mono }}>{d.name}</span>
                <span style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, fontVariantNumeric: 'tabular-nums' }}>
                  {d.items > 1 ? `${count} / ${d.items}` : pending ? '—' : running ? 'running' : 'done'}
                </span>
              </div>
              <div style={{ paddingLeft: 22, height: 2, background: t.bg3 }}>
                <i style={{ display: 'block', height: '100%', width: `${p * 100}%`, background: col, transition: 'width 80ms linear' }}/>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------- Streaming console ----------------
function ConsoleLog({ elapsed, findings, phaseIdx }) {
  const app = useApp();
  const t = app.theme;
  const logRef = React.useRef(null);

  // Derive log lines from elapsed time
  const lines = React.useMemo(() => buildLog(elapsed, findings), [elapsed, findings]);

  React.useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines.length]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', background: t.bg1, borderBottom: `1px solid ${t.line}`, fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, flexShrink: 0 }}>
        STREAM · {lines.length} lines
      </div>
      <div ref={logRef} style={{
        flex: 1, minHeight: 0,
        background: '#050507',
        padding: '8px 14px',
        fontFamily: t.mono, fontSize: 11, color: '#a8a8b0',
        overflow: 'auto', lineHeight: 1.55,
      }}>
        {lines.map((l, i) => {
          const col = l.kind === 'cmd' ? '#f5f5f0'
            : l.kind === 'ok' ? '#4ade80'
            : l.kind === 'warn' ? '#f5a623'
            : l.kind === 'err' ? '#d43a2f'
            : l.kind === 'found' ? '#d97757'
            : l.kind === 'meta' ? '#4aa8ff'
            : '#a8a8b0';
          return (
            <div key={i} style={{ color: col, whiteSpace: 'pre' }}>
              {l.line}
            </div>
          );
        })}
        <div style={{ color: '#d97757', animation: 'blink 0.8s step-end infinite' }}>▋</div>
      </div>
      <style>{`@keyframes blink { 50% { opacity: 0; } }`}</style>
    </div>
  );
}

// ---------------- Inspector ----------------
function AZInspector({ done, elapsed, totalDur, findings, phaseInfo }) {
  const app = useApp();
  const t = app.theme;
  const song = window.HIGHWAY;
  const p = elapsed / totalDur;
  return (
    <div style={{ width: 300, background: t.bg1, borderLeft: `1px solid ${t.line}`, display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
      <div style={{ padding: '10px 12px', fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, borderBottom: `1px solid ${t.line}`, display: 'flex' }}>
        <span style={{ flex: 1 }}>FINDINGS</span>
        <span style={{ color: done ? t.ok : t.accent }}>{done ? '✓ DONE' : '● LIVE'}</span>
      </div>

      {/* Progress ring / elapsed */}
      <div style={{ padding: '14px 16px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
          <span style={{ fontFamily: t.mono, fontSize: 24, fontWeight: 600, color: done ? t.ok : t.accent, fontVariantNumeric: 'tabular-nums' }}>
            {Math.floor(p * 100)}%
          </span>
          <span style={{ fontFamily: t.mono, fontSize: 11, color: t.ink3, flex: 1 }}>
            {elapsed.toFixed(1)}s / {totalDur}s
          </span>
        </div>
        <div style={{ height: 4, background: t.bg3 }}>
          <i style={{ display: 'block', height: '100%', width: `${p * 100}%`, background: done ? t.ok : t.accent, transition: 'width 80ms linear' }}/>
        </div>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, marginTop: 8 }}>
          {done ? 'all detectors complete' : AZ_PHASES[phaseInfo.idx].label}
        </div>
      </div>

      {/* Live counts */}
      <div style={{ padding: '12px 14px', borderBottom: `1px solid ${t.line}` }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 10 }}>DETECTED</div>
        {[
          ['waveform',   findings.decoded ? `${findings.duration}s` : '—', findings.decoded],
          ['tempo',      findings.bpm     ? `${findings.bpm} BPM`   : '—', !!findings.bpm],
          ['key',        findings.key     || '—',                          !!findings.key],
          ['beats',      findings.beats   ? `${findings.beats}`     : '—', findings.beats > 0],
          ['bars',       findings.bars    ? `${findings.bars}`      : '—', findings.bars > 0],
          ['impacts',    findings.impacts ? `${findings.impacts}`   : '—', findings.impacts > 0],
          ['sections',   findings.sections.length > 0 ? `${findings.sections.length}` : '—', findings.sections.length > 0],
          ['themes',     findings.themesAssigned ? `auto-assigned` : '—', findings.themesAssigned],
        ].map(([k, v, has], i) => (
          <div key={i} style={{ display: 'flex', fontFamily: t.mono, fontSize: 11, marginBottom: 5 }}>
            <span style={{ color: has ? t.ok : t.ink3, width: 14 }}>{has ? '✓' : '·'}</span>
            <span style={{ flex: 1, color: has ? t.ink2 : t.ink3 }}>{k}</span>
            <span style={{ color: has ? t.ink : t.ink3, fontVariantNumeric: 'tabular-nums' }}>{v}</span>
          </div>
        ))}
      </div>

      {/* Sections list as they arrive */}
      <div style={{ flex: 1, overflow: 'auto', padding: '10px 14px' }}>
        <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, letterSpacing: 1, marginBottom: 10 }}>
          SECTIONS · {findings.sections.length}
        </div>
        {findings.sections.length === 0 && (
          <div style={{ fontFamily: t.mono, fontSize: 10, color: t.ink3, fontStyle: 'italic' }}>
            waiting for MSA to converge…
          </div>
        )}
        {findings.sections.map((s, i) => {
          const th = findings.themesAssigned ? THEMES_BY_ID[s.defaultTheme] : null;
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontFamily: t.mono, fontSize: 11 }}>
              <i style={{ width: 8, height: 8, background: th ? th.accent : t.ink3, flexShrink: 0 }}/>
              <span style={{ color: t.ink3, width: 20 }}>{String(i + 1).padStart(2, '0')}</span>
              <span style={{ flex: 1, color: t.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.label}</span>
              <span style={{ color: t.ink3, fontVariantNumeric: 'tabular-nums' }}>{Math.round(s.end - s.start)}s</span>
            </div>
          );
        })}
      </div>

      <div style={{ padding: '10px 14px', borderTop: `1px solid ${t.line}` }}>
        <button
          onClick={() => done ? app.setScreen('timeline') : app.setScreen('timeline')}
          disabled={p < 0.4 && !done}
          style={{
            width: '100%',
            background: done ? t.ok : p >= 0.4 ? t.accent : t.bg3,
            color: done || p >= 0.4 ? '#000' : t.ink3,
            border: 'none', padding: '10px 12px',
            fontFamily: t.mono, fontSize: 12, fontWeight: 700, letterSpacing: 0.5,
            cursor: p < 0.4 && !done ? 'not-allowed' : 'pointer',
            opacity: p < 0.4 && !done ? 0.5 : 1,
          }}>
          {done ? '▶ REVIEW TIMELINE →' : p >= 0.4 ? 'SKIP TO TIMELINE →' : 'WAITING…'}
        </button>
      </div>
    </div>
  );
}

// ---------------- Findings computation (deterministic from elapsed) ----------------
function computeFindings(elapsed, song) {
  // Detect which phase finished when
  let acc = 0;
  const phaseEnds = {};
  AZ_PHASES.forEach(p => { acc += p.dur; phaseEnds[p.id] = acc; });

  const decoded = elapsed >= phaseEnds.decode;

  // beats stream in gradually during the beats phase
  let beatProgress = 0;
  const beatsStart = phaseEnds.decode, beatsEnd = phaseEnds.beats;
  if (elapsed >= beatsEnd) beatProgress = 1;
  else if (elapsed > beatsStart) beatProgress = (elapsed - beatsStart) / (beatsEnd - beatsStart);
  const beats = Math.floor(beatProgress * song.beats.length);

  let barProgress = 0;
  const barsStart = phaseEnds.beats, barsEnd = phaseEnds.bars;
  if (elapsed >= barsEnd) barProgress = 1;
  else if (elapsed > barsStart) barProgress = (elapsed - barsStart) / (barsEnd - barsStart);
  const bars = Math.floor(barProgress * song.bars.length);

  const bpm = elapsed >= phaseEnds.tempo ? song.bpm : null;
  const key = elapsed >= phaseEnds.tempo ? song.key : null;

  let impactProgress = 0;
  const impactsStart = phaseEnds.tempo, impactsEnd = phaseEnds.impacts;
  if (elapsed >= impactsEnd) impactProgress = 1;
  else if (elapsed > impactsStart) impactProgress = (elapsed - impactsStart) / (impactsEnd - impactsStart);
  const impacts = Math.floor(impactProgress * (song.impacts?.length || 0));

  // sections stream in one by one
  let sectionProgress = 0;
  const sectStart = phaseEnds.impacts, sectEnd = phaseEnds.sections;
  if (elapsed >= sectEnd) sectionProgress = 1;
  else if (elapsed > sectStart) sectionProgress = (elapsed - sectStart) / (sectEnd - sectStart);
  const allSecs = song.sections; // use full set
  const sections = allSecs.slice(0, Math.floor(sectionProgress * allSecs.length));

  const themesAssigned = elapsed >= phaseEnds.themes;

  return {
    decoded, duration: song.duration, bpm, key,
    beats, bars, impacts, sections, themesAssigned,
  };
}

// ---------------- Console log lines (from findings & elapsed) ----------------
function buildLog(elapsed, findings) {
  const song = window.HIGHWAY;
  const lines = [];
  const push = (line, kind = 'info') => lines.push({ line, kind });

  // decode phase
  push(`$ xo analyze "${song.title}.mp3"`, 'cmd');
  push(`› libsndfile: decoding 8.4 MB → pcm_s16le stereo 44.1 kHz`, 'info');

  if (elapsed >= 2)  push(`  chunk 1 / 6 · 32768 frames`, 'info');
  if (elapsed >= 4)  push(`  chunk 3 / 6 · 98304 frames`, 'info');
  if (elapsed >= 7)  push(`  chunk 5 / 6 · 163840 frames`, 'info');
  if (elapsed >= 14) push(`✓ decoded · ${song.duration.toFixed(1)}s · mono mix-down done`, 'ok');

  // beats phase
  if (elapsed >= 14) push(`› madmom: building tempo hypothesis tree…`, 'info');
  if (elapsed >= 18) push(`  hypothesis 116.2 BPM · confidence 0.87`, 'info');
  if (elapsed >= 22) push(`  hypothesis 116.5 BPM · confidence 0.92 · promoted`, 'ok');
  if (elapsed >= 26) push(`  ${Math.floor(findings.beats / 2)} beats tracked · drifting beat 48 (+12ms)`, 'info');
  if (elapsed >= 30) push(`  snapping beat 48 to nearest onset (-12ms)`, 'info');
  if (elapsed >= 36) push(`✓ ${findings.beats} beats · drift ≤ 8ms after snap`, 'ok');

  // bars phase
  if (elapsed >= 36) push(`› qm_bars: finding downbeats…`, 'info');
  if (elapsed >= 40) push(`  time signature: 4/4 · confidence 0.94`, 'info');
  if (elapsed >= 44) push(`✓ ${findings.bars} bars · 4-beat period locked`, 'ok');

  // key/tempo phase
  if (elapsed >= 44) push(`› essentia: key detector (profile: krumhansl)`, 'info');
  if (elapsed >= 46) push(`  candidate: A major (0.81) · F# minor (0.64)`, 'info');
  if (elapsed >= 48) push(`✓ key = A major · tempo = 116 BPM`, 'ok');

  // impacts phase
  if (elapsed >= 48) push(`› demucs: separating drums stem…`, 'info');
  if (elapsed >= 52) push(`  drums stem extracted · 2.1 MB`, 'info');
  if (elapsed >= 56) push(`  spectral flux → peak picking (thr 0.32)`, 'info');
  if (elapsed >= 62) push(`✓ ${findings.impacts} impacts · 96 kicks · 48 snares`, 'ok');

  // sections phase
  if (elapsed >= 62) push(`› MSA: building self-similarity matrix (256x256)…`, 'info');
  if (elapsed >= 66) push(`  novelty peak at 13.2s · confidence 0.72`, 'found');
  if (elapsed >= 68) push(`  novelty peak at 45.6s · confidence 0.88`, 'found');
  if (elapsed >= 70) push(`  novelty peak at 78.1s · confidence 0.91`, 'found');
  if (elapsed >= 72) push(`  novelty peak at 128.4s · confidence 0.85`, 'found');
  if (elapsed >= 74) push(`  novelty peak at 173.2s · confidence 0.48 (weak)`, 'warn');
  if (elapsed >= 76) push(`✓ ${findings.sections.length} sections segmented · 1 low-confidence flag`, 'ok');

  // themes phase
  if (elapsed >= 76) push(`› theme heuristic: matching section → theme`, 'info');
  if (elapsed >= 78) push(`  intro → quiet · verse → driving · chorus → punchy`, 'meta');
  if (elapsed >= 82) push(`  solo → bright · bridge → ember · outro → quiet`, 'meta');
  if (elapsed >= 88) push(`✓ themes auto-assigned for ${findings.sections.length} sections`, 'ok');
  if (elapsed >= 88) push(`✓ analysis complete · 88.0s total · ready for review`, 'ok');

  return lines;
}

Object.assign(window, { AnalyzeScreenV2 });
