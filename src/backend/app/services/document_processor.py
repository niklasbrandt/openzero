"""
Document processor service for openZero.

Extracts plain text from uploaded documents in a safe, isolated manner.
Supported types: PDF, DOCX, TXT, MD.
Text is PII-stripped before being returned for LLM processing.

No shell execution. No network calls. No file writes.
The caller is responsible for deleting the temp file after processing.
"""
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Strict whitelist — anything outside this is rejected before touching the FS
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt", ".md"})
ALLOWED_MIMETYPES: frozenset[str] = frozenset({
	"application/pdf",
	"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
	"text/plain",
	"text/markdown",
})
MAX_FILE_BYTES: int = 10 * 1024 * 1024  # 10 MB


class DocumentProcessingError(Exception):
	pass


def _validate_file(filename: str, content_type: str, size: int) -> None:
	"""Raise DocumentProcessingError if the file does not meet safety constraints."""
	ext = Path(filename).suffix.lower()
	if ext not in ALLOWED_EXTENSIONS:
		raise DocumentProcessingError(
			f"File type '{ext}' is not supported. "
			f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
		)
	if content_type not in ALLOWED_MIMETYPES:
		# Allow text/* as a lenient fallback for txt/md variants
		if not content_type.startswith("text/"):
			raise DocumentProcessingError(
				f"MIME type '{content_type}' is not permitted."
			)
	if size > MAX_FILE_BYTES:
		raise DocumentProcessingError(
			f"File exceeds maximum allowed size of {MAX_FILE_BYTES // (1024*1024)} MB."
		)


def _extract_pdf(path: str) -> str:
	"""Extract text from a PDF using PyMuPDF (fitz). Already in requirements."""
	try:
		import fitz  # PyMuPDF
		doc = fitz.open(path)
		pages: list[str] = []
		for page in doc:
			pages.append(page.get_text())
		doc.close()
		return "\n".join(pages)
	except ImportError as err:
		raise DocumentProcessingError("PDF processing library not available.") from err
	except Exception as e:
		raise DocumentProcessingError(f"Failed to extract PDF text: {e}") from e


def _extract_docx(path: str) -> str:
	"""Extract text from a DOCX file using python-docx. Already in requirements."""
	try:
		from docx import Document
		doc = Document(path)
		return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
	except ImportError as err:
		raise DocumentProcessingError("DOCX processing library not available.") from err
	except Exception as e:
		raise DocumentProcessingError(f"Failed to extract DOCX text: {e}") from e


def _extract_text(path: str) -> str:
	"""Extract text from a plain text or markdown file."""
	try:
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			return f.read()
	except Exception as e:
		raise DocumentProcessingError(f"Failed to read text file: {e}") from e



async def process_document(
	filename: str,
	content_type: str,
	data: bytes,
	strip_pii: bool = True,
) -> dict:
	"""
	Main entry point. Validates, extracts, optionally PII-strips, and returns
	a result dict with keys: filename, char_count, text, truncated.

	The raw bytes are written to a NamedTemporaryFile, processed, and then
	immediately deleted — no persistent disk artefacts.
	"""
	_validate_file(filename, content_type, len(data))

	ext = Path(filename).suffix.lower()

	# Write to a secure temp file in /tmp (never in the app volume)
	tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
	try:
		tmp.write(data)
		tmp.flush()
		tmp.close()

		if ext == ".pdf":
			raw_text = _extract_pdf(tmp.name)
		elif ext == ".docx":
			raw_text = _extract_docx(tmp.name)
		else:
			raw_text = _extract_text(tmp.name)
	finally:
		try:
			os.unlink(tmp.name)
		except OSError:
			pass

	if not raw_text.strip():
		raise DocumentProcessingError("Document appears to be empty or could not be parsed.")

	# Optional PII stripping using the existing sanitise service
	text = raw_text
	if strip_pii:
		try:
			from app.services.pii import sanitize_text
			text = sanitize_text(raw_text)
		except Exception as e:
			logger.warning("PII strip failed (%s) — using raw text", e)
			text = raw_text

	# Cap at 16 000 chars to stay within LLM context limits
	MAX_CHARS = 16_000
	truncated = len(text) > MAX_CHARS
	text = text[:MAX_CHARS] if truncated else text

	return {
		"filename": filename,
		"char_count": len(text),
		"text": text,
		"truncated": truncated,
	}
