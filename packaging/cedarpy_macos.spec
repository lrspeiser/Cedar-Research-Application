# -*- mode: python ; coding: utf-8 -*-

import sys
import os

block_cipher = None

# Build datas list including core files and optional UI assets (assets/, static/)
_datas = [
    ('../main.py', '.'),
    ('../PROJECT_SEPARATION_README.md', '.'),
    ('../page.html', '.'),
]
try:
    _repo = os.path.abspath('..')
    for _ui_dir_name in ['assets', 'static']:
        _dir = os.path.join(_repo, _ui_dir_name)
        if os.path.isdir(_dir):
            for root, _dirs, _files in os.walk(_dir):
                for _f in _files:
                    _src = os.path.join(root, _f)
                    _rel = os.path.relpath(root, _repo)
                    _datas.append((_src, _rel))
except Exception:
    pass

a = Analysis(
    ['../run_cedarpy.py'],
    pathex=[os.path.abspath('..')],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'starlette',
        'starlette.applications',
        'starlette.routing',
        'starlette.responses',
        'starlette.middleware',
        'starlette.middleware.cors',
        'sqlalchemy.sql.default_comparator',
        'sqlalchemy.ext.baked',
        'h11._impl',
        'websockets.legacy',
'websockets.legacy.server',
        'click',
        'anyio._backends._asyncio',
        'multiprocessing',
        'multiprocessing.pool',
        'multipart',  # python-multipart for FastAPI forms/uploads
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CedarPy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # Headless app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='CedarPy',
)

app = BUNDLE(
    coll,
    name='CedarPy.app',
    icon=None,
    bundle_identifier='is.grue.cedarpy',
    info_plist={
        'CFBundleName': 'CedarPy',
        'CFBundleDisplayName': 'CedarPy',
        'CFBundleIdentifier': 'is.grue.cedarpy',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSBackgroundOnly': False,
        'LSUIElement': True,  # Run without dock icon
    },
)