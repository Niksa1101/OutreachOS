# ADR-0007: FFmpeg GPL static build

**Status:** Accepted — **supersedes p0-questionnaire.md Q52**

---

## Context

P0's Q52 pinned an **LGPL** BtbN build on the reasoning that distributing a GPL
binary carries a source-offer obligation the LGPL shared build does not. That
reasoning was incomplete.

Tech.md §5.1/§5.2/§7 and PRD §8 all name **libx264** as the CPU fallback and
the golden-frame test encoder. libx264 is GPL-only. FFmpeg's `configure` refuses
`--enable-libx264` without `--enable-gpl`, so an LGPL build **cannot contain
the encoder the specification names**.

The LGPL alternative (libopenh264) has no CRF control, is weaker on
screen-recording content, and sits *outside* Cisco's MPEG-LA umbrella once
statically linked — a worse patent posture and worse video, to avoid a written
source offer.

## Decision

Take the BtbN **`win64-gpl` static build** — two self-contained executables
(`ffmpeg.exe`, `ffprobe.exe`). The DLL-resolution hazard that came with the
LGPL *shared* build disappears entirely.

Pin an immutable release **tag** (never `latest`), verify with `Get-FileHash`
against a pinned SHA256, and archive the matching FFmpeg source tarball alongside
the binaries for GPL compliance.

## Alternatives considered

- **Keep LGPL + libopenh264.** Rejected: no CRF, worse quality on the dominant
  input class, worse patent posture when statically linked.
- **LGPL shared build + libx264 from elsewhere.** Rejected: two binary sources,
  two license regimes, and the shared-build DLL path resolution hazard returns.
- **GPL shared build.** Rejected: static executables eliminate the DLL hazard
  and simplify PyInstaller bundling in P6.

## Consequences

- GPL source-offer obligations apply; the compliance artifact is built now rather
  than retrofitted at P6.
- `vendor/README.md` and `scripts/fetch-ffmpeg.ps1` encode GPL + static, not
  LGPL + shared.
- Golden-frame tests force `libx264`; hardware encoders remain non-deterministic.
- Version mismatch against the pin warns at runtime and **hard-fails under
  `-m render`**.

## References

p1-questionnaire Q127–Q132. Tech.md §5, §7. PRD §8 Risk #3. ADR-0004.
