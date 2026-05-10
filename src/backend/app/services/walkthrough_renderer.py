"""Channel renderer for openZero walk-throughs."""
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def render_telegram(walkthrough: dict[str, Any]) -> None:
	"""Send walk-through to Telegram: summary first, then one message per stop."""
	from app.services.notifier import send_notification
	from app.config import settings

	summary = walkthrough.get("summary", "")
	web_link = f"{settings.BASE_URL}/dashboard" if getattr(settings, "BASE_URL", None) else ""
	header = summary
	if web_link:
		header += f"\n\n[View in Dashboard]({web_link})"
	try:
		await send_notification(header)
	except Exception as e:
		logger.warning("render_telegram: header send failed: %s", e)

	stops = walkthrough.get("stops", [])
	total = len(stops)
	for stop in stops:
		stop_text = f"Stop {stop.get('position', '?')}/{total}: {stop.get('node_label', 'Node')}\n\n{stop.get('context', '')}"
		# Chunk to 3800 chars
		chunk_size = 3800
		for offset in range(0, max(len(stop_text), 1), chunk_size):
			chunk = stop_text[offset:offset + chunk_size]
			try:
				await send_notification(chunk)
			except Exception as e:
				logger.warning("render_telegram: stop send failed: %s", e)


async def render_whatsapp(walkthrough: dict[str, Any]) -> None:
	"""Send walk-through to WhatsApp: plain text, no Markdown bold."""
	from app.config import settings
	if not getattr(settings, "WHATSAPP_TOKEN", None) and not getattr(settings, "WHATSAPP_ACCESS_TOKEN", None):
		logger.debug("render_whatsapp: WhatsApp not configured — skipping")
		return
	from app.api.whatsapp import send_whatsapp_message

	summary = walkthrough.get("summary", "")
	try:
		await send_whatsapp_message(summary)
	except Exception as e:
		logger.warning("render_whatsapp: header send failed: %s", e)

	stops = walkthrough.get("stops", [])
	total = len(stops)
	for stop in stops:
		stop_text = f"Stop {stop.get('position', '?')}/{total}: {stop.get('node_label', 'Node')}\n\n{stop.get('context', '')}"
		chunk_size = 3800
		for offset in range(0, max(len(stop_text), 1), chunk_size):
			chunk = stop_text[offset:offset + chunk_size]
			try:
				await send_whatsapp_message(chunk)
			except Exception as e:
				logger.warning("render_whatsapp: stop send failed: %s", e)


async def render_dashboard(walkthrough: dict[str, Any]) -> None:
	"""Walk-through is already persisted; push SSE notification event."""
	try:
		from app.services.message_bus import bus
		await bus.push("dashboard", f"[WALKTHROUGH:{walkthrough.get('id')}] New walk-through available.")
	except Exception as e:
		logger.debug("render_dashboard: SSE push failed (non-fatal): %s", e)


async def render_all(walkthrough: dict[str, Any]) -> None:
	"""Dispatch to all enabled channels."""
	from app.config import settings

	if getattr(settings, "TELEGRAM_BOT_TOKEN", None):
		try:
			await render_telegram(walkthrough)
		except Exception as e:
			logger.warning("render_all: Telegram render failed: %s", e)

	if getattr(settings, "WHATSAPP_TOKEN", None) or getattr(settings, "WHATSAPP_ACCESS_TOKEN", None):
		try:
			await render_whatsapp(walkthrough)
		except Exception as e:
			logger.warning("render_all: WhatsApp render failed: %s", e)

	try:
		await render_dashboard(walkthrough)
	except Exception as e:
		logger.warning("render_all: Dashboard render failed: %s", e)
