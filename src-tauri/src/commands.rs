//! The `invoke` surface.
//!
//! Kept deliberately small. Tech.md §2: Rust is a shell, not a third
//! business-logic layer — anything that could be an HTTP call to the sidecar
//! should be one. A command earns its place here only when it must work while
//! the sidecar is dead or has never existed.

use std::path::{Path, PathBuf};
use std::sync::Arc;

use serde::Deserialize;
use tauri::{AppHandle, State};

use crate::boot::{BackendInfo, BootMachine, BootState, SpawnFlags};
use crate::logging::CLIENT_TARGET;
use crate::workspace::WorkspaceValidation;
use crate::{paths, pointer, window, workspace};

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
    machine.set_spawn_flags(SpawnFlags::default());
    machine.start();
}

/// Claim a workspace lock held by another instance (Q83).
#[tauri::command]
pub fn take_over_workspace(machine: State<'_, Arc<BootMachine>>) {
    tracing::info!("take over requested");
    machine.set_spawn_flags(SpawnFlags {
        take_over: true,
        ..SpawnFlags::default()
    });
    machine.start();
}

/// Retry migration without a pre-migration backup (Q85).
#[tauri::command]
pub fn proceed_without_backup(machine: State<'_, Arc<BootMachine>>) {
    tracing::info!("proceed without backup requested");
    machine.set_spawn_flags(SpawnFlags {
        allow_without_backup: true,
        ..SpawnFlags::default()
    });
    machine.start();
}

/* -------------------------------------------------------------------------- */
/* Workspace                                                                   */
/* -------------------------------------------------------------------------- */

/// Q13: validation is a Rust command, not an API call.
///
/// It has to be — the picker runs when there is no workspace, and Q13's
/// invariant is that no workspace means no sidecar. There is nothing to ask.
#[tauri::command]
pub fn validate_workspace(path: String) -> WorkspaceValidation {
    workspace::validate(Path::new(&path))
}

/// Validate, store, and re-run the boot sequence.
///
/// Returns the validation either way, so the picker can render the rejection
/// itself rather than parsing a message out of an error string. Nothing is
/// stored unless it passes — a stored path that fails validation is exactly
/// the boot loop Q40 added "Forget this workspace" to escape.
#[tauri::command]
pub fn set_workspace(
    app: AppHandle,
    machine: State<'_, Arc<BootMachine>>,
    path: String,
) -> Result<WorkspaceValidation, String> {
    let validation = workspace::validate(Path::new(&path));

    if !validation.is_acceptable() {
        return Ok(validation);
    }

    // Q80: the *canonical* form is stored, never what the picker handed us.
    pointer::write(&app, &validation.path)?;
    machine.start();

    Ok(validation)
}

/// Q40: "Forget this workspace".
///
/// The escape hatch from a pointer that no longer resolves. Without it, that
/// state is a permanent boot loop into diagnostics whose only exit is editing
/// app-data by hand.
#[tauri::command]
pub fn forget_workspace(
    app: AppHandle,
    machine: State<'_, Arc<BootMachine>>,
) -> Result<(), String> {
    pointer::clear(&app)?;
    // Re-running the machine with no pointer lands in `AwaitingWorkspace`,
    // which routes to the picker. No separate "go to setup" path to keep in
    // step with the guard.
    machine.start();
    Ok(())
}

/* -------------------------------------------------------------------------- */
/* Diagnostics                                                                 */
/* -------------------------------------------------------------------------- */

/// Which log to read. Q87 and the locked assumptions: a **discriminant, never
/// a path**.
///
/// Path traversal is impossible by construction rather than prevented by
/// validation — there is no user-supplied string to sanitise, so there is no
/// sanitiser to get wrong.
#[derive(Debug, Clone, Copy, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogTarget {
    /// `%LOCALAPPDATA%\OutreachOS\logs\boot.log` — Rust and pre-ready client
    /// errors.
    Boot,
    /// `<workspace>\logs\outreachos.log` — Python.
    Backend,
}

/// How much of the log the diagnostics screen shows inline.
const TAIL_LINES: usize = 200;

fn resolve_log(target: LogTarget, machine: &BootMachine) -> Option<PathBuf> {
    match target {
        LogTarget::Boot => Some(paths::boot_log_path()),
        LogTarget::Backend => machine
            .snapshot()
            .workspace_path
            .map(|workspace| PathBuf::from(workspace).join("logs").join("outreachos.log")),
    }
}

/// Q87: the tail is read **Rust-side**.
///
/// The diagnostics screen is displayed precisely when the backend is dead, so
/// an API-based log read fails exactly when it is needed.
#[tauri::command]
pub fn read_log_tail(machine: State<'_, Arc<BootMachine>>, which: LogTarget) -> String {
    let Some(path) = resolve_log(which, &machine) else {
        return "No workspace selected, so there is no backend log yet.".to_owned();
    };

    match std::fs::read_to_string(&path) {
        Ok(contents) => {
            let lines: Vec<&str> = contents.lines().collect();
            let start = lines.len().saturating_sub(TAIL_LINES);
            lines[start..].join("\n")
        }
        // Q86: the read closes immediately and is bounded, so it cannot be the
        // thing blocking rotation. A missing file is a normal state on a first
        // run, not an error worth a stack trace.
        Err(error) => format!("Could not read {}:\n{error}", path.display()),
    }
}

/// Reveal the log's folder in Explorer.
///
/// The folder, not the file: opening a `.log` hands it to whatever is
/// registered for the extension, which on a default Windows install is
/// nothing at all.
#[tauri::command]
pub fn open_logs_folder(
    app: AppHandle,
    machine: State<'_, Arc<BootMachine>>,
    which: LogTarget,
) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;

    let path = resolve_log(which, &machine).ok_or("No workspace selected.")?;
    let folder = path.parent().ok_or("The log path has no parent folder.")?;

    app.opener()
        .open_path(folder.to_string_lossy(), None::<&str>)
        .map_err(|error| error.to_string())
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
