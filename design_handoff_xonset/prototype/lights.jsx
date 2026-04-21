// Live animated lights strip. Reacts to beats + section + theme.
const { useApp, THEMES_BY_ID } = window;

function LightsPreview({ height = 60, cells = 54, label = null, compact = false }) {
  const app = useApp();
  const { time, playing, sectionThemes, curSectionIdx, energyPulse, theme: pt } = app;
  const themeId = sectionThemes[curSectionIdx] || 'driving';
  const theme = THEMES_BY_ID[themeId];
  const sec = app.sections[curSectionIdx];

  // Pick palette based on theme + section kind
  const palette = theme.swatches;

  // Animate per cell: combine a per-cell phase offset with the current beat.
  // Rendering via SVG rects for reliability.
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    let rafId = 0;
    const loop = () => { setTick(t => t + 1); rafId = requestAnimationFrame(loop); };
    rafId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafId);
  }, []);

  // Find next beat for sync hint
  const nowT = time;
  // Boolean: are we within 60ms of a beat?
  const beats = window.HIGHWAY.beats;
  const beatIdx = React.useMemo(() => {
    let idx = 0;
    for (let i = 0; i < beats.length; i++) { if (beats[i].t <= nowT) idx = i; else break; }
    return idx;
  }, [nowT]);
  const sinceBeat = nowT - (beats[beatIdx]?.t ?? 0);

  const cellsArr = [];
  for (let i = 0; i < cells; i++) {
    // base color from palette
    const phase = (i * 0.3) + beatIdx * 0.7;
    const pi = (i + beatIdx) % palette.length;
    let col = palette[pi];
    // override for kicks/choruses: punchy flashes white briefly after beat
    let opacity;
    let glow = false;
    if (sec.kind === 'chorus' || themeId === 'punchy') {
      // on kick beats flash high
      const beatPulse = Math.max(0, 1 - sinceBeat * 4);
      if (i % 4 === (beatIdx % 4)) { col = '#ffffff'; opacity = 0.4 + beatPulse * 0.6; glow = beatPulse > 0.3; }
      else { opacity = 0.25 + Math.sin(phase + tick * 0.08) * 0.35; }
    } else if (sec.kind === 'solo' || themeId === 'storm' || themeId === 'bright') {
      const strobe = (Math.floor(tick / 3) + i) % 5 === 0;
      opacity = strobe ? 1 : 0.2 + Math.sin(phase + tick * 0.12) * 0.4;
      if (strobe) { col = palette[palette.length - 1]; glow = true; }
    } else if (sec.kind === 'intro' || themeId === 'quiet') {
      // slow soft fade
      opacity = 0.25 + Math.sin(phase + tick * 0.02) * 0.25;
    } else {
      // driving / ember: amber pulse on beats
      const beatPulse = Math.max(0, 1 - sinceBeat * 3);
      opacity = 0.35 + beatPulse * 0.6 + Math.sin(phase + tick * 0.05) * 0.2;
      if (beatPulse > 0.5) glow = true;
    }
    opacity = Math.max(0.08, Math.min(1, opacity));
    cellsArr.push({ c: col, o: opacity, g: glow });
  }

  return (
    <div style={{
      height, background: '#000', border: `1px solid ${pt.line}`,
      display: 'flex', padding: compact ? 2 : 4, gap: 1, position: 'relative',
      boxShadow: energyPulse > 0.7 ? `0 0 18px ${theme.accent}66` : 'none',
      transition: 'box-shadow 120ms',
    }}>
      {cellsArr.map((c, i) => (
        <div key={i} style={{
          flex: 1,
          background: c.c,
          opacity: c.o,
          boxShadow: c.g ? `0 0 8px ${c.c}` : 'none',
          transition: 'opacity 60ms linear',
        }}/>
      ))}
      {label && (
        <div style={{
          position: 'absolute', top: 4, right: 6,
          fontFamily: pt.mono, fontSize: 9, color: pt.ink3, letterSpacing: 1,
          pointerEvents: 'none',
        }}>{label}</div>
      )}
      {!playing && (
        <div style={{
          position: 'absolute', top: 4, left: 6,
          fontFamily: pt.mono, fontSize: 9, color: pt.ink3, letterSpacing: 1,
        }}>▸ press play to see lights react</div>
      )}
    </div>
  );
}

// A tiny one-line preview, for use in section cards
function MiniLights({ themeId, kind, beatPulse = 0, width = '100%', height = 28 }) {
  const { theme: pt } = useApp();
  const theme = THEMES_BY_ID[themeId];
  const palette = theme.swatches;
  const N = 28;
  const cells = [];
  for (let i = 0; i < N; i++) {
    const base = palette[i % palette.length];
    let op = 0.45;
    if (kind === 'chorus' && i % 4 === 0) op = 0.9;
    else if (kind === 'intro') op = 0.25 + (i % 3) * 0.15;
    else if (kind === 'solo' && i % 5 === 0) op = 1;
    else op = 0.3 + ((i * 7) % 10) / 14;
    cells.push({ c: base, o: op });
  }
  return (
    <div style={{ width, height, background: '#000', display: 'flex', padding: 2, gap: 1 }}>
      {cells.map((c, i) => <div key={i} style={{ flex: 1, background: c.c, opacity: c.o }}/>)}
    </div>
  );
}

Object.assign(window, { LightsPreview, MiniLights });
