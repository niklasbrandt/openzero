# Agent Rules

This file is for hard-coding Z's operational behaviour without using the personality widget on the dashboard.

Rules written here are loaded at startup and injected into every system prompt. They take effect immediately after a server restart or the hourly context refresh.

Use this file for machine-level behavioural constraints that should always apply regardless of conversation context — things like communication style preferences, forbidden topics, fixed response formats, or operator-level restrictions.

Leave this file empty (or with only these instructions) if you have no rules to add. Z will detect an empty file and skip it gracefully.

## How to Add Rules

Add rules as plain numbered lists or bullet points under a section heading. Be explicit and directive.

Example structure:

```
## Communication Style
- Always respond in British English.
- Never use bullet points when a single sentence will do.

## Forbidden Topics
- Do not discuss competitor products.

## Response Format
- When asked for a summary, always use the format: Context / Decision / Next Step.
```

## Your Rules

<!-- Add your hard-coded behavioural rules below this line. -->
