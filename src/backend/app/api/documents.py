"""
Document processing API endpoints for openZero dashboard.

POST /api/dashboard/documents/process
  - Accepts a file upload (PDF, DOCX, TXT, MD, max 10 MB)
  - Extracts and PII-strips text
  - Returns summary via LLM + offers to store in Qdrant memory

Auth: Dashboard token (same as all dashboard endpoints).
"""
import logging
from fastapi import APIRouter, Depends, File, Query, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.config import settings
from app.services.document_processor import (
	process_document,
	DocumentProcessingError,
	MAX_FILE_BYTES,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard/documents", tags=["documents"])


def _verify_token(token: str = Query(...)) -> None:
	"""Shared token check — mirrors the pattern used in dashboard.py."""
	if token != settings.DASHBOARD_TOKEN:
		raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/process")
async def process_document_endpoint(
	file: UploadFile = File(...),
	token: str = Query(...),
	summarize: bool = Query(default=True),
	learn: bool = Query(default=False),
	db: AsyncSession = Depends(get_db),
):
	"""
	Upload a document for Z to read.

	- **summarize**: If true, Z generates a summary of the document content.
	- **learn**: If true, the extracted (PII-stripped) text is stored as a
	  memory point in Qdrant so Z retains the knowledge permanently.
	"""
	_verify_token(token)

	if not file.filename:
		raise HTTPException(status_code=400, detail="No filename provided.")

	# Read with size guard
	data = await file.read(MAX_FILE_BYTES + 1)
	if len(data) > MAX_FILE_BYTES:
		raise HTTPException(
			status_code=413,
			detail=f"File exceeds maximum allowed size of {MAX_FILE_BYTES // (1024*1024)} MB.",
		)

	content_type = file.content_type or "application/octet-stream"

	try:
		result = await process_document(
			filename=file.filename,
			content_type=content_type,
			data=data,
			strip_pii=True,
		)
	except DocumentProcessingError as e:
		raise HTTPException(status_code=422, detail=str(e)) from None

	extracted_text = result["text"]
	response: dict = {
		"filename": result["filename"],
		"char_count": result["char_count"],
		"truncated": result["truncated"],
		"summary": None,
		"learned": False,
	}

	# Generate LLM summary if requested
	if summarize:
		try:
			from app.services.llm import chat_completion
			prompt = (
				f"The following is the extracted text of a document called "
				f"'{result['filename']}'. Please summarise it concisely in "
				f"3-5 bullet points, highlighting the most important information.\n\n"
				f"---\n{extracted_text}\n---"
			)
			summary = await chat_completion(
				messages=[{"role": "user", "content": prompt}],
				max_tokens=512,
			)
			response["summary"] = summary
		except Exception as e:
			logger.warning("Document summarization failed: %s", e)
			response["summary"] = None

	# Store in Qdrant memory if requested
	if learn:
		try:
			from app.services.memory import store_memory
			await store_memory(
				text=extracted_text,
				metadata={
					"source": "document_upload",
					"filename": result["filename"],
					"char_count": result["char_count"],
					"truncated": result["truncated"],
				},
			)
			response["learned"] = True
			logger.info(
				"Document '%s' stored in memory (%d chars)",
				result["filename"],
				result["char_count"],
			)
		except Exception as e:
			logger.error("Failed to store document in memory: %s", e)
			response["learned"] = False

	return response

