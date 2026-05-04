use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct BackendProcess(Mutex<Option<CommandChild>>);

// ---------------------------------------------------------------------------
// Config helpers
// ---------------------------------------------------------------------------

fn config_path() -> PathBuf {
    #[cfg(windows)]
    {
        let base = std::env::var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir());
        base.join("JARVIS").join("config.json")
    }
    #[cfg(not(windows))]
    {
        let home = std::env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir());
        home.join(".jarvis").join("config.json")
    }
}

fn log_path() -> PathBuf {
    #[cfg(windows)]
    {
        let base = std::env::var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir());
        base.join("JARVIS").join("backend.log")
    }
    #[cfg(not(windows))]
    {
        std::env::temp_dir().join("vector_backend.log")
    }
}

fn read_config() -> serde_json::Value {
    let path = config_path();
    std::fs::read_to_string(&path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or(serde_json::json!({}))
}

fn write_config(data: &serde_json::Value) -> Result<(), String> {
    let path = config_path();
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
    }
    let text = serde_json::to_string_pretty(data).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| e.to_string())
}

fn load_api_key() -> Option<String> {
    let cfg = read_config();
    cfg["gemini_api_key"]
        .as_str()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[tauri::command]
fn has_api_key() -> bool {
    load_api_key().is_some()
}

#[tauri::command]
fn save_api_key(key: String) -> Result<(), String> {
    let key = key.trim().to_string();
    if key.is_empty() {
        return Err("API key cannot be empty".to_string());
    }
    let mut cfg = read_config();
    cfg["gemini_api_key"] = serde_json::Value::String(key);
    write_config(&cfg)
}

// Called by the frontend once the API key is confirmed to be present.
#[tauri::command]
fn start_backend(app: AppHandle) {
    // Kill any previously running instance first.
    if let Some(child) = app.state::<BackendProcess>().0.lock().unwrap().take() {
        let _ = child.kill();
    }
    std::thread::spawn(move || {
        spawn_python_backend(&app);
    });
}

// ---------------------------------------------------------------------------
// App entry
// ---------------------------------------------------------------------------

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![has_api_key, save_api_key, start_backend])
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

// ---------------------------------------------------------------------------
// Sidecar
// ---------------------------------------------------------------------------

fn spawn_python_backend(app: &AppHandle) {
    let log = log_path();
    if let Some(dir) = log.parent() {
        let _ = std::fs::create_dir_all(dir);
    }

    let mut cmd = match app.shell().sidecar("vector-backend") {
        Ok(c) => c,
        Err(e) => {
            eprintln!("[JARVIS] Sidecar 'vector-backend' not found: {}", e);
            let _ = app.emit("backend-error", "sidecar not found".to_string());
            return;
        }
    };

    // Inject GEMINI_API_KEY from config into the sidecar environment.
    if let Some(key) = load_api_key() {
        cmd = cmd.env("GEMINI_API_KEY", key);
    }

    let (mut rx, child) = match cmd.spawn() {
        Ok(pair) => pair,
        Err(e) => {
            eprintln!("[JARVIS] Failed to spawn sidecar: {}", e);
            let _ = app.emit("backend-error", e.to_string());
            return;
        }
    };

    eprintln!("[JARVIS] Sidecar started (PID {})", child.pid());
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
