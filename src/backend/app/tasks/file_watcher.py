"""
Proactive file watcher for openZero.

Polls /app/watch/ on a configurable interval. When new or changed files
are detected, they are processed through document_processor.py,
PII-stripped, stored in Qdrant memory, and the operator is notified
via Telegram.

The watch directory is a Docker volume (watch_data) — operators populate
it via rsync or the dashboard upload endpoint. No inotify dependency;
polling is used for simplicity and VPS compatibility.

File state is tracked in Redis via SHA-256 content hashes to avoid
processing the same file twice.
"""
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

WATCH_DIR = Path("/app/watch")
REDIS_KEY_PREFIX = "watcher:file_hash:"
MAX_FILES_PER_RUN = 5


def _hash_file(path: Path) -> str:
	"""Return the SHA-256 hex digest of a file's contents."""
	h = hashlib.sha256()
	with open(path, "rb") as f:
		for chunk in iter(lambda: f.read(65536), b""):
			h.update(chunk)
	return h.hexdigest()


async def _get_stored_hash(redis_client, file_path: Path) -> str | None:
	key = REDIS_KEY_PREFIX + str(file_path.relative_to(WATCH_DIR))
	val = await redis_client.get(key)
	return val.decode() if val else None


async def _store_hash(redis_client, file_path: Path, digest: str) -> None:
	key = REDIS_KEY_PREFIX + str(file_path.relative_to(WATCH_DIR))
	await redis_client.set(key, digest)


async def run_file_watcher() -> None:
	"""
	APScheduler entry point. Scans the watch directory for new or changed
	files and processes each one through the document pipeline.
	"""
	from app.config import settings

	# Guard: feature must be explicitly enabled in config.yaml
	doc_cfg = getattr(settings, "WATCH_DIRECTORY_ENABLED", False)
	if not doc_cfg:
		return

	if not WATCH_DIR.exists():
		logger.debug("Watch directory %s does not exist — skipping.", WATCH_DIR)
		return

	# Collect candidate files — skip hidden, temp, and oversized files
	from app.services.document_processor import ALLOWED_EXTENSIONS, MAX_FILE_BYTES

	candidates: list[Path] = []
	for entry in WATCH_DIR.iterdir():
		if not entry.is_file():
			continue
		if entry.name.startswith(".") or entry.name.startswith("~"):
			continue
		if entry.suffix.lower() not in ALLOWED_EXTENSIONS:
			continue
		try:
			if entry.stat().st_size > MAX_FILE_BYTES:
				logger.warning("Watcher: skipping oversized file %s", entry.name)
				continue
		except OSError:
			continue
		candidates.append(entry)

	if not candidates:
		return

	# Redis for hash-based change detection
	try:
		import redis.asyncio as aioredis
		redis_client = aioredis.from_url(
			f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"
			if settings.REDIS_PASSWORD
			else f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"
		)
	except Exception as e:
		logger.error("Watcher: Redis connection failed: %s", e)
		return

	new_files: list[Path] = []
	for path in candidates:
		try:
			digest = _hash_file(path)
			stored = await _get_stored_hash(redis_client, path)
			if stored != digest:
				new_files.append(path)
		except Exception as e:
			logger.warning("Watcher: hash check failed for %s: %s", path.name, e)

	if not new_files:
		await redis_client.aclose()
		return

	# Rate-limit: process at most MAX_FILES_PER_RUN per interval
	to_process = new_files[:MAX_FILES_PER_RUN]
	skipped = len(new_files) - len(to_process)
	if skipped:
		logger.info("Watcher: rate-limiting — deferring %d file(s) to next run.", skipped)

	from app.services.document_processor import process_document, DocumentProcessingError
	from app.services.memory import store_memory

	processed: list[str] = []

	for path in to_process:
		try:
			data = path.read_bytes()
			content_type = _guess_content_type(path)

			result = await process_document(
				filename=path.name,
				content_type=content_type,
				data=data,
				strip_pii=True,
			)

			# Store in Qdrant
			await store_memory(
				text=result["text"],
				metadata={
					"source": "file_watcher",
					"filename": path.name,
					"char_count": result["char_count"],
					"truncated": result["truncated"],
				},
			)

			# Update stored hash so this file is not reprocessed
			digest = _hash_file(path)
			await _store_hash(redis_client, path, digest)

			processed.append(path.name)
			logger.info("Watcher: processed and stored '%s' (%d chars)", path.name, result["char_count"])

		except DocumentProcessingError as e:
			logger.warning("Watcher: skipped '%s' — %s", path.name, e)
		except Exception as e:
			logger.error("Watcher: unexpected error processing '%s': %s", path.name, e)

	await redis_client.aclose()

	# Notify operator via Telegram if any files were processed
	if processed:
		try:
			from app.services.notifier import send_notification
			noun = "file" if len(processed) == 1 else "files"
			names = ", ".join(f"`{n}`" for n in processed)
			message = (
				f"Z has automatically processed {len(processed)} new {noun} "
				f"from the watch directory and stored the content in memory.\n\n"
				f"Files: {names}"
			)
			await send_notification(message)
		except Exception as e:
			logger.warning("Watcher: notification failed: %s", e)


def _guess_content_type(path: Path) -> str:
	"""Return a best-guess MIME type for the given file extension."""
	ext = path.suffix.lower()
	mapping = {
		".pdf": "application/pdf",
		".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		".txt": "text/plain",
		".md": "text/markdown",
	}
	return mapping.get(ext, "application/octet-stream")
