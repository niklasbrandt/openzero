"""
i18n Coverage Gate -- openZero
================================
Static checks for translation completeness and hardcoded English strings.
Runs without network access and without importing any backend modules.

Checks covered
--------------
1. TestSelectorCoverage
   Ensures every language code offered in the UserCard UI selector has a
   non-empty translation dict in _TRANSLATIONS. Languages that are offered
   to the user but fall back to 100% English are a UX bug.

2. TestKeyCompleteness
   Every non-empty, non-English language dict in _TRANSLATIONS must cover
   all keys present in _EN (100% parity). Missing keys = CI fail.

3. TestDE_NoAsciiUmlauts
   Regression guard: the _DE dict must not contain ASCII umlaut substitutions
   (ae/oe/ue/ss used in place of ä/ö/ü/ß) in any translation value.

4. TestHardcodedStrings
   TypeScript source files must not contain multi-word English strings in
   aria-label, placeholder, or title attributes that bypass the tr() helper,
   and must not contain multi-word capitalised English text directly between
   HTML tags in template literals. Strings inside tr('key', 'fallback') calls
   are explicitly permitted (they are correct usage).

Run:
	python -m pytest tests/test_i18n_coverage.py -v
"""

import ast
import pathlib
import re
from typing import Dict, FrozenSet, List, Set, Tuple

# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).parent.parent

TRANSLATIONS_PY = REPO_ROOT / "src" / "backend" / "app" / "services" / "translations.py"
USERCARD_TS     = REPO_ROOT / "src" / "dashboard" / "components" / "UserCard.ts"

TS_SOURCES: List[pathlib.Path] = sorted(
	list(REPO_ROOT.glob("src/dashboard/components/**/*.ts"))
	+ list(REPO_ROOT.glob("src/dashboard/services/**/*.ts"))
	+ list(REPO_ROOT.glob("src/dashboard/src/**/*.ts"))
)

# ---------------------------------------------------------------------------
# Shared AST / regex helpers
# ---------------------------------------------------------------------------

def _extract_ui_language_codes() -> Set[str]:
	"""Parse the ``private languages = { ... }`` block in UserCard.ts and
	return the set of 2-3 character language codes offered in the selector."""
	src = USERCARD_TS.read_text(encoding="utf-8")
	# Match the TypeScript object literal: en: { ... }, de: { ... }, ...
	# Keys are bare identifiers (no quotes) in the private field initialiser.
	# The file uses tabs; keys appear with leading whitespace at any indent level.
	return set(re.findall(r"^\s+([a-z]{2,3}):\s*\{\s*native:", src, re.MULTILINE))


def _extract_lang_dicts() -> Dict[str, FrozenSet[str]]:
	"""AST-walk translations.py and return a mapping of language code → frozenset
	of string keys defined in the corresponding ``_XX = { ... }`` assignment.

	Only top-level assignments whose name matches ``_[A-Z]{2,3}`` are collected.
	The language code is derived by lower-casing the suffix (e.g. _EN → 'en').
	"""
	src   = TRANSLATIONS_PY.read_bytes()
	tree  = ast.parse(src)
	result: Dict[str, FrozenSet[str]] = {}

	for node in ast.iter_child_nodes(tree):
		if not isinstance(node, ast.Assign):
			continue
		if len(node.targets) != 1:
			continue
		target = node.targets[0]
		if not (isinstance(target, ast.Name) and re.fullmatch(r"_[A-Z]{2,3}", target.id)):
			continue
		code = target.id[1:].lower()  # "_EN" → "en"
		if not isinstance(node.value, ast.Dict):
			continue
		keys: Set[str] = set()
		for k in node.value.keys:
			if k is not None and isinstance(k, ast.Constant) and isinstance(k.value, str):
				keys.add(k.value)
		result[code] = frozenset(keys)

	return result


def _extract_translation_registry() -> Dict[str, bool]:
	"""AST-walk translations.py and inspect the ``_TRANSLATIONS`` dict literal.
	Returns a mapping of language code → True if the value is a non-empty
	variable reference, False if it is an empty dict literal ``{}``.

	Note: _TRANSLATIONS uses an annotated assignment (``_TRANSLATIONS: dict[...] = {...}``),
	which is an ``ast.AnnAssign`` node, not a plain ``ast.Assign``.
	"""
	src  = TRANSLATIONS_PY.read_bytes()
	tree = ast.parse(src)
	registry: Dict[str, bool] = {}

	for node in ast.walk(tree):
		# Handle both plain and annotated assignments
		if isinstance(node, ast.AnnAssign):
			target = node.target
			value  = node.value
		elif isinstance(node, ast.Assign):
			if len(node.targets) != 1:
				continue
			target = node.targets[0]
			value  = node.value
		else:
			continue

		if not (isinstance(target, ast.Name) and target.id == "_TRANSLATIONS"):
			continue
		if value is None or not isinstance(value, ast.Dict):
			continue
		for k, v in zip(value.keys, value.values):
			if not (k is not None and isinstance(k, ast.Constant)):
				continue
			code = k.value
			if isinstance(v, ast.Name):
				# Points to a named variable → non-empty
				registry[code] = True
			elif isinstance(v, ast.Dict):
				# Inline dict: empty iff no keys
				registry[code] = len(v.keys) > 0
	return registry


# ---------------------------------------------------------------------------
# 1. TestSelectorCoverage
# ---------------------------------------------------------------------------

class TestSelectorCoverage:
	"""Every language offered in the UI selector must have a non-empty translation
	dict. Offering a language that silently falls back to 100% English is a bug."""

	def test_ui_selector_has_no_stub_languages(self) -> None:
		ui_codes  = _extract_ui_language_codes()
		registry  = _extract_translation_registry()

		assert ui_codes, "Could not parse any language codes from UserCard.ts"

		stubs: List[str] = []
		for code in sorted(ui_codes):
			is_non_empty = registry.get(code)
			if is_non_empty is None:
				stubs.append(f"  '{code}' -- listed in UI selector but absent from _TRANSLATIONS registry")
			elif not is_non_empty:
				stubs.append(f"  '{code}' -- listed in UI selector but has empty {{}} dict in _TRANSLATIONS")

		assert not stubs, (
			f"{len(stubs)} language(s) in the UI selector have no translation data "
			f"and silently fall back to English:\n" + "\n".join(stubs)
		)


# ---------------------------------------------------------------------------
# 2. TestKeyCompleteness
# ---------------------------------------------------------------------------

class TestKeyCompleteness:
	"""Every non-empty, non-English language dict must cover all keys in _EN.
	Any gap causes the dashboard to silently display English for that string."""

	def test_all_translation_dicts_cover_en_keys(self) -> None:
		lang_dicts = _extract_lang_dicts()

		assert "en" in lang_dicts, "Could not find _EN dict in translations.py"
		en_keys = lang_dicts["en"]
		assert len(en_keys) > 0, "_EN is empty -- something is wrong"

		violations: List[str] = []
		for code, keys in sorted(lang_dicts.items()):
			if code == "en":
				continue
			if len(keys) == 0:
				# Empty stubs are caught by TestSelectorCoverage; skip here to
				# avoid duplicate noise (they have no keys to compare).
				continue
			missing = sorted(en_keys - keys)
			if missing:
				preview = missing[:15]
				more    = len(missing) - 15
				suffix  = f"  ... and {more} more" if more > 0 else ""
				violations.append(
					f"\n  _{code.upper()} is missing {len(missing)} key(s):\n"
					+ "".join(f"    - {k}\n" for k in preview)
					+ (f"    ... and {more} more\n" if more > 0 else "")
				)

		assert not violations, (
			"Translation dicts missing keys present in _EN "
			"(will silently fall back to English at runtime):"
			+ "".join(violations)
		)


# ---------------------------------------------------------------------------
# 3. TestDE_NoAsciiUmlauts
# ---------------------------------------------------------------------------

# Known ASCII umlaut substitution patterns that must not appear in _DE values.
# These are word-boundary–anchored where possible to avoid false positives on
# technical strings like "procedure", "infrastructure", etc.
_DE_UMLAUT_PATTERNS: List[Tuple[str, str]] = [
	(r"\bfuer\b",         "fuer (should be für)"),
	(r"\bueber\b",        "ueber (should be über)"),
	(r"\boeffn",          "oeffn* (should be öffn*)"),
	(r"\bschliess(?!lich)","schliess* (should be schließ*)"),
	(r"\bloeschen?\b",    "loesch* (should be lösch*)"),
	(r"\bmoechten?\b",    "moecht* (should be möcht*)"),
	(r"\bpruefen?\b",     "pruefen (should be prüfen)"),
	(r"\bausfuehr",       "ausfuehr* (should be ausführ*)"),
	(r"\bhinzufueg",      "hinzufueg* (should be hinzufüg*)"),
	(r"\buebersicht\b",   "uebersicht (should be übersicht)"),
	(r"\bnaechst",        "naechst* (should be nächst*)"),
	(r"\bgroess",         "groess* (should be größ*)"),
	(r"\baeussere?\b",    "aeusser* (should be äußer*)"),
	(r"\bpersoenl",       "Persoenl* (should be Persönl*)"),
	(r"\bvollstaend",     "Vollstaend* (should be Vollständ*)"),
	(r"\bunterstuetzt\b", "unterstuetzt (should be unterstützt)"),
	(r"\bverfuegbar\b",   "verfuegbar (should be verfügbar)"),
	(r"\bhaeufig\b",      "haeufig (should be häufig)"),
	(r"\bsaettigung\b",   "saettigung (should be Sättigung)"),
	(r"\bfarbwaehler\b",  "farbwaehler (should be Farbwähler)"),
	(r"\bwaehlen?\b",     "waehlen (should be wählen)"),
	(r"\bgedaechtnis\b",  "gedaechtnis (should be Gedächtnis)"),
	(r"\bansaessig\b",    "ansaessig (should be ansässig)"),
	(r"\bganztaegig\b",   "ganztaegig (should be ganztägig)"),
	(r"\bnavigationsmenue\b", "navigationsmenue (should be Navigationsmenü)"),
	(r"\bfranzoesisch\b", "franzoesisch (should be Französisch)"),
	(r"\bnierlaendisch\b","niederlaendisch (should be Niederländisch)"),
	(r"\bdaenisch\b",     "daenisch (should be Dänisch)"),
	(r"\btuerkisch\b",    "tuerkisch (should be Türkisch)"),
	(r"\brumaenisch\b",   "rumaenisch (should be Rumänisch)"),
	(r"\bverzoegerung\b", "verzoegerung (should be Verzögerung)"),
	(r"\bspuerbar",       "spuerbar* (should be spürbar*)"),
	(r"\bschaltflaeche\b","schaltflaeche (should be Schaltfläche)"),
	(r"\blaeuft\b",       "laeuft (should be läuft)"),
	(r"\baufloesungs",    "aufloesungs* (should be Auflösungs*)"),
	(r"\bidentitaet\b",   "identitaet (should be Identität)"),
	(r"\bfaehigkeiten\b", "faehigkeiten (should be Fähigkeiten)"),
	(r"\bdemnachst\b",    "demnachst (should be demnächst)"),
]


class TestDE_NoAsciiUmlauts:
	"""Regression guard: _DE translation values must use proper Unicode umlauts
	(ä, ö, ü, ß), never ASCII substitutions like ae/oe/ue/ss."""

	def _collect_de_string_values(self) -> List[Tuple[str, str]]:
		"""Return (key, value) pairs for every string entry in _DE."""
		src  = TRANSLATIONS_PY.read_bytes()
		tree = ast.parse(src)
		pairs: List[Tuple[str, str]] = []
		for node in ast.walk(tree):
			if not isinstance(node, ast.Assign):
				continue
			for t in node.targets:
				if not (isinstance(t, ast.Name) and t.id == "_DE"):
					continue
				if not isinstance(node.value, ast.Dict):
					continue
				for k, v in zip(node.value.keys, node.value.values):
					if not (
						k is not None
						and isinstance(k, ast.Constant) and isinstance(k.value, str)
					):
						continue
					# Value may be a string constant or a joined-string (f-string/concat)
					if isinstance(v, ast.Constant) and isinstance(v.value, str):
						pairs.append((k.value, v.value))
					elif isinstance(v, ast.JoinedStr):
						# Reconstruct the literal parts for partial scanning
						parts = [
							nd.value for nd in ast.walk(v)
							if isinstance(nd, ast.Constant) and isinstance(nd.value, str)
						]
						pairs.append((k.value, " ".join(parts)))
		return pairs

	def test_de_no_ascii_umlaut_substitutions(self) -> None:
		pairs = self._collect_de_string_values()
		assert pairs, "Could not extract any string values from _DE"

		hits: List[str] = []
		for key, value in pairs:
			for pattern, description in _DE_UMLAUT_PATTERNS:
				if re.search(pattern, value, re.IGNORECASE):
					hits.append(f"  _DE[{key!r}] contains {description}: {value!r}")
					break  # one report per key is enough

		assert not hits, (
			f"{len(hits)} _DE value(s) contain ASCII umlaut substitutions "
			f"instead of proper Unicode characters:\n" + "\n".join(hits)
		)


# ---------------------------------------------------------------------------
# 4. TestHardcodedStrings
# ---------------------------------------------------------------------------

# Minimum word count and character length to consider a string "visible text"
# worth flagging. Single words and very short strings are too noisy.
_MIN_WORDS  = 2
_MIN_LENGTH = 8

# tr() call pattern -- strings that appear as the fallback argument to tr() are
# correct usage and must not be flagged.
_TR_CALL_RE = re.compile(r"""this\.tr\s*\(\s*['"][^'"]+['"]\s*,\s*['"]([^'"]+)['"]\s*\)""")

# aria-label / aria-description / aria-placeholder with literal (non-template) values
_ARIA_ATTR_RE = re.compile(
	r'aria-(?:label|description|placeholder)\s*=\s*"([^"$\n][^"\n]*\s[^"\n]{2,})"'
)

# placeholder and title attributes
_ATTR_RE = re.compile(
	r'(?:placeholder|title)\s*=\s*"([^"$\n][^"\n]*\s[^"\n]{2,})"'
)

# Multi-word capitalised text between HTML tags in template literals.
# Matches: >Some Multi Word Text< but not >${expr}< or >singleword<
_VISIBLE_TEXT_RE = re.compile(
	r">\s*([A-Z][a-zA-Z',.\-!?]{0,3}(?:\s+[a-zA-Z',.\-!?]{2,}){" + str(_MIN_WORDS - 1) + r",})\s*<(?!/)"
)

# Technical single-token identifiers that should not be flagged even if they
# appear as attribute values (e.g. button types, input types).
_SKIP_VALUE_RE = re.compile(r"^[\w\-/:.@#]+$")


def _is_in_tr_fallback(line: str, match_start: int, match_value: str) -> bool:
	"""Return True if ``match_value`` appears as the fallback argument of a
	tr() call on the same line."""
	for m in _TR_CALL_RE.finditer(line):
		if m.group(1) == match_value:
			return True
	return False


def _collect_ts_hardcoded(
	attr_pattern: re.Pattern,  # type: ignore[type-arg]
	is_visible_text: bool = False,
) -> List[str]:
	hits: List[str] = []
	for path in TS_SOURCES:
		src   = path.read_text(encoding="utf-8")
		lines = src.splitlines()
		for lineno, line in enumerate(lines, 1):
			# Skip comment lines
			stripped = line.lstrip()
			if stripped.startswith("//") or stripped.startswith("*"):
				continue
			for m in attr_pattern.finditer(line):
				value = m.group(1).strip()
				# Skip trivial / non-natural-language values
				if _SKIP_VALUE_RE.match(value):
					continue
				if len(value) < _MIN_LENGTH:
					continue
				word_count = len(value.split())
				if word_count < _MIN_WORDS:
					continue
				# Skip template expressions inside the value
				if "${" in value:
					continue
				# Skip values that themselves contain a tr() call (e.g. string
				# concatenation patterns like aria-label="' + this.tr(...) + '"
				if "this.tr(" in value:
					continue
				# Skip strings already inside tr() fallback
				if _is_in_tr_fallback(line, m.start(), value):
					continue
				# For visible text: skip lines that also contain this.tr(
				if is_visible_text and "this.tr(" in line:
					continue
				hits.append(
					f"  {path.relative_to(REPO_ROOT)}:{lineno}  {value!r}"
				)
	return hits


class TestHardcodedStrings:
	"""TypeScript sources must not contain multi-word English UI strings that
	bypass the tr() translation helper. Every user-visible string must go
	through this.tr('key', 'fallback') so it can be translated."""

	def test_ts_no_hardcoded_aria_labels(self) -> None:
		hits = _collect_ts_hardcoded(_ARIA_ATTR_RE)
		assert not hits, (
			f"{len(hits)} hardcoded English string(s) found in aria-label / "
			"aria-description / aria-placeholder attributes "
			"(should use this.tr()):\n" + "\n".join(hits)
		)

	def test_ts_no_hardcoded_placeholder_and_title(self) -> None:
		hits = _collect_ts_hardcoded(_ATTR_RE)
		assert not hits, (
			f"{len(hits)} hardcoded English string(s) found in placeholder / "
			"title attributes (should use this.tr()):\n" + "\n".join(hits)
		)

	def test_ts_no_hardcoded_visible_text(self) -> None:
		hits = _collect_ts_hardcoded(_VISIBLE_TEXT_RE, is_visible_text=True)
		assert not hits, (
			f"{len(hits)} potentially hardcoded English string(s) found as "
			"visible text between HTML tags in template literals "
			"(should use this.tr()):\n" + "\n".join(hits)
		)
