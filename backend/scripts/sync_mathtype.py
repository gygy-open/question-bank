"""同步复制进本仓库的 mathtypejx MTEF 解析器。

用法(在 backend/ 下):
    uv run python scripts/sync_mathtype.py                 # 同步到上游默认分支最新 commit
    uv run python scripts/sync_mathtype.py --ref <sha|tag|branch>
    uv run python scripts/sync_mathtype.py --source /path/to/mathtypejx   # 用本地 checkout(离线)

会整体替换 app/services/importing/mathtype/ 下的上游文件(VENDORED.md 除外)、重新打本地补丁、
更新 VENDORED.md 里的 commit,并同步上游测试用 OLE 样本。之后请 `git diff --stat` 审阅并跑测试。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

REPO = "a917470154/mathtypejx"
BACKEND = Path(__file__).resolve().parent.parent
VENDOR_DIR = BACKEND / "app" / "services" / "importing" / "mathtype"
FIXTURE_DIR = BACKEND / "tests" / "fixtures" / "mathtype"
VENDORED_MD = VENDOR_DIR / "VENDORED.md"
KEEP = {"VENDORED.md"}

# 上游代码里引用自身包名的地方，需要改成本仓库路径。(旧文本, 新文本)
LOCAL_PATCHES: List[Tuple[str, str]] = [
    ("from mathtypejx.mtef import", "from app.services.importing.mathtype import"),
]
_COMMIT_RE = re.compile(r"(- Commit: `)([0-9a-f]{7,40})(`)")


def _http_get(url: str, accept: Optional[str] = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "question-bank-sync"})
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _resolve_sha(ref: str) -> str:
    data = _http_get(f"https://api.github.com/repos/{REPO}/commits/{ref}")
    return json.loads(data)["sha"]


def _download(sha: str, dest: Path) -> Path:
    data = _http_get(f"https://codeload.github.com/{REPO}/tar.gz/{sha}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        tar.extractall(dest, filter="data")
    roots = [p for p in dest.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"Unexpected tarball layout: {roots}")
    return roots[0]


def _current_sha() -> Optional[str]:
    if not VENDORED_MD.exists():
        return None
    m = _COMMIT_RE.search(VENDORED_MD.read_text(encoding="utf-8"))
    return m.group(2) if m else None


def _replace_vendor_dir(upstream: Path) -> None:
    src_pkg = upstream / "src" / "mathtypejx" / "mtef"
    if not (src_pkg / "mathml.py").is_file():
        raise RuntimeError(f"{src_pkg} does not look like the mathtypejx mtef package")

    for item in VENDOR_DIR.iterdir():
        if item.name in KEEP:
            continue
        shutil.rmtree(item) if item.is_dir() else item.unlink()

    shutil.copytree(
        src_pkg, VENDOR_DIR, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("LICENSE", "NOTICE"):
        if (upstream / name).is_file():
            shutil.copy2(upstream / name, VENDOR_DIR / name)


def _apply_local_patches() -> List[str]:
    leftovers: List[str] = []
    for py in VENDOR_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for old, new in LOCAL_PATCHES:
            text = text.replace(old, new)
        py.write_text(text, encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+mathtypejx\b", text, re.MULTILINE):
            leftovers.append(str(py.relative_to(BACKEND)))
    return leftovers


def _sync_fixtures(upstream: Path) -> int:
    src = upstream / "tests" / "fixtures"
    if not src.is_dir():
        return 0
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src.glob("*.bin"):
        shutil.copy2(f, FIXTURE_DIR / f.name)
        count += 1
    return count


def _update_vendored_md(sha: str) -> None:
    text = VENDORED_MD.read_text(encoding="utf-8")
    new_text, n = _COMMIT_RE.subn(rf"\g<1>{sha}\g<3>", text)
    if n == 0:
        raise RuntimeError("Commit line not found in VENDORED.md")
    VENDORED_MD.write_text(new_text, encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ref", default="HEAD", help="上游 commit / tag / 分支(默认 HEAD)")
    parser.add_argument("--source", type=Path, help="使用本地 mathtypejx checkout,不联网")
    parser.add_argument("--sha", help="配合 --source 指定写入 VENDORED.md 的 commit")
    args = parser.parse_args(argv)

    old_sha = _current_sha()

    with tempfile.TemporaryDirectory() as tmp:
        if args.source:
            upstream = args.source.resolve()
            sha = args.sha or old_sha or "unknown"
        else:
            sha = _resolve_sha(args.ref)
            if sha == old_sha:
                print(f"Already up to date at {sha}")
                return 0
            print(f"Downloading {REPO}@{sha} ...")
            upstream = _download(sha, Path(tmp))

        _replace_vendor_dir(upstream)
        leftovers = _apply_local_patches()
        fixtures = _sync_fixtures(upstream)

    _update_vendored_md(sha)

    print(f"Synced {VENDOR_DIR.relative_to(BACKEND)}: {old_sha} -> {sha} ({fixtures} fixtures)")
    if old_sha and sha != old_sha and not args.source:
        print(f"Upstream changes: https://github.com/{REPO}/compare/{old_sha}...{sha}")
    if leftovers:
        print("WARNING: still importing `mathtypejx` (add a LOCAL_PATCHES entry):", *leftovers, sep="\n  ")
        return 1
    print("Next: git diff --stat && uv run pytest tests/test_importing_docx_math.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
