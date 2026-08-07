# 27 — PyInstaller sidecar and bundled FFmpeg

**What to build:** The FastAPI backend freezes into a single sidecar executable that boots, binds its port, runs migrations, and serves the API exactly as the development process does. Static FFmpeg and FFprobe binaries ship alongside it with correct licensing attribution, and are resolved by bundled path — never from PATH.

This is where the known PyInstaller risk gets settled: freezing FastAPI, uvicorn, and SQLAlchemy on Windows needs hidden-imports tuning, and if that proves unworkable the fallback is an embedded runtime. Whichever way it lands, record it.

Note: this ticket is technically independent of the P2–P5 feature work, but is deliberately sequenced after P5 to match the project's phase order.

**Blocked by:** 26 — Workspace relocation.

**Status:** done

- [x] The backend builds to a sidecar executable that starts, binds a free port, runs migrations, and serves the API
- [x] The frozen build works with no Python installed on the machine
- [x] FFmpeg and FFprobe are bundled as static binaries and resolved by bundled path, with PATH explicitly not consulted
- [x] Licensing attribution for the bundled binaries ships with the application
- [x] A render runs successfully end to end using the bundled binaries from the frozen backend
- [x] The build is reproducible from a documented command and runs in CI or is documented as a manual release step
- [x] The outcome of the freezing risk is recorded as an ADR, including any hidden-imports tuning or a fallback decision
