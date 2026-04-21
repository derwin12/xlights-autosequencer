// Shared state, theme palettes, helpers, tweak mode.
// All components read from and mutate `window.useAppState` hook.

const THEMES = [
  { id: 'quiet',   name: 'quiet',         desc: 'soft fades · long dwells',       swatches: ['#2f2f3a','#4a4a5a','#7a7a90','#b8b8c8'],  accent: '#7a7a90', tags: ['ambient','slow'] },
  { id: 'driving', name: 'driving pulse', desc: 'beat-synced · warm amber',       swatches: ['#3a1408','#8a2a12','#d97757','#f5b97a'],  accent: '#d97757', tags: ['on-beat','warm'] },
  { id: 'punchy',  name: 'punchy',        desc: 'hits on kicks · high contrast',  swatches: ['#0a0a0a','#d43a2f','#f5a623','#fff48a'],  accent: '#d43a2f', tags: ['kicks','contrast'] },
  { id: 'bright',  name: 'bright',        desc: 'major-key lift · full spectrum', swatches: ['#2f5ad4','#2f8f3e','#f5a623','#f5d5e3'],  accent: '#f5a623', tags: ['solos','lift'] },
  { id: 'storm',   name: 'storm',         desc: 'blues + whites · stabbing',      swatches: ['#0a0a1a','#1e3a8a','#4aa8ff','#ffffff'],  accent: '#4aa8ff', tags: ['solos','high-energy'] },
  { id: 'ember',   name: 'ember',         desc: 'red/orange simmer',              swatches: ['#1a0606','#4a1408','#a63a23','#e87a3a'],  accent: '#e87a3a', tags: ['warm','slow'] },
];
const THEMES_BY_ID = Object.fromEntries(THEMES.map(t => [t.id, t]));

const ALGOS = [
  { id: 'beats',   name: 'beats · librosa',     color: '#d43a2f', on: true  },
  { id: 'bars',    name: 'bars · qm_bars',      color: '#2f5ad4', on: true  },
  { id: 'onsets',  name: 'onsets · librosa',    color: '#2f8f3e', on: false },
  { id: 'chord',   name: 'chords · chordino',   color: '#a74cc7', on: false },
  { id: 'kick',    name: 'impacts · energy',    color: '#e87a3a', on: true  },
  { id: 'drop',    name: 'drops · energy',      color: '#4aa8ff', on: true  },
  { id: 'bass',    name: 'bass · stem onsets',  color: '#8f6b2a', on: false },
  { id: 'voc',     name: 'vocals · phonemes',   color: '#f5a623', on: false },
];

// ------------------------------- theme palette -------------------------------
const PALETTE = {
  dark: {
    bg0: '#111114',
    bg1: '#1a1a20',
    bg2: '#22222a',
    bg3: '#2a2a33',
    bg4: '#33333e',
    line: '#2a2a33',
    line2: '#3a3a46',
    ink: '#f5f5f0',
    ink2: '#a8a8b0',
    ink3: '#6a6a78',
    accent: '#d97757',
    accentInk: '#000',
    ok: '#4ade80',
    warn: '#f5a623',
    err: '#d43a2f',
    mono: "'JetBrains Mono', ui-monospace, monospace",
    sans: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  },
  light: {
    bg0: '#f4f4ef',
    bg1: '#ffffff',
    bg2: '#ececec',
    bg3: '#dcdcd4',
    bg4: '#cac8bf',
    line: '#dcdcd4',
    line2: '#c4c4bc',
    ink: '#1a1a20',
    ink2: '#555560',
    ink3: '#8a8a90',
    accent: '#d97757',
    accentInk: '#fff',
    ok: '#2f8f3e',
    warn: '#b8881a',
    err: '#c42818',
    mono: "'JetBrains Mono', ui-monospace, monospace",
    sans: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
  },
};

// ------------------------------- app state -----------------------------------
function useAppStateImpl() {
  // navigation
  const [screen, setScreen] = React.useState(
    () => localStorage.getItem('xo.screen') || 'theme'
  );
  React.useEffect(() => { localStorage.setItem('xo.screen', screen); }, [screen]);

  // editable sections — persist user edits, allow reset to detected
  const detectedSections = React.useMemo(() =>
    window.HIGHWAY.sections.map((s, i) => ({
      ...s, id: `det-${i}`, conf: 0.5 + ((i * 13) % 40) / 100,
    })), []);
  const [sections, setSectionsRaw] = React.useState(() => {
    const saved = localStorage.getItem('xo.sections');
    if (saved) { try { return JSON.parse(saved); } catch {} }
    return detectedSections;
  });
  const setSections = (next) => {
    const s = typeof next === 'function' ? next(sections) : next;
    setSectionsRaw(s);
    localStorage.setItem('xo.sections', JSON.stringify(s));
  };
  const resetSections = () => setSections(detectedSections);

  // Alternate (ghost) boundaries the analyzer found but aren't used
  const altBoundaries = React.useMemo(() => [
    { t: 22.5,  conf: 0.42, kind: 'verse' },
    { t: 38.2,  conf: 0.51, kind: 'verse' },
    { t: 88.7,  conf: 0.38, kind: 'verse' },
    { t: 140.0, conf: 0.61, kind: 'solo' },
    { t: 173.2, conf: 0.48, kind: 'chorus' },
    { t: 201.8, conf: 0.55, kind: 'outro' },
  ], []);

  const updateSection = (idx, patch) =>
    setSections(prev => prev.map((s, i) => i === idx ? { ...s, ...patch } : s));
  const splitSection = (idx, atT) =>
    setSections(prev => {
      const s = prev[idx];
      if (atT <= s.start + 0.5 || atT >= s.end - 0.5) return prev;
      const a = { ...s, end: atT, id: s.id + 'a' };
      const b = { ...s, start: atT, id: s.id + 'b', label: s.label + ' (b)' };
      return [...prev.slice(0, idx), a, b, ...prev.slice(idx + 1)];
    });
  const mergeWithNext = (idx) =>
    setSections(prev => {
      if (idx >= prev.length - 1) return prev;
      const a = prev[idx], b = prev[idx + 1];
      const merged = { ...a, end: b.end };
      return [...prev.slice(0, idx), merged, ...prev.slice(idx + 2)];
    });
  const deleteSection = (idx) =>
    setSections(prev => {
      if (prev.length <= 1) return prev;
      if (idx === 0) return [{ ...prev[1], start: prev[0].start }, ...prev.slice(2)];
      const a = prev[idx - 1], b = prev[idx];
      return [...prev.slice(0, idx - 1), { ...a, end: b.end }, ...prev.slice(idx + 1)];
    });
  const promoteAlt = (t) =>
    setSections(prev => {
      const idx = prev.findIndex(s => t > s.start && t < s.end);
      if (idx < 0) return prev;
      const s = prev[idx];
      const a = { ...s, end: t, id: s.id + 'a' };
      const b = { ...s, start: t, id: s.id + 'b', label: s.label + ' (b)' };
      return [...prev.slice(0, idx), a, b, ...prev.slice(idx + 1)];
    });

  // section theme assignments keyed by section id (so survives edits)
  const [sectionThemesById, setSectionThemesById] = React.useState(() => {
    const saved = localStorage.getItem('xo.sectionThemesById');
    if (saved) { try { return JSON.parse(saved); } catch {} }
    const m = {}; detectedSections.forEach(s => { m[s.id] = s.defaultTheme; });
    return m;
  });
  React.useEffect(() => {
    localStorage.setItem('xo.sectionThemesById', JSON.stringify(sectionThemesById));
  }, [sectionThemesById]);
  const sectionThemes = sections.map(s => sectionThemesById[s.id] || s.defaultTheme || 'driving');
  const setSectionTheme = (idx, themeId) => {
    const id = sections[idx].id;
    setSectionThemesById(prev => ({ ...prev, [id]: themeId }));
  };

  // Sections edit mode
  const [sectionsMode, setSectionsMode] = React.useState(false);

  // selected section
  const [selectedSection, setSelectedSection] = React.useState(2); // chorus 1

  // playback
  const audioRef = React.useRef(null);
  if (!audioRef.current && typeof Audio !== 'undefined') {
    const a = new Audio('assets/highway.mp3');
    a.preload = 'auto';
    a.volume = 0.7;
    audioRef.current = a;
  }
  const [playing, setPlaying] = React.useState(false);
  const [time, setTime] = React.useState(() => {
    const s = parseFloat(localStorage.getItem('xo.time'));
    return isFinite(s) ? s : 52.4;
  });
  // RAF-driven updates when playing; also handle manual scrub
  React.useEffect(() => {
    const a = audioRef.current; if (!a) return;
    let rafId = 0;
    const tick = () => {
      setTime(a.currentTime);
      rafId = requestAnimationFrame(tick);
    };
    if (playing) {
      a.currentTime = time;
      a.play().catch(() => setPlaying(false));
      rafId = requestAnimationFrame(tick);
    } else {
      a.pause();
    }
    return () => cancelAnimationFrame(rafId);
    // eslint-disable-next-line
  }, [playing]);
  // persist time occasionally
  React.useEffect(() => {
    const id = setInterval(() => {
      localStorage.setItem('xo.time', String(time));
    }, 500);
    return () => clearInterval(id);
  }, [time]);

  const seekTo = (t) => {
    const clamped = Math.max(0, Math.min(window.HIGHWAY.duration, t));
    setTime(clamped);
    if (audioRef.current) audioRef.current.currentTime = clamped;
  };
  const togglePlay = () => setPlaying(p => !p);

  // Algorithm tracks on/off
  const [algoStates, setAlgoStates] = React.useState(() => {
    const map = {};
    ALGOS.forEach(a => map[a.id] = a.on);
    return map;
  });
  const toggleAlgo = (id) => setAlgoStates(prev => ({ ...prev, [id]: !prev[id] }));

  // tweaks
  const [mode, setMode] = React.useState('dark'); // 'dark' | 'light'
  const [density, setDensity] = React.useState('compact'); // 'compact' | 'comfortable'
  const [inspectorOpen, setInspectorOpen] = React.useState(true);
  const [tweaksOpen, setTweaksOpen] = React.useState(false);

  // derived: current section index from time (uses editable sections)
  const curSectionIdx = React.useMemo(() => {
    for (let i = 0; i < sections.length; i++) {
      if (time >= sections[i].start && time < sections[i].end) return i;
    }
    return sections.length - 1;
  }, [time, sections]);

  // derived: current bar / beat
  const curBeat = React.useMemo(() => {
    const beats = window.HIGHWAY.beats;
    let idx = 0;
    for (let i = 0; i < beats.length; i++) {
      if (beats[i].t <= time) idx = i; else break;
    }
    return beats[idx];
  }, [time]);

  // derived: "energy" at this moment (for animation pulse)
  const [energyPulse, setEnergyPulse] = React.useState(0);
  React.useEffect(() => {
    if (!playing) { setEnergyPulse(0); return; }
    let rafId = 0;
    let lastBeatT = -1;
    const tick = () => {
      const t = audioRef.current ? audioRef.current.currentTime : time;
      const beats = window.HIGHWAY.beats;
      let hit = null;
      for (let i = 0; i < beats.length; i++) {
        if (beats[i].t > t) break;
        if (beats[i].t > lastBeatT && (t - beats[i].t) < 0.3) hit = beats[i];
      }
      if (hit && hit.t !== lastBeatT) { lastBeatT = hit.t; setEnergyPulse(1); }
      else setEnergyPulse(e => Math.max(0, e - 0.08));
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [playing]);

  const theme = PALETTE[mode];

  return {
    screen, setScreen,
    sections, detectedSections, altBoundaries,
    updateSection, splitSection, mergeWithNext, deleteSection, promoteAlt, resetSections,
    sectionsMode, setSectionsMode,
    sectionThemes, setSectionTheme,
    selectedSection, setSelectedSection,
    playing, togglePlay, time, seekTo,
    algoStates, toggleAlgo,
    mode, setMode, density, setDensity,
    inspectorOpen, setInspectorOpen,
    tweaksOpen, setTweaksOpen,
    curSectionIdx, curBeat,
    energyPulse,
    theme,
  };
}

// Context so every component can read state without prop drilling
const AppCtx = React.createContext(null);
const useApp = () => React.useContext(AppCtx);
function AppProvider({ children }) {
  const v = useAppStateImpl();
  return <AppCtx.Provider value={v}>{children}</AppCtx.Provider>;
}

// ------------------------------- helpers -------------------------------
const fmt = {
  time: (t) => {
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    const ms = Math.floor((t % 1) * 1000);
    return `${String(m).padStart(1,'0')}:${String(s).padStart(2,'0')}.${String(ms).padStart(3,'0')}`;
  },
  timeShort: (t) => {
    const m = Math.floor(t / 60);
    const s = Math.floor(t % 60);
    return `${m}:${String(s).padStart(2,'0')}`;
  },
};

// stable waveform (like shared.jsx) — precomputed once
function makeWaveform(n = 520) {
  const arr = new Array(n);
  const secs = window.HIGHWAY.sections;
  let seed = 4242;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  for (let i = 0; i < n; i++) {
    const t = (i / n) * window.HIGHWAY.duration;
    // find section for energy hint
    const sec = secs.find(s => t >= s.start && t < s.end) || secs[0];
    let base = 0.2;
    if (sec.kind === 'chorus') base = 0.6;
    else if (sec.kind === 'solo') base = 0.55;
    else if (sec.kind === 'verse') base = 0.35;
    else if (sec.kind === 'bridge') base = 0.3;
    else if (sec.kind === 'intro') base = 0.15;
    else if (sec.kind === 'outro') base = 0.5;
    const env = base + 0.18 * Math.sin(t * 1.3);
    const detail = (rnd() - 0.5) * 0.55;
    arr[i] = Math.max(0.05, Math.min(1, env + detail * env));
  }
  return arr;
}
const WAVE = makeWaveform();

Object.assign(window, {
  THEMES, THEMES_BY_ID, ALGOS, PALETTE, AppProvider, useApp, fmt, WAVE,
});
