// Release builds must not allocate a console. Q49 makes the same point about
// `CREATE_NO_WINDOW` for the sidecar: a console window flashing on launch is
// the most visible possible symptom of an otherwise invisible decision.
// Debug builds keep it — that is where sidecar stdout is read by eye.
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

fn main() {
    outreachos_lib::run();
}
