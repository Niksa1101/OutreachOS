//! The boot log.
//!
//! Q63 picks `tracing` + `tracing-appender` over a hand-rolled appender, for
//! non-blocking writes and the ecosystem-standard macros. That is not a
//! reversal of Q49's "drop the plugin" — `tracing` is a crate, not a Tauri
//! plugin. The decisive reason is that Rust most needs to log precisely when
//! Python is dead or never started, which is exactly when an
//! API-round-tripping logger has nothing to write to.
//!
//! What `tracing-appender` does *not* provide is size-based rotation with a
//! bounded file count — its `RollingFileAppender` rotates on a time interval.
//! Q119 asks for 2 MB x 3 appended across runs, so [`RotatingWriter`] below
//! supplies the rotation and `tracing_appender::non_blocking` supplies the
//! off-thread write.

use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use time::macros::format_description;
use time::OffsetDateTime;
use tracing::{Event, Level, Subscriber};
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::fmt::format::Writer;
use tracing_subscriber::fmt::{FmtContext, FormatEvent, FormatFields, FormattedFields};
use tracing_subscriber::registry::LookupSpan;

/// Q119: 2 MB per file.
const MAX_BYTES: u64 = 2 * 1024 * 1024;
/// Three files total: `boot.log`, `boot.log.1`, `boot.log.2`.
const KEEP_FILES: usize = 3;

/// Events emitted with this target are tagged `[client]` instead of `[rust]`.
///
/// Q64: frontend errors thrown before the backend exists have nowhere to POST,
/// so they come through `invoke("log_client_error")` and land here. The tag is
/// the only thing distinguishing them once they are in the file, and a user
/// reading this log needs to know which side of the IPC boundary failed.
pub const CLIENT_TARGET: &str = "outreachos::client";

/// Keeps the non-blocking writer's worker thread alive.
///
/// Dropping this flushes and joins. It must therefore live as long as the
/// process — dropping it early silently turns every subsequent log call into a
/// no-op, which is a genuinely miserable thing to debug.
pub struct LogGuard {
    _worker: WorkerGuard,
}

/// Initialise the boot log and install it as the global subscriber.
///
/// Returns the path actually written to alongside the guard, so the caller can
/// report it on the diagnostics screen without recomputing it.
pub fn init(boot_id: &str, verbose: bool) -> (PathBuf, Option<LogGuard>) {
    let path = crate::paths::boot_log_path();

    let writer = match RotatingWriter::open(&path, MAX_BYTES, KEEP_FILES) {
        Ok(writer) => writer,
        // A log we cannot open is not a reason to refuse to start. The window
        // and the diagnostics screen are more useful to the user than a
        // process that exited because it could not write a diagnostic.
        Err(error) => {
            eprintln!("outreachos: cannot open {}: {error}", path.display());
            return (path, None);
        }
    };

    let mut writer = writer;
    // Q119: one separator per launch, written before the subscriber exists so
    // it is a bare line rather than a formatted event.
    let _ = writeln!(writer, "\n=== boot {boot_id} {} ===", now());
    let _ = writer.flush();

    let (non_blocking, worker) = tracing_appender::non_blocking(writer);

    let max_level = if verbose { Level::DEBUG } else { Level::INFO };

    // Q57: `--dev` sets the default level to DEBUG; `--log-level` overrides in
    // either direction. On the Rust side `verbose` is that resolved decision.
    // No `with_ansi(false)`: that knob belongs to the stock formatter, and
    // `BootLogFormat` has no colour to switch off. A file a user opens in
    // Notepad must never contain escape sequences.
    let installed = tracing_subscriber::fmt()
        .event_format(BootLogFormat)
        .with_writer(non_blocking)
        .with_max_level(max_level)
        .try_init()
        .is_ok();

    if !installed {
        // Only happens if something already installed a global subscriber,
        // which in this binary means `init` was called twice.
        eprintln!("outreachos: a tracing subscriber was already installed");
    }

    (path, Some(LogGuard { _worker: worker }))
}

fn now() -> String {
    let format =
        format_description!("[year]-[month]-[day] [hour]:[minute]:[second].[subsecond digits:3]Z");
    OffsetDateTime::now_utc()
        .format(&format)
        .unwrap_or_else(|_| "0000-00-00 00:00:00.000Z".to_owned())
}

/* -------------------------------------------------------------------------- */
/* Formatting                                                                  */
/* -------------------------------------------------------------------------- */

/// Q24: human-readable text lines. A user opens this file, so it is not JSON.
///
/// ```text
/// 2026-08-04 11:20:31.884Z INFO  [rust] outreachos::boot: sidecar spawned pid=18244
/// ```
struct BootLogFormat;

impl<S, N> FormatEvent<S, N> for BootLogFormat
where
    S: Subscriber + for<'a> LookupSpan<'a>,
    N: for<'a> FormatFields<'a> + 'static,
{
    fn format_event(
        &self,
        ctx: &FmtContext<'_, S, N>,
        mut writer: Writer<'_>,
        event: &Event<'_>,
    ) -> std::fmt::Result {
        let meta = event.metadata();
        let tag = if meta.target() == CLIENT_TARGET {
            "client"
        } else {
            "rust"
        };

        write!(writer, "{} {:<5} [{tag}] ", now(), meta.level())?;

        // Span context, when there is any. Boot is a linear sequence so this is
        // usually empty, but the sidecar supervisor runs inside one.
        if let Some(scope) = ctx.event_scope() {
            for span in scope.from_root() {
                write!(writer, "{}", span.name())?;
                let ext = span.extensions();
                if let Some(fields) = ext.get::<FormattedFields<N>>() {
                    if !fields.is_empty() {
                        write!(writer, "{{{fields}}}")?;
                    }
                }
                write!(writer, ":")?;
            }
            write!(writer, " ")?;
        }

        ctx.field_format().format_fields(writer.by_ref(), event)?;
        writeln!(writer)
    }
}

/* -------------------------------------------------------------------------- */
/* Rotation                                                                    */
/* -------------------------------------------------------------------------- */

/// A `RotatingFileHandler` equivalent: roll at `max_bytes`, keep `keep` files.
///
/// Every failure path here degrades to "keep writing where we are" rather than
/// propagating. An `Err` returned from this writer surfaces inside
/// `tracing-appender`'s worker thread where nothing can act on it, and the
/// alternative to a slightly-too-large log file is no log file at all.
pub struct RotatingWriter {
    path: PathBuf,
    max_bytes: u64,
    keep: usize,
    file: File,
    written: u64,
}

impl RotatingWriter {
    pub fn open(path: &Path, max_bytes: u64, keep: usize) -> io::Result<Self> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }

        let file = OpenOptions::new().create(true).append(true).open(path)?;
        let written = file.metadata().map(|m| m.len()).unwrap_or(0);

        Ok(Self {
            path: path.to_path_buf(),
            max_bytes,
            keep: keep.max(1),
            file,
            written,
        })
    }

    /// `boot.log.1` .. `boot.log.{keep - 1}`, oldest discarded.
    fn rotate(&mut self) -> io::Result<()> {
        let _ = self.file.flush();

        for index in (1..self.keep).rev() {
            let from = if index == 1 {
                self.path.clone()
            } else {
                suffixed(&self.path, index - 1)
            };
            let to = suffixed(&self.path, index);

            if from.exists() {
                // A rename can fail on Windows when another process holds the
                // file open — a tail read, or an editor the user left on it.
                // Q86 makes the same allowance on the Python side. Give up on
                // this rotation and try again on the next write.
                if fs::rename(&from, &to).is_err() {
                    return Ok(());
                }
            }
        }

        self.file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        self.written = 0;
        Ok(())
    }
}

fn suffixed(path: &Path, index: usize) -> PathBuf {
    let mut name = path.as_os_str().to_os_string();
    name.push(format!(".{index}"));
    PathBuf::from(name)
}

impl Write for RotatingWriter {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        // Roll before writing, and only when there is something to roll — a
        // single line larger than `max_bytes` must still be written somewhere
        // rather than triggering an infinite rotation.
        if self.written > 0 && self.written + buf.len() as u64 > self.max_bytes {
            let _ = self.rotate();
        }

        match self.file.write(buf) {
            Ok(n) => {
                self.written += n as u64;
                Ok(n)
            }
            // Claim the bytes anyway. Reporting a short write upstream makes
            // the appender retry a line it can never place.
            Err(_) => Ok(buf.len()),
        }
    }

    fn flush(&mut self) -> io::Result<()> {
        let _ = self.file.flush();
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("outreachos-log-test-{name}"));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("create temp dir");
        dir
    }

    #[test]
    fn appends_across_runs_rather_than_truncating() {
        let dir = temp_dir("append");
        let path = dir.join("boot.log");

        {
            let mut writer = RotatingWriter::open(&path, MAX_BYTES, 3).unwrap();
            writer.write_all(b"first run\n").unwrap();
        }
        {
            let mut writer = RotatingWriter::open(&path, MAX_BYTES, 3).unwrap();
            writer.write_all(b"second run\n").unwrap();
        }

        let contents = fs::read_to_string(&path).unwrap();
        assert!(contents.contains("first run"), "{contents}");
        assert!(contents.contains("second run"), "{contents}");
    }

    #[test]
    fn rotates_at_the_size_limit_and_keeps_a_bounded_number_of_files() {
        let dir = temp_dir("rotate");
        let path = dir.join("boot.log");

        let mut writer = RotatingWriter::open(&path, 64, 3).unwrap();
        for index in 0..40 {
            writer
                .write_all(format!("line {index:0>20}\n").as_bytes())
                .unwrap();
        }
        writer.flush().unwrap();
        drop(writer);

        assert!(path.exists(), "live log missing");
        assert!(suffixed(&path, 1).exists(), "boot.log.1 missing");
        assert!(suffixed(&path, 2).exists(), "boot.log.2 missing");
        assert!(
            !suffixed(&path, 3).exists(),
            "retention is not bounded at {KEEP_FILES} files"
        );

        for index in 0..3 {
            let file = if index == 0 {
                path.clone()
            } else {
                suffixed(&path, index)
            };
            let len = fs::metadata(&file).unwrap().len();
            assert!(len <= 64 + 32, "{} grew to {len} bytes", file.display());
        }
    }

    #[test]
    fn a_line_larger_than_the_limit_is_still_written() {
        let dir = temp_dir("oversized");
        let path = dir.join("boot.log");

        let mut writer = RotatingWriter::open(&path, 16, 3).unwrap();
        let line = "x".repeat(200);
        writer.write_all(line.as_bytes()).unwrap();
        writer.flush().unwrap();

        assert_eq!(fs::metadata(&path).unwrap().len(), 200);
    }
}
