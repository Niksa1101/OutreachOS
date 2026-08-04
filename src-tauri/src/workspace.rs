//! Workspace validation and the pointer.
//!
//! Q13 settles the ordering problem by dissolving it: **the sidecar is never
//! spawned without a workspace.** No pointer means no backend, which means
//! validation cannot be an API call — it runs here, in Rust, before anything
//! else exists. That single invariant is what stops every later phase from
//! having to reason about a backend with two lifecycle states.
//!
//! Q80 fixes the rules: existence, a write probe, a SQLite header sniff, and a
//! typed result carrying warnings. Q14 makes the blocking set deliberately
//! small and everything else a dismissible warning — hard-refusing OneDrive
//! paths would misfire constantly, because Windows 11 puts `Documents` under
//! OneDrive by default.
//!
//! Canonicalisation is not cosmetic. `C:\Work\ws` and `C:\Work\ws\` would
//! otherwise be two different pointers, and the lock file in checkpoint 5 could
//! not match itself.

use std::fs;
use std::path::{Component, Path};

use serde::Serialize;

/// Q116: reject beyond this. `MAX_PATH` is 260 and the workspace is a *prefix* —
/// P1 writes `<workspace>/cache/alpha/<64-char sha>.mov` underneath it, so the
/// budget that matters is what is left over, not the workspace path itself.
pub const PATH_LENGTH_REJECT: usize = 150;
/// Q116: warn beyond this.
pub const PATH_LENGTH_WARN: usize = 120;

/// DB.md §1.
pub const DATABASE_FILENAME: &str = "outreachos.db";
/// Written and deleted by the write probe.
const WRITE_PROBE_FILENAME: &str = ".oos-write-test";
/// Every SQLite file starts with this. 16 bytes including the NUL.
const SQLITE_MAGIC: &[u8] = b"SQLite format 3\0";

/// Q81: the segment scan. Crude-looking and, for this case, the most reliable
/// signal available.
///
/// `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` was considered and rejected: it marks
/// *dehydrated files*, not sync-root folders, so a freshly created empty
/// workspace inside OneDrive carries no such attribute and the check misses the
/// common case entirely while adding Win32 surface.
const CLOUD_SYNC_SEGMENTS: [&str; 4] = ["onedrive", "dropbox", "google drive", "iclouddrive"];

/// Why a directory cannot be a workspace. All blocking.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum WorkspaceRejection {
    NotFound,
    NotADirectory,
    /// The write probe failed. `Program Files` under a non-admin user.
    NotWritable,
    /// Q14: neither empty nor an existing workspace.
    ///
    /// Q117 leans on this rather than on a blocklist: it already rejects
    /// Desktop, `%USERPROFILE%`, and Documents, which are never empty. Three
    /// hard refusals plus this rule is a complete set without the paternalism.
    NotEmpty,
    /// `outreachos.db` is present but is not a SQLite file.
    CorruptDatabase,
    /// Q117. The entire drive is not a project folder.
    DriveRoot,
    /// Q117. Writing user data next to the executable breaks on upgrade.
    InstallDirectory,
    /// Q117. This is where the *pointer* lives; a workspace here would nest
    /// the map inside the territory.
    AppDataDirectory,
    /// Q116.
    PathTooLong,
}

/// Dismissible. The user may choose anyway (Q14).
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum WorkspaceWarning {
    /// `GetDriveTypeW` returned `DRIVE_REMOTE`.
    NetworkDrive,
    /// A UNC path. SQLite over SMB has locking semantics you do not want.
    UncPath,
    /// A cloud-sync folder. The provider can rewrite files underneath an open
    /// database handle.
    CloudSync { provider: String },
    /// Q116: over the warn threshold but under the reject one.
    PathLength { length: usize },
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct WorkspaceValidation {
    /// The canonical form. This is what gets stored, and what every later
    /// comparison is made against.
    pub path: String,
    pub rejection: Option<WorkspaceRejection>,
    pub warnings: Vec<WorkspaceWarning>,
    /// True when `outreachos.db` is already present — the difference between
    /// "create a workspace here" and "open this one".
    pub existing: bool,
}

impl WorkspaceValidation {
    pub fn is_acceptable(&self) -> bool {
        self.rejection.is_none()
    }

    fn rejected(path: String, rejection: WorkspaceRejection) -> Self {
        Self {
            path,
            rejection: Some(rejection),
            warnings: Vec::new(),
            existing: false,
        }
    }
}

/* -------------------------------------------------------------------------- */
/* Pure rules — no filesystem access, so `cargo test` reaches all of them      */
/* -------------------------------------------------------------------------- */

/// Strip Windows' verbatim prefix from a canonicalised path.
///
/// `fs::canonicalize` returns `\\?\C:\Work\ws`. That form is correct and is
/// also unusable: it is what the user sees on the diagnostics screen, what gets
/// written to `workspace.json`, and what is compared against `current_exe()`
/// (which has no such prefix). Stripping it once, here, is what keeps those
/// three from disagreeing.
///
/// UNC paths keep their meaning: `\\?\UNC\server\share` becomes
/// `\\server\share`.
pub fn strip_verbatim_prefix(path: &str) -> String {
    if let Some(rest) = path.strip_prefix(r"\\?\UNC\") {
        return format!(r"\\{rest}");
    }
    if let Some(rest) = path.strip_prefix(r"\\?\") {
        return rest.to_owned();
    }
    path.to_owned()
}

/// Q80: absolute, no trailing separator, verbatim prefix removed.
///
/// A trailing separator is stripped only when it is not the whole path — `C:\`
/// must stay `C:\`, because `C:` alone means "the current directory on drive C"
/// in Windows path grammar, which is a different place.
pub fn normalise(path: &Path) -> String {
    let text = strip_verbatim_prefix(&path.to_string_lossy());
    let trimmed = text.trim_end_matches(['\\', '/']);

    if trimmed.is_empty() || trimmed.ends_with(':') {
        // A drive root, or a UNC root that trimmed away to nothing.
        return text.to_string();
    }

    trimmed.to_owned()
}

/// Case-insensitive path comparison. Q80: Windows paths are case-insensitive,
/// so `C:\Work` and `c:\work` are the same pointer and must compare equal.
pub fn same_path(left: &str, right: &str) -> bool {
    left.eq_ignore_ascii_case(right)
}

/// Is `path` inside `ancestor`, or the same directory?
pub fn is_within(path: &str, ancestor: &str) -> bool {
    if same_path(path, ancestor) {
        return true;
    }

    let prefix = format!("{}\\", ancestor.trim_end_matches('\\'));
    path.len() > prefix.len() && path[..prefix.len()].eq_ignore_ascii_case(&prefix)
}

/// `C:\`, `D:\`, or a bare UNC share root.
pub fn is_drive_root(path: &Path) -> bool {
    let mut components = path.components();
    let Some(first) = components.next() else {
        return false;
    };

    if !matches!(first, Component::Prefix(_)) {
        return false;
    }

    // After the prefix, a root directory and nothing else.
    matches!(components.next(), Some(Component::RootDir)) && components.next().is_none()
}

/// Q81: does any path segment name a known sync provider?
///
/// Segment-wise rather than substring, so `C:\Projects\dropbox-clone` is not
/// flagged while `C:\Users\me\Dropbox\ws` is.
pub fn detect_cloud_sync(path: &Path) -> Option<String> {
    for component in path.components() {
        let Component::Normal(segment) = component else {
            continue;
        };
        let lowered = segment.to_string_lossy().to_ascii_lowercase();

        for provider in CLOUD_SYNC_SEGMENTS {
            // `starts_with` rather than equality: OneDrive names business
            // roots `OneDrive - Contoso`.
            if lowered == provider || lowered.starts_with(&format!("{provider} ")) {
                return Some(segment.to_string_lossy().into_owned());
            }
        }
    }
    None
}

pub fn is_unc(path: &str) -> bool {
    path.starts_with(r"\\")
}

/// Q80's header sniff, as a pure function over the first bytes of a file.
pub fn looks_like_sqlite(header: &[u8]) -> bool {
    header.starts_with(SQLITE_MAGIC)
}

/* -------------------------------------------------------------------------- */
/* Validation                                                                  */
/* -------------------------------------------------------------------------- */

/// Full validation, including filesystem access.
pub fn validate(candidate: &Path) -> WorkspaceValidation {
    // Canonicalise first so every subsequent comparison is against one form.
    // A path that cannot be canonicalised does not exist, which is its own
    // answer.
    let canonical = match fs::canonicalize(candidate) {
        Ok(resolved) => resolved,
        Err(_) => {
            return WorkspaceValidation::rejected(
                normalise(candidate),
                WorkspaceRejection::NotFound,
            );
        }
    };

    let path = normalise(&canonical);

    if path.chars().count() > PATH_LENGTH_REJECT {
        return WorkspaceValidation::rejected(path, WorkspaceRejection::PathTooLong);
    }

    if !canonical.is_dir() {
        return WorkspaceValidation::rejected(path, WorkspaceRejection::NotADirectory);
    }

    if is_drive_root(&canonical) {
        return WorkspaceValidation::rejected(path, WorkspaceRejection::DriveRoot);
    }

    if let Some(install_dir) = install_directory() {
        if is_within_reference(&path, &install_dir) {
            return WorkspaceValidation::rejected(path, WorkspaceRejection::InstallDirectory);
        }
    }

    if is_within_reference(&path, &crate::paths::app_data_dir()) {
        return WorkspaceValidation::rejected(path, WorkspaceRejection::AppDataDirectory);
    }

    if write_probe(&canonical).is_err() {
        return WorkspaceValidation::rejected(path, WorkspaceRejection::NotWritable);
    }

    let database = canonical.join(DATABASE_FILENAME);
    let existing = database.is_file();

    if existing {
        if !database_header_is_sqlite(&database) {
            return WorkspaceValidation::rejected(path, WorkspaceRejection::CorruptDatabase);
        }
    } else if !is_effectively_empty(&canonical) {
        return WorkspaceValidation::rejected(path, WorkspaceRejection::NotEmpty);
    }

    WorkspaceValidation {
        warnings: collect_warnings(&canonical, &path),
        path,
        rejection: None,
        existing,
    }
}

fn collect_warnings(canonical: &Path, path: &str) -> Vec<WorkspaceWarning> {
    let mut warnings = Vec::new();

    if is_unc(path) {
        warnings.push(WorkspaceWarning::UncPath);
    } else if is_network_drive(path) {
        warnings.push(WorkspaceWarning::NetworkDrive);
    }

    if let Some(provider) = detect_cloud_sync(canonical) {
        warnings.push(WorkspaceWarning::CloudSync { provider });
    }

    let length = path.chars().count();
    if length > PATH_LENGTH_WARN {
        warnings.push(WorkspaceWarning::PathLength { length });
    }

    warnings
}

/// Q14: "empty or already contains `outreachos.db`".
///
/// Our own bookkeeping files do not count against emptiness — a crashed run
/// leaves `.oos-lock` behind (Q83 makes that the normal case, not the
/// exception), and refusing the workspace afterwards would strand the user in
/// the picker with no way back to their own data.
fn is_effectively_empty(directory: &Path) -> bool {
    let Ok(entries) = fs::read_dir(directory) else {
        return false;
    };

    !entries
        .flatten()
        .any(|entry| !entry.file_name().to_string_lossy().starts_with(".oos"))
}

fn write_probe(directory: &Path) -> std::io::Result<()> {
    let probe = directory.join(WRITE_PROBE_FILENAME);
    fs::write(&probe, b"outreachos")?;
    // Best-effort removal: the probe already succeeded, and a leftover file is
    // ignored by `is_effectively_empty`.
    let _ = fs::remove_file(&probe);
    Ok(())
}

fn database_header_is_sqlite(database: &Path) -> bool {
    use std::io::Read;

    let Ok(mut file) = fs::File::open(database) else {
        return false;
    };

    let mut header = [0u8; 16];
    match file.read_exact(&mut header) {
        Ok(()) => looks_like_sqlite(&header),
        // A file too short to hold a header is not a database. A zero-byte
        // `outreachos.db` is the shape a killed first run leaves behind.
        Err(_) => false,
    }
}

/// Is `path` inside `reference`, comparing **both** the reference's raw and
/// canonical forms?
///
/// They are not always the same string. Filesystem redirection — an MSIX or
/// AppContainer package, a junctioned profile directory, a folder-redirection
/// policy — means `%LOCALAPPDATA%\OutreachOS` and what `canonicalize` resolves
/// it to name one directory through two different paths. `path` has already
/// been canonicalised by the time it reaches here, so checking only the raw
/// reference silently lets a refused location through. Observed in practice,
/// not hypothesised.
///
/// Both forms are checked rather than only the canonical one because the
/// reference may not exist yet, and a refusal that stops working when a
/// directory is missing is a refusal that stops working on a clean install.
fn is_within_reference(path: &str, reference: &Path) -> bool {
    if is_within(path, &normalise(reference)) {
        return true;
    }

    fs::canonicalize(reference)
        .map(|resolved| is_within(path, &normalise(&resolved)))
        .unwrap_or(false)
}

fn install_directory() -> Option<std::path::PathBuf> {
    std::env::current_exe()
        .ok()?
        .parent()
        .map(Path::to_path_buf)
}

/* -------------------------------------------------------------------------- */
/* Drive type                                                                  */
/* -------------------------------------------------------------------------- */

#[cfg(windows)]
fn is_network_drive(path: &str) -> bool {
    use std::os::windows::ffi::OsStrExt;

    use windows_sys::Win32::Storage::FileSystem::GetDriveTypeW;

    // `windows-sys` files the DRIVE_* constants under a different module in
    // every other release, and this one is a fixed part of the Win32 ABI.
    // Naming it here beats a feature flag that moves.
    const DRIVE_REMOTE: u32 = 4;

    // GetDriveTypeW wants a root: `C:\`, with the trailing separator.
    let Some(drive) = path.get(..2) else {
        return false;
    };
    if !drive.ends_with(':') {
        return false;
    }

    let root: Vec<u16> = std::ffi::OsStr::new(&format!("{drive}\\"))
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();

    // SAFETY: `root` is a NUL-terminated wide string that outlives the call.
    unsafe { GetDriveTypeW(root.as_ptr()) == DRIVE_REMOTE }
}

#[cfg(not(windows))]
fn is_network_drive(_path: &str) -> bool {
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- normalisation (Q80) ---------------------------------------------

    #[test]
    fn a_trailing_separator_is_stripped() {
        // Without this, `C:\Work\ws` and `C:\Work\ws\` are two pointers and
        // checkpoint 5's lock file cannot match itself.
        assert_eq!(normalise(Path::new(r"C:\Work\ws\")), r"C:\Work\ws");
        assert_eq!(normalise(Path::new(r"C:\Work\ws")), r"C:\Work\ws");
    }

    #[test]
    fn a_drive_root_keeps_its_separator() {
        // `C:` without the separator means "the current directory on drive C",
        // which is a different place entirely.
        assert_eq!(normalise(Path::new(r"C:\")), r"C:\");
    }

    #[test]
    fn the_verbatim_prefix_is_removed() {
        // `fs::canonicalize` produces this form. It is what the user would see
        // on the diagnostics screen and what gets compared against
        // `current_exe()`, which never has the prefix.
        assert_eq!(strip_verbatim_prefix(r"\\?\C:\Work\ws"), r"C:\Work\ws");
    }

    #[test]
    fn a_verbatim_unc_path_keeps_its_unc_meaning() {
        assert_eq!(
            strip_verbatim_prefix(r"\\?\UNC\server\share"),
            r"\\server\share"
        );
    }

    #[test]
    fn comparison_ignores_case() {
        assert!(same_path(r"C:\Work\WS", r"c:\work\ws"));
        assert!(!same_path(r"C:\Work\ws", r"C:\Work\ws2"));
    }

    // --- containment ------------------------------------------------------

    #[test]
    fn containment_is_case_insensitive_and_includes_the_directory_itself() {
        assert!(is_within(r"C:\Program Files\App", r"C:\Program Files\App"));
        assert!(is_within(
            r"c:\program files\app\sub",
            r"C:\Program Files\App"
        ));
    }

    #[test]
    fn a_sibling_with_a_shared_prefix_is_not_contained() {
        // The bug a naive `starts_with` produces: `C:\AppData2` is not inside
        // `C:\AppData`, and refusing it would be inexplicable to the user.
        assert!(!is_within(r"C:\AppData2", r"C:\AppData"));
        assert!(!is_within(r"C:\App", r"C:\Application"));
    }

    #[test]
    fn a_trailing_separator_on_the_ancestor_does_not_change_the_answer() {
        assert!(is_within(r"C:\Work\ws", r"C:\Work\"));
    }

    // --- refusals (Q117) --------------------------------------------------

    #[test]
    fn drive_roots_are_recognised() {
        assert!(is_drive_root(Path::new(r"C:\")));
        assert!(is_drive_root(Path::new(r"D:\")));
        assert!(!is_drive_root(Path::new(r"C:\Work")));
    }

    #[test]
    fn a_directory_one_level_below_the_root_is_not_the_root() {
        assert!(!is_drive_root(Path::new(r"C:\ws")));
    }

    // --- cloud sync (Q81) -------------------------------------------------

    #[test]
    fn a_onedrive_segment_is_detected() {
        assert_eq!(
            detect_cloud_sync(Path::new(r"C:\Users\me\OneDrive\Projects\ws")).as_deref(),
            Some("OneDrive")
        );
    }

    #[test]
    fn a_business_onedrive_root_is_detected() {
        // OneDrive names business roots `OneDrive - Contoso`, which an
        // equality check would miss — and business accounts are exactly where
        // a synced workspace is most likely.
        assert_eq!(
            detect_cloud_sync(Path::new(r"C:\Users\me\OneDrive - Contoso\ws")).as_deref(),
            Some("OneDrive - Contoso")
        );
    }

    #[test]
    fn every_configured_provider_is_matched() {
        for (path, expected) in [
            (r"C:\Users\me\Dropbox\ws", "Dropbox"),
            (r"C:\Users\me\Google Drive\ws", "Google Drive"),
            (r"C:\Users\me\iCloudDrive\ws", "iCloudDrive"),
        ] {
            assert_eq!(
                detect_cloud_sync(Path::new(path)).as_deref(),
                Some(expected),
                "{path}"
            );
        }
    }

    #[test]
    fn a_segment_that_merely_contains_a_provider_name_is_not_flagged() {
        // Segment-wise, not substring. A false positive here is a warning the
        // user cannot make sense of on a folder they named themselves.
        assert_eq!(
            detect_cloud_sync(Path::new(r"C:\Projects\dropbox-clone\ws")),
            None
        );
        assert_eq!(detect_cloud_sync(Path::new(r"C:\my-onedrive-backup")), None);
    }

    #[test]
    fn unc_paths_are_recognised() {
        assert!(is_unc(r"\\server\share\ws"));
        assert!(!is_unc(r"C:\ws"));
    }

    // --- header sniff (Q80) -----------------------------------------------

    #[test]
    fn a_real_sqlite_header_is_accepted() {
        let mut header = b"SQLite format 3\0".to_vec();
        header.extend_from_slice(&[0u8; 84]);
        assert!(looks_like_sqlite(&header));
    }

    #[test]
    fn anything_else_is_rejected() {
        assert!(!looks_like_sqlite(b""));
        assert!(
            !looks_like_sqlite(b"SQLite format 3"),
            "the NUL is part of the magic"
        );
        assert!(!looks_like_sqlite(b"not a database at all"));
        // The shape a killed first run leaves behind.
        assert!(!looks_like_sqlite(&[0u8; 16]));
    }

    // --- path length (Q116) -----------------------------------------------

    /// The workspace is a *prefix*: P1 writes
    /// `<workspace>/cache/alpha/<64-char sha>.mov` beneath it, so the budget
    /// that matters is what `MAX_PATH` leaves over, not the workspace path
    /// itself. Evaluated at compile time — these are constants, and a runtime
    /// assertion over constants is a test that can never fail late.
    const _: () = {
        assert!(PATH_LENGTH_WARN < PATH_LENGTH_REJECT);
        assert!(PATH_LENGTH_REJECT + 64 + "/cache/alpha/.mov".len() < 260);
    };

    // --- validation against a real directory ------------------------------

    fn temp_dir(name: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("outreachos-ws-test-{name}"));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("create temp dir");
        dir
    }

    #[test]
    fn an_empty_directory_is_accepted() {
        let dir = temp_dir("empty");
        let result = validate(&dir);
        assert_eq!(result.rejection, None, "{result:?}");
        assert!(!result.existing);
    }

    #[test]
    fn a_missing_directory_is_rejected() {
        let dir = temp_dir("missing").join("nope");
        assert_eq!(validate(&dir).rejection, Some(WorkspaceRejection::NotFound));
    }

    #[test]
    fn a_file_is_not_a_directory() {
        let dir = temp_dir("file");
        let file = dir.join("thing.txt");
        fs::write(&file, b"x").unwrap();
        assert_eq!(
            validate(&file).rejection,
            Some(WorkspaceRejection::NotADirectory)
        );
    }

    #[test]
    fn a_non_empty_directory_without_a_database_is_rejected() {
        // Q117 leans on this instead of a blocklist: Desktop, %USERPROFILE%
        // and Documents are all rejected here, without naming any of them.
        let dir = temp_dir("occupied");
        fs::write(dir.join("holiday.jpg"), b"x").unwrap();
        assert_eq!(validate(&dir).rejection, Some(WorkspaceRejection::NotEmpty));
    }

    #[test]
    fn an_existing_workspace_is_accepted_and_reported_as_existing() {
        let dir = temp_dir("existing");
        let mut header = b"SQLite format 3\0".to_vec();
        header.extend_from_slice(&[0u8; 84]);
        fs::write(dir.join(DATABASE_FILENAME), header).unwrap();
        // A real workspace has other things in it too.
        fs::create_dir_all(dir.join("cache")).unwrap();

        let result = validate(&dir);
        assert_eq!(result.rejection, None, "{result:?}");
        assert!(result.existing);
    }

    #[test]
    fn a_corrupt_database_header_is_caught_at_pick_time() {
        // Manual checklist item 6. Better here than as a confusing failure
        // three seconds later inside Alembic.
        let dir = temp_dir("corrupt");
        fs::write(dir.join(DATABASE_FILENAME), b"this is not a database").unwrap();
        assert_eq!(
            validate(&dir).rejection,
            Some(WorkspaceRejection::CorruptDatabase)
        );
    }

    #[test]
    fn a_zero_byte_database_is_caught() {
        let dir = temp_dir("zero-byte");
        fs::write(dir.join(DATABASE_FILENAME), b"").unwrap();
        assert_eq!(
            validate(&dir).rejection,
            Some(WorkspaceRejection::CorruptDatabase)
        );
    }

    #[test]
    fn a_leftover_lock_file_does_not_make_a_workspace_look_occupied() {
        // Q83: the Job Object kill path means a crashed run leaves `.oos-lock`
        // behind, so this is the normal case. Refusing the folder afterwards
        // would strand the user with no route back to their own data.
        let dir = temp_dir("stale-lock");
        fs::write(dir.join(".oos-lock"), b"{}").unwrap();
        assert_eq!(validate(&dir).rejection, None);
    }

    #[test]
    fn the_stored_path_is_the_canonical_one() {
        let dir = temp_dir("canonical");
        let awkward = dir.join("sub").join("..");
        fs::create_dir_all(dir.join("sub")).unwrap();

        let result = validate(&awkward);
        assert!(!result.path.contains(".."), "{}", result.path);
        assert!(!result.path.contains(r"\\?\"), "{}", result.path);
    }

    #[test]
    fn the_app_data_directory_is_refused() {
        // Q117: the pointer lives here, so a workspace here would nest the map
        // inside the territory.
        let app_data = crate::paths::app_data_dir();
        fs::create_dir_all(&app_data).unwrap();
        assert_eq!(
            validate(&app_data).rejection,
            Some(WorkspaceRejection::AppDataDirectory)
        );
    }

    #[test]
    fn a_reference_directory_is_matched_through_filesystem_redirection() {
        // `validate` canonicalises its input, so a reference path that has not
        // been canonicalised can name the same directory through a different
        // string — under an MSIX container, a junctioned profile, or a folder
        // redirection policy. This test was written because a real environment
        // did exactly that and the app-data refusal above silently stopped
        // working.
        let app_data = crate::paths::app_data_dir();
        fs::create_dir_all(&app_data).unwrap();

        let canonical = normalise(&fs::canonicalize(&app_data).unwrap());
        assert!(
            is_within_reference(&canonical, &app_data),
            "canonical form {canonical} was not matched against raw reference {}",
            app_data.display()
        );
    }

    #[test]
    fn a_missing_reference_directory_still_matches_its_raw_form() {
        // A refusal that stops working when the directory does not exist is a
        // refusal that stops working on a clean install.
        let absent = std::env::temp_dir().join("outreachos-does-not-exist-ref");
        let _ = fs::remove_dir_all(&absent);

        assert!(is_within_reference(
            &normalise(&absent.join("child")),
            &absent
        ));
    }
}
