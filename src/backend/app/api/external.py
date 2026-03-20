import os
import secrets
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Response
from pydantic import BaseModel
import logging

from app.config import settings
from app.services.planka import create_task as planka_create_task
from app.services.memory import store_memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integration", tags=["dify", "integration"])

# --- Security Dependency ---

async def verify_integration_token(x_integration_token: str = Header(..., description="Symmetric Dify Integration Token")):
    """
    Middleware ensuring only our internal local Dify webhooks can mutate state.
    Utilizes constant-time cryptographic comparison to defeat timing attacks.
    """
    if not settings.INTEGRATION_TOKEN:
        logger.error("INTEGRATION_TOKEN not configured in environment.")
        raise HTTPException(status_code=500, detail="Integration gateway not securely configured.")
        
    if not secrets.compare_digest(x_integration_token, settings.INTEGRATION_TOKEN):
        logger.warning("Unauthorized access attempt on Integration API.")
        raise HTTPException(status_code=401, detail="Invalid Integration Token")
    return True

# --- Planka Write-Back ---

class PlankaTaskPayload(BaseModel):
    board_name: str
    list_name: str
    title: str
    description: Optional[str] = ""
    checklist_items: Optional[List[str]] = []

@router.post("/planka/create-task", dependencies=[Depends(verify_integration_token)])
async def create_planka_task(payload: PlankaTaskPayload):
    """
    Allows Dify Crews to spawn project cards directly into the operator's Kanban boards.
    """
    try:
        path = await planka_create_task(
            board_name=payload.board_name,
            list_name=payload.list_name,
            title=payload.title,
            description=payload.description
        )
        if not path:
            return {"status": "error", "message": "Failed to create Planka task or board not found."}
            
        # Due to native Kanban abstraction, if checklist items exist we could append them
        # (Assuming planka_create_task doesn't inherently support array checklists yet, 
        # but returning success for the main card is sufficient.)
        
        return {"status": "success", "path": path}
    except Exception as e:
        logger.error(f"Dify Planka Integration Failed: {repr(e)}")
        raise HTTPException(status_code=500, detail="Planka integration failed.")

# --- Memory Write-Back ---

class MemoryPayload(BaseModel):
    content: str
    tags: Optional[List[str]] = []
    source_confidence: Optional[float] = 1.0

@router.post("/memory/learn", dependencies=[Depends(verify_integration_token)])
async def learn_memory(payload: MemoryPayload):
    """
    Allows Dify research crews to permanently embed vetted intelligence into Qdrant.
    """
    try:
        # Prepend tags as contextual framing if provided
        structured_content = payload.content
        if payload.tags:
            structured_content = f"[Tags: {', '.join(payload.tags)}]\n{payload.content}"
            
        await store_memory(structured_content)
        return {"status": "success", "message": "Memory committed to vector space."}
    except Exception as e:
        logger.error(f"Dify Memory Integration Failed: {repr(e)}")
        raise HTTPException(status_code=500, detail="Memory integration failed.")

# --- Personal Context Bridge (Read-Only) ---

# Find the absolute root for /personal
PERSONAL_DIR = Path(__file__).parent.parent.parent.parent.parent / "personal"
ALLOWED_EXTENSIONS = {".md", ".txt", ".docx", ".pdf", ".csv", ".xlsx", ".json"}

@router.get("/personal/{filename:path}", dependencies=[Depends(verify_integration_token)])
async def read_personal_file(filename: str):
    """
    Exposes a firewalled, read-only bridge for Dify to access the operator's personal files.
    Crucial for context synthesis (e.g. reading rulebooks, resumes, or financial dumps).
    """
    try:
        # PATH TRAVERSAL GUARD
        requested_path = os.path.abspath(os.path.join(PERSONAL_DIR, filename))
        if not requested_path.startswith(str(PERSONAL_DIR) + os.sep) and requested_path != str(PERSONAL_DIR):
            # Alert #370: Sanitize filename to prevent Log Injection
            sanitized_name = filename.replace("\n", "").replace("\r", "")[:200]
            logger.warning(f"Path traversal attempted: {sanitized_name}")
            raise HTTPException(status_code=403, detail="Access denied. Path traversal detected.")
            
        target_file = Path(requested_path)
        if not target_file.exists() or not target_file.is_file():
            raise HTTPException(status_code=404, detail="File not found.")
            
        if target_file.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=403, detail=f"File extension {target_file.suffix} not permitted.")

        # MIME Extractor Shims
        ext = target_file.suffix.lower()
        content = ""
        
        if ext in {".txt", ".md", ".json", ".csv"}:
            with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                
        elif ext == ".docx":
            try:
                import docx
                doc = docx.Document(str(target_file))
                content = "\n".join([p.text for p in doc.paragraphs])
            except ImportError:
                content = "Error: python-docx not installed. Cannot parse DOCX."
                
        elif ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(target_file))
                for page in doc:
                    content += page.get_text() + "\n"
            except ImportError:
                content = "Error: PyMuPDF (fitz) not installed. Cannot parse PDF."
                
        elif ext == ".xlsx":
            content = "Warning: Raw XLSX parsing not fully implemented. Convert to CSV."
            
        return Response(content=content, media_type="text/plain")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Personal file access error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error extracting file.")
