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
}
