"""Per-resource redaction allowlists."""

REDACTION_RULES: dict[str, list[str]] = {
	"calendar_availability": ["title", "attendees", "location", "description", "notes", "attachments"],
	"memory": [],  # redactions specified per-contract
	"planka_board": ["description", "attachments", "comments"],
	"personal_fact": ["raw_text", "source_path"],
}

def apply_redactions(resource: str, item: dict, additional: list[str] | None = None) -> dict:
	"""Removes redacted fields from item. Returns a shallow copy."""
	fields_to_remove = set(REDACTION_RULES.get(resource, []))
	if additional:
		fields_to_remove.update(additional)
	return {k: v for k, v in item.items() if k not in fields_to_remove}
