// App entry: mount, route to screen, keyboard shortcuts.
const {
  AppProvider, useApp,
  ThemePicker, ReviewTimeline,
  LibraryScreen, DropScreen, AnalyzeScreenV2, ExportScreenV2,
  SCREENS,
} = window;

function Router() {
  const app = useApp();
  // Keyboard
  React.useEffect(() => {
    const onKey = (e) => {
      // don't interfere with text inputs
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      if (e.key === 'Escape' && app.sectionsMode) { app.setSectionsMode(false); return; }
      if (e.code === 'Space') { e.preventDefault(); app.togglePlay(); return; }
      if (e.key === 'ArrowLeft') {
        if (e.shiftKey) {
          // jump to prev section
          const secs = app.sections;
          for (let i = secs.length - 1; i >= 0; i--) {
            if (secs[i].start < app.time - 0.5) { app.seekTo(secs[i].start); return; }
          }
          app.seekTo(0);
        } else app.seekTo(app.time - 1);
        return;
      }
      if (e.key === 'ArrowRight') {
        if (e.shiftKey) {
          const secs = app.sections;
          for (let i = 0; i < secs.length; i++) {
            if (secs[i].start > app.time + 0.5) { app.seekTo(secs[i].start); return; }
          }
        } else app.seekTo(app.time + 1);
        return;
      }
      // number keys switch screens
      const n = parseInt(e.key);
      if (n >= 1 && n <= SCREENS.length) {
        app.setScreen(SCREENS[n - 1].id);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [app.time, app.togglePlay]);

  switch (app.screen) {
    case 'library':  return <LibraryScreen/>;
    case 'drop':     return <DropScreen/>;
    case 'analyze':  return <AnalyzeScreenV2/>;
    case 'theme':    return <ThemePicker/>;
    case 'timeline': return <ReviewTimeline/>;
    case 'export':   return <ExportScreenV2/>;
    default:         return <ThemePicker/>;
  }
}

function App() {
  return <AppProvider><Router/></AppProvider>;
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
