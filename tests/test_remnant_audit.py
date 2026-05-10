"""Static remnant audit -- guards against reintroduction of deleted symbols.

Pure static analysis only. No dynamic imports. One pytest test per phase.
After a phase's deletions land, the corresponding forbidden-symbol list is
populated here. CI fails immediately if any listed symbol reappears in
tracked source files.
"""
import os
import re
from pathlib import Path
from typing import Generator

import pytest

_ROOT = Path(__file__).resolve().parent.parent

# --- Exclusion rules ---

# Directory names that stop the walk (matched against any single path component)
_EXCLUDE_DIR_NAMES: frozenset[str] = frozenset({
	".git",
	"node_modules",
	"dist",
	"pw-browsers",
	"playwright-report",
	"__pycache__",
	".venv",
	".venv312",
	"artifacts",  # docs/artifacts/ holds removal-plan prose, not live code
})

# File name prefixes that indicate generated / binary artifacts to skip
_EXCLUDE_NAME_PREFIXES: tuple[str, ...] = ("lighthouse-report",)

# Extensions never scanned as text
_SKIP_EXTENSIONS: frozenset[str] = frozenset({
	".png", ".jpg", ".jpeg", ".gif", ".ico",
	".woff", ".woff2", ".ttf", ".eot", ".otf",
	".pdf", ".zip", ".tar", ".gz", ".bin", ".pyc",
	".map", ".lock", ".json",
})

# This file must never scan itself (symbol literals appear here as data)
_SELF_BASENAME = "test_remnant_audit.py"

# Line-based checks are restricted to code files so that removal-plan prose
# in .md documents does not trigger false positives.
_CODE_EXTENSIONS: frozenset[str] = frozenset({
	".py", ".ts", ".js", ".html", ".yaml", ".yml",
})

# Top-level subdirectories of _ROOT included in the scan
_SCAN_SUBDIRS: tuple[str, ...] = (
	"src", "tests", "docs", "agent", "personal", "infrastructure", "scripts",
)

# ---------------------------------------------------------------------------
# Forbidden symbol registry
# ---------------------------------------------------------------------------
# Category semantics:
#   filenames   -- any file whose *basename* equals this string fails.
#   imports     -- regex matched against any code line that contains "import".
#   identifiers -- regex matched against any code line.
#   i18n_keys   -- literal key matched inside quoted strings ("key" / 'key').
#   api_routes  -- literal path string matched against any code line.
# ---------------------------------------------------------------------------
PHASE_FORBIDDEN: dict[str, dict[str, list[str]]] = {
	"P1_email_optin": {
		"filenames": ["EmailRules.ts"],
		"imports": ["from app.services.email_rules"],
		"identifiers": ["EmailRulesWidget"],
		"i18n_keys": ["email_rule", "email_rules"],
		"api_routes": ["/api/email/rules"],
	},
	"P2_wizard_kill": {
		"filenames": ["WelcomeOnboarding.ts"],
		"imports": [],
		"identifiers": ["WelcomeOnboarding", "onboarding-step"],
		"i18n_keys": ["step_inner_circle", "step_welcome", "step_connect"],
		"api_routes": [],
	},
	"P3_automation_kill": {
		"filenames": ["automation.py"],
		"imports": ["from app.services.automation"],
		"identifiers": ["AutomationRule", "evaluate_rules"],
		"i18n_keys": [],
		"api_routes": ["/api/automation"],
	},
	"P4_circle_rip": {
		"filenames": ["CircleManager.ts"],
		"imports": ["from app.models.db import.*Person"],
		"identifiers": [
			"class Person",
			"CircleManager",
			"circle_type",
			"inner_circle",
			"outer_circle",
			"social_circles",
			"get_person_briefing_data",
		],
		"i18n_keys": [
			"circles",
			"circles_empty",
			"inner_circle",
			"inner_circle_desc",
			"inner_circle_full",
			"outer_circle_full",
			"social_circles",
			"step_inner_circle",
			"add_to_circle",
			"update_person",
			"aria_add_inner",
			"aria_add_person",
			"aria_delete_person",
			"aria_edit_person",
			"confirm_delete_person",
			"edit_person",
			"error_adding_person",
			"error_deleting_person",
			"no_people",
			"nav_circles",
		],
		"api_routes": ["/api/dashboard/people", "/api/circle"],
	},
	"MA0_atlas_template_legacy": {
		"filenames": [],
		"imports": [],
		"identifiers": ["ATLAS_TEMPLATE[^_]", "atlas_template[^_]"],  # forbid old ATLAS_TEMPLATE (not ATLAS_TEMPLATE_HINT)
		"i18n_keys": [],
		"api_routes": [],
	},
}


# ---------------------------------------------------------------------------
# File walking helpers
# ---------------------------------------------------------------------------

def _prune_dirs(dirnames: list[str]) -> None:
	"""Remove excluded directory names in-place so os.walk does not descend."""
	dirnames[:] = [
		d for d in dirnames
		if d not in _EXCLUDE_DIR_NAMES
		and not any(d.startswith(pfx) for pfx in _EXCLUDE_NAME_PREFIXES)
	]


def _skip_file(path: Path) -> bool:
	"""Return True if this file should not be scanned."""
	if path.name == _SELF_BASENAME:
		return True
	if path.suffix.lower() in _SKIP_EXTENSIONS:
		return True
	return any(path.name.startswith(pfx) for pfx in _EXCLUDE_NAME_PREFIXES)


def _all_files() -> Generator[Path, None, None]:
	"""Yield every scannable file within the workspace."""
	# Root-level .md and .yaml files only
	for p in _ROOT.iterdir():
		if p.is_file() and p.suffix in (".md", ".yaml") and not _skip_file(p):
			yield p
	# Subdirectory walk
	for subdir_name in _SCAN_SUBDIRS:
		subdir = _ROOT / subdir_name
		if not subdir.exists():
			continue
		for dirpath_str, dirnames, filenames in os.walk(subdir):
			_prune_dirs(dirnames)
			dp = Path(dirpath_str)
			for fname in filenames:
				fpath = dp / fname
				if not _skip_file(fpath):
					yield fpath


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def _scan_phase(phase_key: str) -> list[tuple[str, str, str, int, str]]:
	"""
	Scan all tracked files for any forbidden symbol in the given phase.
	Returns list of (symbol, category, rel_path, line_no, excerpt).
	"""
	spec = PHASE_FORBIDDEN[phase_key]
	hits: list[tuple[str, str, str, int, str]] = []

	filename_syms: list[str] = spec.get("filenames", [])
	import_syms: list[str] = spec.get("imports", [])
	ident_syms: list[str] = spec.get("identifiers", [])
	i18n_syms: list[str] = spec.get("i18n_keys", [])
	route_syms: list[str] = spec.get("api_routes", [])

	# Compile patterns once.
	# Symbols in imports/identifiers are treated as regex patterns (bounded,
	# no overlapping groups -- per agents.md rule 19 anti-backtracking guidance).
	# i18n_keys and api_routes use re.escape() for literal matching.
	import_pats = [(sym, re.compile(sym)) for sym in import_syms]
	ident_pats = [(sym, re.compile(sym)) for sym in ident_syms]
	i18n_pats = [
		(sym, re.compile(r"['\"]" + re.escape(sym) + r"['\"]"))
		for sym in i18n_syms
	]
	route_pats = [(sym, re.compile(re.escape(sym))) for sym in route_syms]

	for fpath in _all_files():
		rel = str(fpath.relative_to(_ROOT))
		is_code = fpath.suffix.lower() in _CODE_EXTENSIONS

		# Filename check applies to all files
		for sym in filename_syms:
			if fpath.name == sym:
				hits.append((sym, "filenames", rel, 0, fpath.name))

		# Line-based checks apply only to code files
		if not is_code:
			continue

		try:
			text = fpath.read_text(encoding="utf-8", errors="replace")
		except OSError:
			continue

		for lineno, line in enumerate(text.splitlines(), start=1):
			# imports: only on lines that contain the word "import"
			if "import" in line:
				for sym, pat in import_pats:
					if pat.search(line):
						hits.append((sym, "imports", rel, lineno, line.strip()[:120]))

			# identifiers: every code line
			for sym, pat in ident_pats:
				if pat.search(line):
					hits.append((sym, "identifiers", rel, lineno, line.strip()[:120]))

			# i18n_keys: quoted key occurrences
			for sym, pat in i18n_pats:
				if pat.search(line):
					hits.append((sym, "i18n_keys", rel, lineno, line.strip()[:120]))

			# api_routes: literal path in any code line
			for sym, pat in route_pats:
				if pat.search(line):
					hits.append((sym, "api_routes", rel, lineno, line.strip()[:120]))

	return hits


def _format_hits(hits: list[tuple[str, str, str, int, str]]) -> str:
	lines = []
	for sym, cat, path, lineno, excerpt in hits:
		loc = f"{path}:{lineno}" if lineno else path
		lines.append(f"  [{cat}] {sym!r}  @  {loc}\n    {excerpt}")
	return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests -- one per phase
# ---------------------------------------------------------------------------

def test_phase_p1_email_optin() -> None:
	"""No EmailRules / email_rules remnants survive after Phase P1."""
	hits = _scan_phase("P1_email_optin")
	assert not hits, f"P1_email_optin remnants found:\n{_format_hits(hits)}"


def test_phase_p2_wizard_kill() -> None:
	"""No WelcomeOnboarding / multi-step wizard remnants survive after Phase P2."""
	hits = _scan_phase("P2_wizard_kill")
	assert not hits, f"P2_wizard_kill remnants found:\n{_format_hits(hits)}"


def test_phase_p3_automation_kill() -> None:
	"""No automation.py rule-engine remnants survive after Phase P3."""
	hits = _scan_phase("P3_automation_kill")
	assert not hits, f"P3_automation_kill remnants found:\n{_format_hits(hits)}"


def test_phase_p4_circle_remnants() -> None:
	"""No Person / Circle / inner_circle remnants survive after Phase P4."""
	hits = _scan_phase("P4_circle_rip")
	assert not hits, f"P4_circle_rip remnants found:\n{_format_hits(hits)}"


def test_phase_ma0_atlas_template_legacy() -> None:
	"""ATLAS_TEMPLATE (bare, without _HINT suffix) must not appear after MA0."""
	hits = _scan_phase("MA0_atlas_template_legacy")
	assert not hits, f"MA0_atlas_template_legacy remnants found:\n{_format_hits(hits)}"
