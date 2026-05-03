# Build command (run from project root on Windows):
#   pip install pyinstaller
#   pyinstaller backend.spec --noconfirm --distpath desktop/tauri/src-tauri/binaries
#
# Runtime files the user must place next to the .exe after building
# (code reads them via sys.executable.parent, not sys._MEIPASS):
#   .env                  — GEMINI_API_KEY and any other secrets
#   core/prompt.txt       — system prompt loaded by main.py via BASE_DIR
#   config/api_keys.json  — API config read by protocol_manager / ws_ui
#   config/protocols.json — protocol definitions

block_cipher = None

from pathlib import Path
ROOT = Path(SPECPATH).resolve()

a = Analysis(
    [str(ROOT / 'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # These land in sys._MEIPASS — covers __file__-relative lookups (e.g. ws_ui.py).
        # Also copy them next to the .exe for BASE_DIR-relative lookups in main.py.
        (str(ROOT / 'config' / 'api_keys.json'),  'config'),
        (str(ROOT / 'config' / 'protocols.json'), 'config'),
        (str(ROOT / 'core'   / 'prompt.txt'),     'core'),
    ],
    hiddenimports=[
        # Google GenAI / auth
        'google.genai',
        'google.generativeai',
        'google.api_core',
        'google.auth',
        'google.auth.transport',
        'google.auth.transport.requests',
        # WebSocket (ws_ui.py + ARIA)
        'websockets',
        'websockets.legacy',
        'websockets.legacy.server',
        'websockets.legacy.client',
        # FastAPI / uvicorn (ARIA server)
        'fastapi',
        'uvicorn',
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
        # Vector memory
        'sentence_transformers',
        'qdrant_client',
        'qdrant_client.local',
        'qdrant_client.local.local_collection',
        # Audio
        'pyaudio',
        # Windows-specific
        'comtypes',
        'pycaw',
        'win10toast',
        # UI automation
        'pyautogui',
        'pyperclip',
        # Screen capture / vision
        'mss',
        'cv2',
        'numpy',
        'PIL',
        'PIL.Image',
        # Web / search
        'requests',
        'bs4',
        'duckduckgo_search',
        'youtube_transcript_api',
        # Misc
        'psutil',
        'dotenv',
        'send2trash',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / 'hook_utf8.py')],
    excludes=['tkinter', 'matplotlib', 'scipy', 'test'],
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
    name='vector-backend-x86_64-pc-windows-msvc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
