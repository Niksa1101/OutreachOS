//! The workspace pointer.
//!
//! DB.md §1: two storage locations, and the split is deliberate. The pointer
//! cannot live inside the workspace it points to, so it goes to OS app-data;
//! everything else lives in the workspace so it moves as one unit.
//!
//! Q15 splits it further. The pointer gets its own `workspace.json` through the
//! store plugin, and window geometry stays with `tauri-plugin-window-state` —
//! two files, two owners, no shared schema to keep in step.

use tauri::{AppHandle, Wry};
use tauri_plugin_store::StoreExt;

/// Q15. Named for what it holds, not for the plugin that writes it.
const POINTER_FILE: &str = "workspace.json";
const PATH_KEY: &str = "path";

/// Read the stored workspace path, if there is one.
///
/// `None` is not an error state — it is a first run, and Q13 makes it the state
/// in which no sidecar is spawned at all.
pub fn read(app: &AppHandle<Wry>) -> Option<String> {
    let store = app.store(POINTER_FILE).ok()?;
    let value = store.get(PATH_KEY)?;
    let path = value.as_str()?.trim().to_owned();

    if path.is_empty() {
        None
    } else {
        Some(path)
    }
}

/// Store a validated, canonicalised path.
///
/// The caller must have validated first. Storing a path that fails validation
/// produces exactly the boot loop Q40 added "Forget this workspace" to escape.
pub fn write(app: &AppHandle<Wry>, path: &str) -> Result<(), String> {
    let store = app.store(POINTER_FILE).map_err(|error| error.to_string())?;
    store.set(PATH_KEY, serde_json::Value::String(path.to_owned()));
    // Explicit save: the plugin's auto-save is time-based, and a pointer that
    // is lost to a crash five seconds later sends the user back to the picker
    // with no idea why.
    store.save().map_err(|error| error.to_string())?;

    tracing::info!(path, "workspace pointer written");
    Ok(())
}

/// Q40: "Forget this workspace".
///
/// Without this, a pointer to a folder that has been renamed or unplugged is a
/// permanent boot loop into diagnostics with no exit that does not involve
/// editing app-data by hand. It is a button and a store write.
pub fn clear(app: &AppHandle<Wry>) -> Result<(), String> {
    let store = app.store(POINTER_FILE).map_err(|error| error.to_string())?;
    store.delete(PATH_KEY);
    store.save().map_err(|error| error.to_string())?;

    tracing::info!("workspace pointer cleared");
    Ok(())
}
