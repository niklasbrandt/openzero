import re


def format_review_markdown(content: str, default_title: str, date_range_str: str) -> str:
	"""Clean and normalize markdown headings in review content."""
	if not content:
		return ""
	text = content.strip()

	# 1. Normalize bracketed headers e.g. [Monatsrückblick – 02.08.2026 – 01.09.2026]
	text = re.sub(
		r"^\s*\[\s*(?:Monatsrückblick|Wochenrückblick|Quartalsrückblick|Jahresrückblick|[A-Za-z]+rückblick|[A-Za-z\s]+Review)[^\]]*\]\s*",
		f"# {default_title} ({date_range_str})\n\n",
		text,
		flags=re.IGNORECASE,
	)

	# 2. Normalize '# [Title]' -> '# Title'
	text = re.sub(
		r"^\s*#\s*\[([^\]]+)\]",
		r"# \1",
		text,
	)

	# 3. If it does not start with an H1 heading (# ...), prepend the default H1 heading
	if not re.match(r"^\s*#\s+[^\n]+", text):
		text = f"# {default_title} ({date_range_str})\n\n{text}"

	# 4. Ensure any subsequent headings (## or ###) are not glued to preceding characters or single newlines
	text = re.sub(r"([^\n])\s*(#{1,6}\s+)", r"\1\n\n\2", text)
	text = re.sub(r"(?<!\n)\n(#{1,6}\s+)", r"\n\n\1", text)

	# 5. Collapse 3+ newlines to 2
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()
