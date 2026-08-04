//! Window geometry, and the single place the window becomes visible.
//!
//! Two decisions converge here:
//!
//! - Q54: the window starts hidden (`"visible": false` in `tauri.conf.json`)
//!   and is shown once React has painted the boot UI, or after a watchdog
//!   expires. Otherwise the user sees a white flash before any state renders.
//! - Q46 / Q101: `tauri-plugin-window-state` restores the geometry and Rust
//!   clamps it. **Size as well as position** — a window restored at 2560x1400
//!   onto a 1920x1080 panel is positioned perfectly and still unusable.
//!
//! Clamping runs at reveal time rather than at startup so it is guaranteed to
//! observe the geometry the plugin restored, whatever order the plugin's own
//! hooks fire in.

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{AppHandle, Manager, PhysicalPosition, PhysicalSize};

/// Matches the `label` in `tauri.conf.json`. Q22 rejects multi-window outright,
/// so there is exactly one and every lookup goes through this constant.
pub const MAIN_WINDOW_LABEL: &str = "main";

/// Q46: the window minimums. These are *also* declared in `tauri.conf.json`,
/// where they constrain user resizing; here they constrain the restore clamp.
/// `min_size_matches_the_tauri_config` below is what stops the two drifting —
/// a mismatch would let the clamp produce a size the window manager then
/// refuses, which looks like the clamp is broken.
pub const MIN_WIDTH: u32 = 1100;
pub const MIN_HEIGHT: u32 = 700;

/// The window is revealed by whichever of `app_ready` and the watchdog arrives
/// first (Q77). Both call [`reveal`]; this makes the second call a no-op.
static REVEALED: AtomicBool = AtomicBool::new(false);

/// A physical-pixel rectangle. Deliberately not `tauri::Rect` so the clamping
/// logic below is testable without a Tauri runtime (Q107).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub width: u32,
    pub height: u32,
}

impl Rect {
    pub fn new(x: i32, y: i32, width: u32, height: u32) -> Self {
        Self {
            x,
            y,
            width,
            height,
        }
    }

    fn right(&self) -> i64 {
        self.x as i64 + self.width as i64
    }

    fn bottom(&self) -> i64 {
        self.y as i64 + self.height as i64
    }

    /// Area of the overlap with `other`, in square pixels. Used only to decide
    /// which monitor a window "is on", so the units never leave this module.
    fn intersection_area(&self, other: &Rect) -> i64 {
        let width = (self.right().min(other.right()) - (self.x.max(other.x)) as i64).max(0);
        let height = (self.bottom().min(other.bottom()) - (self.y.max(other.y)) as i64).max(0);
        width * height
    }
}

/// Fit `window` inside whichever work area it mostly occupies.
///
/// When no work area contains any part of it — the monitor it was last saved on
/// has been unplugged — it is re-centered on the first (primary) one rather
/// than dragged to the nearest edge. Q101 notes that the Job Object kill path
/// means geometry is often *not* saved on a crash, so landing on stale-but-
/// plausible coordinates is the normal case, not the exception.
///
/// Returns `window` unchanged when `work_areas` is empty: with no information
/// about the display layout, moving the window is strictly worse than leaving
/// it where the user last had it.
pub fn clamp_to_work_areas(window: Rect, work_areas: &[Rect]) -> Rect {
    let Some(primary) = work_areas.first() else {
        return window;
    };

    let best = work_areas
        .iter()
        .max_by_key(|area| window.intersection_area(area));

    let (area, recenter) = match best {
        Some(area) if window.intersection_area(area) > 0 => (area, false),
        _ => (primary, true),
    };

    // Never grow past the work area; never shrink below the configured minimum
    // unless the work area itself is smaller, in which case the work area wins.
    // A minimum that exceeds the screen would put the titlebar offscreen, which
    // is the exact failure Q46 called out on a 1366x768 laptop.
    let width = window
        .width
        .min(area.width)
        .max(MIN_WIDTH.min(area.width))
        .max(1);
    let height = window
        .height
        .min(area.height)
        .max(MIN_HEIGHT.min(area.height))
        .max(1);

    let max_x = area.x + (area.width.saturating_sub(width)) as i32;
    let max_y = area.y + (area.height.saturating_sub(height)) as i32;

    let (x, y) = if recenter {
        (
            area.x + (area.width.saturating_sub(width) / 2) as i32,
            area.y + (area.height.saturating_sub(height) / 2) as i32,
        )
    } else {
        (window.x.clamp(area.x, max_x), window.y.clamp(area.y, max_y))
    };

    Rect::new(x, y, width, height)
}

/// Clamp the main window's geometry, then show and focus it.
///
/// Idempotent: the first caller wins and the rest return immediately.
pub fn reveal(app: &AppHandle) {
    if REVEALED.swap(true, Ordering::SeqCst) {
        return;
    }

    let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) else {
        tracing::error!("window `{MAIN_WINDOW_LABEL}` is missing; nothing to reveal");
        return;
    };

    match current_geometry(&window) {
        Ok(current) => {
            let areas = work_areas(&window);
            let clamped = clamp_to_work_areas(current, &areas);

            if clamped != current {
                tracing::info!(
                    from = ?current,
                    to = ?clamped,
                    monitors = areas.len(),
                    "restored geometry did not fit the current display layout; clamped"
                );
                let _ = window.set_size(PhysicalSize::new(clamped.width, clamped.height));
                let _ = window.set_position(PhysicalPosition::new(clamped.x, clamped.y));
            }
        }
        Err(error) => {
            // Showing an unclamped window beats not showing one.
            tracing::warn!(%error, "could not read window geometry; showing unclamped");
        }
    }

    if let Err(error) = window.show() {
        tracing::error!(%error, "failed to show the main window");
    }
    let _ = window.set_focus();

    tracing::info!("main window revealed");
}

/// Bring the existing window forward. Q22: a second launch focuses the first
/// instance and exits; it never opens a second window onto one SQLite file.
pub fn focus_existing(app: &AppHandle) {
    let Some(window) = app.get_webview_window(MAIN_WINDOW_LABEL) else {
        return;
    };

    // Order matters: a minimised window ignores `set_focus`.
    let _ = window.unminimize();
    let _ = window.show();
    let _ = window.set_focus();
}

fn current_geometry(window: &tauri::WebviewWindow) -> tauri::Result<Rect> {
    let position = window.outer_position()?;
    let size = window.outer_size()?;
    Ok(Rect::new(position.x, position.y, size.width, size.height))
}

/// The usable area of every attached monitor, taskbar excluded.
///
/// The primary monitor is placed first so [`clamp_to_work_areas`] re-centers
/// there when the saved monitor is gone.
fn work_areas(window: &tauri::WebviewWindow) -> Vec<Rect> {
    let monitors = match window.available_monitors() {
        Ok(monitors) => monitors,
        Err(error) => {
            tracing::warn!(%error, "could not enumerate monitors");
            return Vec::new();
        }
    };

    let primary = window.primary_monitor().ok().flatten();
    let primary_name = primary.as_ref().and_then(|m| m.name()).cloned();

    let mut areas: Vec<(bool, Rect)> = monitors
        .iter()
        .map(|monitor| {
            let is_primary = primary_name.is_some() && monitor.name() == primary_name.as_ref();
            let area = monitor.work_area();
            (
                is_primary,
                Rect::new(
                    area.position.x,
                    area.position.y,
                    area.size.width,
                    area.size.height,
                ),
            )
        })
        .collect();

    areas.sort_by_key(|(is_primary, _)| !is_primary);
    areas.into_iter().map(|(_, area)| area).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const LAPTOP: Rect = Rect {
        x: 0,
        y: 0,
        width: 1366,
        height: 728,
    };
    const DESKTOP: Rect = Rect {
        x: 0,
        y: 0,
        width: 1920,
        height: 1040,
    };
    const SECONDARY: Rect = Rect {
        x: 1920,
        y: 0,
        width: 2560,
        height: 1400,
    };

    #[test]
    fn a_fitting_window_is_left_alone() {
        let window = Rect::new(200, 100, 1440, 900);
        assert_eq!(clamp_to_work_areas(window, &[DESKTOP]), window);
    }

    #[test]
    fn no_monitor_information_means_no_change() {
        let window = Rect::new(-9000, -9000, 1440, 900);
        assert_eq!(clamp_to_work_areas(window, &[]), window);
    }

    #[test]
    fn oversized_window_shrinks_to_the_work_area() {
        // Q46's 1366x768 laptop: 1440x900 does not fit and Tauri centers
        // without clamping, putting the titlebar offscreen.
        let clamped = clamp_to_work_areas(Rect::new(0, 0, 1440, 900), &[LAPTOP]);
        assert_eq!(clamped.width, LAPTOP.width);
        assert_eq!(clamped.height, LAPTOP.height);
        assert_eq!((clamped.x, clamped.y), (0, 0));
    }

    #[test]
    fn size_is_clamped_not_only_position() {
        // Q101 verbatim: restored at 2560x1400 onto a 1920x1080 panel.
        let clamped = clamp_to_work_areas(Rect::new(0, 0, 2560, 1400), &[DESKTOP]);
        assert_eq!(clamped.width, DESKTOP.width);
        assert_eq!(clamped.height, DESKTOP.height);
    }

    #[test]
    fn unplugged_monitor_recenters_on_primary() {
        // Saved on the secondary panel, which is now gone.
        let window = Rect::new(2400, 300, 1440, 900);
        let clamped = clamp_to_work_areas(window, &[DESKTOP]);

        assert_eq!(clamped.width, 1440);
        assert_eq!(clamped.height, 900);
        assert_eq!(clamped.x, (1920 - 1440) / 2);
        assert_eq!(clamped.y, (1040 - 900) / 2);
    }

    #[test]
    fn a_window_on_the_secondary_monitor_stays_there() {
        let window = Rect::new(2100, 200, 1440, 900);
        assert_eq!(
            clamp_to_work_areas(window, &[DESKTOP, SECONDARY]),
            window,
            "a window fully inside a secondary work area must not be moved"
        );
    }

    #[test]
    fn a_window_straddling_two_monitors_is_pulled_onto_the_larger_overlap() {
        // Mostly on the secondary: 1920..3260 overlaps the secondary by 1340px
        // and the primary by 100px.
        let window = Rect::new(1820, 100, 1440, 900);
        let clamped = clamp_to_work_areas(window, &[DESKTOP, SECONDARY]);
        assert_eq!(clamped.x, SECONDARY.x, "should snap onto the secondary");
        assert_eq!(clamped.y, 100, "vertical position already fits");
    }

    #[test]
    fn a_negative_position_is_pulled_back_on_screen() {
        let clamped = clamp_to_work_areas(Rect::new(-500, -300, 1440, 900), &[DESKTOP]);
        assert_eq!((clamped.x, clamped.y), (0, 0));
    }

    #[test]
    fn the_bottom_right_corner_stays_reachable() {
        let clamped = clamp_to_work_areas(Rect::new(1900, 1000, 1440, 900), &[DESKTOP]);
        assert_eq!(clamped.x, (DESKTOP.width - 1440) as i32);
        assert_eq!(clamped.y, (DESKTOP.height - 900) as i32);
    }

    #[test]
    fn the_minimum_size_is_honoured_when_the_screen_allows_it() {
        let clamped = clamp_to_work_areas(Rect::new(0, 0, 400, 300), &[DESKTOP]);
        assert_eq!(clamped.width, MIN_WIDTH);
        assert_eq!(clamped.height, MIN_HEIGHT);
    }

    #[test]
    fn a_work_area_smaller_than_the_minimum_beats_the_minimum() {
        let tiny = Rect::new(0, 0, 800, 600);
        let clamped = clamp_to_work_areas(Rect::new(0, 0, 1440, 900), &[tiny]);
        assert_eq!(clamped.width, 800);
        assert_eq!(clamped.height, 600);
        assert!(clamped.width < MIN_WIDTH, "the screen has to win here");
    }

    /// The constants above and `tauri.conf.json` describe the same window.
    /// Nothing at runtime would notice them disagreeing until a restored
    /// window came back a few pixels smaller than the manager allows.
    #[test]
    fn min_size_matches_the_tauri_config() {
        let raw = include_str!("../tauri.conf.json");
        let config: serde_json::Value = serde_json::from_str(raw).expect("tauri.conf.json parses");

        let windows = config["app"]["windows"]
            .as_array()
            .expect("app.windows is an array");
        let main = windows
            .iter()
            .find(|w| w["label"] == MAIN_WINDOW_LABEL)
            .expect("a window labelled `main` is declared");

        assert_eq!(main["minWidth"].as_u64(), Some(MIN_WIDTH as u64));
        assert_eq!(main["minHeight"].as_u64(), Some(MIN_HEIGHT as u64));

        // The default size must itself satisfy the minimum, or the very first
        // launch on a clean profile starts out of spec.
        let width = main["width"].as_u64().expect("width is declared");
        let height = main["height"].as_u64().expect("height is declared");
        assert!(width >= MIN_WIDTH as u64, "default width {width} < minimum");
        assert!(
            height >= MIN_HEIGHT as u64,
            "default height {height} < minimum"
        );

        // Q54: the window must start hidden, or the boot state renders behind
        // a white flash. This is one JSON key away from silently regressing.
        assert_eq!(
            main["visible"].as_bool(),
            Some(false),
            "the main window must be created hidden (Q54)"
        );
    }
}
