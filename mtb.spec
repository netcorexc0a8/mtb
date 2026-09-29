# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller --clean mtb.spec  ->  dist/mtb[.exe]
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

datas = collect_data_files("tzdata") + copy_metadata("apscheduler") + [("mtb/web", "mtb/web")]

a = Analysis(
    ["packaging/entry.py"],
    pathex=[SPECPATH],
    datas=datas,
    hiddenimports=["tzdata"],
    excludes=["tkinter", "unittest", "pydoc_data"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="mtb",
    console=True,
    upx=False,
    strip=False,
)
