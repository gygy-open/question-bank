"""摄取阶段:把各种源(docx / markdown / image)归一为 CanonicalDoc。

CanonicalDoc 是抽取阶段唯一认识的输入:文本源产出 markdown,图像源产出 image_data。
文档内的本地图片在此交给 ImageStore 入库并改写为资产 URL,中间文件只落在临时 job 目录,
下游不再感知物理路径。
"""
from __future__ import annotations

import asyncio
import glob
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, BinaryIO, Callable, Optional
from urllib.parse import unquote, urlsplit

import pypandoc

from app.core import storage

# (图片字节, 原文件名) -> 替换后的 URL;返回 None 表示该图片保持原引用。
ImageStore = Callable[[bytes, str], Awaitable[Optional[str]]]


@dataclass
class CanonicalDoc:
    task_id: str
    markdown: str = ""                       # 文本源内容;图像源为空
    filename: Optional[str] = None           # 传给 AI 抽取的文件名上下文
    image_data: Optional[bytes] = None       # 视觉抽取用


def _ensure_task_id(task_id: Optional[str]) -> str:
    return task_id or str(uuid.uuid4())


# --- Markdown 归档(zip)摄取:解压 + 本地图片落地 + 路径重写 ---------------------

# zip 炸弹防护上限:文件数 / 解压后总字节 / 单文件字节。
_ARCHIVE_MAX_FILES = 2000
_ARCHIVE_MAX_TOTAL_BYTES = 200 * 1024 * 1024
_ARCHIVE_MAX_FILE_BYTES = 50 * 1024 * 1024

_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".emf", ".wmf",
}

# markdown 图片语法 ![alt](URL "可选标题"):分三段捕获,只重写中间的 URL 段。
_MD_IMAGE_RE = re.compile(
    r"(!\[[^\]]*\]\()"      # 1: ![alt](
    r"([^)\s]+)"           # 2: URL(不含空格/右括号)
    r"((?:\s+\"[^\"]*\")?\))"  # 3: 可选标题 + )
)


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """把 zip 解压到 dest,防 zip-slip(拒绝 ../ 或绝对路径逃逸)与 zip 炸弹(数量/体积上限)。"""
    dest_root = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > _ARCHIVE_MAX_FILES:
            raise ValueError(f"压缩包内文件过多(>{_ARCHIVE_MAX_FILES})")
        total = 0
        for info in infos:
            if info.file_size > _ARCHIVE_MAX_FILE_BYTES:
                raise ValueError(f"压缩包内单个文件过大: {info.filename}")
            total += info.file_size
            if total > _ARCHIVE_MAX_TOTAL_BYTES:
                raise ValueError("压缩包解压后总体积过大")
            target = (dest_root / info.filename).resolve()
            if dest_root not in target.parents and target != dest_root:
                raise ValueError(f"压缩包包含非法路径: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _local_image_resolver(base_dir: Path, root: Path) -> Callable[[str], Optional[Path]]:
    """把 markdown 图片 URL 解析成 root 内的本地图片文件;解析不到返回 None。

    URL(http/https/data 等)、绝对路径、逃逸出 root、不存在或非图片扩展名的引用一律不处理
    (原样保留,坏链但保文字)。
    """
    root = root.resolve()

    def resolve(raw_url: str) -> Optional[Path]:
        if urlsplit(raw_url).scheme or raw_url.startswith("/"):
            return None
        rel = unquote(raw_url.split("#", 1)[0].split("?", 1)[0])
        if not rel:
            return None
        src = (base_dir / rel).resolve()
        if root not in src.parents:
            return None
        if not src.is_file() or src.suffix.lower() not in _IMAGE_EXTENSIONS:
            return None
        return src

    return resolve


async def _rewrite_local_images(
    markdown: str, *, resolve: Callable[[str], Optional[Path]], store: ImageStore
) -> str:
    """把能解析到的本地图片交给 store 入库,并把引用改写成 store 返回的 URL。"""
    replacements: dict[str, str] = {}
    for raw_url in dict.fromkeys(m.group(2) for m in _MD_IMAGE_RE.finditer(markdown)):
        src = resolve(raw_url)
        if src is None:
            continue
        data = await asyncio.to_thread(src.read_bytes)
        new_url = await store(data, src.name)
        if new_url:
            replacements[raw_url] = new_url
    if not replacements:
        return markdown

    def _sub(match: re.Match[str]) -> str:
        new_url = replacements.get(match.group(2))
        if new_url is None:
            return match.group(0)
        return f"{match.group(1)}{new_url}{match.group(3)}"

    return _MD_IMAGE_RE.sub(_sub, markdown)


async def extract_markdown_archive(zip_path: Path, *, store: ImageStore) -> list[tuple[str, str]]:
    """解压 markdown 归档,把被引用的本地图片交给 store,返回 [(包内 md 相对路径, 重写后 markdown)]。

    解压只落在临时 job 目录,返回前即清理。无 md 文件时抛 ValueError。**不做 AI 抽取**,
    同步/批量入口共用。
    """
    with storage.job_dir() as extract_root:
        await asyncio.to_thread(_safe_extract_zip, zip_path, extract_root)

        md_paths = sorted(
            (p for p in extract_root.rglob("*") if p.is_file() and p.suffix.lower() == ".md"),
            key=lambda p: p.relative_to(extract_root).as_posix(),
        )
        if not md_paths:
            raise ValueError("压缩包内未找到 .md 文件")

        results: list[tuple[str, str]] = []
        for md_path in md_paths:
            content = await asyncio.to_thread(md_path.read_text, encoding="utf-8")
            rewritten = await _rewrite_local_images(
                content,
                resolve=_local_image_resolver(md_path.parent, extract_root),
                store=store,
            )
            results.append((md_path.relative_to(extract_root).as_posix(), rewritten))
        return results


class MarkdownArchiveIngestor:
    async def ingest(
        self,
        zip_path: Path,
        *,
        store: ImageStore,
        task_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CanonicalDoc:
        """同步/单条导入用:解压归档、图片入库,把包内所有 md 按路径序拼成一个文档。"""
        parts = await extract_markdown_archive(zip_path, store=store)
        markdown = "\n\n".join(md for _, md in parts)
        return CanonicalDoc(
            task_id=_ensure_task_id(task_id), markdown=markdown, filename=filename or zip_path.name
        )


class MarkdownIngestor:
    async def ingest(
        self, content: str, *, task_id: Optional[str] = None, filename: Optional[str] = None
    ) -> CanonicalDoc:
        return CanonicalDoc(task_id=_ensure_task_id(task_id), markdown=content, filename=filename)


# pandoc 转换 Word 公式时，把非 ASCII 希腊字母原样塞进 \text{}；KaTeX 的 text 模式
# 字体没有这些字形的度量信息，需要换成对应的 LaTeX 宏才能正常渲染。
_GREEK_TO_MACRO = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon",
    "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota", "κ": "kappa",
    "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho",
    "σ": "sigma", "ς": "sigma", "τ": "tau", "υ": "upsilon", "φ": "phi",
    "χ": "chi", "ψ": "psi", "ω": "omega",
    "Γ": "Gamma", "Δ": "Delta", "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi",
    "Π": "Pi", "Σ": "Sigma", "Φ": "Phi", "Χ": "Chi", "Ψ": "Psi", "Ω": "Omega",
}
_TEXT_WRAPPED_GREEK_RE = re.compile(
    r'\\text\{([' + ''.join(_GREEK_TO_MACRO) + r']+)\}'
)


def _fix_text_wrapped_greek(content: str) -> str:
    """把 \\text{π} 这类 pandoc 产物换成 \\pi,避免 KaTeX 报 unknownSymbol/缺字形。"""
    def repl(match: re.Match) -> str:
        return ' '.join(f'\\{_GREEK_TO_MACRO[ch]}' for ch in match.group(1))

    return _TEXT_WRAPPED_GREEK_RE.sub(repl, content)


class DocxIngestor:
    async def ingest(
        self,
        file_path: Path,
        *,
        store: ImageStore,
        task_id: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> CanonicalDoc:
        """file_path 可以是无扩展名的存储对象,因此显式指定输入格式为 docx。"""
        with storage.job_dir() as job:
            try:
                content = await asyncio.to_thread(
                    pypandoc.convert_file,
                    glob.escape(str(file_path.resolve())),
                    # 只保留 pipe 表格(禁用 grid/multiline/simple):下游 markdown-it 仅解析 pipe 表格。
                    "markdown-grid_tables-multiline_tables-simple_tables",
                    format="docx",
                    # 在 job 目录内以相对路径抽取媒体,引用形如 media/image1.png,避免路径含空格被转义。
                    # --wrap=none:避免 pandoc 把表格行硬换行,破坏 pipe 表格结构。
                    extra_args=["--extract-media=.", "--mathml", "--wrap=none"],
                    cworkdir=str(job),
                )
            except Exception as e:
                raise RuntimeError(f"Pandoc conversion failed: {e}") from e

            content = await _rewrite_local_images(
                content, resolve=_local_image_resolver(job, job), store=store
            )

        return CanonicalDoc(
            task_id=_ensure_task_id(task_id),
            markdown=_fix_text_wrapped_greek(content),
            filename=filename or file_path.name,
        )


class ImageIngestor:
    async def ingest(self, image_file: BinaryIO, *, task_id: Optional[str] = None) -> CanonicalDoc:
        """识别用图片只送给视觉模型,不落盘。"""
        image_data = await asyncio.to_thread(image_file.read)
        return CanonicalDoc(task_id=_ensure_task_id(task_id), image_data=image_data)
