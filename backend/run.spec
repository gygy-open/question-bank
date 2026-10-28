# PyInstaller spec for the QuestionBank desktop build.
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

# Channel of the build: pre-release versions are the preview app (app/channel.py).
# Pass frozen=True because the spec itself doesn't run frozen.
try:
    from app.channel import is_preview

    _PREVIEW = is_preview(frozen=True)
except Exception:
    _PREVIEW = False

# Render the brand logo (frontend/public/logo.svg) to a multi-size .ico that is
# embedded into the executable. Drawn with PIL, so no SVG renderer is required.
# Preview builds get the amber variant. deploy/windows/installer.iss reuses this file.
_ICON = os.path.abspath(os.path.join("build", "logo.ico"))
os.makedirs(os.path.dirname(_ICON), exist_ok=True)
try:
    from app.branding import save_ico

    save_ico(_ICON, preview=_PREVIEW)
except Exception:
    _ICON = None  # fall back to the default PyInstaller icon

# Startup splash: the onefile bootloader unpacks hundreds of MB before Python even starts (minutes on
# a first launch with antivirus scanning), during which nothing else is visible. The splash is shown
# by the bootloader and closed from app.tray once the server is ready. Needs Tcl/Tk at build time.
_SPLASH = None
try:
    import tkinter  # noqa: F401

    from app.branding import save_splash

    _splash_img = os.path.abspath(os.path.join("build", "splash.png"))
    save_splash(_splash_img, preview=_PREVIEW)
    _SPLASH = Splash(
        _splash_img,
        binaries=[],
        datas=[],
        text_pos=(30, 150),
        text_size=11,
        text_color="#374151",
        text_default="QuestionBank 正在启动（首次较慢，请稍候）· Starting…",
        always_on_top=False,
    )
except Exception:
    _SPLASH = None  # build without a splash rather than failing

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
    "latex2mathml",
    "mutagen",
    # MCP 服务(/api/mcp):SDK 内部有按协议版本动态加载的模块,并在运行时读取包元数据
    "mcp",
    "mcp_types",
    "sse_starlette",
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

# Alembic migration scripts and the built frontend must be shipped as data
# (they are read at runtime, not imported).
datas += [
    ("alembic", "alembic"),
    ("alembic.ini", "."),
    ("../frontend/.output/public", "frontend"),
    # Vendored MathType MTEF→MathML parser loads its XSLT/fontmaps from disk.
    ("app/services/importing/mathtype/xslt", "app/services/importing/mathtype/xslt"),
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
    *([_SPLASH, _SPLASH.binaries] if _SPLASH else []),
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
