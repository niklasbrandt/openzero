# Agent Rules

This file is for hard-coding Z's operational behaviour without using the personality widget on the dashboard.

Rules written here are loaded at startup and injected into every system prompt. They take effect immediately after a server restart or the hourly context refresh.

Use this file for machine-level behavioural constraints that should always apply regardless of conversation context — things like communication style preferences, forbidden topics, fixed response formats, or operator-level restrictions.

Leave this file empty (or with only these instructions) if you have no rules to add. Z will detect an empty file and skip it gracefully.

## Your Rules

<!-- Add your hard-coded behavioural rules below this line. -->
