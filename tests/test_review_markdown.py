import pytest
from app.tasks.review_utils import format_review_markdown


def test_format_review_markdown_glued_header():
	raw = "[Monatsrückblick – 02.08.2026 – 01.09.2026]### Was gelaufen ist\nDrei Dinge hast du durchgezogen."
	formatted = format_review_markdown(raw, "Monatsrückblick", "02.08.2026 – 01.09.2026")
	expected = "# Monatsrückblick (02.08.2026 – 01.09.2026)\n\n### Was gelaufen ist\nDrei Dinge hast du durchgezogen."
	assert formatted == expected


def test_format_review_markdown_glued_h2():
	raw = "# Monatsrückblick (02.08.2026 – 01.09.2026)## Erledigt\nDrei Dinge hast du durchgezogen."
	formatted = format_review_markdown(raw, "Monatsrückblick", "02.08.2026 – 01.09.2026")
	expected = "# Monatsrückblick (02.08.2026 – 01.09.2026)\n\n## Erledigt\nDrei Dinge hast du durchgezogen."
	assert formatted == expected


def test_format_review_markdown_glued_h2_no_space():
	raw = "# Monatsrückblick (02.08.2026 – 01.09.2026)##Erledigt\nDrei Dinge hast du durchgezogen."
	formatted = format_review_markdown(raw, "Monatsrückblick", "02.08.2026 – 01.09.2026")
	expected = "# Monatsrückblick (02.08.2026 – 01.09.2026)\n\n## Erledigt\nDrei Dinge hast du durchgezogen."
	assert formatted == expected


def test_format_review_markdown_standard_h1():
	raw = "# Monatsrückblick (02.08.2026 – 01.09.2026)\n\n## Erledigt\nDrei Dinge hast du durchgezogen."
	formatted = format_review_markdown(raw, "Monatsrückblick", "02.08.2026 – 01.09.2026")
	assert formatted == raw


def test_format_review_markdown_missing_h1():
	raw = "## Erledigt\nDrei Dinge hast du durchgezogen."
	formatted = format_review_markdown(raw, "Monatsrückblick", "02.08.2026 – 01.09.2026")
	expected = "# Monatsrückblick (02.08.2026 – 01.09.2026)\n\n## Erledigt\nDrei Dinge hast du durchgezogen."
	assert formatted == expected


def test_format_review_markdown_bracketed_h1():
	raw = "# [Monatsrückblick – 02.08.2026 – 01.09.2026]\n\n## Erledigt\nDrei Dinge."
	formatted = format_review_markdown(raw, "Monatsrückblick", "02.08.2026 – 01.09.2026")
	expected = "# Monatsrückblick – 02.08.2026 – 01.09.2026\n\n## Erledigt\nDrei Dinge."
	assert formatted == expected


def test_format_review_markdown_glued_middle_heading():
	raw = "# Monatsrückblick (02.08.2026 – 01.09.2026)\n\nEtwas Text hier.### Stillstand\nKeine Tasks."
	formatted = format_review_markdown(raw, "Monatsrückblick", "02.08.2026 – 01.09.2026")
	expected = "# Monatsrückblick (02.08.2026 – 01.09.2026)\n\nEtwas Text hier.\n\n### Stillstand\nKeine Tasks."
	assert formatted == expected
