use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct BackendProcess(Mutex<Option<CommandChild>>);

fn log_path() -> PathBuf {
    #[cfg(windows)]
    {
        let base = std::env::var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir());
        base.join("vector-ui").join("backend.log")
    }
    #[cfg(not(windows))]
    {
        std::env::temp_dir().join("vector_backend.log")
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_millis(500));
                spawn_python_backend(&handle);
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(child) = window
                    .app_handle()
                    .state::<BackendProcess>()
                    .0
                    .lock()
                    .unwrap()
                    .take()
                {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn spawn_python_backend(app: &AppHandle) {
    let log = log_path();
    if let Some(dir) = log.parent() {
        let _ = std::fs::create_dir_all(dir);
    }

    let cmd = match app.shell().sidecar("vector-backend") {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[VECTOR] Sidecar 'vector-backend' not found: {}", e);
            let _ = app.emit("backend-error", "sidecar not found".to_string());
            return;
        }
    };

    let (mut rx, child) = match cmd.spawn() {
        Ok(pair) => pair,
        Err(e) => {
            eprintln!("[VECTOR] Failed to spawn sidecar: {}", e);
            let _ = app.emit("backend-error", e.to_string());
            return;
        }
    };

    eprintln!("[VECTOR] Sidecar started (PID {})", child.pid());
    *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);

    // Pipe sidecar stdout/stderr to the log file.
    tauri::async_runtime::spawn(async move {
        let mut log_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log)
            .ok();

        while let Some(event) = rx.recv().await {
            let line = match event {
                CommandEvent::Stdout(b) => {
                    format!("[OUT] {}\n", String::from_utf8_lossy(&b))
                }
                CommandEvent::Stderr(b) => {
                    format!("[ERR] {}\n", String::from_utf8_lossy(&b))
                }
                CommandEvent::Error(e) => format!("[ERR] {}\n", e),
                CommandEvent::Terminated(s) => {
                    format!("[EXIT] code={:?}\n", s.code)
                }
                _ => continue,
            };
            if let Some(f) = &mut log_file {
                let _ = f.write_all(line.as_bytes());
            }
        }
    });
}
