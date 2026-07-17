# PyInstaller spec for the Question Bank desktop build.
#
# Build with:  uv run pyinstaller run.spec --clean
#
# Produces a single console executable that runs migrations, the API, the
# background worker and serves the bundled Nuxt SPA. Keep console=True until the
# build is verified, then flip to False for a windowed app.
#
# Prerequisites:
#   1. Build the frontend:  (cd ../frontend && pnpm generate)
#   2. Copy/point the output so the datas entry below can find it.

from PyInstaller.utils.hooks import collect_all, collect_submodules

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
hiddenimports += [
    "aiosqlite",
    "passlib.handlers.bcrypt",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
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
    console=True,  # set to False once verified
    disable_windowed_traceback=False,
    argv_emulation=False,
)
