# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

project_root = Path(SPECPATH)

# Native tools inherited from the host PATH (e.g. Poppler) can supply DLLs
# with Windows system names but incompatible exports, notably icuuc.dll.
# Limit dependency discovery to this Python environment and Windows itself.
if sys.platform == "win32":
    windows_dir = Path(os.environ["SystemRoot"])
    os.environ["PATH"] = os.pathsep.join(str(path) for path in (
        Path(sys.executable).parent,
        Path(sys.base_prefix),
        windows_dir / "System32",
        windows_dir,
    ))

assets_dir = project_root / "assets"
icon_file = assets_dir / "icon.ico"

datas = []

if assets_dir.exists():
    datas.append((str(assets_dir), "assets"))

a = Analysis(
    ["run.py"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SunriseCast",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_file) if icon_file.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=["*.dll", "*.pyd"],
    name="SunriseCast",
)
