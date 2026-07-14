import re
import os
import tempfile
import pypandoc
from fastapi import HTTPException

def process_latex_formulas(content: str) -> str:
    """
    Process LaTeX formulas in markdown content.
    Specifically replaces \hspace{...} with appropriate number of \quad or \qquad
    to ensure compatibility with Pandoc's OMML (Word) output.
    """
    def replace_hspace(match):
        val_str = match.group(1) # e.g. "0.5cm"
        # Parse value and unit
        m = re.match(r'^([0-9.]+)\s*([a-zA-Z]+)$', val_str)
        if not m:
            return r'\quad' # Fallback if format is weird
        
        try:
            num = float(m.group(1))
        except ValueError:
            return r'\quad'
            
        unit = m.group(2).lower()
        
        # Approximate conversion to em (1em approx 1 \quad)
        # Based on typical 12pt font: 1cm approx 2.4em
        em_val = 0
        if unit == 'cm':
            em_val = num * 2.4
        elif unit == 'mm':
            em_val = num * 0.24
        elif unit == 'in':
            em_val = num * 6.1
        elif unit == 'pt':
            em_val = num / 12.0
        elif unit == 'em':
            em_val = num
        else:
            return r'\quad' # Unknown unit fallback
            
        # Calculate number of quads needed
        count = round(em_val)
        if count <= 0:
            count = 1 # Ensure at least some space
            
        # Generate replacement string
        # Use \qquad (2em) where possible for cleaner latex
        qquads = count // 2
        quads = count % 2
        
        result = (r'\qquad' * int(qquads)) + (r'\quad' * int(quads))
        return result if result else r'\quad'

    def process_formula_content(match):
        formula = match.group(0)
        # Replace \hspace{...} only inside the matched formula
        return re.sub(r'\\hspace\{([^}]+)\}', replace_hspace, formula)

    # Regex to match LaTeX formulas:
    # 1. Block formulas: $$ ... $$
    # 2. Inline formulas: $ ... $ (excluding escaped \$)
    # We use a simplified pattern that works for most markdown cases
    pattern = r'(\$\$[\s\S]*?\$\$|\$[^$\n]+\$)'
    
    return re.sub(pattern, process_formula_content, content)

def convert_md_to_docx(content: str, template_path: str = None) -> str:
    """
    Convert markdown content to docx.
    Returns the path to the generated docx file.
    """
    # Replace \hspace{...} with \quad to fix pandoc conversion issues with OMML
    content_str = process_latex_formulas(content)

    # Create a temporary directory to store input and output files
    with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode='w', encoding='utf-8') as input_tmp:
        input_tmp.write(content_str)
        input_path = input_tmp.name
    
    output_path = input_path.replace(".md", ".docx")

    try:
        extra_args = []
        if template_path and os.path.exists(template_path):
            extra_args.append(f"--reference-doc={template_path}")

        pypandoc.convert_file(
            input_path,
            'docx',
            outputfile=output_path,
            extra_args=extra_args
        )
        
        # Cleanup input file immediately
        if os.path.exists(input_path):
            os.remove(input_path)
            
        return output_path

    except Exception as e:
        # Cleanup on error
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        raise e
