use std::fs::OpenOptions;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager};

struct BackendProcess(Mutex<Option<Child>>);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
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
                if let Some(mut child) = window
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

fn log_path() -> PathBuf {
    if cfg!(windows) {
        PathBuf::from(r"C:\Users\zowel\AppData\Local\vector-ui\vector_backend.log")
    } else {
        std::env::temp_dir().join("vector_backend.log")
    }
}

fn spawn_python_backend(app: &AppHandle) {
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
            eprintln!("[VECTOR] main.py not found — searched resource_dir and exe ancestors");
            let _ = app.emit("backend-error", "main.py not found".to_string());
            return;
        }
    };

    let cwd = script_path.parent().unwrap().to_path_buf();
    let log = log_path();

    eprintln!("[VECTOR] script_path = {}", script_path.display());
    eprintln!("[VECTOR] cwd         = {}", cwd.display());
    eprintln!("[VECTOR] log_file    = {}", log.display());

    if let Some(dir) = log.parent() {
        let _ = std::fs::create_dir_all(dir);
    }

    // On Windows try "python" first (standard install), then "python3" (MS Store alias).
    // On Unix prefer "python3" then fall back to "python".
    let candidates: &[&str] = if cfg!(windows) {
        &["python", "python3"]
    } else {
        &["python3", "python"]
    };

    for &exe_name in candidates {
        eprintln!("[VECTOR] Trying: {} main.py  (cwd: {})", exe_name, cwd.display());

        // Re-open log each attempt so we get fresh file handles for stdout + stderr.
        let stdout_file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log)
            .ok();
        let stderr_file = stdout_file.as_ref().and_then(|f| f.try_clone().ok());

        let mut cmd = Command::new(exe_name);
        cmd.arg("main.py").current_dir(&cwd);

        match stdout_file {
            Some(f) => { cmd.stdout(f); }
            None    => { cmd.stdout(Stdio::null()); }
        }
        match stderr_file {
            Some(f) => { cmd.stderr(f); }
            None    => { cmd.stderr(Stdio::null()); }
        }

        match cmd.spawn() {
            Ok(child) => {
                eprintln!("[VECTOR] Backend started with '{}' (PID {})", exe_name, child.id());
                *app.state::<BackendProcess>().0.lock().unwrap() = Some(child);
                return;
            }
            Err(e) => {
                eprintln!("[VECTOR] '{}' failed: {}", exe_name, e);
            }
        }
    }

    eprintln!("[VECTOR] All Python executables failed — backend not started");
    let _ = app.emit("backend-error", "Python executable not found".to_string());
}
