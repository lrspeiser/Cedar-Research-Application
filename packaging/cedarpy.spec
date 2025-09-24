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


datas = []
binaries = []
hiddenimports = []
for m in modules:
    d, b, h = collect_all(m)
    datas += d
    binaries += b
    hiddenimports += h

# Ensure top-level PySide6 import is present for runtime
hiddenimports = list(set(hiddenimports + ['PySide6']))

# Safety: filter out any Qt3D frameworks that may have been collected indirectly
# (avoid macOS frameworks symlink collisions)

def _is_qt3d_entry(entry):
    try:
        return 'Qt3D' in str(entry)
    except Exception:
        return False

binaries = [e for e in binaries if not _is_qt3d_entry(e)]
datas = [e for e in datas if not _is_qt3d_entry(e)]

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
hiddenimports = list(set(hiddenimports + ['main', 'main_mini', 'cedar_app.main_impl_full'] + _backend_hidden))

# Exclude unused Qt3D modules to avoid macOS framework symlink collisions (FileExistsError)
# See: known PyInstaller + Qt frameworks dedup issues on macOS
excludes = [
    'PySide6.Qt3DCore',
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DExtras',
]

# Resolve repo root relative to current working directory when PyInstaller runs
repo_root = os.path.abspath(os.getcwd())

# Ensure main.py and main_mini.py are present as data files for cedarqt fallback
for fname in ['main.py', 'main_mini.py', 'page.html']:
    try:
        datas.append((os.path.join(repo_root, fname), '.'))
    except Exception:
        pass

# Include UI asset directories if present (assets/ and static/ at repo root)
for _ui_dir_name in ['assets', 'static']:
    try:
        _dir = os.path.join(repo_root, _ui_dir_name)
        if os.path.isdir(_dir):
            for root, _dirs, _files in os.walk(_dir):
                for _f in _files:
                    _src = os.path.join(root, _f)
                    _rel = os.path.relpath(root, repo_root)
                    datas.append((_src, _rel))
    except Exception:
        pass

a = Analysis([
    os.path.join(repo_root, 'cedarqt.py'),
],
    pathex=[repo_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
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
