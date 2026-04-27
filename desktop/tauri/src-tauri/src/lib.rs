use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{AppHandle, Manager};
use tauri_plugin_shell::ShellExt;

struct BackendProcess(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendProcess(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle().clone();
            // Run in a background thread so the window can open first,
            // giving the frontend time to mount and register event listeners.
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

// Walk up the directory tree from the exe until main.py is found.
// In dev builds the exe lives deep inside target/debug/; in production
// the user is expected to place main.py next to the exe.
fn find_script() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let mut dir = exe.parent()?;
    loop {
        let candidate = dir.join("main.py");
        if candidate.exists() {
            return Some(candidate);
        }
        dir = dir.parent()?;
    }
}

fn spawn_python_backend(app: &AppHandle) {
    // 1. Prefer bundled resource (production bundle)
    // 2. Fall back to walking up from the exe (dev + portable installs)
    let script_path = app
        .path()
        .resource_dir()
        .ok()
        .map(|d| d.join("main.py"))
        .filter(|p| p.exists())
        .or_else(find_script);

    let script_path = match script_path {
        Some(p) => p,
        None => {
            eprintln!("[VECTOR] main.py not found");
            let _ = app.emit("backend-error", "main.py not found".to_string());
            return;
        }
    };

    // Run from main.py's directory so relative imports resolve correctly.
    let cwd = script_path.parent().unwrap().to_path_buf();
    let python = if cfg!(windows) { "python" } else { "python3" };

    match app
        .shell()
        .command(python)
        .args(["main.py"])
        .current_dir(&cwd)
        .spawn()
    {
        Ok((_rx, child)) => {
            *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);
        }
        Err(e) => {
            eprintln!("[VECTOR] Backend launch failed: {e}");
            let _ = app.emit("backend-error", e.to_string());
        }
    }
}
