// Prevents an additional console window on release builds.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod handshake;

use std::io::{BufRead, BufReader, Write};
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::Mutex;

/// Prevents Windows from allocating a visible console window for the
/// backend sidecar. `backend.exe` is a console-subsystem executable
/// (PyInstaller's `console=True`, so it also works when run directly for
/// debugging), and spawning a console-subsystem child from a
/// windows-subsystem GUI parent otherwise pops up a new (blank -- its
/// stdout/stderr are redirected to our pipes below, not this window's
/// screen buffer) console regardless of the `Stdio::piped()` redirection.
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};

/// Cached backend port; written once the handshake line is parsed on the
/// sidecar's stdout, read by the frontend via `get_backend_port` and also
/// used for graceful shutdown.
struct BackendState {
    port: Mutex<Option<u16>>,
    // We intentionally do NOT retain a reference to the child process here;
    // the Command handle is consumed by the waiter thread, and shutdown is
    // performed via `taskkill /F` against the pid recorded at spawn.
    pid: Mutex<Option<u32>>,
}

impl BackendState {
    fn new() -> Self {
        Self {
            port: Mutex::new(None),
            pid: Mutex::new(None),
        }
    }
}

#[derive(Clone, Serialize)]
struct BackendReadyPayload {
    port: u16,
}

#[derive(Clone, Serialize)]
struct BackendStartupFailedPayload {
    message: String,
}

/// Frontend-callable command: return the cached port, or null if the
/// handshake hasn't completed yet. Exists so a frontend listener that
/// attaches after the event has already fired can still learn the port.
#[tauri::command]
fn get_backend_port(state: State<'_, BackendState>) -> Option<u16> {
    state.port.lock().ok().and_then(|g| *g)
}

/// Return the directory containing backend.log, so the frontend can open
/// it in Explorer for support/diagnostics without needing its own copy of
/// app_support_root()'s path logic.
#[tauri::command]
fn get_log_dir() -> Result<String, String> {
    Ok(app_support_root()?.join("logs").to_string_lossy().to_string())
}

/// Write bytes to an absolute path chosen via the dialog plugin's save().
/// Exists because there is no fs plugin/capability wired up (see
/// capabilities/main.json) -- the frontend fetches file bytes itself
/// (already origin-correct via backendPort.ts) and hands them to this
/// command purely for the disk write, keeping filesystem write access
/// scoped to this one explicit command rather than a blanket fs capability.
#[tauri::command]
fn write_file_bytes(path: String, data: Vec<u8>) -> Result<(), String> {
    std::fs::write(&path, data).map_err(|e| format!("failed to write {path}: {e}"))
}

/// Resolve the backend binary path. Tauri copies the PyInstaller onedir
/// into the resource dir (under `backend/`) per `tauri.conf.json >
/// bundle.resources` — in dev that's `target/debug/backend/`, in release
/// it's `<install-dir>/resources/backend/`. The binary name must match
/// whatever `build-backend.ps1` renamed the PyInstaller output to.
fn backend_binary_path(app: &AppHandle) -> Result<PathBuf, String> {
    let arch = std::env::consts::ARCH;
    let binary_name = format!("backend-{arch}-pc-windows-msvc.exe");
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;
    Ok(resource_dir.join("backend").join(&binary_name))
}

/// Append one line to the shared backend log file, ignoring write errors
/// (a full disk or locked file shouldn't take down the backend reader).
fn write_log_line(log: &std::sync::Arc<Mutex<std::fs::File>>, stream: &str, line: &str) {
    if let Ok(mut file) = log.lock() {
        let _ = writeln!(file, "[{stream}] {}", line.trim_end());
    }
}

/// Spawn the PyInstaller backend and wire up stdout parsing.
fn spawn_backend(app: &AppHandle) -> Result<(), String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;

    let vamp_path = resource_dir.join("vamp");
    let torch_home = app_support_root()?
        .join("models")
        .join("torch-hub");
    std::fs::create_dir_all(torch_home.join("hub").join("checkpoints")).ok();

    let backend_path = backend_binary_path(app)?;

    // Piped stdout/stderr have no console attached in a release build (the
    // GUI-subsystem shell has none of its own either), so without this the
    // backend's own log lines -- including any startup crash -- are
    // discarded entirely. One shared log file makes both readers' output
    // inspectable after the fact.
    let log_path = app_support_root()?.join("logs").join("backend.log");
    if let Some(parent) = log_path.parent() {
        std::fs::create_dir_all(parent).ok();
    }
    let log_file = std::sync::Arc::new(Mutex::new(
        std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .map_err(|e| format!("failed to open log file ({}): {e}", log_path.display()))?,
    ));

    let mut child = Command::new(&backend_path)
        .env("XLIGHT_PACKAGED", "1")
        .env("PYTHONUNBUFFERED", "1")
        // Python defaults piped (non-console) stdout/stderr to the Windows
        // ANSI codepage (cp1252) rather than UTF-8, so any print() containing
        // a Unicode character (e.g. the analyzer's checkmark/x-mark
        // capability status lines) crashes with UnicodeEncodeError. Force
        // UTF-8 regardless of the console's codepage.
        .env("PYTHONIOENCODING", "utf-8")
        .env("VAMP_PATH", vamp_path.to_string_lossy().to_string())
        .env("TORCH_HOME", torch_home.to_string_lossy().to_string())
        // Cap torch/openmp thread count so we don't spike CPU at startup.
        .env("OMP_NUM_THREADS", "4")
        .env("MKL_NUM_THREADS", "4")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
        .map_err(|e| format!("failed to spawn backend ({}): {e}", backend_path.display()))?;

    let pid = child.id();
    if let Ok(mut slot) = app.state::<BackendState>().pid.lock() {
        *slot = Some(pid);
    }

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "backend: no stdout".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "backend: no stderr".to_string())?;

    // Stdout reader: parses the port handshake and passes remaining lines
    // through to our log.
    let stdout_handle = app.clone();
    let stdout_log = log_file.clone();
    std::thread::spawn(move || {
        let reader = BufReader::new(stdout);
        let mut port_announced = false;
        for line in reader.lines() {
            let Ok(line) = line else { break };
            if !port_announced {
                if let Some(port) = handshake::parse_port_line(&line) {
                    port_announced = true;
                    if let Ok(mut slot) = stdout_handle.state::<BackendState>().port.lock() {
                        *slot = Some(port);
                    }
                    let _ = stdout_handle
                        .emit("backend-ready", BackendReadyPayload { port });
                }
            }
            eprintln!("[backend stdout] {}", line.trim_end());
            write_log_line(&stdout_log, "stdout", &line);
        }
    });

    // Stderr reader: pass-through to our log.
    let stderr_log = log_file.clone();
    std::thread::spawn(move || {
        let reader = BufReader::new(stderr);
        for line in reader.lines() {
            if let Ok(line) = line {
                eprintln!("[backend stderr] {}", line.trim_end());
                write_log_line(&stderr_log, "stderr", &line);
            }
        }
    });

    // Waiter: detects backend termination and emits the appropriate event
    // (startup-failed if the port was never announced, backend-lost if the
    // process exited after handshake).
    let wait_handle = app.clone();
    std::thread::spawn(move || {
        let status = child.wait();
        let port = wait_handle
            .state::<BackendState>()
            .port
            .lock()
            .ok()
            .and_then(|g| *g);
        let code = status.as_ref().ok().and_then(|s| s.code());
        let event = if port.is_some() {
            "backend-lost"
        } else {
            "backend-startup-failed"
        };
        let _ = wait_handle.emit(
            event,
            BackendStartupFailedPayload {
                message: format!("Backend process exited (code={code:?})"),
            },
        );
    });

    // Handshake deadline: if the port hasn't been announced within 30s,
    // surface a failure event so the frontend can stop waiting.
    let deadline_handle = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_secs(30));
        let port = deadline_handle
            .state::<BackendState>()
            .port
            .lock()
            .ok()
            .and_then(|g| *g);
        if port.is_none() {
            let _ = deadline_handle.emit(
                "backend-startup-failed",
                BackendStartupFailedPayload {
                    message: "Handshake timed out (30s)".to_string(),
                },
            );
        }
    });

    Ok(())
}

/// Return the user's home directory as a `PathBuf`, via `USERPROFILE`
/// (Windows's actual home-dir env var; `HOME` is not reliably set). Kept as
/// a small helper so tests can mock it without pulling in an external crate.
fn dirs_home() -> Option<std::path::PathBuf> {
    std::env::var_os("USERPROFILE").map(std::path::PathBuf::from)
}

/// Application Support root, matching
/// `src/packaging/platform_paths.py::app_support_root()` exactly:
/// `%LOCALAPPDATA%\XLight` (falling back to `<home>/AppData/Local/XLight`
/// if the env var is unset).
fn app_support_root() -> Result<PathBuf, String> {
    let local = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .or_else(|| dirs_home().map(|h| h.join("AppData").join("Local")))
        .ok_or_else(|| "no LOCALAPPDATA or home dir".to_string())?;
    Ok(local.join("XLight"))
}

/// Best-effort: terminate the backend pid we recorded at spawn via
/// `taskkill` (avoids pulling in a Windows-API crate just for
/// `TerminateProcess`).
fn terminate_sidecar(pid: u32) {
    let _ = Command::new("taskkill")
        .args(["/PID", &pid.to_string(), "/F"])
        .status();
}

fn main() {
    tauri::Builder::default()
        .plugin(
            tauri_plugin_single_instance::init(|app, _argv, _cwd| {
                // Focus the existing window instead of starting a second
                // instance (covers spec Edge Case: multiple instances).
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.set_focus();
                    let _ = window.show();
                }
            }),
        )
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendState::new())
        .invoke_handler(tauri::generate_handler![get_backend_port, write_file_bytes, get_log_dir])
        .setup(|app| {
            if let Err(err) = spawn_backend(&app.handle()) {
                eprintln!("spawn_backend failed: {err}");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<BackendState>() {
                    if let Ok(guard) = state.pid.lock() {
                        if let Some(pid) = *guard {
                            terminate_sidecar(pid);
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
