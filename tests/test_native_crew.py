import sys
import os
import asyncio
import logging
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

from app.services.crews import crew_registry
from app.services.crews_native import native_crew_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.mark.anyio
async def test_native():
	await crew_registry.load()
	logger.info("Native Test: Initiating tactical mission 'nutrition'...")
	res = await native_crew_engine.run_crew("nutrition", "What is a good sugar-free cookie recipe?")
	assert res, "native_crew_engine.run_crew returned empty result"
	logger.info(f"Native Test Result: {res[:200]}...")
	logger.info("Native Tactical Handshake: SUCCESSFUL")

if __name__ == "__main__":
	asyncio.run(test_native())
