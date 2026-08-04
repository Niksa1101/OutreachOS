//! OutreachOS desktop shell.
//!
//! The application lives in the library rather than the binary so `cargo test`
//! can reach the pure logic — window clamping, log rotation, and (from
//! checkpoint 3 on) the sidecar control-line parser — without standing up a
//! Tauri runtime. Q107.

mod commands;
mod logging;
mod paths;
mod window;

use std::time::Duration;

use uuid::Uuid;

/// How long to wait for `invoke("app_ready")` before showing the window anyway.
///
/// Q77: the watchdog exists because a frontend that crashes before its first
/// paint would otherwise leave an invisible process running with no way to
/// interact with it. The React error boundary also calls `app_ready` on mount,
/// so a *caught* crash reveals the window immediately and this only covers the
/// uncaught case.
const APP_READY_WATCHDOG: Duration = Duration::from_secs(3);

/// Build and run the application. Returns when the last window closes.
pub fn run() {
    // Q75: Rust owns `boot_id` and generates it once per spawn. It is the
    // answer to "did the sidecar silently restart?", so it has to be minted
    // before anything that could restart.
    let boot_id = Uuid::new_v4().to_string();

    // Q57: `--dev` derives from `cfg!(debug_assertions)` and sets the default
    // log level to DEBUG. There is no `--log-level` on the Rust side — that
    // argument is passed *to Python*; Rust's own verbosity follows the build.
    let (log_path, _log_guard) = logging::init(&boot_id, cfg!(debug_assertions));

    tracing::info!(
        boot_id = %boot_id,
        version = env!("CARGO_PKG_VERSION"),
        log = %log_path.display(),
        dev = cfg!(debug_assertions),
        "OutreachOS starting"
    );

    let result = tauri::Builder::default()
        // Q22: a second launch focuses the first and exits. Two processes
        // against one SQLite workspace is a corruption path, and this plugin
        // must be registered first for its handler to intercept the launch.
        .plugin(tauri_plugin_single_instance::init(|app, argv, cwd| {
            tracing::info!(?argv, ?cwd, "second instance rejected; focusing the first");
            window::focus_existing(app);
        }))
        // Q15: window geometry is the plugin's job. Hand-rolled restore gets
        // multi-monitor unplug and offscreen-position cases wrong. Rust clamps
        // what it restores — see `window::reveal`.
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .plugin(tauri_plugin_dialog::init())
        // Q15 again: the *workspace pointer* goes in this store, in its own
        // `workspace.json`. Window state stays with the plugin above.
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_opener::init())
        // Q103: the diagnostics screen's "Copy to clipboard" is the one button
        // that only ever renders when the user is already stuck. A dead button
        // there would be found by a user rather than by us.
        .plugin(tauri_plugin_clipboard_manager::init())
        .invoke_handler(tauri::generate_handler![
            commands::app_ready,
            commands::log_client_error
        ])
        .setup(move |app| {
            let handle = app.handle().clone();

            std::thread::spawn(move || {
                std::thread::sleep(APP_READY_WATCHDOG);
                let watchdog_handle = handle.clone();
                // Window operations are dispatched to the main thread rather
                // than issued from this one. Tauri tolerates either, but the
                // reveal path reads geometry before writing it and that pair
                // should not interleave with the event loop.
                let _ = handle.run_on_main_thread(move || {
                    tracing::debug!("app_ready watchdog expired");
                    window::reveal(&watchdog_handle);
                });
            });

            Ok(())
        })
        .run(tauri::generate_context!());

    if let Err(error) = result {
        tracing::error!(%error, "the application exited with an error");
        // The log guard drops here and flushes. Exiting through a panic would
        // skip that and lose the line that explains why we exited.
        std::process::exit(1);
    }

    tracing::info!(boot_id = %boot_id, "OutreachOS exiting");
}
