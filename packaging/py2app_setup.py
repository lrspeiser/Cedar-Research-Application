from setuptools import setup

APP = ['run_cedarpy.py']
OPTIONS = {
    # We run headless and open the browser from run_cedarpy
    'argv_emulation': False,
    'includes': [
        'main',
        'sqlite3',
        'typing_extensions', 
        'certifi',
        'multiprocessing',
        'multiprocessing.pool',
        'multiprocessing.dummy',
        'starlette',
        'starlette.applications',
        'starlette.routing',
        'starlette.responses',
        'starlette.middleware',
        'starlette.middleware.cors',
        'click'
    ],
    'packages': [
        'uvicorn', 
        'fastapi', 
        'sqlalchemy', 
        'pydantic',
        'pydantic_core',
        'anyio', 
        'websockets', 
        'h11',
        'sniffio',
        'starlette'
    ],
    'plist': {
        'CFBundleName': 'CedarPy',
        'CFBundleIdentifier': 'is.grue.cedarpy',
        'LSBackgroundOnly': False,
        'LSUIElement': True,  # Run without dock icon
    },
    'iconfile': None,  # Don't require an icon for now
}

setup(
    app=APP,
    options={'py2app': OPTIONS},
    data_files=['main.py', 'PROJECT_SEPARATION_README.md'],
    setup_requires=['py2app'],
)
