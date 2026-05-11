"""Backup API — GET /preview, GET /export, POST /import."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, File  # noqa: B008
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, AsyncIterator

from app.api.dashboard import require_auth
from app.services.backup import (
	build_export_bundle,
	get_preview_section,
	import_bundle,
	passphrase_strength,
	backup_filename,
	ImportReport,
)

router = APIRouter(prefix="/api/dashboard/backup", dependencies=[Depends(require_auth)])


class StrengthResponse(BaseModel):
	score: int
	warning: str
	ok: bool


@router.get("/strength")
async def check_passphrase_strength(p: str = Query(..., min_length=1, max_length=256)) -> StrengthResponse:
	result = passphrase_strength(p)
	return StrengthResponse(**result)


@router.get("/preview")
async def backup_preview(
	section: str = Query("planka"),
	cursor: int = Query(0, ge=0),
	page_size: int = Query(50, ge=1, le=200),
) -> dict:
	allowed_sections = {"planka", "memory", "atlas", "custom_tasks", "walkthroughs"}
	if section not in allowed_sections:
		raise HTTPException(status_code=400, detail=f"Unknown section. Valid: {sorted(allowed_sections)}")
	return await get_preview_section(section, cursor, page_size)


@router.get("/export")
async def backup_export(
	passphrase: str = Query(..., min_length=12, max_length=256),
	include_preferences: bool = Query(True),
) -> StreamingResponse:
	strength = passphrase_strength(passphrase)
	if not strength.get("ok"):
		raise HTTPException(status_code=400, detail="Passphrase must be at least 12 characters.")

	encrypted_bytes, bundle = await build_export_bundle(
		passphrase=passphrase,
		include_preferences=include_preferences,
	)

	slug = bundle.manifest.instance_slug
	filename = backup_filename(slug)

	async def _stream() -> AsyncIterator[bytes]:
		yield encrypted_bytes

	return StreamingResponse(
		_stream(),
		media_type="application/octet-stream",
		headers={
			"Content-Disposition": f'attachment; filename="{filename}"',
			"X-Backup-Schema-Version": str(bundle.manifest.schema_version),
			"X-Backup-Instance": slug,
			"X-Backup-Sections": ",".join(bundle.manifest.sections),
		},
	)


class ImportQueryParams(BaseModel):
	dry_run: bool = False
	conflict: str = "skip"
	include_preferences: bool = False


@router.post("/import")
async def backup_import(
	file: UploadFile = File(...),  # noqa: B008
	passphrase: str = Query(..., min_length=1, max_length=256),
	dry_run: bool = Query(False),
	conflict: str = Query("skip"),
	include_preferences: bool = Query(False),
	x_confirm_destructive: Optional[str] = Header(None),
) -> ImportReport:
	allowed_conflicts = {"skip", "merge", "replace"}
	if conflict not in allowed_conflicts:
		raise HTTPException(status_code=400, detail=f"conflict must be one of {sorted(allowed_conflicts)}")

	confirm_destructive = (x_confirm_destructive or "").lower() == "yes"

	# Read uploaded file
	data = await file.read()
	if not data:
		raise HTTPException(status_code=400, detail="Uploaded file is empty.")

	# Limit file size to 256 MB
	if len(data) > 256 * 1024 * 1024:
		raise HTTPException(status_code=413, detail="Backup file exceeds 256 MB limit.")

	return await import_bundle(
		data=data,
		passphrase=passphrase,
		dry_run=dry_run,
		conflict=conflict,
		include_preferences=include_preferences,
		confirm_destructive=confirm_destructive,
	)
