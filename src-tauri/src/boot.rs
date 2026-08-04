//! The boot state machine.
//!
//! Q54: **Rust owns this**, and the event payload is a full snapshot rather
//! than a delta — so `get_boot_state` and the `boot://state` event deserialise
//! into the same type and React has one reducer, not two code paths that must
//! be kept in agreement.
//!
//! Q78 makes the ownership sharper than it first looks: Rust's child-exit
//! observation is *authoritative*. An API request failing does not mean the
//! backend is gone — it might be a bad request, a timeout, a race with
//! shutdown — so the frontend never navigates to diagnostics on a fetch
//! failure. Only this machine decides.
//!
//! Retry re-runs the whole sequence: new spawn, new token, **new `boot_id`**.
//! That last part is why the frontend must `queryClient.clear()` on a
//! successful retry — returning to a cache populated by a process that no
//! longer exists is a subtle enough bug to name here rather than discover.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};
use uuid::Uuid;

use crate::diagnostics::{Diagnostic, DiagnosticCode};
use crate::sidecar::{self, Sidecar, SpawnRequest};

/// The event name the frontend subscribes to. Full snapshots only.
pub const BOOT_STATE_EVENT: &str = "boot://state";

/// How often the supervisor checks whether the sidecar is still alive.
///
/// Polling rather than blocking on `wait`: the `Child` is shared with the
/// shutdown path, and holding its lock for the process lifetime would deadlock
/// the one operation that needs it most.
const EXIT_POLL_INTERVAL: Duration = Duration::from_millis(500);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BootPhase {
    /// Before anything has been attempted.
    Starting,
    /// The sidecar is spawning or completing its handshake.
    StartingBackend,
    /// Handshake complete. The shell may mount.
    Ready,
    /// Terminal until Retry. `diagnostic` is always populated here.
    Failed,
}

/// Everything the frontend knows about the boot.
///
/// Note the absence of the token. Q56 keeps it in one non-exported binding in
/// `core/api`; putting it in a broadcast event would make it readable by any
/// listener and therefore eventually logged by someone's debug `console.log`.
#[derive(Debug, Clone, Serialize)]
pub struct BootState {
    pub phase: BootPhase,
    pub boot_id: String,
    /// Q102: the boot UI is a wordmark and **one** status line.
    pub status: String,
    pub workspace_path: Option<String>,
    pub port: Option<u16>,
    pub diagnostic: Option<Diagnostic>,
}

impl BootState {
    fn initial() -> Self {
        Self {
            phase: BootPhase::Starting,
            boot_id: String::new(),
            status: "Starting…".to_owned(),
            workspace_path: None,
            port: None,
            diagnostic: None,
        }
    }
}

/// What `get_backend_info` returns. Q9.
#[derive(Debug, Clone, Serialize)]
pub struct BackendInfo {
    pub port: u16,
    pub token: String,
    pub boot_id: String,
}

pub struct BootMachine {
    app: AppHandle,
    state: Mutex<BootState>,
    /// `Some` only between a successful handshake and the process exiting.
    session: Mutex<Option<Session>>,
}

struct Session {
    sidecar: Arc<Sidecar>,
    token: String,
    boot_id: String,
    /// Bumped on every attempt so a stale exit watcher from a previous spawn
    /// cannot report against the current one. Retry makes this reachable: the
    /// old process can die *after* the new one is ready.
    generation: u64,
}

impl BootMachine {
    pub fn new(app: AppHandle) -> Self {
        Self {
            app,
            state: Mutex::new(BootState::initial()),
            session: Mutex::new(None),
        }
    }

    pub fn snapshot(&self) -> BootState {
        self.state
            .lock()
            .map(|state| state.clone())
            .unwrap_or_else(|poisoned| poisoned.into_inner().clone())
    }

    pub fn backend_info(&self) -> Option<BackendInfo> {
        let session = self.session.lock().ok()?;
        let session = session.as_ref()?;
        Some(BackendInfo {
            port: session.sidecar.port,
            token: session.token.clone(),
            boot_id: session.boot_id.clone(),
        })
    }

    fn set(&self, update: impl FnOnce(&mut BootState)) {
        let snapshot = {
            let mut state = self
                .state
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            update(&mut state);
            state.clone()
        };

        tracing::debug!(phase = ?snapshot.phase, status = %snapshot.status, "boot state");

        if let Err(error) = self.app.emit(BOOT_STATE_EVENT, &snapshot) {
            tracing::warn!(%error, "could not emit the boot state");
        }
    }

    /// Run the boot sequence on a worker thread.
    ///
    /// Never blocks the caller: this is invoked from `setup` and from the
    /// `retry_boot` command, and neither may stall the event loop while a
    /// 30-second handshake budget plays out.
    pub fn start(self: &Arc<Self>) {
        let machine = Arc::clone(self);
        std::thread::Builder::new()
            .name("boot".into())
            .spawn(move || machine.run())
            .expect("spawn boot thread");
    }

    fn run(self: Arc<Self>) {
        // Q78: a new attempt is a new identity in every respect. Reusing the
        // previous boot_id would let SSE clients replay events from a process
        // that no longer exists (Q65).
        let boot_id = Uuid::new_v4().to_string();
        let token = generate_token();

        let generation = {
            let mut session = self
                .session
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            // Tear down anything still running before starting a replacement,
            // or the old process keeps the workspace lock.
            if let Some(previous) = session.take() {
                tracing::info!("stopping the previous sidecar before retrying");
                previous.sidecar.shutdown();
                previous.generation.wrapping_add(1)
            } else {
                0
            }
        };

        let workspace = provisional_workspace();

        self.set(|state| {
            state.phase = BootPhase::StartingBackend;
            state.boot_id = boot_id.clone();
            state.status = "Starting the backend…".to_owned();
            state.workspace_path = Some(workspace.display().to_string());
            state.port = None;
            state.diagnostic = None;
        });

        let resource_dir = self.app.path().resource_dir().ok();

        let result = sidecar::spawn(SpawnRequest {
            boot_id: &boot_id,
            token: &token,
            workspace: &workspace,
            dev: cfg!(debug_assertions),
            resource_dir: resource_dir.as_deref(),
        });

        match result {
            Ok(started) => {
                let sidecar = Arc::new(started);
                let port = sidecar.port;

                {
                    let mut session = self
                        .session
                        .lock()
                        .unwrap_or_else(|poisoned| poisoned.into_inner());
                    *session = Some(Session {
                        sidecar: Arc::clone(&sidecar),
                        token,
                        boot_id: boot_id.clone(),
                        generation,
                    });
                }

                self.set(|state| {
                    state.phase = BootPhase::Ready;
                    state.status = "Ready".to_owned();
                    state.port = Some(port);
                    state.diagnostic = None;
                });

                self.watch_for_exit(sidecar, generation);
            }
            Err(diagnostic) => {
                tracing::error!(
                    code = ?diagnostic.code,
                    detail = diagnostic.detail.as_deref().unwrap_or("-"),
                    "boot failed: {}",
                    diagnostic.message
                );
                self.set(|state| {
                    state.phase = BootPhase::Failed;
                    state.status = diagnostic.message.clone();
                    state.diagnostic = Some(diagnostic);
                });
            }
        }
    }

    /// Q78: the authoritative death notice.
    fn watch_for_exit(self: &Arc<Self>, sidecar: Arc<Sidecar>, generation: u64) {
        let machine = Arc::clone(self);

        std::thread::Builder::new()
            .name("sidecar-supervisor".into())
            .spawn(move || {
                let status = loop {
                    if let Some(status) = sidecar.try_exit_status() {
                        break status;
                    }
                    std::thread::sleep(EXIT_POLL_INTERVAL);
                };

                // A retry may have replaced this session while we were
                // polling. Reporting the old process's death against the new
                // one would send a working application to diagnostics.
                let current = machine
                    .session
                    .lock()
                    .ok()
                    .and_then(|session| session.as_ref().map(|s| s.generation));

                if current != Some(generation) {
                    tracing::debug!(?status, generation, "a superseded sidecar exited");
                    return;
                }

                tracing::error!(?status, "the sidecar exited unexpectedly");

                if let Ok(mut session) = machine.session.lock() {
                    *session = None;
                }

                machine.set(|state| {
                    state.phase = BootPhase::Failed;
                    state.status = "The backend stopped unexpectedly.".to_owned();
                    state.port = None;
                    state.diagnostic = Some(
                        Diagnostic::new(
                            DiagnosticCode::SidecarExited,
                            "The backend stopped unexpectedly.",
                        )
                        .with_detail(format!("Process exit: {status}")),
                    );
                });
            })
            .expect("spawn sidecar supervisor");
    }

    /// Stop the sidecar. Called when the last window closes.
    pub fn shutdown(&self) {
        let session = self
            .session
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
            .take();

        if let Some(session) = session {
            session.sidecar.shutdown();
        }
    }
}

/// Q9: 32 bytes of CSPRNG output, hex-encoded.
fn generate_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("the OS random source is available");
    bytes
        .iter()
        .fold(String::with_capacity(64), |mut out, byte| {
            use std::fmt::Write;
            let _ = write!(out, "{byte:02x}");
            out
        })
}

/// **Checkpoint 3 scaffolding.** Replaced in checkpoint 4 by the validated
/// pointer read from `workspace.json`.
///
/// The sidecar requires `--workspace` and Q13's invariant is that it is never
/// spawned without one — but the picker that produces a real path does not
/// exist yet. Q70 calls this out as honest incrementalism rather than an
/// oversight. A temp directory is used rather than `%LOCALAPPDATA%\OutreachOS`
/// precisely because Q117 *refuses* that location for a real workspace, and
/// scaffolding should not model something the next checkpoint rejects.
fn provisional_workspace() -> PathBuf {
    let path = std::env::temp_dir().join("outreachos-provisional-workspace");
    let _ = std::fs::create_dir_all(&path);
    path
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_token_is_64_hex_characters() {
        let token = generate_token();
        assert_eq!(token.len(), 64, "32 bytes, hex-encoded");
        assert!(token.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn tokens_are_not_reused_between_attempts() {
        // Q78: retry mints a new token. If this ever collides, the generator
        // is not what it claims to be.
        assert_ne!(generate_token(), generate_token());
    }

    #[test]
    fn the_initial_state_has_no_diagnostic_and_no_port() {
        let state = BootState::initial();
        assert_eq!(state.phase, BootPhase::Starting);
        assert!(state.diagnostic.is_none());
        assert!(state.port.is_none());
    }

    #[test]
    fn phases_serialise_to_the_snake_case_the_reducer_matches_on() {
        assert_eq!(
            serde_json::to_string(&BootPhase::StartingBackend).unwrap(),
            "\"starting_backend\""
        );
        assert_eq!(
            serde_json::to_string(&BootPhase::Ready).unwrap(),
            "\"ready\""
        );
    }

    #[test]
    fn a_snapshot_carries_no_token_field() {
        // Q56: the token reaches the frontend only through
        // `invoke("get_backend_info")`. A serialiser change that leaked it
        // into the broadcast event would be invisible without this.
        let json = serde_json::to_string(&BootState::initial()).unwrap();
        assert!(!json.contains("token"), "{json}");
    }
}
