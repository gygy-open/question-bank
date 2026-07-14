import pypandoc
import os
import logging
import tempfile
import json
import re
import shutil
from typing import List, Dict, Any, Callable, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from app.models.question import Question, QuestionType
from app.schemas.paper import OutputFormat
from app.core.config import settings

logger = logging.getLogger(__name__)

class PaperGenerator:
    def __init__(self):
        self.template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
        self.jinja_env = Environment(
            loader=FileSystemLoader(self.template_dir),
            block_start_string='\\BLOCK{',
            block_end_string='}',
            variable_start_string='\\VAR{',
            variable_end_string='}',
            comment_start_string='\\#{',
            comment_end_string='}',
            line_statement_prefix='%%',
            line_comment_prefix='%#',
            trim_blocks=True,
            autoescape=False,
        )

    def _process_images(self, text: str, image_handler: Optional[Callable[[Path], str]] = None) -> str:
        """Replace web image paths with absolute file system paths or custom paths via handler"""
        if not text:
            return ""
        
        def replace_match(match):
            alt = match.group(1)
            url = match.group(2)
            
            # Handle local media files
            if url.startswith('/static/media/'):
                # Remove prefix to get relative path
                rel_path = url.replace('/static/media/', '', 1)
                # settings.MEDIA_DIR is "static/media"
                file_path = settings.MEDIA_DIR / rel_path
                
                # Resolve to absolute path
                try:
                    abs_path = file_path.resolve()
                    if abs_path.exists():
                        if image_handler:
                            new_path = image_handler(abs_path)
                            return f'![{alt}]({new_path})'
                        return f'![{alt}]({abs_path.as_posix()})'
                except Exception as e:
                    logger.warning(f"Failed to resolve image path {url}: {e}")
            
            return match.group(0)

        return re.sub(r'!\[(.*?)\]\((.*?)\)', replace_match, text)

    def _format_answer(self, q: Question) -> str:
        """Format answer based on question type"""
        answer = q.answer
        if not answer:
            return ""
            
        q_type = q.q_type
        if hasattr(q_type, "value"): 
            q_type = q_type.value
        
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
            except:
                pass
                
        return answer

    def _md_to_latex(self, text: str, image_handler: Optional[Callable[[Path], str]] = None) -> str:
        """Convert markdown text to latex fragment"""
        if not text:
            return ""
        # Process images first
        text = self._process_images(text, image_handler)
        return pypandoc.convert_text(text, 'latex', format='markdown+tex_math_dollars')

    def generate_latex_via_jinja(self, title: str, questions: List[Question],
                                 include_answer: bool = True, include_analysis: bool = True, 
                                 include_explanation: bool = True, include_summary: bool = True,
                                 include_source: bool = False,
                                 image_handler: Optional[Callable[[Path], str]] = None) -> str:
        # Group questions
        parts = {
            "choice": [],
            "true_false": [],
            "fill": [],
            "essay": []
        }
        
        for q in questions:
            # Convert content
            q_data = {
                "score": 5, # Default score
                "content_tex": self._md_to_latex(q.content, image_handler),
                "options_tex": [],
                "answer_tex": self._md_to_latex(self._format_answer(q), image_handler) if include_answer else "",
                "thinking_tex": self._md_to_latex(q.thinking, image_handler) if include_analysis else "",
                "analysis_tex": self._md_to_latex(q.analysis, image_handler) if include_explanation else "",
                "summary_tex": self._md_to_latex(q.summary, image_handler) if include_summary else "",
                "source_tex": self._md_to_latex(q.source, image_handler) if include_source else ""
            }
            
            # Handle options
            if q.options:
                opts = q.options
                if isinstance(opts, str):
                    try: opts = json.loads(opts)
                    except: pass
                
                if isinstance(opts, list):
                    for opt in opts:
                        # Try 'content' first (frontend uses this), then 'text' (legacy/import), then string
                        text = ""
                        if isinstance(opt, dict):
                            text = opt.get('content') or opt.get('text', '')
                        else:
                            text = str(opt)
                        q_data["options_tex"].append(self._md_to_latex(text, image_handler))

            # Categorize
            q_type = q.q_type
            if hasattr(q_type, "value"): q_type = q_type.value
            
            if q_type in [QuestionType.SINGLE_CHOICE.value, QuestionType.MULTIPLE_CHOICE.value, "选择题"]:
                parts["choice"].append(q_data)
            elif q_type in [QuestionType.TRUE_FALSE.value, "判断题"]:
                parts["true_false"].append(q_data)
            elif q_type in [QuestionType.FILL_IN_THE_BLANK.value, "填空题"]:
                parts["fill"].append(q_data)
            elif q_type in [QuestionType.FREE_RESPONSE.value, "解答题"]:
                parts["essay"].append(q_data)
            else:
                # Fallback to essay if unknown
                parts["essay"].append(q_data)

        # Render template
        template = self.jinja_env.get_template("exam_paper.tex.j2")
        return template.render(title=title, parts=parts)

    def _append_question_details(self, md_lines: List[str], q: Question, 
                                 include_answer: bool, include_analysis: bool, 
                                 include_explanation: bool, include_summary: bool,
                                 include_source: bool):
        if include_answer and q.answer:
            formatted_answer = self._format_answer(q)
            md_lines.append(f"**【答案】** {self._process_images(formatted_answer)}")
            md_lines.append("")
        if include_analysis and q.thinking:
            md_lines.append(f"**【分析】** {self._process_images(q.thinking)}")
            md_lines.append("")
        if include_explanation and q.analysis:
            md_lines.append(f"**【解析】** {self._process_images(q.analysis)}")
            md_lines.append("")
        if include_summary and q.summary:
            md_lines.append(f"**【总结】** {self._process_images(q.summary)}")
            md_lines.append("")
        if include_source and q.source:
            md_lines.append(f"**【来源】** {self._process_images(q.source)}")
            md_lines.append("")

    def generate_markdown(self, title: str, questions: List[Question],
                          include_answer: bool = True, include_analysis: bool = True, 
                          include_explanation: bool = True, include_summary: bool = True,
                          include_source: bool = False) -> str:
        md_lines = [f"# {title}", ""]
        
        # Grouping
        choice_qs = []
        true_false_qs = []
        fill_qs = []
        essay_qs = []
        others = []
        
        for q in questions:
            # q.q_type is an Enum, so compare with value or Enum member
            q_type = q.q_type
            if hasattr(q_type, "value"):
                q_type = q_type.value
                
            if q_type in [QuestionType.SINGLE_CHOICE.value, QuestionType.MULTIPLE_CHOICE.value, "选择题"]:
                choice_qs.append(q)
            elif q_type in [QuestionType.TRUE_FALSE.value, "判断题"]:
                true_false_qs.append(q)
            elif q_type in [QuestionType.FILL_IN_THE_BLANK.value, "填空题"]:
                fill_qs.append(q)
            elif q_type in [QuestionType.FREE_RESPONSE.value, "解答题", "essay"]:
                essay_qs.append(q)
            else:
                others.append(q)
        
        if choice_qs:
            md_lines.append("## 一、选择题")
            for i, q in enumerate(choice_qs, 1):
                # Use bold number instead of list to avoid indentation issues
                md_lines.append(f"**{i}.** {self._process_images(q.content)}")
                md_lines.append("")
                
                if q.options:
                    opts = q.options
                    if isinstance(opts, str):
                        try:
                            opts = json.loads(opts)
                        except:
                            pass
                    
                    if isinstance(opts, list):
                        # Check structure
                        if opts and isinstance(opts[0], dict) and "label" in opts[0]:
                            # Format: A. xxx
                            #         B. xxx
                            for o in opts:
                                label = o.get('label', '')
                                text = o.get('content') or o.get('text', '')
                                # Escape dot to prevent list conversion, use double space for line break
                                md_lines.append(f"{label}\\. {self._process_images(text)}  ")
                        else:
                            # Just list them
                            for idx, opt in enumerate(opts):
                                label = chr(65 + idx) # A, B, C...
                                md_lines.append(f"{label}\\. {self._process_images(str(opt))}  ")
                        
                        md_lines.append("") # Blank line after options
                
                self._append_question_details(md_lines, q, include_answer, include_analysis, include_explanation, include_summary, include_source)
                md_lines.append("")

        if true_false_qs:
            md_lines.append("## 二、判断题")
            for i, q in enumerate(true_false_qs, 1):
                md_lines.append(f"**{i}.** {self._process_images(q.content)}")
                md_lines.append("")
                self._append_question_details(md_lines, q, include_answer, include_analysis, include_explanation, include_summary, include_source)

        if fill_qs:
            md_lines.append("## 三、填空题")
            for i, q in enumerate(fill_qs, 1):
                md_lines.append(f"**{i}.** {self._process_images(q.content)}")
                md_lines.append("")
                self._append_question_details(md_lines, q, include_answer, include_analysis, include_explanation, include_summary, include_source)

        if essay_qs:
            md_lines.append("## 四、解答题")
            for i, q in enumerate(essay_qs, 1):
                md_lines.append(f"**{i}.** {self._process_images(q.content)}")
                md_lines.append("")
                self._append_question_details(md_lines, q, include_answer, include_analysis, include_explanation, include_summary, include_source)
                
        if others:
            md_lines.append("## 五、其他")
            for i, q in enumerate(others, 1):
                md_lines.append(f"**{i}.** {self._process_images(q.content)}")
                md_lines.append("")
                self._append_question_details(md_lines, q, include_answer, include_analysis, include_explanation, include_summary, include_source)
                
        return "\n".join(md_lines)

    def generate_file(self, title: str, questions: List[Question], format: OutputFormat,
                      include_answer: bool = True, include_analysis: bool = True, 
                      include_explanation: bool = True, include_summary: bool = True,
                      include_source: bool = False) -> str:
        logger.debug(f"Generating paper file in format: {format.value}")
        
        if format == OutputFormat.LATEX:
            # Create a temporary directory for the build
            with tempfile.TemporaryDirectory() as tmpdirname:
                base_dir = Path(tmpdirname)
                images_dir = base_dir / "images"
                images_dir.mkdir()
                
                def latex_image_handler(src_path: Path) -> str:
                    # Copy file to images_dir
                    dst_name = src_path.name
                    # Handle duplicate names if necessary? For now assume unique names or overwrite is fine
                    shutil.copy2(src_path, images_dir / dst_name)
                    # Return relative path for latex (forward slashes)
                    return f"images/{dst_name}"

                try:
                    latex_content = self.generate_latex_via_jinja(
                        title, questions, 
                        include_answer, include_analysis, include_explanation, include_summary, include_source,
                        image_handler=latex_image_handler
                    )
                    
                    tex_file = base_dir / f"{title}.tex"
                    with open(tex_file, 'w', encoding='utf-8') as f:
                        f.write(latex_content)
                    
                    # Create zip
                    # We want to return a persistent temp file (until cleaned up by caller)
                    zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
                    os.close(zip_fd)
                    # remove the empty temp file created by mkstemp because make_archive might complain or we overwrite
                    os.remove(zip_path)
                    
                    # make_archive appends .zip, so we strip it from base_name
                    archive_base = zip_path.replace(".zip", "")
                    
                    shutil.make_archive(archive_base, 'zip', base_dir)
                    
                    # make_archive adds .zip extension, so zip_path should be correct now if we stripped it
                    # But wait, if zip_path was /tmp/foo.zip, archive_base is /tmp/foo
                    # make_archive creates /tmp/foo.zip
                    
                    return zip_path
                except Exception as e:
                    logger.error(f"Error generating latex zip: {e}", exc_info=True)
                    raise e

        # Fallback to Pandoc for DOCX
        # Create a temp file
        suffix = f".{format.value}"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)

        markdown_content = self.generate_markdown(title, questions, include_answer, include_analysis, include_explanation, include_summary, include_source)
        extra_args = ['--standalone']
        if format == OutputFormat.DOCX:
            reference_doc = os.path.join(self.template_dir, "yuanxuan-standard-math.docx")
            if os.path.exists(reference_doc):
                extra_args.append(f'--reference-doc={reference_doc}')

        try:
            pypandoc.convert_text(
                markdown_content,
                format.value,
                format='markdown+tex_math_dollars',
                outputfile=path,
                extra_args=extra_args
            )
        except Exception as e:
            # Cleanup if failed
            logger.error(f"Pandoc conversion failed: {e}", exc_info=True)
            if os.path.exists(path):
                os.remove(path)
            raise e
        
        return path

paper_generator = PaperGenerator()
