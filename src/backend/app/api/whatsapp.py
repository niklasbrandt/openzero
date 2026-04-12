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
	"""Process an inbound WhatsApp message through the bus and reply."""
	from app.services.llm import chat_with_context, last_model_used
	from app.services.message_bus import bus

	history = await bus.ingest("whatsapp", text)

	try:
		raw = await chat_with_context(
			text,
			history=history,
			include_projects=True,
			include_people=True,
		)
	except Exception as exc:
		logger.error("WhatsApp LLM call failed: %s", exc)
		await send_whatsapp_message("I encountered an error reaching my reasoning core. Try again in a moment.")
		return

	if not raw or not raw.strip():
		logger.warning("WhatsApp: LLM returned empty response.")
		return

	reply, _, _ = await bus.commit_reply(
		channel="whatsapp",
		raw_reply=raw,
		model=last_model_used.get(),
		user_text=text,
	)

	await send_whatsapp_message(reply)


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

	if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
		logger.info("WhatsApp webhook verified by Meta.")
		return hub_challenge or ""

	logger.warning(
		"WhatsApp webhook verification failed: mode=%r token_match=%s",
		str(hub_mode).replace('\n', ' ').replace('\r', ' '),
		hub_verify_token == settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN,
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
				else:
					logger.info(
						"WhatsApp: unsupported message type %r from %s — skipped.",
						str(msg_type).replace('\n', ' ').replace('\r', ' '),
						sender.replace('\n', ' ').replace('\r', ' '),
					)

	return {"status": "ok"}
