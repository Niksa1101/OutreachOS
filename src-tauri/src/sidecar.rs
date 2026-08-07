//! Spawning and supervising the Python backend.
//!
//! ADR-0003 / Q49: spawned with `std::process::Command`, not
//! `tauri-plugin-shell`. Three things need control that the plugin's sidecar
//! API does not expose cleanly, and all three are non-negotiable:
//!
//! - **`CREATE_NO_WINDOW`.** Without it the packaged build flashes a console
//!   window on every launch.
//! - **A Job Object with `KILL_ON_JOB_CLOSE`** (Q38). If Tauri is killed from
//!   Task Manager there is no shutdown path to run, and the OS is the only
//!   thing that can still guarantee the Python process dies with it.
//! - **stdin held open for the process lifetime** (Q34, Q37). It carries the
//!   token on its first line and then its EOF is the shutdown signal.
//!
//! The handshake budgets are Q76's: the `@@OOS` port line within 10s, then
//! `/health` returning 200 within a further 20s, polled at 250ms. Both misses
//! produce `handshake_timeout`, with `detail` saying which.

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::path::Path;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, RecvTimeoutError};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Deserialize;

use crate::diagnostics::{Diagnostic, DiagnosticCode};

/// Q76: how long to wait for the port to be reported.
const PORT_BUDGET: Duration = Duration::from_secs(10);
/// Q76: how long to wait for `/health` *after* the port arrives.
const HEALTH_BUDGET: Duration = Duration::from_secs(20);
/// Q76. Fast enough that a warm start feels instant; `access_log=False` on the
/// uvicorn side is what stops it filling the log.
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(250);
/// Q37: how long a polite shutdown gets before the hard kill.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(5);

/// `CREATE_NO_WINDOW`. Not in `std`, and not optional — see the module docs.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// How much stderr to keep for the diagnostics screen.
///
/// Bounded because a Python traceback loop could otherwise pin unbounded
/// memory in the one code path that runs when things are already wrong.
const STDERR_CAPTURE_LINES: usize = 40;

/* -------------------------------------------------------------------------- */
/* Control line parsing                                                        */
/* -------------------------------------------------------------------------- */

/// The payload of an `@@OOS` line.
///
/// Q39: `@@OOS <json>` lines are structured messages for us; everything else on
/// stdout and stderr is forwarded verbatim into the log. JSON rather than
/// positional fields (Q75) so a field can be added without a parser change.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ControlMessage {
    pub port: Option<u16>,
    pub boot_id: Option<String>,
}

pub const CONTROL_PREFIX: &str = "@@OOS ";

/// Parse one line of sidecar stdout.
///
/// Returns `None` for ordinary output, which the caller forwards to the log.
/// A malformed control line is also `None` — it is logged as-is rather than
/// silently dropped, and the handshake budget turns it into a timeout with the
/// offending text visible.
pub fn parse_control_line(line: &str) -> Option<ControlMessage> {
    let payload = line
        .trim_end_matches(['\r', '\n'])
        .strip_prefix(CONTROL_PREFIX)?;
    serde_json::from_str(payload.trim()).ok()
}

/* -------------------------------------------------------------------------- */
/* Job Object                                                                  */
/* -------------------------------------------------------------------------- */

#[cfg(windows)]
mod job {
    use std::io;
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;

    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    /// A Windows Job Object configured to kill its members when the last
    /// handle to it closes.
    ///
    /// Q38: this is the *only* orphan-prevention mechanism that survives Tauri
    /// being killed from Task Manager, because handle closure is performed by
    /// the kernel on process teardown whether or not any of our code runs.
    ///
    /// The handle is held for the lifetime of the application. Dropping this
    /// value kills the sidecar, which is why it is owned by the supervisor and
    /// never by a temporary.
    pub struct JobObject(HANDLE);

    // The handle is only ever passed to Win32 calls that are themselves
    // thread-safe, and is closed exactly once, in `Drop`.
    unsafe impl Send for JobObject {}
    unsafe impl Sync for JobObject {}

    impl JobObject {
        pub fn create() -> io::Result<Self> {
            // SAFETY: null name and null security attributes are documented as
            // valid, producing an unnamed job owned by this process.
            let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
            if handle.is_null() {
                return Err(io::Error::last_os_error());
            }

            let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

            // SAFETY: `limits` is a correctly-sized, fully-initialised struct
            // of the type the information class names.
            let ok = unsafe {
                SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    std::ptr::addr_of!(limits).cast(),
                    u32::try_from(std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>())
                        .expect("struct size fits in u32"),
                )
            };

            if ok == 0 {
                let error = io::Error::last_os_error();
                // SAFETY: `handle` is a live handle we created above.
                unsafe { CloseHandle(handle) };
                return Err(error);
            }

            Ok(Self(handle))
        }

        pub fn assign(&self, child: &Child) -> io::Result<()> {
            // SAFETY: the child is alive — we hold its `Child` — so its handle
            // is valid for the duration of this call.
            let ok = unsafe { AssignProcessToJobObject(self.0, child.as_raw_handle() as HANDLE) };
            if ok == 0 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        }
    }

    impl Drop for JobObject {
        fn drop(&mut self) {
            // SAFETY: created in `create`, closed exactly once here.
            unsafe { CloseHandle(self.0) };
        }
    }
}

#[cfg(not(windows))]
mod job {
    use std::io;
    use std::process::Child;

    /// Non-Windows stub. Windows is the only target platform (Tech.md §2), but
    /// `cargo test` on a Linux contributor's machine should still compile.
    pub struct JobObject;

    impl JobObject {
        pub fn create() -> io::Result<Self> {
            Ok(Self)
        }
        pub fn assign(&self, _child: &Child) -> io::Result<()> {
            Ok(())
        }
    }
}

use job::JobObject;

/* -------------------------------------------------------------------------- */
/* Spawn configuration                                                         */
/* -------------------------------------------------------------------------- */

pub struct SpawnRequest<'a> {
    pub boot_id: &'a str,
    pub token: &'a str,
    pub workspace: &'a Path,
    pub dev: bool,
    pub resource_dir: Option<&'a Path>,
    pub take_over: bool,
    pub allow_without_backup: bool,
}

/// A running sidecar.
pub struct Sidecar {
    pub port: u16,
    pub pid: u32,
    child: Arc<Mutex<Child>>,
    /// Held open deliberately. Dropping it closes the pipe, which is the
    /// shutdown signal (Q37).
    stdin: Mutex<Option<ChildStdin>>,
    /// Kills the process on drop, and on an abrupt Tauri exit.
    _job: JobObject,
}

impl Sidecar {
    /// Ask the process to stop, then make sure it did.
    ///
    /// Q118 describes what happens on the Python side of this; here we close
    /// stdin and give it [`SHUTDOWN_GRACE`] before escalating.
    pub fn shutdown(&self) {
        if let Ok(mut guard) = self.stdin.lock() {
            // Dropping the handle closes the pipe. Python's reader thread sees
            // EOF, releases the SSE streams, and stops uvicorn.
            guard.take();
        }

        let deadline = Instant::now() + SHUTDOWN_GRACE;
        while Instant::now() < deadline {
            if let Ok(mut child) = self.child.lock() {
                match child.try_wait() {
                    Ok(Some(status)) => {
                        tracing::info!(?status, "sidecar exited cleanly");
                        return;
                    }
                    Ok(None) => {}
                    Err(error) => {
                        tracing::warn!(%error, "could not poll the sidecar");
                        break;
                    }
                }
            }
            std::thread::sleep(Duration::from_millis(50));
        }

        tracing::warn!(
            pid = self.pid,
            "sidecar did not exit within the grace period; killing"
        );
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
        }
    }

    /// Poll for exit without blocking. `None` while still running.
    pub fn try_exit_status(&self) -> Option<std::process::ExitStatus> {
        self.child.lock().ok()?.try_wait().ok().flatten()
    }
}

/* -------------------------------------------------------------------------- */
/* Spawn                                                                       */
/* -------------------------------------------------------------------------- */

/// Start the sidecar and complete the handshake.
///
/// On success the process is bound to a port, has answered `/health`, and is
/// being supervised by two reader threads.
pub fn spawn(request: SpawnRequest<'_>) -> Result<Sidecar, Diagnostic> {
    let paths = crate::paths::sidecar_paths(request.resource_dir);

    // Q79: log both, always. A packaged build that cannot find its own backend
    // should say where it looked rather than only that it failed.
    tracing::info!(
        program = %paths.program.display(),
        ffmpeg_dir = %paths.ffmpeg_dir.display(),
        workspace = %request.workspace.display(),
        dev = request.dev,
        "spawning sidecar"
    );

    let mut command = Command::new(&paths.program);
    command
        .args(&paths.leading_args)
        .arg("--workspace")
        .arg(request.workspace)
        .arg("--ffmpeg-dir")
        .arg(&paths.ffmpeg_dir)
        .arg("--app-version")
        .arg(env!("CARGO_PKG_VERSION"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if request.dev {
        command.arg("--dev");
    }

    if request.take_over {
        command.arg("--take-over");
    }

    if request.allow_without_backup {
        command.arg("--allow-without-backup");
    }

    // Note what is *not* passed: the token. Q34 — argv is readable by any
    // same-user process through WMI, so it goes over stdin below.

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command.spawn().map_err(|error| {
        Diagnostic::new(
            DiagnosticCode::SidecarSpawnFailed,
            "The backend process could not be started.",
        )
        .with_detail(format!("{}: {error}", paths.program.display()))
    })?;

    let pid = child.id();

    // Assigned before the handshake, so a process that hangs at startup is
    // already covered by the kill-on-close guarantee.
    let job = JobObject::create().map_err(|error| {
        let _ = child.kill();
        Diagnostic::new(
            DiagnosticCode::SidecarSpawnFailed,
            "The backend could not be placed under process supervision.",
        )
        .with_detail(format!("CreateJobObject failed: {error}"))
    })?;

    if let Err(error) = job.assign(&child) {
        let _ = child.kill();
        return Err(Diagnostic::new(
            DiagnosticCode::SidecarSpawnFailed,
            "The backend could not be placed under process supervision.",
        )
        .with_detail(format!("AssignProcessToJobObject failed: {error}")));
    }

    let mut stdin = child.stdin.take().expect("stdin was piped");
    let stdout = child.stdout.take().expect("stdout was piped");
    let stderr = child.stderr.take().expect("stderr was piped");

    // Q75: one JSON line, both fields, no positional ambiguity.
    let handshake = serde_json::json!({ "boot_id": request.boot_id, "token": request.token });
    if let Err(error) = writeln!(stdin, "{handshake}").and_then(|()| stdin.flush()) {
        let _ = child.kill();
        return Err(Diagnostic::new(
            DiagnosticCode::SidecarSpawnFailed,
            "The backend closed its input before the handshake completed.",
        )
        .with_detail(error.to_string()));
    }
    // `stdin` is deliberately not dropped here — it stays open for the process
    // lifetime and its EOF is the shutdown signal.

    let stderr_tail = Arc::new(Mutex::new(Vec::<String>::new()));
    let (port_tx, port_rx) = mpsc::channel::<u16>();

    spawn_stdout_reader(stdout, port_tx);
    let stderr_done = spawn_stderr_reader(stderr, Arc::clone(&stderr_tail));

    let child = Arc::new(Mutex::new(child));

    let port = match port_rx.recv_timeout(PORT_BUDGET) {
        Ok(port) => port,
        Err(reason) => {
            let _ = child.lock().map(|mut c| c.kill());
            // Stderr arrives on a separate pipe and thread. On a fast exit
            // (e.g. port_bind_failed + SystemExit(3)) stdout can close before
            // the stderr reader has appended the marker — wait for that thread
            // to finish (pipe closed by kill above) before classifying.
            let _ = stderr_done.recv_timeout(Duration::from_millis(200));
            let cause = match reason {
                // The reader thread ended, which means stdout closed, which
                // means the process is gone. Almost always an import error.
                RecvTimeoutError::Disconnected => "the process exited before reporting a port",
                RecvTimeoutError::Timeout => "no @@OOS port line within 10s",
            };
            return Err(diagnostic_for_missing_port(
                cause,
                &captured(&stderr_tail),
            ));
        }
    };

    tracing::info!(port, pid, "sidecar reported its port");

    let sidecar = Sidecar {
        port,
        pid,
        child: Arc::clone(&child),
        stdin: Mutex::new(Some(stdin)),
        _job: job,
    };

    if let Err(diagnostic) = await_health(port, request.token, &child) {
        sidecar.shutdown();
        return Err(diagnostic);
    }

    tracing::info!(port, "sidecar handshake complete");
    Ok(sidecar)
}

fn captured(tail: &Arc<Mutex<Vec<String>>>) -> String {
    tail.lock()
        .map(|lines| lines.join("\n"))
        .unwrap_or_default()
}

/// Ticket 29: classify stderr from a sidecar that died before the @@OOS line.
fn diagnostic_for_missing_port(cause: &str, stderr: &str) -> Diagnostic {
    if stderr.contains("port_bind_failed") {
        return Diagnostic::new(
            DiagnosticCode::PortBindFailed,
            "The backend could not bind a local port.",
        )
        .with_detail(format!("{cause}\n\n{stderr}"));
    }

    Diagnostic::new(
        DiagnosticCode::HandshakeTimeout,
        "The backend started but never reported a port.",
    )
    .with_detail(format!("{cause}\n\n{stderr}"))
}

fn spawn_stdout_reader(stdout: std::process::ChildStdout, port_tx: mpsc::Sender<u16>) {
    std::thread::Builder::new()
        .name("sidecar-stdout".into())
        .spawn(move || {
            let mut reported = false;
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                match parse_control_line(&line) {
                    Some(message) => {
                        if let Some(port) = message.port {
                            if !reported {
                                reported = true;
                                let _ = port_tx.send(port);
                            }
                        }
                        tracing::debug!(control = %line, "sidecar control line");
                    }
                    // Q39: everything that is not a control line is forwarded
                    // verbatim. Python's own stderr handler writes here too, so
                    // this is where a traceback ends up in boot.log.
                    None => tracing::info!(target: "sidecar", "{line}"),
                }
            }
            tracing::debug!("sidecar stdout closed");
        })
        .expect("spawn stdout reader");
}

fn spawn_stderr_reader(
    stderr: std::process::ChildStderr,
    tail: Arc<Mutex<Vec<String>>>,
) -> mpsc::Receiver<()> {
    let (done_tx, done_rx) = mpsc::channel();
    std::thread::Builder::new()
        .name("sidecar-stderr".into())
        .spawn(move || {
            let _done_tx = done_tx;
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                // INFO, not WARN. Python's logging config sends *everything*
                // to stderr so that a crash before the file handler has a
                // workspace is still visible — so the stream carries INFO
                // lines too, and tagging the whole channel as a warning makes
                // a healthy boot.log read like a fault. The real severity is
                // in the forwarded text, and the diagnostics capture below is
                // what surfaces a genuine failure.
                tracing::info!(target: "sidecar", "{line}");
                if let Ok(mut lines) = tail.lock() {
                    if lines.len() == STDERR_CAPTURE_LINES {
                        lines.remove(0);
                    }
                    lines.push(line);
                }
            }
            tracing::debug!("sidecar stderr closed");
        })
        .expect("spawn stderr reader");
    done_rx
}

/* -------------------------------------------------------------------------- */
/* Health                                                                      */
/* -------------------------------------------------------------------------- */

const HEALTH_RESPONSE_CAP: usize = 8192;

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
struct HealthResponseBody {
    status: String,
    #[serde(default)]
    diagnostic_code: Option<String>,
    #[serde(default)]
    detail: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum HealthProbe {
    Ok,
    Degraded {
        code: Option<String>,
        detail: Option<String>,
    },
    HttpStatus(u16),
}

/// Poll `/health` until it answers with a healthy body or the budget expires.
fn await_health(port: u16, token: &str, child: &Arc<Mutex<Child>>) -> Result<(), Diagnostic> {
    let deadline = Instant::now() + HEALTH_BUDGET;
    let mut last_error = String::from("no response");

    while Instant::now() < deadline {
        if let Ok(mut guard) = child.lock() {
            if let Ok(Some(status)) = guard.try_wait() {
                return Err(Diagnostic::new(
                    DiagnosticCode::HandshakeTimeout,
                    "The backend never became ready.",
                )
                .with_detail(format!(
                    "the process exited during the health poll ({status})"
                )));
            }
        }

        match probe_health(port, token) {
            Ok(HealthProbe::Ok) => return Ok(()),
            Ok(HealthProbe::Degraded { code, detail }) => {
                return Err(crate::diagnostics::diagnose_degraded_health(
                    code.as_deref(),
                    detail.as_deref(),
                ));
            }
            Ok(HealthProbe::HttpStatus(status)) => {
                last_error = format!("/health returned {status}");
            }
            Err(error) => last_error = format!("/health: {error}"),
        }

        std::thread::sleep(HEALTH_POLL_INTERVAL);
    }

    Err(Diagnostic::new(
        DiagnosticCode::HandshakeTimeout,
        "The backend never became ready.",
    )
    .with_detail(format!(
        "/health did not return a healthy response within 20s ({last_error})"
    )))
}

fn probe_health(port: u16, token: &str) -> std::io::Result<HealthProbe> {
    let mut stream = TcpStream::connect(("127.0.0.1", port))?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;

    write!(
        stream,
        "GET /api/v1/health HTTP/1.1\r\n\
         Host: 127.0.0.1:{port}\r\n\
         Authorization: Bearer {token}\r\n\
         Accept: application/json\r\n\
         Connection: close\r\n\r\n"
    )?;
    stream.flush()?;

    let response = read_http_response(&mut stream)?;
    parse_health_probe(&response)
}

fn read_http_response(stream: &mut TcpStream) -> std::io::Result<Vec<u8>> {
    let mut buffer = Vec::new();
    let mut chunk = [0u8; 1024];

    loop {
        let read = stream.read(&mut chunk)?;
        if read == 0 {
            break;
        }
        buffer.extend_from_slice(&chunk[..read]);
        if buffer.len() >= HEALTH_RESPONSE_CAP {
            break;
        }
    }

    Ok(buffer)
}

fn parse_health_probe(bytes: &[u8]) -> std::io::Result<HealthProbe> {
    let status =
        parse_status_code(bytes).ok_or_else(|| std::io::Error::other("unparseable status line"))?;

    if status != 200 {
        return Ok(HealthProbe::HttpStatus(status));
    }

    let text = std::str::from_utf8(bytes)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;
    let body = text
        .split_once("\r\n\r\n")
        .or_else(|| text.split_once("\n\n"))
        .map(|(_, body)| body.trim())
        .unwrap_or("");

    if body.is_empty() {
        return Ok(HealthProbe::Ok);
    }

    let parsed: HealthResponseBody = serde_json::from_str(body)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;

    if parsed.status == "degraded" {
        return Ok(HealthProbe::Degraded {
            code: parsed.diagnostic_code,
            detail: parsed.detail,
        });
    }

    Ok(HealthProbe::Ok)
}

/* -------------------------------------------------------------------------- */
/* Render queue                                                                */
/* -------------------------------------------------------------------------- */

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
struct BatchProgressBody {
    active_job_count: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
struct RenderQueueResponseBody {
    batch: BatchProgressBody,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum QueueProbe {
    ActiveCount(u32),
    HttpStatus(u16),
}

/// Poll `/render-queue` and return `batch.active_job_count`.
pub fn probe_queue_activity(port: u16, token: &str) -> std::io::Result<u32> {
    match probe_queue(port, token)? {
        QueueProbe::ActiveCount(count) => Ok(count),
        QueueProbe::HttpStatus(status) => Err(std::io::Error::other(format!(
            "render queue probe returned HTTP {status}"
        ))),
    }
}

fn probe_queue(port: u16, token: &str) -> std::io::Result<QueueProbe> {
    let mut stream = TcpStream::connect(("127.0.0.1", port))?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;

    write!(
        stream,
        "GET /api/v1/render-queue HTTP/1.1\r\n\
         Host: 127.0.0.1:{port}\r\n\
         Authorization: Bearer {token}\r\n\
         Accept: application/json\r\n\
         Connection: close\r\n\r\n"
    )?;
    stream.flush()?;

    let response = read_http_response(&mut stream)?;
    parse_queue_probe(&response)
}

fn parse_queue_probe(bytes: &[u8]) -> std::io::Result<QueueProbe> {
    let status =
        parse_status_code(bytes).ok_or_else(|| std::io::Error::other("unparseable status line"))?;

    if status != 200 {
        return Ok(QueueProbe::HttpStatus(status));
    }

    let text = std::str::from_utf8(bytes)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;
    let body = text
        .split_once("\r\n\r\n")
        .or_else(|| text.split_once("\n\n"))
        .map(|(_, body)| body.trim())
        .unwrap_or("");

    if body.is_empty() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "empty render queue response body",
        ));
    }

    let parsed: RenderQueueResponseBody = serde_json::from_str(body)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;

    Ok(QueueProbe::ActiveCount(parsed.batch.active_job_count))
}

/// `HTTP/1.1 200 OK` -> `200`.
fn parse_status_code(bytes: &[u8]) -> Option<u16> {
    let text = std::str::from_utf8(bytes).ok()?;
    let mut parts = text.split_whitespace();
    let version = parts.next()?;
    if !version.starts_with("HTTP/") {
        return None;
    }
    parts.next()?.parse().ok()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_the_port_line_the_backend_actually_writes() {
        let message = parse_control_line("@@OOS {\"port\":56721,\"boot_id\":\"abc\"}\n")
            .expect("a control line");
        assert_eq!(message.port, Some(56721));
        assert_eq!(message.boot_id.as_deref(), Some("abc"));
    }

    #[test]
    fn tolerates_crlf_from_a_windows_pipe() {
        let message = parse_control_line("@@OOS {\"port\":1}\r\n").expect("a control line");
        assert_eq!(message.port, Some(1));
    }

    #[test]
    fn ordinary_output_is_not_a_control_line() {
        assert!(parse_control_line("Traceback (most recent call last):").is_none());
        assert!(parse_control_line("").is_none());
        // The prefix requires its trailing space, so a log line that merely
        // begins with the sigil is still ordinary output.
        assert!(parse_control_line("@@OOSNOTACONTROLLINE {}").is_none());
    }

    #[test]
    fn a_malformed_control_line_is_treated_as_output_rather_than_crashing() {
        assert!(parse_control_line("@@OOS not json").is_none());
        assert!(parse_control_line("@@OOS {\"port\":").is_none());
    }

    #[test]
    fn a_port_outside_u16_is_rejected_rather_than_truncated() {
        // 70000 would be 4464 if this were silently wrapped, and we would then
        // poll a port nothing is listening on until the budget expired.
        assert!(parse_control_line("@@OOS {\"port\":70000}").is_none());
    }

    #[test]
    fn unknown_fields_are_ignored_so_the_format_can_grow() {
        // Q75 chose JSON specifically so a field could be added without a
        // parser change. This is that promise, tested.
        let message =
            parse_control_line("@@OOS {\"port\":8080,\"future_field\":true}").expect("parsed");
        assert_eq!(message.port, Some(8080));
    }

    #[test]
    fn a_control_line_without_a_port_parses_but_reports_nothing() {
        let message = parse_control_line("@@OOS {\"boot_id\":\"x\"}").expect("parsed");
        assert_eq!(message.port, None);
    }

    #[test]
    fn reads_the_status_code_out_of_a_status_line() {
        assert_eq!(parse_status_code(b"HTTP/1.1 200 OK\r\n"), Some(200));
        assert_eq!(
            parse_status_code(b"HTTP/1.1 401 Unauthorized\r\n"),
            Some(401)
        );
        assert_eq!(parse_status_code(b"HTTP/1.0 503 "), Some(503));
    }

    #[test]
    fn rejects_anything_that_is_not_an_http_response() {
        assert_eq!(parse_status_code(b""), None);
        assert_eq!(parse_status_code(b"hello"), None);
        assert_eq!(parse_status_code(b"\xff\xfe not utf8"), None);
    }

    #[test]
    fn parses_a_healthy_health_body() {
        let response = concat!(
            "HTTP/1.1 200 OK\r\n",
            "Content-Type: application/json\r\n",
            "\r\n",
            r#"{"status":"ok","boot_id":"abc"}"#
        );
        assert_eq!(
            parse_health_probe(response.as_bytes()).unwrap(),
            HealthProbe::Ok
        );
    }

    #[test]
    fn parses_a_degraded_health_body() {
        let response = concat!(
            "HTTP/1.1 200 OK\r\n",
            "\r\n",
            r#"{"status":"degraded","diagnostic_code":"workspace_locked","detail":"locked"}"#
        );
        assert_eq!(
            parse_health_probe(response.as_bytes()).unwrap(),
            HealthProbe::Degraded {
                code: Some("workspace_locked".to_owned()),
                detail: Some("locked".to_owned()),
            }
        );
    }

    #[test]
    fn non_200_responses_are_http_status_failures() {
        let response = b"HTTP/1.1 503 Service Unavailable\r\n\r\n";
        assert_eq!(
            parse_health_probe(response).unwrap(),
            HealthProbe::HttpStatus(503)
        );
    }

    #[test]
    fn port_bind_marker_maps_to_port_bind_failed() {
        let stderr = "outreachos-backend: port_bind_failed: [WinError 10048] address already in use";
        let diagnostic = super::diagnostic_for_missing_port("the process exited before reporting a port", stderr);
        assert_eq!(diagnostic.code, DiagnosticCode::PortBindFailed);
    }

    /// Exercises the stderr-reader drain wait: the marker line lands in the
    /// tail after a brief delay, and classification must not run until the
    /// reader thread has finished (disconnect signal on the done channel).
    #[test]
    fn stderr_drain_waits_for_late_tail_lines() {
        let tail = Arc::new(Mutex::new(Vec::<String>::new()));
        let (done_tx, done_rx) = mpsc::channel::<()>();

        let tail_clone = Arc::clone(&tail);
        std::thread::Builder::new()
            .name("test-stderr".into())
            .spawn(move || {
                let _done_tx = done_tx;
                std::thread::sleep(Duration::from_millis(30));
                if let Ok(mut lines) = tail_clone.lock() {
                    lines.push(
                        "outreachos-backend: port_bind_failed: [WinError 10048]".into(),
                    );
                }
            })
            .expect("spawn test stderr reader");

        let _ = done_rx.recv_timeout(Duration::from_millis(200));

        let diagnostic = super::diagnostic_for_missing_port(
            "the process exited before reporting a port",
            &super::captured(&tail),
        );
        assert_eq!(diagnostic.code, DiagnosticCode::PortBindFailed);
    }

    #[test]
    fn missing_port_without_marker_stays_handshake_timeout() {
        let diagnostic = super::diagnostic_for_missing_port(
            "no @@OOS port line within 10s",
            "Traceback (most recent call last):",
        );
        assert_eq!(diagnostic.code, DiagnosticCode::HandshakeTimeout);
    }

    #[test]
    fn parses_a_render_queue_body() {
        let response = concat!(
            "HTTP/1.1 200 OK\r\n",
            "Content-Type: application/json\r\n",
            "\r\n",
            r#"{"jobs":[],"batch":{"total":3,"completed":1,"failed":0,"active":1,"waiting":1,"active_job_count":2,"progress_pct":33.3,"eta_seconds":null},"paused":false,"show_resume_prompt":false}"#
        );
        assert_eq!(
            parse_queue_probe(response.as_bytes()).unwrap(),
            QueueProbe::ActiveCount(2)
        );
    }
}
