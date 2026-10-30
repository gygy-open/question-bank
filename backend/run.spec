# PyInstaller spec for the QuestionBank desktop build.
#
# Build with:  uv run pyinstaller run.spec --clean
#
# Produces a windowed app that shows a system-tray (menu-bar) icon, runs
# migrations, the API, the background worker and serves the bundled Nuxt SPA:
#   - Windows: a single-file dist/question-bank.exe (wrapped by deploy/windows/installer.iss)
#   - macOS:   a dist/QuestionBank.app bundle (onedir; see deploy/macos/package.sh)
#
# Prerequisites:
#   1. Build the frontend:  (cd ../frontend && pnpm generate)
#   2. Copy/point the output so the datas entry below can find it.

from PyInstaller.utils.hooks import collect_all, collect_submodules

import os
import re
import sys

IS_MAC = sys.platform == "darwin"

# Make ``app`` importable so we can generate the brand icon below.
sys.path.insert(0, os.path.abspath("."))

# Channel of the build: pre-release versions are the preview app (app/channel.py).
# Pass frozen=True because the spec itself doesn't run frozen.
try:
    from app.channel import is_preview

    _PREVIEW = is_preview(frozen=True)
except Exception:
    _PREVIEW = False

# Render the brand logo (frontend/public/logo.svg) to the platform icon format
# (.ico on Windows, .icns on macOS). Drawn with PIL, so no SVG renderer is required.
# Preview builds get the amber variant. deploy/windows/installer.iss reuses the .ico.
_ICON = os.path.abspath(os.path.join("build", "logo.icns" if IS_MAC else "logo.ico"))
os.makedirs(os.path.dirname(_ICON), exist_ok=True)
try:
    from app.branding import save_icns, save_ico

    if IS_MAC:
        save_icns(_ICON, preview=_PREVIEW)
    else:
        save_ico(_ICON, preview=_PREVIEW)
except Exception:
    _ICON = None  # fall back to the default PyInstaller icon

# Startup splash: the onefile bootloader unpacks hundreds of MB before Python even starts (minutes on
# a first launch with antivirus scanning), during which nothing else is visible. The splash is shown
# by the bootloader and closed from app.tray once the server is ready. Needs Tcl/Tk at build time.
# Windows only: PyInstaller rejects Splash on macOS (SystemExit, not catchable below), and the
# onedir .app starts quickly anyway because nothing has to be unpacked.
_SPLASH = None
try:
    if IS_MAC:
        raise ImportError("splash is not supported on macOS")
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
    "pystray._darwin" if IS_MAC else "pystray._win32",
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

if IS_MAC:
    from app._version import __version__

    # Bundle identity mirrors the Windows installer's stable/preview split so both can be installed.
    _APP_NAME = "QuestionBank Preview" if _PREVIEW else "QuestionBank"
    _BUNDLE_ID = "io.github.gygy-open.questionbank" + (".preview" if _PREVIEW else "")
    # CFBundleShortVersionString must be numeric (1.2.3); the full version stays in app/_version.py.
    _match = re.match(r"\d+(?:\.\d+){0,2}", __version__)
    _SHORT_VERSION = _match.group(0) if _match else "0.0.0"

    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="question-bank",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,  # UPX breaks code signatures on macOS
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,  # build for the host architecture (separate arm64 / x86_64 builds)
        # Ad-hoc signed here; deploy/macos/package.sh re-signs with a Developer ID when available.
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="question-bank")
    app = BUNDLE(
        coll,
        name=f"{_APP_NAME}.app",
        icon=_ICON,
        bundle_identifier=_BUNDLE_ID,
        version=_SHORT_VERSION,
        info_plist={
            "CFBundleName": _APP_NAME,
            "CFBundleDisplayName": _APP_NAME,
            "CFBundleShortVersionString": _SHORT_VERSION,
            "CFBundleVersion": _SHORT_VERSION,
            "QBFullVersion": __version__,
            # onnxruntime wheels require macOS 13+.
            "LSMinimumSystemVersion": "13.0",
            "LSApplicationCategoryType": "public.app-category.education",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Released under the project LICENSE.",
            "CFBundleDevelopmentRegion": "zh_CN",
            "CFBundleLocalizations": ["zh_CN", "en"],
            # LAN sharing advertises an mDNS (Bonjour) service; macOS 15+ asks for Local Network access.
            "NSLocalNetworkUsageDescription": (
                "QuestionBank uses the local network to share the question bank with other devices "
                "when LAN sharing is turned on."
            ),
            "NSBonjourServices": ["_http._tcp"],
        },
    )
else:
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
