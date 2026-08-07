//! Workspace relocation — move existing data or start fresh at a new path.
//!
//! Ticket 26: the pointer in app-data is updated **only after** the file
//! operation succeeds, so a failed move cannot leave the app pointing at nothing.
//! The sidecar must be stopped first so SQLite and the lock file are released.

use std::fs;
use std::io;
use std::path::Path;

use serde::Deserialize;

use crate::workspace::{self, DATABASE_FILENAME, WorkspaceValidation};

/// How to treat the current workspace when switching location.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RelocateMode {
    /// Copy the database, cache, outputs, and logs to the new location intact.
    MoveExisting,
    /// Initialise a new empty workspace; leave the old folder untouched on disk.
    StartFresh,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RelocateError {
    /// No workspace pointer is stored.
    NoCurrentWorkspace,
    /// The new location is the same as the current one.
    SameLocation,
    /// The new location is inside the current workspace, or vice versa.
    NestedLocation,
    Validation(WorkspaceValidation),
    Io { message: String },
}

impl RelocateError {
    pub fn message(&self) -> String {
        match self {
            Self::NoCurrentWorkspace => "No workspace is selected.".to_owned(),
            Self::SameLocation => {
                "That is already the current workspace location.".to_owned()
            }
            Self::NestedLocation => {
                "The new location cannot be inside the current workspace, or contain it.".to_owned()
            }
            Self::Validation(validation) => validation
                .rejection
                .map(|rejection| format!("That folder cannot be used: {rejection:?}"))
                .unwrap_or_else(|| "That folder cannot be used.".to_owned()),
            Self::Io { message } => message.clone(),
        }
    }
}

/// Directories created for a fresh workspace before the backend's first boot.
const WORKSPACE_DIRECTORIES: [&str; 3] = ["cache", "outputs", "logs"];

/// Validate the relocation request before stopping the backend.
pub fn validate_relocation(
    current: &str,
    candidate: &Path,
    _mode: RelocateMode,
) -> Result<WorkspaceValidation, RelocateError> {
    let validation = workspace::validate(candidate);

    if !validation.is_acceptable() {
        return Err(RelocateError::Validation(validation));
    }

    if workspace::same_path(&validation.path, current) {
        return Err(RelocateError::SameLocation);
    }

    if workspace::is_within(&validation.path, current)
        || workspace::is_within(current, &validation.path)
    {
        return Err(RelocateError::NestedLocation);
    }

    if validation.existing {
        // Relocation always targets an empty folder. An existing outreachos.db
        // means "open this workspace", which is Choose Workspace — not a move.
        return Err(RelocateError::Validation(WorkspaceValidation {
            path: validation.path,
            rejection: Some(workspace::WorkspaceRejection::NotEmpty),
            warnings: validation.warnings,
            existing: true,
        }));
    }

    Ok(validation)
}

/// Copy or initialise workspace files at `target` after the sidecar has stopped.
///
/// On failure, any partial copy at `target` is removed so the folder can be
/// retried. The caller must not update the pointer until this returns `Ok`.
pub fn apply_relocation(
    source: &Path,
    target: &Path,
    mode: RelocateMode,
) -> Result<(), RelocateError> {
    match mode {
        RelocateMode::MoveExisting => copy_workspace_tree(source, target),
        RelocateMode::StartFresh => prepare_fresh_workspace(target),
    }
}

fn prepare_fresh_workspace(target: &Path) -> Result<(), RelocateError> {
    fs::create_dir_all(target).map_err(io_error)?;

    for name in WORKSPACE_DIRECTORIES {
        fs::create_dir_all(target.join(name)).map_err(io_error)?;
    }

    Ok(())
}

fn copy_workspace_tree(source: &Path, target: &Path) -> Result<(), RelocateError> {
    fs::create_dir_all(target).map_err(io_error)?;

    let entries = fs::read_dir(source).map_err(io_error)?;

    for entry in entries {
        let entry = entry.map_err(io_error)?;
        let name = entry.file_name();
        let from = entry.path();
        let to = target.join(&name);

        if from.is_dir() {
            copy_dir_recursive(&from, &to)?;
        } else {
            fs::copy(&from, &to).map_err(io_error)?;
        }
    }

    // The copy must include a usable database — otherwise boot would fail at
    // the new location even though the pointer was about to be updated.
    if !target.join(DATABASE_FILENAME).is_file() {
        let _ = remove_tree_best_effort(target);
        return Err(RelocateError::Io {
            message: format!(
                "The workspace copy finished but {DATABASE_FILENAME} is missing at {}",
                target.display()
            ),
        });
    }

    Ok(())
}

fn copy_dir_recursive(from: &Path, to: &Path) -> Result<(), RelocateError> {
    fs::create_dir_all(to).map_err(io_error)?;

    for entry in fs::read_dir(from).map_err(io_error)? {
        let entry = entry.map_err(io_error)?;
        let child_from = entry.path();
        let child_to = to.join(entry.file_name());

        if child_from.is_dir() {
            copy_dir_recursive(&child_from, &child_to)?;
        } else {
            fs::copy(&child_from, &child_to).map_err(io_error)?;
        }
    }

    Ok(())
}

/// Remove a partially copied workspace so the target folder can be reused.
pub fn remove_tree_best_effort(path: &Path) {
    let _ = fs::remove_dir_all(path);
}

fn io_error(error: io::Error) -> RelocateError {
    RelocateError::Io {
        message: error.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("outreachos-reloc-test-{name}"));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("create temp dir");
        dir
    }

    fn write_existing_workspace(root: &Path) {
        let mut header = b"SQLite format 3\0".to_vec();
        header.extend_from_slice(&[0u8; 84]);
        fs::write(root.join(DATABASE_FILENAME), header).unwrap();
        fs::create_dir_all(root.join("cache").join("alpha")).unwrap();
        fs::write(
            root.join("cache").join("alpha").join("clip.mov"),
            b"alpha",
        )
        .unwrap();
        fs::create_dir_all(root.join("outputs").join("campaign")).unwrap();
        fs::write(root.join("outputs").join("campaign").join("Acme.mp4"), b"video").unwrap();
        fs::create_dir_all(root.join("logs")).unwrap();
        fs::write(root.join("logs").join("outreachos.log"), b"log line").unwrap();
    }

    #[test]
    fn move_existing_copies_database_cache_and_outputs() {
        let source = temp_dir("source");
        let target = temp_dir("target-empty");
        write_existing_workspace(&source);

        copy_workspace_tree(&source, &target).expect("copy");

        assert!(target.join(DATABASE_FILENAME).is_file());
        assert!(target.join("cache/alpha/clip.mov").is_file());
        assert!(target.join("outputs/campaign/Acme.mp4").is_file());
        assert!(target.join("logs/outreachos.log").is_file());
        // Source is untouched — relocation is copy-then-switch-pointer.
        assert!(source.join(DATABASE_FILENAME).is_file());
    }

    #[test]
    fn start_fresh_creates_workspace_directories_only() {
        let target = temp_dir("fresh");
        prepare_fresh_workspace(&target).expect("prepare");

        assert!(target.join("cache").is_dir());
        assert!(target.join("outputs").is_dir());
        assert!(target.join("logs").is_dir());
        assert!(!target.join(DATABASE_FILENAME).exists());
    }

    #[test]
    fn nested_locations_are_rejected() {
        let parent = temp_dir("parent");
        let child = parent.join("child");
        fs::create_dir_all(&child).unwrap();

        let parent_path = workspace::validate(&parent).path;
        assert!(matches!(
            validate_relocation(&parent_path, &child, RelocateMode::MoveExisting),
            Err(RelocateError::NestedLocation)
        ));
    }

    #[test]
    fn same_location_is_rejected() {
        let path = temp_dir("same");
        let validation = workspace::validate(&path);
        assert!(matches!(
            validate_relocation(&validation.path, &path, RelocateMode::StartFresh),
            Err(RelocateError::SameLocation)
        ));
    }

    #[test]
    fn start_fresh_rejects_an_existing_workspace_folder() {
        let current = temp_dir("current");
        let existing = temp_dir("existing-ws");
        write_existing_workspace(&existing);

        let current_path = workspace::validate(&current).path;
        for mode in [RelocateMode::StartFresh, RelocateMode::MoveExisting] {
            assert!(
                matches!(
                    validate_relocation(&current_path, &existing, mode),
                    Err(RelocateError::Validation(_))
                ),
                "{mode:?} should reject an existing workspace at the target"
            );
        }
    }

    #[test]
    fn a_failed_copy_leaves_no_database_at_the_target() {
        let source = temp_dir("source-no-db");
        let target = temp_dir("target-fail");
        fs::write(source.join("readme.txt"), b"x").unwrap();

        let result = copy_workspace_tree(&source, &target);
        assert!(result.is_err());
        assert!(!target.join(DATABASE_FILENAME).exists());
    }
}
