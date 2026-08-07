//! Why the application cannot run.
//!
//! Q124 fixes the boot diagnostic set; ticket 26 adds `workspace_relocation_failed`
//! for an interrupted or partial workspace move; ticket 29 adds `port_bind_failed`,
//! `ffmpeg_missing`, and `ffmpeg_unrunnable` for packaged-only startup failures.
//! Q41 explains the shape: real causes plus `unknown`, because an unmapped failure
//! must not render a blank screen. `unknown` carries the raw error in `detail`.
//!
//! # These are not API error codes
//!
//! There is a second enum — `ApiErrorCode` in
//! `backend/src/outreachos_backend/core/errors.py` — with `validation_error`,
//! `not_found`, `conflict`, `workspace_error`, `unauthorized`, and
//! `internal_error`. **The two namespaces share no values and nothing is ever
//! both.** These codes describe why the *application* cannot run; those
//! describe why a *request* failed.
//!
//! Q124 predicts the temptation to reach across arrives around P4. It is
//! called out here, and in the Python enum, so that whoever feels it finds the
//! answer before writing the mapping.
//!
//! Two merges were considered and rejected:
//!
//! - `workspace_locked` into `workspace_unwritable`: different causes, and
//!   more importantly different action sets — take over, versus pick somewhere
//!   else. Merging means the screen either offers "Take over" on a permissions
//!   failure or hides it on a lock.
//! - `sidecar_exited` split by at-boot versus mid-session: same condition,
//!   different surrounding state. The boot machine already knows whether there
//!   is a route to return to, so the screen selects its title from that.
//!   Splitting an enum to carry a fact the state already holds is how enums
//!   start drifting.

use serde::Serialize;

// Defined complete in one place because Q124 settles it as one enum of nine,
// and splitting the definition across the checkpoints that happen to construct
// each variant would make the set impossible to read.
//
// Constructed as: `sidecar_*` and `handshake_timeout` here in checkpoint 3;
// `workspace_*` and `unknown` in checkpoint 4; `migration_failed` and
// `database_newer_than_app` in checkpoint 5. **Delete this attribute in
// checkpoint 5** — once all nine are reachable it is hiding real dead code
// rather than tolerating a half-built enum.
#[allow(dead_code)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DiagnosticCode {
    /// The stored pointer no longer resolves to a directory. Offers
    /// "Forget this workspace" — Q40, because otherwise this is a permanent
    /// boot loop with no exit that does not involve editing app-data by hand.
    WorkspaceMissing,
    /// The write probe failed. Usually `Program Files` under a non-admin user.
    WorkspaceUnwritable,
    /// A live or foreign-host `.oos-lock`. Offers "Take over".
    WorkspaceLocked,
    /// The process could not be started at all — a missing interpreter in dev,
    /// a missing sidecar executable in a packaged build.
    SidecarSpawnFailed,
    /// It started and then died. At boot or mid-session; same code.
    SidecarExited,
    /// Q76's budgets: the `@@OOS` port line within 10s, or `/health` 200
    /// within a further 20s. One code for both misses, with `detail`
    /// distinguishing them — Q124.
    HandshakeTimeout,
    /// Ticket 29: the sidecar exited before reporting a port because binding
    /// `127.0.0.1:0` failed. Distinct from a generic handshake timeout so the
    /// diagnostics screen can name it.
    PortBindFailed,
    /// Ticket 29: bundled FFmpeg binaries are absent from the path the
    /// packaged build was given.
    FfmpegMissing,
    /// Ticket 29: FFmpeg binaries are present but cannot be executed.
    FfmpegUnrunnable,
    /// Alembic raised, or the pre-migration backup failed. Q85 folds backup
    /// failure in here rather than adding a code, with `detail` naming it and
    /// an explicit "Proceed without backup" action.
    MigrationFailed,
    /// The database is at a revision this build does not know. Detected
    /// *before* upgrading — Q84.
    DatabaseNewerThanApp,
    /// Ticket 26: a workspace move or fresh init failed after the sidecar was
    /// stopped. The pointer still references the original workspace.
    WorkspaceRelocationFailed,
    /// The fallback. Never rendered as a blank screen; `detail` carries the
    /// original error text verbatim.
    Unknown,
}

/// A diagnostic as the frontend receives it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Diagnostic {
    pub code: DiagnosticCode,
    /// One sentence, written for a user, naming what failed.
    pub message: String,
    /// The technical cause: captured stderr, an OS error, a revision id.
    /// Rendered in a monospace block, not a toast.
    pub detail: Option<String>,
}

impl Diagnostic {
    pub fn new(code: DiagnosticCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            detail: None,
        }
    }

    pub fn with_detail(mut self, detail: impl Into<String>) -> Self {
        let detail = detail.into();
        if !detail.trim().is_empty() {
            self.detail = Some(detail);
        }
        self
    }
}

/// Map a degraded `/health` payload onto a boot diagnostic.
pub fn diagnose_degraded_health(code: Option<&str>, detail: Option<&str>) -> Diagnostic {
    let detail_text = detail.filter(|value| !value.trim().is_empty());

    match code {
        Some("workspace_locked") => Diagnostic::new(
            DiagnosticCode::WorkspaceLocked,
            "The workspace is in use by another copy of OutreachOS.",
        )
        .with_detail(
            detail_text
                .unwrap_or("Another copy of OutreachOS appears to have this workspace open."),
        ),

        Some("migration_failed") => Diagnostic::new(
            DiagnosticCode::MigrationFailed,
            "The database could not be updated.",
        )
        .with_detail(detail_text.unwrap_or(
            "OutreachOS could not apply a required database change. \
                 Your data has not been modified.",
        )),

        Some("database_newer_than_app") => Diagnostic::new(
            DiagnosticCode::DatabaseNewerThanApp,
            "This workspace was made by a newer version of OutreachOS.",
        )
        .with_detail(detail_text.unwrap_or(
            "The database in this workspace uses a newer format than this copy understands.",
        )),

        Some("ffmpeg_missing") => Diagnostic::new(
            DiagnosticCode::FfmpegMissing,
            "The bundled video tools are missing.",
        )
        .with_detail(detail_text.unwrap_or(
            "OutreachOS could not find FFmpeg or FFprobe where the installer placed them.",
        )),

        Some("ffmpeg_unrunnable") => Diagnostic::new(
            DiagnosticCode::FfmpegUnrunnable,
            "The bundled video tools could not be run.",
        )
        .with_detail(detail_text.unwrap_or(
            "FFmpeg or FFprobe is present but failed to start. The log below may show why.",
        )),

        _ => Diagnostic::new(
            DiagnosticCode::Unknown,
            "The backend started in a degraded state.",
        )
        .with_detail(detail_text.unwrap_or("No further detail was provided.")),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Boot diagnostic codes, paired with the wire value the frontend's union
    /// matches on.
    ///
    /// This table is the contract with `frontend/src/core/boot/diagnostics.ts`.
    /// A rename on either side is otherwise invisible until the diagnostics
    /// screen falls through to its "unrecognised code" branch — on the one
    /// screen that only renders when the user is already stuck.
    const ALL: [(DiagnosticCode, &str); 13] = [
        (DiagnosticCode::WorkspaceMissing, "workspace_missing"),
        (DiagnosticCode::WorkspaceUnwritable, "workspace_unwritable"),
        (DiagnosticCode::WorkspaceLocked, "workspace_locked"),
        (DiagnosticCode::SidecarSpawnFailed, "sidecar_spawn_failed"),
        (DiagnosticCode::SidecarExited, "sidecar_exited"),
        (DiagnosticCode::HandshakeTimeout, "handshake_timeout"),
        (DiagnosticCode::PortBindFailed, "port_bind_failed"),
        (DiagnosticCode::FfmpegMissing, "ffmpeg_missing"),
        (DiagnosticCode::FfmpegUnrunnable, "ffmpeg_unrunnable"),
        (DiagnosticCode::MigrationFailed, "migration_failed"),
        (
            DiagnosticCode::DatabaseNewerThanApp,
            "database_newer_than_app",
        ),
        (
            DiagnosticCode::WorkspaceRelocationFailed,
            "workspace_relocation_failed",
        ),
        (DiagnosticCode::Unknown, "unknown"),
    ];

    #[test]
    fn every_code_serialises_to_the_snake_case_the_frontend_expects() {
        for (code, expected) in ALL {
            assert_eq!(
                serde_json::to_string(&code).unwrap(),
                format!("\"{expected}\""),
                "{code:?} does not match the frontend union"
            );
        }
    }

    #[test]
    fn no_diagnostic_code_collides_with_an_api_error_code() {
        // Q124: two namespaces, no shared values, nothing is ever both. The
        // Python set is closed by Q67, so it can be written down here.
        const API_ERROR_CODES: [&str; 6] = [
            "validation_error",
            "not_found",
            "conflict",
            "workspace_error",
            "unauthorized",
            "internal_error",
        ];

        for (_, wire) in ALL {
            assert!(
                !API_ERROR_CODES.contains(&wire),
                "`{wire}` appears in both enums; they must stay disjoint"
            );
        }
    }

    #[test]
    fn blank_detail_is_dropped_rather_than_rendered_as_an_empty_block() {
        let diagnostic =
            Diagnostic::new(DiagnosticCode::SidecarExited, "It stopped.").with_detail("   \n ");
        assert_eq!(diagnostic.detail, None);
    }

    #[test]
    fn detail_is_kept_verbatim() {
        let stderr = "Traceback (most recent call last):\n  File \"x\"";
        let diagnostic =
            Diagnostic::new(DiagnosticCode::SidecarSpawnFailed, "…").with_detail(stderr);
        assert_eq!(diagnostic.detail.as_deref(), Some(stderr));
    }

    #[test]
    fn degraded_ffmpeg_codes_map_to_named_diagnostics() {
        let missing = diagnose_degraded_health(
            Some("ffmpeg_missing"),
            Some("Missing FFmpeg binary: C:/ffmpeg/ffmpeg.exe"),
        );
        assert_eq!(missing.code, DiagnosticCode::FfmpegMissing);

        let unrunnable = diagnose_degraded_health(
            Some("ffmpeg_unrunnable"),
            Some("ffmpeg.exe exited with code 1"),
        );
        assert_eq!(unrunnable.code, DiagnosticCode::FfmpegUnrunnable);
    }
}
