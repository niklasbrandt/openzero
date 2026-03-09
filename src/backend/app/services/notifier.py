"""notifier.py — Thin notification shim that decouples task modules from the Telegram handler.

Task modules (morning, email_poll, quarterly, follow_up, etc.) import from here instead of
app.api.telegram_bot, breaking circular import cycles. The Telegram bot registers its send
functions once at startup via notifier.register(); until then every call is a silent no-op
with a WARNING log — matching the existing behaviour when the bot is not configured.

Usage in task modules:
    from app.services.notifier import send_notification, get_stats_footer

Registration by telegram_bot.py at startup:
    from app.services import notifier as _notifier
    _notifier.register(
        send=send_notification,
        send_html=send_notification_html,
        send_voice=send_voice_message,
        stats_footer=_get_stats_footer,
        nav_markup=get_nav_markup,
    )
"""
from typing import Any, Awaitable, Callable, Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registered callbacks — set by telegram_bot.start_telegram_bot()
# ---------------------------------------------------------------------------
_fn_send: Optional[Callable[..., Awaitable[None]]] = None
_fn_send_html: Optional[Callable[..., Awaitable[None]]] = None
_fn_send_voice: Optional[Callable[..., Awaitable[None]]] = None
_fn_stats_footer: Optional[Callable[[], Awaitable[str]]] = None
_fn_nav_markup: Optional[Callable[..., Any]] = None


def register(
	send: Callable[..., Awaitable[None]],
	send_html: Callable[..., Awaitable[None]],
	send_voice: Callable[..., Awaitable[None]],
	stats_footer: Callable[[], Awaitable[str]],
	nav_markup: Callable[..., Any],
) -> None:
	"""Register Telegram send functions. Called once by start_telegram_bot()."""
	global _fn_send, _fn_send_html, _fn_send_voice, _fn_stats_footer, _fn_nav_markup
	_fn_send = send
	_fn_send_html = send_html
	_fn_send_voice = send_voice
	_fn_stats_footer = stats_footer
	_fn_nav_markup = nav_markup
	logger.debug("notifier: Telegram send functions registered")


# ---------------------------------------------------------------------------
# Public API — mirrors the signatures from telegram_bot.py
# ---------------------------------------------------------------------------

async def send_notification(text: str, **kwargs: Any) -> None:
	"""Send a plain-text or Markdown Telegram notification."""
	if _fn_send is None:
		logger.warning("notifier: bot not initialised — dropping notification")
		return
	await _fn_send(text, **kwargs)


async def send_notification_html(text: str, **kwargs: Any) -> None:
	"""Send an HTML-formatted Telegram notification."""
	if _fn_send_html is None:
		logger.warning("notifier: bot not initialised — dropping HTML notification")
		return
	await _fn_send_html(text, **kwargs)


async def send_voice_message(audio_bytes: bytes, **kwargs: Any) -> None:
	"""Send a voice message via Telegram."""
	if _fn_send_voice is None:
		logger.warning("notifier: bot not initialised — dropping voice message")
		return
	await _fn_send_voice(audio_bytes, **kwargs)


async def get_stats_footer() -> str:
	"""Return the formatted Z stats footer string (e.g. for briefings)."""
	if _fn_stats_footer is None:
		return ""
	return await _fn_stats_footer()


def get_nav_markup(*args: Any, **kwargs: Any) -> Any:
	"""Return the standard navigation InlineKeyboardMarkup, or None if bot not ready."""
	if _fn_nav_markup is None:
		return None
	return _fn_nav_markup(*args, **kwargs)
