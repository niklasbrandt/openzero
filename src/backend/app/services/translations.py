"""
Translation tables for openZero.

Individual language files live in i18n/{code}.py.
Each non-EN file contains only genuinely translated strings.
Missing keys fall back to English at runtime via get_translations().
"""
from app.services.i18n.en import translations as _EN
from app.services.i18n.de import translations as _DE
from app.services.i18n.es import translations as _ES
from app.services.i18n.fr import translations as _FR
from app.services.i18n.ja import translations as _JA
from app.services.i18n.zh import translations as _ZH
from app.services.i18n.hi import translations as _HI
from app.services.i18n.ru import translations as _RU
from app.services.i18n.ko import translations as _KO
from app.services.i18n.vi import translations as _VI
from app.services.i18n.bn import translations as _BN
from app.services.i18n.id import translations as _ID
from app.services.i18n.it import translations as _IT
from app.services.i18n.tr import translations as _TR
from app.services.i18n.pt import translations as _PT
from app.services.i18n.ar import translations as _AR

_TRANSLATIONS: dict[str, dict[str, str]] = {
	"en": _EN,
	"de": _DE,
	"es": _ES,
	"fr": _FR,
	"ja": _JA,
	"zh": _ZH,
	"hi": _HI,
	"ar": _AR,
	"pt": _PT,
	"ru": _RU,
	"it": _IT,
	"ko": _KO,
	"vi": _VI,
	"bn": _BN,
	"id": _ID,
	"tr": _TR,
	# Stub languages — no translations yet (fall back to English entirely)
	"nl": {},
	"pl": {},
	"sv": {},
	"el": {},
	"ro": {},
	"cs": {},
	"da": {},
	"no": {},
}


def get_translations(lang_code: str = "en") -> dict[str, str]:
	"""Return the full translation dict for a language, falling back to English
	for any missing or empty keys."""
	base = _EN.copy()
	if lang_code != "en" and lang_code in _TRANSLATIONS:
		# Only apply non-empty values so omitted keys in partial lang files
		# transparently fall back to the English string.
		base.update({k: v for k, v in _TRANSLATIONS[lang_code].items() if v})
	return base


def get_all_values(key: str) -> set[str]:
	"""Return the set of all translated values for a given key across every
	registered language. Useful for matching Planka entity names regardless
	of which language they were created in."""
	values: set[str] = set()
	for lang_dict in _TRANSLATIONS.values():
		val = lang_dict.get(key)
		if val:
			values.add(val)
	# Always include English
	en_val = _EN.get(key)
	if en_val:
		values.add(en_val)
	return values


def get_planka_entity_names(lang_code: str = "en") -> dict[str, str]:
	"""Convenience: return only the Planka-relevant entity names for a language."""
	t = get_translations(lang_code)
	return {
		"project_name": t["project_name"],
		"board_name": t["board_name"],
		"list_today": t["list_today"],
		"list_this_week": t["list_this_week"],
		"list_backlog": t["list_backlog"],
		"list_done": t["list_done"],
		"list_inbox": t["list_inbox"],
	}


def get_done_keywords() -> set[str]:
	"""Return all translated variants of 'done' list names, plus common English
	synonyms, for use in progress-percentage calculations."""
	keywords: set[str] = set()
	for lang_dict in _TRANSLATIONS.values():
		done_val = lang_dict.get("list_done", "")
		if done_val:
			keywords.add(done_val.lower())
	keywords.update({"done", "complete", "finish", "erledigt", "termine", "hecho"})
	return keywords


async def get_user_lang() -> str:
	"""Fetch the configured language from the identity profile.
	Uses a fresh DB session -- safe to call from any api or service module."""
	try:
		from app.models.db import AsyncSessionLocal, Person
		from sqlalchemy import select
		async with AsyncSessionLocal() as session:
			res = await session.execute(select(Person).where(Person.circle_type == "identity"))
			ident = res.scalar_one_or_none()
			return ident.language if ident and ident.language else "en"
	except Exception:
		return "en"  # DB unavailable -- fall back to English
