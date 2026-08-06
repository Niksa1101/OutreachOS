//! OutreachOS desktop shell.
//!
//! The application lives in the library rather than the binary so `cargo test`
//! can reach the pure logic — window clamping, log rotation, and (from
//! checkpoint 3 on) the sidecar control-line parser — without standing up a
//! Tauri runtime. Q107.

mod boot;
mod commands;
mod diagnostics;
mod logging;
mod paths;
mod pointer;
mod sidecar;
mod window;
mod workspace;

use std::sync::Arc;
use std::time::Duration;

use tauri::{Manager, RunEvent};
use uuid::Uuid;

use crate::boot::BootMachine;

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
    // Identifies this *launch* in the boot log's per-run separator (Q119).
    //
    // Not to be confused with the sidecar's `boot_id`, which Q75 mints per
    // *spawn* — Retry produces a new one without starting a new launch, so the
    // two cannot be the same value. Each spawn logs its own id, so a line in
    // boot.log can be tied to both.
    let launch_id = Uuid::new_v4().to_string();

    // Q57: `--dev` derives from `cfg!(debug_assertions)` and sets the default
    // log level to DEBUG. There is no `--log-level` on the Rust side — that
    // argument is passed *to Python*; Rust's own verbosity follows the build.
    let (log_path, _log_guard) = logging::init(&launch_id, cfg!(debug_assertions));

    tracing::info!(
        launch_id = %launch_id,
        version = env!("CARGO_PKG_VERSION"),
        log = %log_path.display(),
        dev = cfg!(debug_assertions),
        "OutreachOS starting"
    );

    let built = tauri::Builder::default()
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
            commands::get_boot_state,
            commands::get_backend_info,
            commands::retry_boot,
            commands::take_over_workspace,
            commands::proceed_without_backup,
            commands::validate_workspace,
            commands::set_workspace,
            commands::forget_workspace,
            commands::read_log_tail,
            commands::open_logs_folder,
            commands::log_client_error,
            commands::allow_media_path
        ])
        .setup(move |app| {
            let handle = app.handle().clone();

            // Q54: Rust owns the boot state machine. It is started here rather
            // than lazily on first invoke, so the sidecar handshake overlaps
            // the webview's own startup instead of following it.
            let machine = Arc::new(BootMachine::new(handle.clone()));
            app.manage(Arc::clone(&machine));
            machine.start();

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
        .build(tauri::generate_context!());

    let app = match built {
        Ok(app) => app,
        Err(error) => {
            tracing::error!(%error, "the application failed to start");
            // Returning rather than panicking: the log guard drops on the way
            // out and flushes the line that explains why.
            return;
        }
    };

    app.run(move |handle, event| {
        if matches!(event, RunEvent::Exit) {
            // Q38's Job Object would kill the sidecar regardless, but only
            // abruptly. Going through stdin EOF gives Python the shutdown
            // sequence in Q118 — release the SSE streams, stop uvicorn, remove
            // `.oos-lock`, flush the log — which is what stops the *next*
            // launch from finding a stale lock it has to reason about.
            if let Some(machine) = handle.try_state::<Arc<BootMachine>>() {
                tracing::info!("shutting down");
                machine.shutdown();
            }
        }
    });

    tracing::info!(launch_id = %launch_id, "OutreachOS exiting");
}
