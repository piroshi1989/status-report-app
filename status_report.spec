# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onefile ビルド定義。

    pyinstaller status_report.spec

テンプレート・静的ファイル・フォント・schema.sql を同梱し、単一 exe を生成する。
"""

from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("app/templates", "app/templates"),
    ("app/static", "app/static"),
    ("app/schema.sql", "app"),
]

hiddenimports = (
    collect_submodules("uvicorn")
    + ["app.main", "anyio", "sqlite3", "xlrd", "openpyxl"]
)

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="状況報告書アプリ",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 圧縮は Windows Defender / SmartScreen の誤検知率を上げるため無効化する。
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
