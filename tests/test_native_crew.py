import asyncio
import logging
import httpx
from app.services.crews_native import native_crew_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_native():
	logger.info("Native Test: Initiating tactical mission 'nutrition'...")
	try:
		# We test the 'nutrition' crew directly
		res = await native_crew_engine.run_crew("nutrition", "What is a good sugar-free cookie recipe?")
		logger.info(f"Native Test Result: {res[:200]}...")
		logger.info("✅ Native Tactical Handshake: SUCCESSFUL")
	except Exception as e:
		logger.error(f"❌ Native Tactical Handshake: FAILED - {e}")
		exit(1)

if __name__ == "__main__":
	asyncio.run(test_native())
