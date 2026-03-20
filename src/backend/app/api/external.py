from fastapi import APIRouter, Header, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from typing import Optional, Dict, Any
import logging
from app.config import settings
from app.services.planka import planka_create_task
from app.services.learning import learn_memory
from app.services.notifier import send_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/external", tags=["External Integration"])

INTEGRATION_HEADER = "X-Integration-Token"
api_key_header = APIKeyHeader(name=INTEGRATION_HEADER, auto_error=False)

async def verify_integration_token(token: str = Security(api_key_header)):
	"""Verify that the caller has the correct integration token."""
	if not token or token != settings.INTEGRATION_TOKEN:
		logger.warning("Unauthorized external API access attempt.")
		raise HTTPException(status_code=401, detail="Invalid Integration Token")
	return token

@router.post("/planka/create-task", dependencies=[Depends(verify_integration_token)])
async def external_create_task(payload: Dict[str, Any]):
	"""Create a task on the operator board from an external system (e.g., Dify)."""
	title = payload.get("title")
	description = payload.get("description", "")
	list_name = payload.get("list_name", "Todo")
	
	if not title:
		raise HTTPException(status_code=400, detail="Title is required")
		
	path = await planka_create_task(title, description, list_name)
	if path:
		await send_notification(f"\U0001f504 *External Action: Task Created*\n\n{path}\n- {title}")
		return {"status": "success", "path": path}
	else:
		raise HTTPException(status_code=500, detail="Failed to create task in Planka")

@router.post("/memory/learn", dependencies=[Depends(verify_integration_token)])
async def external_learn_memory(payload: Dict[str, Any]):
	"""Save a new semantic memory from an external system."""
	text = payload.get("text")
	if not text:
		raise HTTPException(status_code=400, detail="Text is required")
		
	success = await learn_memory(text)
	if success:
		await send_notification(f"\U0001f4a1 *External Action: Memory Learned*\n\n{text[:100]}...")
		return {"status": "success"}
	else:
		raise HTTPException(status_code=500, detail="Failed to save memory")

@router.get("/status", dependencies=[Depends(verify_integration_token)])
async def external_status():
	"""Check connection status for external systems."""
	return {"status": "connected", "identity": "openZero Bridge"}
