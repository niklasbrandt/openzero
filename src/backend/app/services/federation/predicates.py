"""ScopePredicate evaluation against a Qdrant search result set."""

def evaluate_predicate(predicate: dict, point_payload: dict) -> bool:
	"""Returns True if the point passes the scope predicate."""
	scopes_in = predicate.get("scopes_in", [])
	tags_any = predicate.get("tags_any", [])
	tags_none = predicate.get("tags_none", [])
	point_scope = point_payload.get("scope", "default")
	point_tags = set(point_payload.get("share_tags", []))
	if scopes_in and point_scope not in scopes_in:
		return False
	if tags_any and not point_tags.intersection(tags_any):
		return False
	if tags_none and point_tags.intersection(tags_none):
		return False
	return True
