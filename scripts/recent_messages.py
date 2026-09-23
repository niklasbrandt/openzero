#!/usr/bin/env python3
"""Rapidly fetch, inspect, and analyze recent conversation turns from openZero.

Connects to PostgreSQL (via SSH to VPS or locally via Docker/localhost) to query
the `global_messages` table. Tracks the last inspected message ID in a watermark file
(.last_read_message_id) so subsequent runs inspect only newly arrived messages.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

WATERMARK_FILE = Path(".last_read_message_id")


def load_env() -> dict[str, str]:
	"""Load configuration from .env if present without external dependencies."""
	env_vars: dict[str, str] = {}
	env_path = Path(".env")
	if env_path.exists():
		with open(env_path, "r", encoding="utf-8") as f:
			for line in f:
				line = line.strip()
				if not line or line.startswith("#"):
					continue
				if "=" in line:
					k, v = line.split("=", 1)
					env_vars[k.strip()] = v.strip().strip("'\"")
	return env_vars


def get_last_watermark() -> int:
	"""Read the last inspected message ID from the watermark file."""
	if WATERMARK_FILE.exists():
		try:
			val = WATERMARK_FILE.read_text(encoding="utf-8").strip()
			return int(val)
		except Exception:
			return 0
	return 0


def set_last_watermark(msg_id: int):
	"""Save the last inspected message ID to the watermark file."""
	try:
		WATERMARK_FILE.write_text(str(msg_id), encoding="utf-8")
	except Exception as e:
		sys.stderr.write(f"Warning: could not write watermark file: {e}\n")


def execute_query(sql: str) -> list[dict]:
	"""Execute SQL against PostgreSQL via SSH (if remote configured) or local docker."""
	env = load_env()
	remote_user = os.environ.get("REMOTE_USER") or env.get("REMOTE_USER", "openzero")
	remote_host = os.environ.get("REMOTE_HOST") or env.get("REMOTE_HOST")

	# Base psql command inside the postgres container
	psql_cmd = (
		f"docker exec openzero-postgres-1 psql -U zero -d zero_db "
		f"-t -A -F '\t' -c \"{sql}\""
	)

	if remote_host and remote_host not in ("localhost", "127.0.0.1", "your_vps_ip"):
		# Remote execution over SSH
		full_cmd = ["ssh", "-o", "ConnectTimeout=8", f"{remote_user}@{remote_host}", psql_cmd]
	else:
		# Local docker execution
		full_cmd = ["bash", "-c", psql_cmd]

	try:
		res = subprocess.run(full_cmd, capture_output=True, text=True, check=True)
	except subprocess.CalledProcessError as e:
		sys.stderr.write(f"Error querying database: {e.stderr.strip() or e.stdout.strip()}\n")
		sys.exit(1)

	rows = []
	for line in res.stdout.strip().split("\n"):
		if not line.strip():
			continue
		parts = line.split("\t")
		if len(parts) >= 6:
			try:
				rows.append({
					"id": int(parts[0]),
					"created_at": parts[1],
					"channel": parts[2] or "unknown",
					"role": parts[3] or "unknown",
					"model": parts[4] or "",
					"content": parts[5],
				})
			except ValueError:
				continue
	return rows


def analyze_conversation_anomalies(messages: list[dict]) -> list[str]:
	"""Run heuristic analysis over the retrieved messages to highlight anomalies."""
	anomalies: list[str] = []

	for i, m in enumerate(messages):
		role = m["role"].lower()
		model = m["model"]
		content = m["content"]

		# 1. Action execution failures
		if "No action was executed" in content or "phantom confirmation detected" in content:
			anomalies.append(f"Turn ID {m['id']}: Action tag failure detected in assistant response.")

		# 2. Crew dispatch on casual/follow-up turn
		if role == "z" and model.startswith("crew:"):
			if i > 0 and messages[i - 1]["role"].lower() == "user":
				prev_user = messages[i - 1]["content"]
				words = prev_user.strip().split()
				if len(words) <= 5 or any(kw in prev_user.lower() for kw in ("dachte", "vorgeschlagen", "z?", "hallo", "ja", "nein")):
					anomalies.append(
						f"Turn ID {m['id']}: Crew '{model}' answered a short follow-up or conversational prompt "
						f"(\"{prev_user[:60]}\"). Possible misroute."
					)

		# 3. Excessive length on simple conversational turns
		if role == "z" and len(content.split()) > 250:
			if i > 0 and len(messages[i - 1]["content"].split()) <= 4:
				anomalies.append(
					f"Turn ID {m['id']}: Assistant produced a large response ({len(content.split())} words) "
					f"following a short {len(messages[i - 1]['content'].split())}-word user prompt."
				)

		# 4. Apology / Hallucination correction markers
		if role == "z" and any(p in content.lower() for p in ("fehlinterpretation meinerseits", "entschuldigung", "sorry, ich habe mich vertan", "gibt es keine tasks mit den titeln")):
			anomalies.append(f"Turn ID {m['id']}: Assistant retracted a previous claim / apologized for hallucination.")

	return anomalies


def main():
	parser = argparse.ArgumentParser(description="Fetch and analyze recent openZero messages.")
	parser.add_argument("--limit", type=int, default=15, help="Maximum number of messages to fetch (default: 15)")
	parser.add_argument("--since", type=int, help="Fetch messages from the last N hours")
	parser.add_argument("--from-id", type=int, help="Fetch messages with ID strictly greater than this ID")
	parser.add_argument("--all", action="store_true", help="Ignore watermark and fetch the last N messages")
	parser.add_argument("--reset", action="store_true", help="Reset watermark file to 0")
	parser.add_argument("--verbose", "-v", action="store_true", help="Print full message content without truncation")

	args = parser.parse_args()

	if args.reset:
		set_last_watermark(0)
		print("Watermark reset to 0.")
		return

	last_id = 0
	if not args.all and args.from_id is None:
		last_id = get_last_watermark()

	if args.from_id is not None:
		last_id = args.from_id

	# Build SQL query
	conditions = []
	if last_id > 0:
		conditions.append(f"id > {last_id}")
	if args.since:
		conditions.append(f"created_at >= NOW() - INTERVAL '{args.since} hours'")

	where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
	sql = (
		f"SELECT id, created_at, channel, role, COALESCE(model, ''), REPLACE(REPLACE(content, E'\\t', ' '), E'\\n', ' [NL] ') "
		f"FROM global_messages {where_clause} "
		f"ORDER BY id DESC LIMIT {args.limit};"
	)

	messages = execute_query(sql)
	messages.sort(key=lambda m: m["id"])

	if not messages:
		if last_id > 0:
			print(f"✓ No new messages found since ID {last_id}.")
		else:
			print("No messages found matching criteria.")
		return

	# Update watermark with the highest ID seen
	max_id = max(m["id"] for m in messages)
	set_last_watermark(max_id)

	print(f"\n{'='*80}")
	print(f" openZero Conversation Stream — {len(messages)} message(s) (IDs {messages[0]['id']}..{max_id})")
	print(f"{'='*80}\n")

	for m in messages:
		clean_content = m["content"].replace(" [NL] ", "\n")
		if not args.verbose and len(clean_content) > 300:
			clean_content = clean_content[:300] + " ... [truncated; use --verbose to view full]"

		model_tag = f" [{m['model']}]" if m["model"] else ""
		role_tag = f"<{m['role'].upper()}{model_tag}>"
		header = f"#{m['id']} | {m['created_at']} | {m['channel'].upper()} | {role_tag}"
		print(header)
		print("-" * len(header))
		for line in clean_content.splitlines():
			print(f"  {line}")
		print()

	# Run automated anomaly analysis
	anomalies = analyze_conversation_anomalies(messages)
	print("-" * 80)
	print("AUTOMATED STREAM ANALYSIS:")
	if anomalies:
		for a in anomalies:
			print(f"  ⚠ {a}")
	else:
		print("  ✓ No routing, hallucination, or action anomalies detected in this stream slice.")
	print("-" * 80 + "\n")


if __name__ == "__main__":
	main()
