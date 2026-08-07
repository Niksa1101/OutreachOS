# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the OutreachOS backend sidecar (ADR-0006: onedir).

Produces ``outreachos-backend.exe`` and ``outreachos-render.exe`` sharing one
``_internal/`` tree. Stage the ``dist/outreachos-backend/`` folder to
``<repo>/dist/backend/`` for Tauri bundle resources.
"""

from pathlib import Path

from PyInstaller.building.build_main import COLLECT, EXE, MERGE, Analysis, PYZ
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
backend_root = Path(SPECPATH)
src_root = backend_root / "src"

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("sqlalchemy")
    + [
        "alembic.runtime.migration",
        "alembic.script",
        "pydantic_settings",
        "anyio._backends._asyncio",
        "outreachos_backend.core.models",
        "outreachos_backend.modules.video_composer.models",
    ]
)

datas = [
    (str(backend_root / "alembic"), "alembic"),
    (str(backend_root / "alembic.ini"), "."),
]

pathex = [str(src_root)]

a_backend = Analysis(
    [str(src_root / "outreachos_backend" / "__main__.py")],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

a_render = Analysis(
    [str(src_root / "outreachos_backend" / "render_entry.py")],
    pathex=pathex,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

MERGE(
    (a_backend, "outreachos-backend", "outreachos-backend"),
    (a_render, "outreachos-render", "outreachos-render"),
)

pyz_backend = PYZ(a_backend.pure, a_backend.zipped_data, cipher=block_cipher)
pyz_render = PYZ(a_render.pure, a_render.zipped_data, cipher=block_cipher)

exe_backend = EXE(
    pyz_backend,
    a_backend.scripts,
    [],
    exclude_binaries=True,
    name="outreachos-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_render = EXE(
    pyz_render,
    a_render.scripts,
    [],
    exclude_binaries=True,
    name="outreachos-render",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# MERGE shares a_backend's dependency graph with a_render; COLLECT takes only
# a_backend's binaries/zipfiles/datas. The render entry must remain a subgraph
# of the backend's — adding a_render.binaries here would duplicate targets, not
# add files. Guard: test_frozen_render_cli_runs_batch in test_frozen_sidecar.py.
coll = COLLECT(
    exe_backend,
    exe_render,
    a_backend.binaries,
    a_backend.zipfiles,
    a_backend.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="outreachos-backend",
)
