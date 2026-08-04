//! The `invoke` surface.
//!
//! Kept deliberately small. Tech.md §2: Rust is a shell, not a third
//! business-logic layer — anything that could be an HTTP call to the sidecar
//! should be one. A command earns its place here only when it must work while
//! the sidecar is dead or has never existed.

use serde::Deserialize;
use tauri::AppHandle;

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
