# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect only the PySide6 components we actually use to avoid framework duplication issues
modules = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebChannel',
]

# Ensure the PySide6 namespace package itself is included so imports like
# "import PySide6" succeed at runtime (some hooks only pull submodules).
_pyside_d, _pyside_b, _pyside_h = collect_all('PySide6')


datas = []
binaries = []
hiddenimports = []
for m in modules:
    d, b, h = collect_all(m)
    datas += d
    binaries += b
    hiddenimports += h

# Merge the top-level PySide6 package collections
_datas = list(_pyside_d) if _pyside_d else []
_binaries = list(_pyside_b) if _pyside_b else []
_hidden = list(_pyside_h) if _pyside_h else []

if _datas:
    datas += _datas
if _binaries:
    binaries += _binaries
if _hidden:
    hiddenimports += _hidden
# Also ensure the namespace import is present explicitly
hiddenimports = list(set(hiddenimports + ['PySide6']))

# Also collect shiboken6 support libs
shib_d, shib_b, shib_h = collect_all('shiboken6')
datas += shib_d
binaries += shib_b
hiddenimports += shib_h

# Ensure server framework dependencies are included in the bundle even when main.py is loaded via fallback
for pkg in [
    'fastapi',
    'starlette',
    'pydantic',
    'pydantic_core',
    'typing_extensions',
    'anyio',
    'sqlalchemy',
    'uvicorn',
    'websockets',
    'httpx',
    'certifi',
    'sniffio',
    'h11',
    'click',
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Explicitly include backend framework modules as hidden imports
_backend_hidden = [
    'fastapi', 'starlette', 'pydantic', 'pydantic_core', 'typing_extensions',
    'anyio', 'sqlalchemy', 'uvicorn', 'websockets', 'httpx', 'certifi', 'sniffio', 'h11', 'click'
]
hiddenimports = list(set(hiddenimports + ['main', 'main_mini'] + _backend_hidden))

# Resolve repo root relative to current working directory when PyInstaller runs
repo_root = os.path.abspath(os.getcwd())

# Ensure main.py and main_mini.py are present as data files for cedarqt fallback
for fname in ['main.py', 'main_mini.py']:
    try:
        datas.append((os.path.join(repo_root, fname), '.'))
    except Exception:
        pass

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
          exclude_binaries=True,
          name='CedarPy',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=False,
          console=False)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=False,
               name='CedarPy')
app = BUNDLE(coll,
             name='CedarPy.app',
             icon=None,
             bundle_identifier='is.grue.cedarpy')
