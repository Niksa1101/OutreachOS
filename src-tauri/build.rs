//! Build script.
//!
//! The only thing here beyond the stock `tauri_build::build()` is the Windows
//! application manifest. Q116 asks for `longPathAware` as belt-and-braces
//! against `MAX_PATH`; overriding the manifest means restating everything
//! `tauri-build` would otherwise supply, so the whole document is spelled out
//! below rather than patched.
//!
//! `longPathAware` only takes effect when the machine-wide `LongPathsEnabled`
//! policy is on, which the app cannot set without admin, and the static FFmpeg
//! builds P1 will ship are not manifested for it regardless. Pick-time path
//! length validation (checkpoint 4) is the actual defense — this is the cheap
//! second layer, not the first.

const WINDOWS_MANIFEST: &str = r#"<?xml version="1.0" encoding="utf-8"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <!-- The app writes only to the user-chosen workspace and to
             %LOCALAPPDATA%. It must never prompt for elevation; a workspace
             that needs admin to write is a workspace we refuse at pick time. -->
        <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <!-- Windows 10/11 -->
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" />
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}" />
      <supportedOS Id="{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}" />
      <supportedOS Id="{35138b9a-5d96-4fbd-8e2d-a2440225f93a}" />
      <supportedOS Id="{e2011457-1546-43c5-a5fe-008deee3d3f0}" />
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/pm</dpiAware>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2, PerMonitor</dpiAwareness>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
      <activeCodePage xmlns="http://schemas.microsoft.com/SMI/2019/WindowsSettings">UTF-8</activeCodePage>
    </windowsSettings>
  </application>
  <dependency>
    <dependentAssembly>
      <!-- NOT optional, and not boilerplate. Tauri's default `common-controls-v6`
           feature calls `TaskDialogIndirect`, which only exists in comctl32
           version 6. Without this element the process links against an export
           the v5 DLL does not have and dies at startup with
           STATUS_ENTRYPOINT_NOT_FOUND (0xc0000139) before `main` runs — no log
           line, no window, no clue. It is here because overriding the manifest
           at all means restating everything `tauri-build` would have supplied. -->
      <assemblyIdentity
        type="win32"
        name="Microsoft.Windows.Common-Controls"
        version="6.0.0.0"
        processorArchitecture="*"
        publicKeyToken="6595b64144ccf1df"
        language="*"
      />
    </dependentAssembly>
  </dependency>
</assembly>
"#;

fn main() {
    let attributes = tauri_build::Attributes::new()
        .windows_attributes(tauri_build::WindowsAttributes::new().app_manifest(WINDOWS_MANIFEST));

    tauri_build::try_build(attributes).expect("failed to run tauri-build");
}
