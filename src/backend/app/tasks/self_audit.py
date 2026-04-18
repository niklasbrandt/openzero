from app.services.self_audit import run_full_audit
import logging

logger = logging.getLogger(__name__)


async def run_self_audit() -> None:
	"""Periodic self-verification & action fulfillment audit task.

	Runs all three audit checks (action fulfillment, hallucination detection,
	redundancy) and surfaces any flags via the existing notifier.
	Skips delivery silently when all checks are clean.
	"""
	logger.info("Self-audit: starting.")
	try:
		report = await run_full_audit()
		if not report:
			logger.info("Self-audit: clean — no flags raised.")
			return
		from app.services.notifier import send_notification
		await send_notification(report)
		logger.info("Self-audit: report sent (%d chars).", len(report))
	except Exception as e:
		logger.error("Self-audit task failed: %s", e)
