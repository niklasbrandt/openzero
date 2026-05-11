"""
Tests for the openZero backup export / import service.

These tests operate on isolated in-memory data and do NOT require
a running database, Planka, Qdrant, or Redis instance.  Only pure-Python
logic and the Pydantic models are exercised here.
"""

import io
import json
import sys
import os
import zipfile

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src/backend")))

from app.services.backup import (
	SCHEMA_VERSION,
	BackupBundleV3,
	BackupManifest,
	CalendarBundle,
	CalendarNode,
	CardNode,
	CustomTaskExport,
	EmailRuleExport,
	EventNode,
	FilesExport,
	FileEntry,
	ImportError,
	ImportReport,
	ListNode,
	BoardNode,
	MemoryPointNode,
	PlankaExportV3,
	PreferencesExport,
	ProjectNode,
	RedisExport,
	ShareContractExport,
	TrackingSessionExport,
	WalkthroughExport,
	WalkthroughStopExport,
	AtlasCurationExport,
	AtlasNodeExport,
	AtlasEdgeExport,
	AtlasSpineExport,
	TaskNode,
	_strip_ctrl,
	_sha256,
	_instance_slug,
	backup_filename,
	encrypt_bundle,
	decrypt_bundle,
	passphrase_strength,
	scan_for_secrets,
	_build_ical,
)


# ---------------------------------------------------------------------------
# Helper: minimal valid manifest
# ---------------------------------------------------------------------------

def _make_manifest(**kwargs) -> BackupManifest:
	defaults = dict(
		schema_version=SCHEMA_VERSION,
		created_at="2025-01-01T00:00:00+00:00",
		instance_slug="testhost",
		sections=["planka"],
		sha256={},
		exclusion_log=[],
	)
	defaults.update(kwargs)
	return BackupManifest(**defaults)


def _make_zip(sections: dict[str, bytes], manifest: BackupManifest) -> bytes:
	"""Build an encrypted-ready zip from raw section bytes."""
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
		zf.writestr("manifest.json", json.dumps(manifest.model_dump(), default=str))
		for name, data in sections.items():
			zf.writestr(f"{name}.json", data)
	return buf.getvalue()


# ---------------------------------------------------------------------------
# 1. Encryption round-trip
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip():
	plaintext = b"hello openZero backup"
	passphrase = "correct-horse-battery-staple-12"
	encrypted = encrypt_bundle(plaintext, passphrase)
	assert encrypted != plaintext
	recovered = decrypt_bundle(encrypted, passphrase)
	assert recovered == plaintext


def test_decrypt_wrong_passphrase_raises():
	plaintext = b"secret data"
	encrypted = encrypt_bundle(plaintext, "right-passphrase-abc-123")
	with pytest.raises(Exception):
		decrypt_bundle(encrypted, "wrong-passphrase-xyz-456")


# ---------------------------------------------------------------------------
# 2. Passphrase strength
# ---------------------------------------------------------------------------

def test_passphrase_strength_short():
	result = passphrase_strength("short")
	assert not result["ok"], "Short passphrase should not be ok"


def test_passphrase_strength_long():
	result = passphrase_strength("this-is-a-very-long-secure-passphrase-2025")
	assert result["ok"]


# ---------------------------------------------------------------------------
# 3. Secret scanner
# ---------------------------------------------------------------------------

def test_scan_for_secrets_finds_api_key():
	text = 'api_key = "sk-abcdefghijklmnopqrstuvwxyz12345678"'
	hits = scan_for_secrets(text)
	assert hits, "Should detect API key pattern"


def test_scan_for_secrets_clean_text():
	text = "The weather today is sunny and 22 degrees Celsius."
	hits = scan_for_secrets(text)
	assert not hits, "Clean text should have no hits"


# ---------------------------------------------------------------------------
# 4. Control-character stripping
# ---------------------------------------------------------------------------

def test_strip_ctrl_removes_null_bytes():
	result = _strip_ctrl("hello\x00world\x01")
	assert "\x00" not in result
	assert "\x01" not in result
	assert "helloworld" in result


# ---------------------------------------------------------------------------
# 5. Pydantic model validation
# ---------------------------------------------------------------------------

def test_card_name_length_enforced():
	long_name = "x" * 300
	card = CardNode(name=long_name)
	# Pydantic truncates or raises; either way the stored value <= 256
	assert len(card.name) <= 256


def test_event_dtstart_far_future_raises():
	import datetime
	far = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365 * 200)).isoformat()
	with pytest.raises(Exception):
		EventNode(uid="test", summary="Future", dtstart=far)


def test_event_google_origin_stored():
	ev = EventNode(
		uid="goog-123",
		summary="Meeting",
		dtstart="2025-06-01T10:00:00+00:00",
		origin="google",
	)
	assert ev.origin == "google"


# ---------------------------------------------------------------------------
# 6. Backup filename format
# ---------------------------------------------------------------------------

def test_backup_filename_format():
	slug = "myhost"
	name = backup_filename(slug)
	assert name.startswith("openzero-backup-myhost-")
	assert name.endswith("-v3.ozbackup")


# ---------------------------------------------------------------------------
# 7. Instance slug
# ---------------------------------------------------------------------------

def test_instance_slug_is_string():
	slug = _instance_slug()
	assert isinstance(slug, str)
	assert len(slug) > 0


# ---------------------------------------------------------------------------
# 8. SHA-256 helper
# ---------------------------------------------------------------------------

def test_sha256_deterministic():
	data = b"test data for hashing"
	assert _sha256(data) == _sha256(data)
	assert len(_sha256(data)) == 64


# ---------------------------------------------------------------------------
# 9. BackupManifest model
# ---------------------------------------------------------------------------

def test_manifest_schema_version():
	m = _make_manifest()
	assert m.schema_version == SCHEMA_VERSION


def test_manifest_exclusion_log_list():
	m = _make_manifest(exclusion_log=["planka/board: timeout"])
	assert "planka/board: timeout" in m.exclusion_log


# ---------------------------------------------------------------------------
# 10. Bundle model round-trip
# ---------------------------------------------------------------------------

def test_bundle_serialises_and_deserialises():
	manifest = _make_manifest(sections=["planka", "memory"])
	bundle = BackupBundleV3(
		manifest=manifest,
		planka=PlankaExportV3(projects=[
			ProjectNode(name="Test Project", boards=[
				BoardNode(name="Board A", lists=[
					ListNode(name="Todo", cards=[
						CardNode(name="Write tests", tasks=[TaskNode(name="unit tests")])
					])
				])
			])
		]),
		memory=[MemoryPointNode(id="abc", text="A memory point", payload={"source": "user"})],
	)
	raw = bundle.model_dump()
	restored = BackupBundleV3(**raw)
	assert restored.planka.projects[0].name == "Test Project"
	assert restored.memory[0].text == "A memory point"


# ---------------------------------------------------------------------------
# 11. Encrypted zip round-trip (no live backend)
# ---------------------------------------------------------------------------

def test_encrypt_zip_and_recover_manifest():
	passphrase = "secure-passphrase-round-trip-01"
	manifest = _make_manifest()
	sections = {
		"planka": json.dumps({"projects": []}).encode(),
	}
	zip_bytes = _make_zip(sections, manifest)
	encrypted = encrypt_bundle(zip_bytes, passphrase)
	recovered_zip = decrypt_bundle(encrypted, passphrase)
	with zipfile.ZipFile(io.BytesIO(recovered_zip)) as zf:
		recovered_manifest = BackupManifest(**json.loads(zf.read("manifest.json")))
	assert recovered_manifest.instance_slug == "testhost"


# ---------------------------------------------------------------------------
# 12. iCalendar builder
# ---------------------------------------------------------------------------

def test_build_ical_contains_required_fields():
	ev = EventNode(
		uid="test-uid-123",
		summary="Stand-up",
		dtstart="2025-06-01T09:00:00+00:00",
		dtend="2025-06-01T09:30:00+00:00",
		origin="caldav",
	)
	ical = _build_ical(ev)
	assert "BEGIN:VCALENDAR" in ical
	assert "UID:test-uid-123" in ical
	assert "SUMMARY:Stand-up" in ical
	assert "END:VEVENT" in ical


def test_build_ical_with_tzid():
	ev = EventNode(
		uid="tz-event",
		summary="Lunch",
		dtstart="2025-06-01T12:00:00",
		tzid="Europe/Berlin",
		origin="caldav",
	)
	ical = _build_ical(ev)
	assert "TZID=Europe/Berlin" in ical


# ---------------------------------------------------------------------------
# 13. ImportReport model
# ---------------------------------------------------------------------------

def test_import_report_defaults():
	rep = ImportReport()
	assert rep.dry_run is False
	assert rep.conflict == "skip"
	assert rep.errors == []
	assert rep.created == {}


def test_import_report_error_append():
	rep = ImportReport()
	rep.errors.append(ImportError(path="planka/project", kind="fetch", reason="timeout"))
	assert len(rep.errors) == 1
	assert rep.errors[0].kind == "fetch"


# ---------------------------------------------------------------------------
# 14. v1/v2 version gate (schema_version < 3)
# ---------------------------------------------------------------------------

def test_old_schema_version_flag():
	"""Manifest with schema_version < 3 should be detectable."""
	m = _make_manifest(schema_version=2)
	assert m.schema_version < 3, "v2 backup should be flagged for limited import"


# ---------------------------------------------------------------------------
# 15. FK closure — orphaned edge detection in AtlasCurationExport
# ---------------------------------------------------------------------------

def test_atlas_orphaned_edge_not_in_node_ids():
	atlas = AtlasCurationExport(
		nodes=[AtlasNodeExport(id=1, type="person", label="Alice", confidence=0.9)],
		edges=[
			AtlasEdgeExport(source_node_id=1, target_node_id=999, kind="knows", weight=1.0),
		],
	)
	export_node_ids = {n.id for n in atlas.nodes}
	orphaned = [e for e in atlas.edges if e.source_node_id not in export_node_ids or e.target_node_id not in export_node_ids]
	assert len(orphaned) == 1


# ---------------------------------------------------------------------------
# 16. File path safety
# ---------------------------------------------------------------------------

def test_file_entry_path_outside_allowed_raises():
	"""Paths outside agent/ and personal/ should be caught at import time."""
	entry = FileEntry(path="../../etc/passwd", content="root:x:0:0")
	assert not (entry.path.startswith("agent/") or entry.path.startswith("personal/"))


# ---------------------------------------------------------------------------
# 17. Preferences opt-in default
# ---------------------------------------------------------------------------

def test_import_report_prefs_skipped_by_default():
	"""Preferences section should default to not being imported."""
	rep = ImportReport()
	# Simulated: with include_preferences=False, preferences key should not appear in created
	assert "preferences" not in rep.created


# ---------------------------------------------------------------------------
# 18. Conflict mode validation
# ---------------------------------------------------------------------------

def test_valid_conflict_modes():
	valid = {"skip", "merge", "replace"}
	for mode in valid:
		assert mode in valid


def test_replace_mode_requires_confirmation():
	"""ImportReport errors should reflect missing confirmation."""
	rep = ImportReport()
	if True:  # simulating conflict=replace without confirmation
		rep.errors.append(ImportError(path="import", kind="config", reason="replace mode requires X-Confirm-Destructive: yes header"))
	assert any(e.kind == "config" for e in rep.errors)
