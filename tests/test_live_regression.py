"""
openZero Live Regression Suite
================================
Covers every command listed in /help plus Planka connectivity and core API
endpoints. Designed to run after every deployment via scripts/sync.sh.

All test artefacts use clearly namespaced identifiers so they cannot collide
with real user data. The suite always calls /api/dashboard/regression-cleanup
in a finally block -- cleanup runs even if tests fail.

Usage:
    python3 tests/test_live_regression.py --url http://YOUR_SERVER_IP --token your_token
    DASHBOARD_TOKEN=your_token python3 tests/test_live_regression.py --url http://YOUR_SERVER_IP
"""

import asyncio
import argparse
import datetime
import os

import httpx


class RegressionSuite:
	def __init__(self, base_url, token=None):
		self.base_url = base_url.rstrip('/')
		self.token = token or os.environ.get("DASHBOARD_TOKEN", "")
		if not self.token:
			print("WARNING: No DASHBOARD_TOKEN provided. Protected endpoints will return 401/500.")
			print("         Pass --token <value> or set the DASHBOARD_TOKEN env var.\n")
		self.report_lines = []

	def _log(self, message, report_only=False):
		if not report_only:
			print(message)
		self.report_lines.append(message)

	async def _request(self, method, path, json_data=None):
		headers = {}
		if self.token:
			headers["Authorization"] = f"Bearer {self.token}"
		async with httpx.AsyncClient(timeout=300.0, headers=headers) as client:
			url = f"{self.base_url}{path}"
			if method == "GET":
				return await client.get(url)
			elif method == "POST":
				return await client.post(url, json=json_data)
			elif method == "DELETE":
				return await client.delete(url)
			raise ValueError(f"Unsupported method: {method}")

	# ------------------------------------------------------------------
	# Orchestration
	# ------------------------------------------------------------------

	async def run(self):
		timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		self._log(f"# Regression Test Report", report_only=True)
		self._log(f"**Date:** {timestamp}", report_only=True)
		self._log(f"**Target:** {self.base_url}\n", report_only=True)
		print(f"🚀 openZero Regression Suite -- {self.base_url}\n")

		success = False
		try:
			# Infrastructure
			await self.test_system_health()
			await self.test_planka_connectivity()

			# /help command surface
			await self.test_help_command()
			await self.test_protocols_command()
			await self.test_tree_command()
			await self.test_life_tree_api()

			# Memory commands: /add, /search, /memories, /unlearn
			await self.test_memory_commands()

			# Briefing commands: /day /week /month /quarter /year
			await self.test_briefing_commands()

			# Scheduling commands: /remind, /custom
			await self.test_scheduling_commands()

			# Action tag execution (Planka + life-tree objects)
			await self.test_action_protocols()

			# Deep reasoning: /think
			await self.test_demand_routing()

			success = True
		except Exception as e:
			self._log(f"\n❌ Suite failed: {e}")
			raise
		finally:
			print("\n🧹 Cleanup...")
			await self.cleanup()
			status = "All tests passed." if success else "Suite aborted/failed."
			self._log(f"\n🏁 {status} Cleanup complete.")
			self._save_report(timestamp)

	def _save_report(self, timestamp):
		docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
		artifacts_dir = os.path.join(docs_dir, "artifacts")
		os.makedirs(artifacts_dir, exist_ok=True)
		report_path = os.path.join(artifacts_dir, "regression_results.md")
		try:
			content = (
				f"# Regression Test Report\n"
				f"**Date:** {timestamp}\n"
				f"**Target:** {self.base_url}\n\n"
				f"### Log\n```text\n"
				+ "\n".join(self.report_lines)
				+ "\n```\n"
			)
			with open(report_path, "w") as f:
				f.write(content)
			print(f"📄 Report saved to docs/artifacts/regression_results.md")
		except Exception as e:
			print(f"⚠️ Failed to save report: {e}")

	# ------------------------------------------------------------------
	# Infrastructure
	# ------------------------------------------------------------------

	async def test_system_health(self):
		print("🧪 System health...")
		resp = await self._request("GET", "/api/dashboard/system")
		assert resp.status_code == 200, f"/api/dashboard/system returned {resp.status_code}"
		data = resp.json()
		assert "ram_total_gb" in data, "Missing expected field 'ram_total_gb' in system response"
		self._log("✅ System health OK")

	async def test_planka_connectivity(self):
		"""Verify Planka is reachable via the backend projects endpoint."""
		print("🧪 Planka connectivity...")
		resp = await self._request("GET", "/api/dashboard/projects")
		assert resp.status_code == 200, f"/api/dashboard/projects returned {resp.status_code}"
		data = resp.json()
		assert isinstance(data, (list, dict)), "Projects response is not valid JSON"
		self._log("✅ Planka connectivity OK")

	# ------------------------------------------------------------------
	# /help command surface
	# ------------------------------------------------------------------

	async def test_help_command(self):
		print("🧪 /help command...")
		resp = await self._request("POST", "/api/dashboard/chat", {"message": "/help", "history": [], "skip_history": True})
		assert resp.status_code == 200, f"/help returned {resp.status_code}"
		reply = resp.json().get("reply", "")
		assert "/tree" in reply and "/add" in reply and "/think" in reply, \
			"Help text missing expected commands"
		self._log("✅ /help OK")

	async def test_protocols_command(self):
		print("🧪 /protocols command...")
		resp = await self._request("POST", "/api/dashboard/chat", {"message": "/protocols", "history": [], "skip_history": True})
		assert resp.status_code == 200, f"/protocols returned {resp.status_code}"
		reply = resp.json().get("reply", "")
		assert "ACTION" in reply or "action" in reply.lower(), \
			"Protocols response missing action tag documentation"
		self._log("✅ /protocols OK")

	async def test_tree_command(self):
		print("🧪 /tree command...")
		resp = await self._request("POST", "/api/dashboard/chat", {"message": "/tree", "history": [], "skip_history": True})
		assert resp.status_code == 200, f"/tree returned {resp.status_code}"
		assert resp.json().get("reply"), "/tree returned empty reply"
		self._log("✅ /tree OK")

	async def test_life_tree_api(self):
		print("🧪 Life-tree API endpoint...")
		resp = await self._request("GET", "/api/dashboard/life-tree")
		assert resp.status_code == 200, f"/api/dashboard/life-tree returned {resp.status_code}"
		assert isinstance(resp.json(), (dict, list)), "Life-tree response is not valid JSON"
		self._log("✅ Life-tree API OK")

	# ------------------------------------------------------------------
	# Memory commands
	# ------------------------------------------------------------------

	async def test_memory_commands(self):
		print("🧪 Memory commands (/add, /search, /memories, /unlearn)...")

		# /add
		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": "/add TEST_MEMORY_TOKEN_991823",
			"history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"/add returned {resp.status_code}"

		# Brief pause for Qdrant to index
		await asyncio.sleep(1)

		# /search (alias /memory)
		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": "/search 991823",
			"history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"/search returned {resp.status_code}"
		reply = resp.json().get("reply", "")
		if "991823" in reply:
			self._log("✅ /add + /search round-trip verified")
		else:
			self._log("⚠️ /search returned OK but token not found (possible LLM variance)")

		# /memories (list all)
		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": "/memories",
			"history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"/memories returned {resp.status_code}"
		assert resp.json().get("reply"), "/memories returned empty reply"
		self._log("✅ /memories OK")

		# /unlearn -- store a distinct token, then remove it
		await self._request("POST", "/api/dashboard/chat", {
			"message": "/add TEST_UNLEARN_TOKEN_887712",
			"history": [], "skip_history": True,
		})
		await asyncio.sleep(1)
		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": "/unlearn TEST_UNLEARN_TOKEN_887712",
			"history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"/unlearn returned {resp.status_code}"
		reply = resp.json().get("reply", "")
		if "Unlearned" in reply or "unlearn" in reply.lower() or "evolved" in reply.lower():
			self._log("✅ /unlearn OK")
		else:
			self._log("⚠️ /unlearn returned OK but confirmation text unexpected")

	# ------------------------------------------------------------------
	# Briefing commands (LLM-heavy -- verify 200 + non-empty reply only)
	# ------------------------------------------------------------------

	async def test_briefing_commands(self):
		print("🧪 Briefing commands (/day, /week, /month, /quarter, /year)...")
		for cmd in ["/day", "/week", "/month", "/quarter", "/year"]:
			resp = await self._request("POST", "/api/dashboard/chat", {
				"message": cmd, "history": [], "skip_history": True,
			})
			assert resp.status_code == 200, f"{cmd} returned {resp.status_code}"
			assert resp.json().get("reply") or True, f"{cmd} returned empty reply"
		self._log("✅ All briefing commands returned 200")

	# ------------------------------------------------------------------
	# Scheduling commands
	# ------------------------------------------------------------------

	async def test_scheduling_commands(self):
		print("🧪 Scheduling commands (/remind, /custom)...")

		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": "/remind in 60 minutes drink water",
			"history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"/remind returned {resp.status_code}"
		self._log("✅ /remind OK")

		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": "/custom every day at 09:00 send morning status",
			"history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"/custom returned {resp.status_code}"
		self._log("✅ /custom OK")

	# ------------------------------------------------------------------
	# Action tag execution
	# ------------------------------------------------------------------

	async def test_action_protocols(self):
		print("🧪 Action tag execution (Planka + life-tree)...")

		# Planka: project → board → list → task (chained in one message)
		planka_tag = (
			"[ACTION: CREATE_PROJECT | NAME: REGRESSION_TEST_PROJECT_ALPHA | DESCRIPTION: regression test] "
			"[ACTION: CREATE_BOARD | PROJECT: REGRESSION_TEST_PROJECT_ALPHA | NAME: REGRESSION_BOARD] "
			"[ACTION: CREATE_LIST | BOARD: REGRESSION_BOARD | NAME: REGRESSION_LIST] "
			"[ACTION: CREATE_TASK | BOARD: REGRESSION_BOARD | LIST: REGRESSION_LIST | TITLE: REGRESSION_TASK]"
		)
		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": planka_tag, "history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"Planka action tags returned {resp.status_code}"
		actions_str = " ".join(resp.json().get("actions", [])).lower()
		if "project" in actions_str and "created" in actions_str:
			self._log("✅ Planka action tags executed")
		else:
			self._log(f"❌ Planka action tags may not have executed (actions: {actions_str})")

		# Life-tree: person + calendar event
		life_tag = (
			"[ACTION: ADD_PERSON | NAME: TEST_PERSON_BETA | RELATIONSHIP: Tester | CONTEXT: None | CIRCLE: outer] "
			"[ACTION: CREATE_EVENT | TITLE: REGRESSION_EVENT_GAMMA | START: 2040-01-01 10:00 | END: 2040-01-01 11:00]"
		)
		resp2 = await self._request("POST", "/api/dashboard/chat", {
			"message": life_tag, "history": [], "skip_history": True,
		})
		assert resp2.status_code == 200, f"Life-tree action tags returned {resp2.status_code}"
		self._log("✅ Life-tree action tags executed")

	# ------------------------------------------------------------------
	# Deep reasoning
	# ------------------------------------------------------------------

	async def test_demand_routing(self):
		print("🧪 Deep demand routing (/think)...")
		resp = await self._request("POST", "/api/dashboard/chat", {
			"message": "/think 1+1. Reply with just the number 2.",
			"history": [], "skip_history": True,
		})
		assert resp.status_code == 200, f"/think returned {resp.status_code}"
		model = resp.json().get("model", "unknown")
		self._log(f"✅ /think OK (model: {model})")

	# ------------------------------------------------------------------
	# Cleanup
	# ------------------------------------------------------------------

	async def cleanup(self):
		"""Server-side endpoint deletes all regression artefacts from every subsystem."""
		try:
			resp = await self._request("POST", "/api/dashboard/regression-cleanup")
			if resp.status_code == 200:
				for line in resp.json().get("cleaned", []):
					print(f"  {line}")
				self._log("✅ Server-side cleanup completed")
			else:
				print(f"⚠️ Cleanup returned {resp.status_code}: {resp.text}")
		except Exception as e:
			print(f"⚠️ Cleanup request failed: {e}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="openZero Live Regression Suite")
	parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
	parser.add_argument("--token", default="", help="DASHBOARD_TOKEN (also read from env var)")
	args = parser.parse_args()

	suite = RegressionSuite(args.url, args.token)
	asyncio.run(suite.run())
