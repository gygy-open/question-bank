import os
import logging
import tempfile
import json
import re
import shutil
from typing import List, Dict, Any, Callable, Optional
from pathlib import Path

import pypandoc

from app.models.question import Question, QuestionType
from app.models.composition import CompositionBlock, BlockType
from app.schemas.composition import OutputFormat
from app.services.composition_display import (
    FIELD_ORDER,
    FIELD_SOURCE,
    FIELD_LABEL,
    REGION_INLINE,
    REGION_APPENDIX,
    resolve_region,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class CompositionRenderer:
    """基于内容块 (Block) 的按需导出渲染引擎。

    渲染管线: Blocks -> 中间态 Markdown -> Pandoc -> DOCX / LaTeX(zip)。
    每种 block_type 由独立的渲染函数负责序列化, 不再依赖固化的整页模板。
    """

    def __init__(self):
        self.template_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "templates"
        )

    # ------------------------------------------------------------------
    # Shared helpers (ported from the legacy generator)
    # ------------------------------------------------------------------
    def _process_images(
        self, text: str, image_handler: Optional[Callable[[Path], str]] = None
    ) -> str:
        """Replace web image paths with absolute file system paths or handler output."""
        if not text:
            return ""

        def replace_match(match):
            alt = match.group(1)
            url = match.group(2)
            if url.startswith('/static/media/'):
                rel_path = url.replace('/static/media/', '', 1)
                file_path = settings.MEDIA_DIR / rel_path
                try:
                    abs_path = file_path.resolve()
                    if abs_path.exists():
                        if image_handler:
                            return f'![{alt}]({image_handler(abs_path)})'
                        return f'![{alt}]({abs_path.as_posix()})'
                except Exception as e:
                    logger.warning(f"Failed to resolve image path {url}: {e}")
            return match.group(0)

        return re.sub(r'!\[(.*?)\]\((.*?)\)', replace_match, text)

    def _format_answer(self, q: Question) -> str:
        answer = q.answer
        if not answer:
            return ""
        q_type = q.q_type.value if hasattr(q.q_type, "value") else q.q_type
        if q_type == QuestionType.FILL_IN_THE_BLANK.value:
            try:
                ans_obj = json.loads(answer)
                if isinstance(ans_obj, list):
                    parts = []
                    for item in ans_obj:
                        if isinstance(item, list):
                            parts.append(" 或 ".join(str(x) for x in item))
                        else:
                            parts.append(str(item))
                    return "；".join(parts)
            except Exception:
                pass
        return answer

    # ------------------------------------------------------------------
    # Block -> Markdown
    # ------------------------------------------------------------------
    def _field_value(self, q: Question, field: str) -> str:
        if field == "answer":
            return self._format_answer(q)
        return getattr(q, FIELD_SOURCE[field], None) or ""

    def _render_fields(
        self,
        md_lines: List[str],
        q: Question,
        fields: List[str],
        image_handler: Optional[Callable[[Path], str]] = None,
    ):
        """按注册表顺序渲染选定字段 (答案/分析/解析/总结/来源)。"""
        for field in FIELD_ORDER:
            if field not in fields:
                continue
            value = self._field_value(q, field)
            if not value:
                continue
            label = FIELD_LABEL[field]
            md_lines.append(f"**【{label}】** {self._process_images(str(value), image_handler)}")
            md_lines.append("")

    def _format_score(self, score: float) -> str:
        return str(int(score)) if score == int(score) else str(score)

    def _render_question_body(
        self,
        md_lines: List[str],
        q: Question,
        number: Optional[str],
        image_handler: Optional[Callable[[Path], str]] = None,
        score: Optional[float] = None,
    ):
        prefix = f"**{number}.** " if number else ""
        suffix = f"\uff08{self._format_score(score)}\u5206\uff09" if score is not None else ""
        md_lines.append(f"{prefix}{self._process_images(q.content, image_handler)}{suffix}")
        md_lines.append("")
        if q.options:
            opts = q.options
            if isinstance(opts, str):
                try:
                    opts = json.loads(opts)
                except Exception:
                    pass
            if isinstance(opts, list):
                if opts and isinstance(opts[0], dict) and "label" in opts[0]:
                    for o in opts:
                        label = o.get('label', '')
                        text = o.get('content') or o.get('text', '')
                        md_lines.append(f"{label}\\. {self._process_images(text, image_handler)}  ")
                else:
                    for idx, opt in enumerate(opts):
                        label = chr(65 + idx)
                        text = opt
                        if isinstance(opt, dict):
                            text = opt.get('content') or opt.get('text', '')
                        md_lines.append(f"{label}\\. {self._process_images(str(text), image_handler)}  ")
                md_lines.append("")

    def _block_content_text(self, block: CompositionBlock) -> str:
        content = block.content or {}
        if isinstance(content, str):
            return content
        return content.get("text", "") if isinstance(content, dict) else ""

    def generate_markdown(
        self,
        blocks: List[CompositionBlock],
        doc_display: Optional[dict] = None,
        image_handler: Optional[Callable[[Path], str]] = None,
        doc_numbering: Optional[dict] = None,
        doc_scoring: Optional[dict] = None,
    ) -> str:
        doc_numbering = doc_numbering or {}
        auto_number = doc_numbering.get("auto", True)
        scope = doc_numbering.get("scope", "section")
        scoring_enabled = (doc_scoring or {}).get("enabled", True)

        md_lines: List[str] = []
        counter = 0
        outline_path: List[int] = []  # 层级编号 (scope=outline) 用: 索引 0/1/2 对应 H2/H3/H4
        leaf_counter = 0              # 层级编号下, 当前路径内的题目序号
        appendix: List[tuple] = []  # (number, question, [appendix_fields])

        for block in blocks:
            btype = block.block_type
            if btype == BlockType.HEADING.value:
                text = self._block_content_text(block).strip()
                if text:
                    content = block.content if isinstance(block.content, dict) else {}
                    level = min(max(int(content.get("level") or 2), 1), 4)
                    if scope == "outline":
                        if level >= 2:
                            idx = level - 2
                            current = outline_path[idx] if idx < len(outline_path) else 0
                            outline_path = outline_path[:idx] + [current + 1]
                            leaf_counter = 0
                    elif scope != "document":
                        counter = 0
                    md_lines.append(f"{'#' * level} {self._process_images(text, image_handler)}")
                    md_lines.append("")
            elif btype == BlockType.TEXT.value:
                text = self._block_content_text(block).strip()
                if text:
                    md_lines.append(self._process_images(text, image_handler))
                    md_lines.append("")
            elif btype == BlockType.PAGE_BREAK.value:
                md_lines.append("```{=latex}")
                md_lines.append("\\newpage")
                md_lines.append("```")
                md_lines.append("")
            elif btype == BlockType.QUESTION.value:
                q = block.question
                if not q:
                    continue
                block_content = block.content if isinstance(block.content, dict) else {}
                label_override = block_content.get("label_override")
                number: Optional[str] = None
                if label_override is not None:
                    number = label_override
                elif auto_number:
                    if scope == "outline":
                        leaf_counter += 1
                        number = ".".join(str(n) for n in (outline_path + [leaf_counter]))
                    else:
                        counter += 1
                        number = str(counter)
                score = block_content.get("score") if scoring_enabled else None
                self._render_question_body(md_lines, q, number, image_handler, score=score)

                block_display = block.content if isinstance(block.content, dict) else None
                block_display = block_display.get("display") if block_display else None
                inline_fields: List[str] = []
                appendix_fields: List[str] = []
                for field in FIELD_ORDER:
                    region = resolve_region(field, block_display, doc_display)
                    if region == REGION_INLINE:
                        inline_fields.append(field)
                    elif region == REGION_APPENDIX:
                        appendix_fields.append(field)
                if inline_fields:
                    self._render_fields(md_lines, q, inline_fields, image_handler)
                if appendix_fields:
                    appendix.append((number, q, appendix_fields))
                md_lines.append("")

        if appendix:
            md_lines.append("```{=latex}")
            md_lines.append("\\newpage")
            md_lines.append("```")
            md_lines.append("")
            md_lines.append("# 参考答案与解析")
            md_lines.append("")
            for number, q, fields in appendix:
                md_lines.append(f"**{number}.** " if number else "")
                md_lines.append("")
                self._render_fields(md_lines, q, fields, image_handler)
                md_lines.append("")

        return "\n".join(md_lines)

    # ------------------------------------------------------------------
    # File generation
    # ------------------------------------------------------------------
    def generate_file(
        self,
        title: str,
        blocks: List[CompositionBlock],
        format: OutputFormat,
        doc_display: Optional[dict] = None,
        doc_numbering: Optional[dict] = None,
        doc_scoring: Optional[dict] = None,
    ) -> str:
        logger.debug(f"Rendering publication '{title}' as {format.value}")

        if format == OutputFormat.LATEX:
            return self._generate_latex_zip(title, blocks, doc_display, doc_numbering, doc_scoring)

        # DOCX via pandoc
        fd, path = tempfile.mkstemp(suffix=f".{format.value}")
        os.close(fd)
        markdown_content = self.generate_markdown(
            blocks, doc_display, doc_numbering=doc_numbering, doc_scoring=doc_scoring,
        )
        extra_args = ['--standalone']
        reference_doc = os.path.join(self.template_dir, "yuanxuan-standard-math.docx")
        if os.path.exists(reference_doc):
            extra_args.append(f'--reference-doc={reference_doc}')
        try:
            pypandoc.convert_text(
                markdown_content,
                format.value,
                format='markdown+tex_math_dollars+raw_attribute',
                outputfile=path,
                extra_args=extra_args,
            )
        except Exception as e:
            logger.error(f"Pandoc conversion failed: {e}", exc_info=True)
            if os.path.exists(path):
                os.remove(path)
            raise
        return path

    def _generate_latex_zip(
        self,
        title: str,
        blocks: List[CompositionBlock],
        doc_display: Optional[dict] = None,
        doc_numbering: Optional[dict] = None,
        doc_scoring: Optional[dict] = None,
    ) -> str:
        with tempfile.TemporaryDirectory() as tmpdirname:
            base_dir = Path(tmpdirname)
            images_dir = base_dir / "images"
            images_dir.mkdir()

            def latex_image_handler(src_path: Path) -> str:
                dst_name = src_path.name
                shutil.copy2(src_path, images_dir / dst_name)
                return f"images/{dst_name}"

            markdown_content = self.generate_markdown(
                blocks, doc_display, image_handler=latex_image_handler,
                doc_numbering=doc_numbering, doc_scoring=doc_scoring,
            )
            tex_file = base_dir / f"{title}.tex"
            preamble = self._load_preamble()
            body = pypandoc.convert_text(
                markdown_content,
                'latex',
                format='markdown+tex_math_dollars+raw_attribute',
            )
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(preamble.replace("%%BODY%%", body))

            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)
            os.remove(zip_path)
            archive_base = zip_path.replace(".zip", "")
            shutil.make_archive(archive_base, 'zip', base_dir)
            return zip_path

    def _load_preamble(self) -> str:
        preamble_path = os.path.join(self.template_dir, "preamble.tex")
        if os.path.exists(preamble_path):
            with open(preamble_path, 'r', encoding='utf-8') as f:
                return f.read()
        # Minimal fallback preamble with CJK + math support
        return (
            "\\documentclass[12pt]{article}\n"
            "\\usepackage{ctex}\n"
            "\\usepackage{amsmath,amssymb}\n"
            "\\usepackage{graphicx}\n"
            "\\usepackage[margin=2.5cm]{geometry}\n"
            "\\usepackage{enumitem}\n"
            "\\begin{document}\n"
            "%%BODY%%\n"
            "\\end{document}\n"
        )


publication_renderer = CompositionRenderer()
composition_renderer = publication_renderer
