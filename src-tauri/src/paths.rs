//! OS path resolution for everything that exists before the workspace does.
//!
//! Q62: the boot log lives in app-data, not the workspace, because it has to be
//! writable in the two states where there is no workspace — first run, and a
//! pointer that no longer resolves. Tauri's own path resolver is not available
//! yet at that point (logging is initialised before the `App` is built), so
//! this reads the environment directly.

use std::env;
use std::path::PathBuf;

/// Matches `productName` in `tauri.conf.json`. Changing one without the other
/// orphans every log a user has already been asked to send.
const APP_DIR_NAME: &str = "OutreachOS";

/// `%LOCALAPPDATA%\OutreachOS`.
///
/// `LOCALAPPDATA` rather than `APPDATA`: logs are machine-local diagnostics and
/// have no business roaming to another machine over a domain profile.
pub fn app_data_dir() -> PathBuf {
    let base = env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        // Only reachable if the environment has been stripped. Falling back to
        // the temp directory keeps logging alive rather than losing the record
        // of the very failure that made the environment strange.
        .unwrap_or_else(env::temp_dir);

    base.join(APP_DIR_NAME)
}

/// `%LOCALAPPDATA%\OutreachOS\logs`.
pub fn app_logs_dir() -> PathBuf {
    app_data_dir().join("logs")
}

/// The pre-workspace log. Q62, Q119: always written, 2 MB x 3, appended across
/// runs with a separator per launch.
pub fn boot_log_path() -> PathBuf {
    app_logs_dir().join("boot.log")
}

/// How the sidecar is reached, resolved by build profile (Q79).
///
/// Both branches are logged at boot so a packaged build that cannot find its
/// own backend says where it looked.
#[derive(Debug, Clone)]
pub struct SidecarPaths {
    /// The executable to run.
    pub program: PathBuf,
    /// Arguments that come before the configuration flags. Empty for a frozen
    /// build; `-m outreachos_backend` in dev.
    pub leading_args: Vec<String>,
    /// Q98: the FFmpeg *directory*, not the executable. P1 needs
    /// `ffprobe.exe` too, and one argument beats two that can disagree.
    pub ffmpeg_dir: PathBuf,
}

/// Resolve the sidecar for a debug build.
///
/// Q7: dev runs the interpreter from the uv venv; the spawn code is otherwise
/// identical to release. Q55 rejects an "attach to an external backend" branch
/// outright — it would be a second lifecycle with no stdin token handoff, no
/// Job Object and no port parse, exercised only in dev and therefore certain to
/// diverge from the one that ships.
#[cfg(debug_assertions)]
pub fn sidecar_paths(_resource_dir: Option<&std::path::Path>) -> SidecarPaths {
    // CARGO_MANIFEST_DIR is `src-tauri/`; the repository root is its parent.
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));

    SidecarPaths {
        program: repo_root.join("backend/.venv/Scripts/python.exe"),
        leading_args: vec!["-m".to_owned(), "outreachos_backend".to_owned()],
        ffmpeg_dir: repo_root.join("vendor/ffmpeg"),
    }
}

/// Join paths under a Tauri resource directory. Testable without a runtime.
#[cfg_attr(debug_assertions, allow(dead_code))]
pub fn packaged_sidecar_paths(resources: &std::path::Path) -> SidecarPaths {
    SidecarPaths {
        // Q: no target-triple suffix. That convention belongs to
        // tauri-plugin-shell's sidecar API, which ADR-0003 dropped.
        program: resources.join("backend/outreachos-backend.exe"),
        leading_args: Vec::new(),
        ffmpeg_dir: resources.join("ffmpeg"),
    }
}

/// Resolve the sidecar for a release build.
///
/// ADR-0006: PyInstaller `onedir`, so this is an executable sitting beside its
/// `_internal/` directory, not a single file. `onefile` extracts the whole
/// bundle to `%TEMP%` on every launch, which is both the multi-second cold
/// start the handshake budgets were sized around and the shape AV heuristics
/// flag hardest.
#[cfg(not(debug_assertions))]
pub fn sidecar_paths(resource_dir: Option<&std::path::Path>) -> SidecarPaths {
    let resources = resource_dir
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));

    packaged_sidecar_paths(&resources)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn boot_log_sits_under_the_app_data_directory() {
        let log = boot_log_path();
        assert!(log.starts_with(app_data_dir()));
        assert!(log.ends_with("logs/boot.log") || log.ends_with("logs\\boot.log"));
    }

    #[test]
    fn app_data_dir_is_namespaced_to_the_product() {
        assert_eq!(
            app_data_dir().file_name().and_then(|n| n.to_str()),
            Some(APP_DIR_NAME)
        );
    }

    #[test]
    fn packaged_paths_target_the_staged_resource_layout() {
        use std::path::Path;

        let resources = Path::new("C:\\Program Files\\OutreachOS\\resources");
        let paths = packaged_sidecar_paths(resources);

        assert_eq!(
            paths.program,
            resources.join("backend/outreachos-backend.exe")
        );
        assert_eq!(paths.ffmpeg_dir, resources.join("ffmpeg"));
        assert!(paths.leading_args.is_empty());
    }

    /// `packaged_sidecar_paths` and `tauri.conf.json` must agree on where the
    /// frozen backend and bundled FFmpeg land under the resource directory.
    /// The array form of `bundle.resources` installs one directory deeper and
    /// breaks every packaged launch — this catches that drift from the config
    /// side, where the staged-layout test above cannot.
    #[test]
    fn bundle_resources_map_matches_packaged_sidecar_paths() {
        use std::collections::HashSet;
        use std::path::Path;

        let raw = include_str!("../tauri.conf.json");
        let config: serde_json::Value =
            serde_json::from_str(raw).expect("tauri.conf.json parses");

        let resources = config["bundle"]["resources"]
            .as_object()
            .expect("bundle.resources must be a map, not an array of globs");

        let sidecar_dests: HashSet<&str> = resources
            .values()
            .filter_map(|value| value.as_str())
            .filter(|dest| !dest.is_empty())
            .collect();

        assert_eq!(
            sidecar_dests,
            HashSet::from(["backend", "ffmpeg"]),
            "sidecar resource destinations must be exactly `backend` and `ffmpeg`"
        );

        let install_root = Path::new("C:\\Program Files\\OutreachOS\\resources");
        let paths = packaged_sidecar_paths(install_root);

        assert_eq!(
            paths.program,
            install_root.join("backend/outreachos-backend.exe")
        );
        assert_eq!(paths.ffmpeg_dir, install_root.join("ffmpeg"));
    }
}
