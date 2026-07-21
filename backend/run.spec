# PyInstaller spec for the Question Bank desktop build.
#
# Build with:  uv run pyinstaller run.spec --clean
#
# Produces a single windowed executable that shows a system-tray icon, runs
# migrations, the API, the background worker and serves the bundled Nuxt SPA.
#
# Prerequisites:
#   1. Build the frontend:  (cd ../frontend && pnpm generate)
#   2. Copy/point the output so the datas entry below can find it.

from PyInstaller.utils.hooks import collect_all, collect_submodules

import os
import sys

# Make ``app`` importable so we can generate the brand icon below.
sys.path.insert(0, os.path.abspath("."))

# Render the brand logo (frontend/public/logo.svg) to a multi-size .ico that is
# embedded into the executable. Drawn with PIL, so no SVG renderer is required.
_ICON = os.path.abspath(os.path.join("build", "logo.ico"))
os.makedirs(os.path.dirname(_ICON), exist_ok=True)
try:
    from app.branding import save_ico

    save_ico(_ICON)
except Exception:
    _ICON = None  # fall back to the default PyInstaller icon

datas, binaries, hiddenimports = [], [], []

# Packages that ship data files / native libs / dynamically imported submodules
# which PyInstaller's static analysis cannot discover on its own.
for pkg in [
    "chromadb",
    "onnxruntime",
    "tokenizers",
    "pypandoc",
    "google",
    "openai",
    "passlib",
    "aiosqlite",
    "aiomysql",
    "pystray",
    "PIL",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        # Optional packages (e.g. aiomysql if a build targets SQLite-only) may
        # be absent; skip them rather than failing the whole build.
        pass

# Alembic migration scripts, mail/doc templates and the built frontend must be
# shipped as data (they are read at runtime, not imported).
datas += [
    ("alembic", "alembic"),
    ("alembic.ini", "."),
    ("app/templates", "app/templates"),
    ("../frontend/.output/public", "frontend"),
]

# App modules are frequently referenced dynamically (CRUD, models, endpoints).
hiddenimports += collect_submodules("app")
hiddenimports += collect_submodules("scripts")
hiddenimports += [
    "aiosqlite",
    "passlib.handlers.bcrypt",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "pystray._win32",
]

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="question-bank",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # tray app: no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=_ICON,
)
