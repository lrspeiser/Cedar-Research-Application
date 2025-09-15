# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect Qt (PySide6) resources so QtWebEngine works inside the bundle
qt_datas, qt_bins, qt_hidden = collect_all('PySide6')
shib_datas, shib_bins, shib_hidden = collect_all('shiboken6')

datas = qt_datas + shib_datas
binaries = qt_bins + shib_bins
hiddenimports = list(set(qt_hidden + shib_hidden + [
    'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel',
]))

project_dir = os.path.abspath(os.path.dirname(__file__))
repo_root = os.path.abspath(os.path.join(project_dir, '..'))

a = Analysis([
    os.path.join(repo_root, 'cedarqt.py'),
],
    pathex=[repo_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='CedarPy',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=False,
          console=False )