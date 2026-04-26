"""
WhatsApp Cloud API Adapter
──────────────────────────
Receives inbound messages from the Meta WhatsApp Cloud API via webhook,
routes them through the universal MessageBus, and delivers Z's reply back
over the Cloud API.

Setup (see BUILD.md for detailed steps):
  1.  Create a Meta App → WhatsApp → add a phone number.
  2.  Set the webhook URL to:  https://<your-domain>/api/whatsapp/webhook
  3.  Set WHATSAPP_WEBHOOK_VERIFY_TOKEN to any random secret you choose.
  4.  Set WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_ACCESS_TOKEN, WHATSAPP_APP_SECRET
      and WHATSAPP_ALLOWED_PHONE in your .env.

Security:
  - All inbound payloads are validated with HMAC-SHA256 (WHATSAPP_APP_SECRET).
  - Only messages from WHATSAPP_ALLOWED_PHONE are processed (owner-only).
  - Signature check is bypassed (warning only) when WHATSAPP_APP_SECRET is not set,
    to allow dev environments without a full Meta app approval.
"""

import hashlib
import hmac
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

_WA_API_VERSION = "v19.0"
_WA_API_BASE = f"https://graph.facebook.com/{_WA_API_VERSION}"


# ─── Outbound ────────────────────────────────────────────────────────────────

async def send_whatsapp_message(text: str) -> None:
	"""Send a plain-text message to the owner's WhatsApp number."""
	if not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_ACCESS_TOKEN:
		logger.debug("WhatsApp not configured — skipping send.")
		return
	if not settings.WHATSAPP_ALLOWED_PHONE:
		logger.warning("WHATSAPP_ALLOWED_PHONE not set — cannot send WhatsApp message.")
		return

	url = f"{_WA_API_BASE}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
	headers = {
		"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
		"Content-Type": "application/json",
	}
	payload = {
		"messaging_product": "whatsapp",
		"to": settings.WHATSAPP_ALLOWED_PHONE,
		"type": "text",
		"text": {"body": text},
	}
	try:
		async with httpx.AsyncClient(timeout=30.0) as client:
			resp = await client.post(url, headers=headers, json=payload)
			if resp.status_code not in (200, 201):
				logger.error(
					"WhatsApp send failed: HTTP %s — %s",
					resp.status_code,
					resp.text[:300],
				)
	except Exception as exc:
		logger.error("WhatsApp send exception: %s", exc)


# ─── Signature Verification ───────────────────────────────────────────────────

def _verify_signature(raw_body: bytes, signature_header: Optional[str]) -> bool:
	"""Validate X-Hub-Signature-256 from Meta.

	Returns True if the signature matches or if WHATSAPP_APP_SECRET is not
	configured (dev-mode fallback — logs a warning).
	"""
	if not settings.WHATSAPP_APP_SECRET:
		logger.warning(
			"WHATSAPP_APP_SECRET not set — skipping signature verification. "
			"Set it in .env before exposing this endpoint to the internet."
		)
		return True

	if not signature_header or not signature_header.startswith("sha256="):
		logger.warning("WhatsApp webhook: missing or malformed X-Hub-Signature-256.")
		return False

	expected = hmac.new(
		settings.WHATSAPP_APP_SECRET.encode(),
		raw_body,
		hashlib.sha256,
	).hexdigest()
	received = signature_header.split("sha256=", 1)[1]
	return hmac.compare_digest(expected, received)


# ─── Background Message Handler ───────────────────────────────────────────────

async def _handle_inbound(sender: str, text: str) -> None:
	"""Process an inbound WhatsApp message through the unified router and reply.

	Routes through route_message_stream so intent classification (structural
	verbs like CREATE_PROJECT, MOVE_BOARD, etc.) and crew routing all work
	identically to the Telegram and Dashboard channels.
	"""
	from app.services.message_bus import bus
	from app.services.router import route_message_stream
	from app.services.crews import resolve_active_crews

	history = await bus.ingest("whatsapp", text)

	# Keyword crew routing (same priority as Telegram)
	routed_crews = await resolve_active_crews(history, text, lang="en")
	if routed_crews:
		from app.services.crews_native import native_crew_engine
		from app.services.llm import last_model_used
		try:
			result = await native_crew_engine.run_crew(routed_crews[0], text)
		except Exception as exc:
			logger.error("WhatsApp crew engine failed: %s", exc)
			await send_whatsapp_message("I encountered an error running that crew. Try again in a moment.")
			return
		reply, _, _ = await bus.commit_reply(
			channel="whatsapp",
			raw_reply=result,
			model=last_model_used.get(),
			user_text=text,
		)
		from app.services.crews import record_crew_session
		record_crew_session("whatsapp", routed_crews[0])
		await send_whatsapp_message(reply)
		return

	# Full router — handles intent classification, ACTION tags, phantom guard, memory
	try:
		import asyncio as _asyncio
		token_stream, result_fut = await route_message_stream(
			user_text=text,
			history=history,
			channel="whatsapp",
			lang="en",
			save_history=True,
		)
		try:
			from app.services.router import _REORGANIZE_BOARD_RE as _reorg_re
			_stream_timeout = 300.0 if _reorg_re.search(text[:500]) else 120.0
			async with _asyncio.timeout(_stream_timeout):
				async for _ in token_stream:
					pass
		except _asyncio.TimeoutError:
			logger.warning("WhatsApp route_message_stream timed out after %s s", _stream_timeout)
			await send_whatsapp_message("I ran out of time on that one. Please try again.")
			return
		result = await result_fut
	except Exception as exc:
		logger.error("WhatsApp route_message_stream failed: %s", exc)
		await send_whatsapp_message("I encountered an error reaching my reasoning core. Try again in a moment.")
		return

	if result.reply.strip():
		await send_whatsapp_message(result.reply)


async def _download_whatsapp_media(media_id: str) -> bytes:
	"""Download a WhatsApp media object by ID using the Graph API."""
	headers = {"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"}
	async with httpx.AsyncClient(timeout=30.0) as client:
		# Step 1: retrieve the download URL
		meta_resp = await client.get(
			f"{_WA_API_BASE}/{media_id}",
			headers=headers,
		)
		meta_resp.raise_for_status()
		download_url = meta_resp.json().get("url", "")
		if not download_url:
			raise ValueError(f"No URL returned for media_id {media_id}")
		# Step 2: download the binary content
		media_resp = await client.get(download_url, headers=headers)
		media_resp.raise_for_status()
		return media_resp.content


async def _handle_inbound_image(sender: str, media_id: str, user_hint: str) -> None:
	"""Download a WhatsApp image, caption it via the vision service, and route through Z."""
	from app.services.vision import caption_image
	from app.services.message_bus import bus
	from app.services.router import route_message_stream
	from app.services.crews import resolve_active_crews

	try:
		image_bytes = await _download_whatsapp_media(media_id)
	except Exception as exc:
		logger.error("WhatsApp: media download failed for %s: %s", media_id, exc)
		await send_whatsapp_message("Could not download your image.")
		return

	caption = await caption_image(image_bytes, user_hint)
	if not caption or caption.startswith("["):
		await send_whatsapp_message(caption or "Could not process image.")
		return

	logger.info("WhatsApp vision caption: %s", caption[:120])

	history = await bus.ingest("whatsapp", caption)

	routed_crews = await resolve_active_crews(history, caption, lang="en")
	if routed_crews:
		from app.services.crews_native import native_crew_engine
		from app.services.llm import last_model_used
		result = await native_crew_engine.run_crew(routed_crews[0], caption)
		reply, _, _ = await bus.commit_reply(
			channel="whatsapp",
			raw_reply=result,
			model=last_model_used.get(),
			user_text=caption,
		)
		from app.services.crews import record_crew_session
		record_crew_session("whatsapp", routed_crews[0])
		await send_whatsapp_message(reply)
		return

	import asyncio as _asyncio
	token_stream, result_fut = await route_message_stream(
		user_text=caption,
		history=history,
		channel="whatsapp",
		lang="en",
		save_history=True,
	)
	try:
		from app.services.router import _REORGANIZE_BOARD_RE as _reorg_re
		_stream_timeout = 300.0 if _reorg_re.search(caption[:500]) else 120.0
		async with _asyncio.timeout(_stream_timeout):
			async for _ in token_stream:
				pass
	except _asyncio.TimeoutError:
		logger.warning("WhatsApp image route_message_stream timed out after %s s", _stream_timeout)
		await send_whatsapp_message("I ran out of time processing that image. Please try again.")
		return
	result = await result_fut

	if result.reply.strip():
		await send_whatsapp_message(result.reply)


# ─── Webhook Routes ───────────────────────────────────────────────────────────

@router.get("/webhook", response_class=PlainTextResponse)
async def webhook_verify(
	hub_mode: Optional[str] = Query(None, alias="hub.mode"),
	hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
	hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
) -> str:
	"""Meta webhook verification handshake.

	Meta calls this GET endpoint once when you configure the webhook URL in
	the developer portal. It checks that hub.verify_token matches the secret
	you chose, then echoes back hub.challenge to confirm ownership.
	"""
	if not settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
		logger.error("WHATSAPP_WEBHOOK_VERIFY_TOKEN not set — rejecting Meta verification.")
		raise HTTPException(status_code=403, detail="Webhook not configured.")

	_token_match = hmac.compare_digest(
		(hub_verify_token or "").encode(),
		settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN.encode(),
	)
	if hub_mode == "subscribe" and _token_match:
		logger.info("WhatsApp webhook verified by Meta.")
		return hub_challenge or ""

	logger.warning(
		"WhatsApp webhook verification failed: mode=%r token_match=%s",
		str(hub_mode).replace('\n', ' ').replace('\r', ' '),
		_token_match,
	)
	raise HTTPException(status_code=403, detail="Verification failed.")


@router.post("/webhook", status_code=200)
async def webhook_receive(
	request: Request,
	background_tasks: BackgroundTasks,
) -> dict:
	"""Receive inbound WhatsApp messages from Meta.

	Meta expects a 200 OK within 5 seconds. The actual LLM processing and
	reply are deferred to a background task so we never miss that window.
	"""
	raw_body = await request.body()
	signature = request.headers.get("X-Hub-Signature-256")

	if not _verify_signature(raw_body, signature):
		raise HTTPException(status_code=403, detail="Signature mismatch.")

	try:
		payload = await request.json()
	except Exception:
		raise HTTPException(status_code=400, detail="Invalid JSON.") from None

	# Walk the standard Meta webhook envelope
	for entry in payload.get("entry", []):
		for change in entry.get("changes", []):
			if change.get("field") != "messages":
				continue
			value = change.get("value", {})
			for msg in value.get("messages", []):
				sender = msg.get("from", "")

				# Owner-only guard — silently discard messages from unknown numbers
				if settings.WHATSAPP_ALLOWED_PHONE and sender != settings.WHATSAPP_ALLOWED_PHONE:
					logger.warning(
						"WhatsApp: message from unallowed number %s — ignored.",
						sender.replace('\n', ' ').replace('\r', ' '),
					)
					continue

				msg_type = msg.get("type", "")
				if msg_type == "text":
					text = msg.get("text", {}).get("body", "").strip()
					if text:
						logger.info("WhatsApp inbound from %s: %s", sender.replace('\n', ' ').replace('\r', ' '), text[:80].replace('\n', ' ').replace('\r', ' '))
						background_tasks.add_task(_handle_inbound, sender, text)
				elif msg_type == "image":
					media_id = msg.get("image", {}).get("id", "")
					user_hint = msg.get("image", {}).get("caption", "")
					if media_id:
						logger.info("WhatsApp image inbound from %s (media_id=%s)", sender.replace('\n', ' ').replace('\r', ' '), media_id.replace('\n', ' ').replace('\r', ' '))
						background_tasks.add_task(_handle_inbound_image, sender, media_id, user_hint)
				else:
					logger.info(
						"WhatsApp: unsupported message type %r from %s — skipped.",
						str(msg_type).replace('\n', ' ').replace('\r', ' '),
						sender.replace('\n', ' ').replace('\r', ' '),
					)

	return {"status": "ok"}
