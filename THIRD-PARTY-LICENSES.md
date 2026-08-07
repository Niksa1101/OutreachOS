# Third-party licenses

OutreachOS ships third-party software whose licenses require attribution.
This file accompanies the Windows installer and staged bundle resources.

---

## FFmpeg and FFprobe (GPL-3.0-or-later)

**Component:** Static `ffmpeg.exe` and `ffprobe.exe`  
**Build:** BtbN FFmpeg Builds — `win64-gpl`  
**Pinned release:** `autobuild-2026-08-03-14-02`  
**Version line:** `ffmpeg version n7.1.5-12-g1fdbca85aa`  
**Fetched by:** `scripts/fetch-ffmpeg.ps1`

These executables are statically linked against GPL libraries including
**libx264**, which is the named CPU fallback encoder in the product
specification (ADR-0007).

**Source code:** The matching FFmpeg source tarball is archived locally by the
fetch script at `vendor/ffmpeg/source/` (not committed to git). It is also
available from the same GitHub release:

https://github.com/BtbN/FFmpeg-Builds/releases/tag/autobuild-2026-08-03-14-02

**License text:** GNU General Public License version 3 or later  
https://www.gnu.org/licenses/gpl-3.0.html

This program uses FFmpeg. FFmpeg is licensed under the GNU General Public
License (GPL) version 3. Corresponding source code is offered alongside the
application as described above.

---

## Inter Variable (OFL-1.1)

**Component:** UI sans-serif typeface  
**Package:** `@fontsource-variable/inter` (bundled in the frontend build)  
**License:** SIL Open Font License 1.1  
https://scripts.sil.org/OFL

---

## JetBrains Mono Variable (OFL-1.1)

**Component:** UI monospace typeface  
**Package:** `@fontsource-variable/jetbrains-mono` (bundled in the frontend build)  
**License:** SIL Open Font License 1.1  
https://scripts.sil.org/OFL
