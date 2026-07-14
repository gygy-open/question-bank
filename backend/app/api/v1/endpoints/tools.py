import os
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.services.pandoc import convert_md_to_docx

router = APIRouter()

class MarkdownConvertRequest(BaseModel):
    content: str
    filename: str = "export"
    template: str | None = None

def cleanup_file(path: str):
    """Cleanup temporary file after response is sent."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"Error removing temp file {path}: {e}")

@router.post("/md2docx")
async def convert_markdown_to_docx(
    request: MarkdownConvertRequest,
    background_tasks: BackgroundTasks,
):
    """
    Convert Markdown content to Docx.
    """
    try:
        template_path = None
        if request.template:
            # Basic security check
            if ".." in request.template:
                raise HTTPException(status_code=400, detail="Invalid template path")
            
            # Check in app/templates
            possible_path = os.path.join("app/templates", request.template)
            if not possible_path.endswith(".docx"):
                possible_path += ".docx"
            
            if os.path.exists(possible_path):
                template_path = possible_path
            else:
                # If template specified but not found, maybe warn or fail? 
                # For now, let's fail if explicit template requested but missing
                raise HTTPException(status_code=400, detail=f"Template '{request.template}' not found.")

        output_path = convert_md_to_docx(request.content, template_path)
        
        # Schedule cleanup
        background_tasks.add_task(cleanup_file, output_path)

        filename = request.filename
        if not filename.endswith(".docx"):
            filename += ".docx"

        return FileResponse(
            output_path, 
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", 
            filename=filename
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
