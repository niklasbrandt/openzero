"""Static eval harness for the openZero semantic intent router.

Fully offline -- no FastAPI app, no Redis, Qdrant, or PostgreSQL.

Exercises:
  1. Keyword routing accuracy (10 parametrized cases)
  2. Disabled crew exclusion (3 parametrized cases)
  3. Ambiguity / multi-match handling (2 cases)
  4. Default fallback (1 case)

Total: 16 tests.
"""

import re
import yaml
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Load crews.yaml statically -- no app imports
# ---------------------------------------------------------------------------
_CREWS_PATH = Path(__file__).parent.parent / "agent" / "crews.yaml"


def _load_crews() -> dict:
	with open(_CREWS_PATH, "r", encoding="utf-8") as f:
		return yaml.safe_load(f)


_CREWS_DATA = _load_crews()


# ---------------------------------------------------------------------------
# Build keyword index and YAML-order crew list
#   _KW_INDEX    : {crew_id: [keyword_lowercase, ...]}  -- enabled crews only, with keywords
#   _CREW_ORDER  : [crew_id, ...]                        -- all enabled crews, in YAML order
#   _DISABLED    : {crew_id, ...}                        -- crews with enabled: false
# ---------------------------------------------------------------------------
def _build_index(data: dict) -> tuple[dict[str, list[str]], list[str], set[str]]:
	"""Parse crews.yaml and return (keyword_index, ordered_ids, disabled_set)."""
	index: dict[str, list[str]] = {}
	ordered: list[str] = []
	disabled: set[str] = set()

	for crew in data.get("crews", []):
		cid: str = crew["id"]
		if crew.get("enabled", True) is False:
			disabled.add(cid)
			continue
		ordered.append(cid)
		kws = crew.get("keywords", [])
		if kws:
			index[cid] = [str(k).lower() for k in kws]

	return index, ordered, disabled


_KW_INDEX, _CREW_ORDER, _DISABLED = _build_index(_CREWS_DATA)


# ---------------------------------------------------------------------------
# Keyword matcher
#   score  = number of distinct keywords from that crew found as substrings in text
#   winner = highest-scoring crew; ties broken by YAML declaration order
#   default = "research" when no keywords match
# ---------------------------------------------------------------------------
def _score(text: str) -> dict[str, int]:
	"""Return per-crew match counts (excludes zero-scoring crews).

	Uses prefix-boundary matching: a keyword matches only when the first character
	is NOT preceded by a letter.  This allows plural/inflected suffixes
	("workouts" matches "workout") while blocking false substring matches
	("heating" does NOT match "eat" or "eating").
	"""
	lower = text.lower()
	scores: dict[str, int] = {}
	for crew_id, keywords in _KW_INDEX.items():
		# Exclude 'research' from competition -- it is always the fallback
		if crew_id == "research":
			continue
		count = sum(
			1 for kw in keywords
			if re.search(r"(?<![a-zA-Z])" + re.escape(kw), lower)
		)
		if count > 0:
			scores[crew_id] = count
	return scores


def _keyword_route(text: str) -> str:
	"""Return the best-matching crew ID, or 'research' if nothing matches."""
	scores = _score(text)
	if not scores:
		return "research"
	max_score = max(scores.values())
	# Deterministic tie-break: first crew in YAML order with the max score
	for cid in _CREW_ORDER:
		if scores.get(cid, 0) == max_score:
			return cid
	return "research"


# ---------------------------------------------------------------------------
# 1. Keyword routing accuracy -- 10 cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
	("what should I eat for dinner?", "recipe"),
	("plan my workouts for next week", "fitness"),
	("how is my hrv looking?", "health"),
	("I feel so angry tonight", "life"),
	("is this SaaS idea worth pursuing?", "idea"),
	("I have a flight to book", "travels"),
	("fix my heating system", "residence"),
	("explain quantum entanglement", "research"),
	("my kids have a birthday party next weekend", "dependents"),
	("check my password hygiene", "security"),
])
def test_keyword_routing_accuracy(text: str, expected: str) -> None:
	result = _keyword_route(text)
	assert result == expected, (
		f"Expected crew '{expected}', got '{result}' for: {text!r}\n"
		f"Scores: {_score(text)}"
	)


# ---------------------------------------------------------------------------
# 2. Disabled crew exclusion -- 3 cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,excluded_crew", [
	("analyse my competitors", "market-intel"),
	("score this inbound lead", "leads"),
	("write a lesson plan for grade 5", "lessons"),
])
def test_disabled_crew_exclusion(text: str, excluded_crew: str) -> None:
	# Confirm crew is flagged disabled in YAML
	assert excluded_crew in _DISABLED, (
		f"Crew '{excluded_crew}' must be marked 'enabled: false' in crews.yaml"
	)
	# Confirm it is absent from the keyword index (disabled crews must not route)
	assert excluded_crew not in _KW_INDEX, (
		f"Disabled crew '{excluded_crew}' must not appear in keyword index"
	)
	# Routing must never return the disabled crew
	result = _keyword_route(text)
	assert result != excluded_crew, (
		f"Routing '{text}' returned disabled crew '{excluded_crew}'"
	)


# ---------------------------------------------------------------------------
# 3. Ambiguity / multi-match handling -- 2 cases
# ---------------------------------------------------------------------------
def test_ambiguity_higher_score_wins() -> None:
	"""fitness scores 2 (workout + training), life scores 1 (routine).

	The router must select the crew with the highest keyword match count.
	"""
	text = "plan my workout training routine"
	scores = _score(text)

	assert "fitness" in scores, f"'fitness' should match 'workout'/'training' in: {text!r}"
	assert "life" in scores, f"'life' should match 'routine' in: {text!r}"
	assert scores["fitness"] > scores["life"], (
		f"fitness score {scores['fitness']} should exceed life score {scores['life']}"
	)

	result = _keyword_route(text)
	assert result == "fitness", (
		f"Expected 'fitness' (highest scorer), got '{result}'\nScores: {scores}"
	)


def test_ambiguity_tie_is_deterministic() -> None:
	"""recipe scores 2 (dinner + meal), travels scores 1 (trip).

	Verifies that the result is stable across repeated calls (not random),
	and that the higher-scoring crew wins.
	"""
	text = "plan my dinner meals for a trip"
	results = [_keyword_route(text) for _ in range(10)]
	unique = set(results)

	assert len(unique) == 1, f"Routing was non-deterministic across 10 calls: {unique}"

	scores = _score(text)
	assert "recipe" in scores, f"'recipe' should match 'dinner'/'meal' in: {text!r}"
	assert "travels" in scores, f"'travels' should match 'trip' in: {text!r}"
	assert scores["recipe"] > scores["travels"], (
		f"recipe score {scores['recipe']} should exceed travels score {scores['travels']}"
	)
	assert results[0] == "recipe", (
		f"Expected 'recipe' (highest scorer), got '{results[0]}'\nScores: {scores}"
	)


# ---------------------------------------------------------------------------
# 4. Default fallback -- 1 case
# ---------------------------------------------------------------------------
def test_fallback_to_research() -> None:
	"""A message with zero keyword matches must route to 'research'."""
	text = "describe the Fermi paradox in detail"
	keyword_scores = _score(text)
	assert keyword_scores == {}, (
		f"Expected no keyword matches for {text!r}, got: {keyword_scores}"
	)
	result = _keyword_route(text)
	assert result == "research", (
		f"Expected fallback to 'research', got '{result}'"
	)
