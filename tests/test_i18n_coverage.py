"""
i18n Coverage Gate -- openZero
================================
Static checks for translation completeness and hardcoded English strings.
Runs without network access and without importing any backend modules.

Checks covered
--------------
1. TestSelectorCoverage
   Ensures every language code offered in the UserCard UI selector either
   has a dedicated i18n/{code}.py file with at least one genuine translation
   OR is explicitly a stub. Languages offering 0 translations are a UX bug.

2. TestKeyCompleteness
   Keys present in any non-EN i18n file must also exist in i18n/en.py
   (no orphan/rogue keys). Partial translation coverage is allowed --
   missing keys fall back to English at runtime via get_translations().

3. TestDE_NoAsciiUmlauts
   Regression guard: i18n/de.py must not contain ASCII umlaut substitutions
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

I18N_DIR        = REPO_ROOT / "src" / "backend" / "app" / "services" / "i18n"
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
	"""Scan the i18n/ directory and return a mapping of language code →
	frozenset of string keys defined in the corresponding ``{code}.py`` file.

	Each file exports ``translations: dict[str, str] = { ... }`` at top level.
	The language code is the filename stem (e.g. ``en.py`` → 'en').
	"""
	result: Dict[str, FrozenSet[str]] = {}

	for lang_file in sorted(I18N_DIR.glob("*.py")):
		if lang_file.stem == "__init__":
			continue
		code = lang_file.stem
		try:
			src  = lang_file.read_bytes()
			tree = ast.parse(src)
		except SyntaxError:
			result[code] = frozenset()
			continue
		keys: Set[str] = set()
		for node in ast.iter_child_nodes(tree):
			if not isinstance(node, (ast.Assign, ast.AnnAssign)):
				continue
			target = node.target if isinstance(node, ast.AnnAssign) else (
				node.targets[0] if len(node.targets) == 1 else None
			)
			if target is None:
				continue
			if not (isinstance(target, ast.Name) and target.id == "translations"):
				continue
			value = node.value if isinstance(node, (ast.AnnAssign, ast.Assign)) else None
			if not isinstance(value, ast.Dict):
				continue
			for k in value.keys:
				if k is not None and isinstance(k, ast.Constant) and isinstance(k.value, str):
					keys.add(k.value)
		result[code] = frozenset(keys)

	return result


def _extract_translation_registry() -> Dict[str, bool]:
	"""Return a mapping of language code → True if the code has a non-empty
	i18n/{code}.py file, False otherwise.

	Also checks translations.py _TRANSLATIONS for stub langs listed as empty
	dict literals ``{}``, which are also marked False.
	"""
	registry: Dict[str, bool] = {}

	# Every language file with >= 1 key is non-empty.
	for lang_file in sorted(I18N_DIR.glob("*.py")):
		if lang_file.stem == "__init__":
			continue
		code = lang_file.stem
		try:
			src  = lang_file.read_bytes()
			tree = ast.parse(src)
		except SyntaxError:
			registry[code] = False
			continue
		has_keys = False
		for node in ast.iter_child_nodes(tree):
			if not isinstance(node, (ast.Assign, ast.AnnAssign)):
				continue
			target = node.target if isinstance(node, ast.AnnAssign) else (
				node.targets[0] if len(node.targets) == 1 else None
			)
			if not (target and isinstance(target, ast.Name) and target.id == "translations"):
				continue
			value = node.value
			if isinstance(value, ast.Dict) and len(value.keys) > 0:
				has_keys = True
		registry[code] = has_keys

	# Mark stubs listed as {} in translations.py _TRANSLATIONS (no i18n file).
	try:
		src  = TRANSLATIONS_PY.read_bytes()
		tree = ast.parse(src)
		for node in ast.walk(tree):
			if isinstance(node, ast.AnnAssign):
				target, value = node.target, node.value
			elif isinstance(node, ast.Assign) and len(node.targets) == 1:
				target, value = node.targets[0], node.value
			else:
				continue
			if not (isinstance(target, ast.Name) and target.id == "_TRANSLATIONS"):
				continue
			if not isinstance(value, ast.Dict):
				continue
			for k, v in zip(value.keys, value.values):
				if not (k and isinstance(k, ast.Constant)):
					continue
				code = k.value
				if code not in registry:
					# Inline dict stub in translations.py
					registry[code] = isinstance(v, ast.Name) or (
						isinstance(v, ast.Dict) and len(v.keys) > 0
					)
	except (SyntaxError, FileNotFoundError):
		pass

	return registry


# ---------------------------------------------------------------------------
# 1. TestSelectorCoverage
# ---------------------------------------------------------------------------

class TestSelectorCoverage:
	"""Every language offered in the UI selector must have at least one genuine
	translation in its i18n/{code}.py file. A language with zero translations
	should be removed from the selector until its file is populated."""

	def test_ui_selector_has_no_stub_languages(self) -> None:
		ui_codes  = _extract_ui_language_codes()
		registry  = _extract_translation_registry()

		assert ui_codes, "Could not parse any language codes from UserCard.ts"

		stubs: List[str] = []
		for code in sorted(ui_codes):
			is_non_empty = registry.get(code)
			if is_non_empty is None:
				stubs.append(f"  '{code}' -- listed in UI selector but no i18n/{code}.py exists")
			elif not is_non_empty:
				stubs.append(f"  '{code}' -- listed in UI selector but i18n/{code}.py has 0 translations")

		assert not stubs, (
			f"{len(stubs)} language(s) in the UI selector have no translation data:\n"
			+ "\n".join(stubs)
		)


# ---------------------------------------------------------------------------
# 2. TestKeyCompleteness
# ---------------------------------------------------------------------------

class TestKeyCompleteness:
	"""Keys present in any non-EN i18n file must also exist in i18n/en.py.
	Partial coverage is fine -- missing keys fall back to English at runtime.
	Orphan keys (in non-EN but absent from EN) are always a mistake."""

	def test_all_translation_dicts_cover_en_keys(self) -> None:
		lang_dicts = _extract_lang_dicts()

		assert "en" in lang_dicts, "Could not find i18n/en.py"
		en_keys = lang_dicts["en"]
		assert len(en_keys) > 0, "i18n/en.py is empty -- something is wrong"

		violations: List[str] = []
		for code, keys in sorted(lang_dicts.items()):
			if code == "en":
				continue
			if len(keys) == 0:
				continue  # empty stubs caught by TestSelectorCoverage
			# Orphan keys: present in lang file but absent from EN (rogue entries)
			orphan = sorted(keys - en_keys)
			if orphan:
				preview = orphan[:10]
				more    = len(orphan) - 10
				violations.append(
					f"\n  i18n/{code}.py has {len(orphan)} key(s) not in en.py:\n"
					+ "".join(f"    - {k}\n" for k in preview)
					+ (f"    ... and {more} more\n" if more > 0 else "")
				)

		assert not violations, (
			"Non-EN i18n files contain orphan keys absent from en.py:"
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
		"""Return (key, value) pairs for every string entry in i18n/de.py."""
		de_file = I18N_DIR / "de.py"
		if not de_file.exists():
			return []
		src  = de_file.read_bytes()
		tree = ast.parse(src)
		pairs: List[Tuple[str, str]] = []
		for node in ast.walk(tree):
			if isinstance(node, ast.AnnAssign):
				target, value = node.target, node.value
			elif isinstance(node, ast.Assign) and len(node.targets) == 1:
				target, value = node.targets[0], node.value
			else:
				continue
			if not (isinstance(target, ast.Name) and target.id == "translations"):
				continue
			if not isinstance(value, ast.Dict):
				continue
			for k, v in zip(value.keys, value.values):
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
