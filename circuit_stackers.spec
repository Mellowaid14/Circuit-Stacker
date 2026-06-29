# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path.cwd()
src_root = project_root / "src"
package_root = src_root / "circuit_stackers"
icon_path = package_root / "assets" / "circuit_stacker_icon.ico"

datas = collect_data_files("circuit_stackers")
datas.append((str(project_root / "README.md"), "."))

analysis = Analysis(
    [str(project_root / "launch_circuit_stackers.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["customtkinter", "PIL"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="CircuitStackers",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.exists() else None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CircuitStackers",
)
