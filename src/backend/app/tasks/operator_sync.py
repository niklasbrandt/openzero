from app.services.operator_board import operator_service
import logging

logger = logging.getLogger(__name__)

async def run_operator_sync():
    """Background task to sync project boards with the Operator Board."""
    logger.info("Starting scheduled Operator Board synchronization...")
    result = await operator_service.sync_operator_tasks()
    logger.info(f"Operator Sync Result: {result}")
