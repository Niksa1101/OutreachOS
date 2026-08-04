//! The `invoke` surface.
//!
//! Kept deliberately small. Tech.md §2: Rust is a shell, not a third
//! business-logic layer — anything that could be an HTTP call to the sidecar
//! should be one. A command earns its place here only when it must work while
//! the sidecar is dead or has never existed.

use std::sync::Arc;

use serde::Deserialize;
use tauri::{AppHandle, State};

use crate::boot::{BackendInfo, BootMachine, BootState};
use crate::logging::CLIENT_TARGET;
use crate::window;

/// Q54: React calls this after the boot UI's first paint and Rust shows the
/// window. Racing it is the watchdog in `lib.rs`; whichever arrives first wins.
#[tauri::command]
pub fn app_ready(app: AppHandle) {
    tracing::debug!("frontend reported ready");
    window::reveal(&app);
}

/// A frontend error captured before there is a backend to POST it to.
#[derive(Debug, Deserialize)]
pub struct ClientError {
    pub message: String,
    /// Which capture point produced it: `window.onerror`,
    /// `unhandledrejection`, or the React error boundary. Knowing this
    /// separates "a render threw" from "a promise was dropped", which need
    /// different things looked at.
    pub source: String,
    pub stack: Option<String>,
    /// The route at the time, when the router is already mounted.
    pub route: Option<String>,
}

/// Q54: called once on mount, so React starts from the same snapshot type the
/// `boot://state` event delivers. One reducer, one shape, no reconciliation
/// between an initial fetch and a stream.
#[tauri::command]
pub fn get_boot_state(machine: State<'_, Arc<BootMachine>>) -> BootState {
    machine.snapshot()
}

/// Q9: how the frontend learns the port and the shared secret.
///
/// A command rather than a field on the boot state, deliberately. The state is
/// broadcast to every listener; this is pulled once, into a module-scoped
/// binding in `core/api` that is never exported (Q56).
///
/// `None` while there is no live backend — the caller is expected to be in the
/// ready phase, and a `null` here means it raced a restart.
#[tauri::command]
pub fn get_backend_info(machine: State<'_, Arc<BootMachine>>) -> Option<BackendInfo> {
    machine.backend_info()
}

/// Re-run the entire boot sequence: new spawn, new token, new `boot_id`.
///
/// Q78 — which is exactly why the frontend must clear the query cache before
/// returning to the remembered route on success.
#[tauri::command]
pub fn retry_boot(machine: State<'_, Arc<BootMachine>>) {
    tracing::info!("retry requested");
    machine.start();
}

/// Q64: the pre-ready half of frontend error ingestion.
///
/// Errors thrown during boot — on the workspace picker, on the diagnostics
/// screen — have no backend to reach, so they land in `boot.log` tagged
/// `[client]` instead. The post-ready half is `POST /api/v1/client-logs`.
///
/// The loop guard Q64 asks for lives on the frontend, where the re-entry
/// actually happens: this command cannot fail in a way that raises back into
/// the reporter.
#[tauri::command]
pub fn log_client_error(error: ClientError) {
    tracing::error!(
        target: CLIENT_TARGET,
        source = %error.source,
        route = error.route.as_deref().unwrap_or("-"),
        stack = error.stack.as_deref().unwrap_or("-"),
        "{}",
        error.message
    );
}
