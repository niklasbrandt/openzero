# My Requirements

> Personal configuration for the AI Operating System.
> These define what matters to you, how you organize your life, and what the
> system should prioritize.
>
> **Copy this file to `personal/requirements.md` and fill in your details.**
> The `personal/` folder is gitignored — your config stays private.

---

## Life Domains

Organize your projects and goals across these domains:

| Domain       | Focus                                        |
|:-------------|:---------------------------------------------|
| **Career**   | <!-- e.g., Job search -->          |
| **Health**   | <!-- e.g., Exercise, habits -->               |
| **Family**   | <!-- e.g., Kids, household -->                |
| **Finance**  | <!-- e.g., Bills, savings -->                 |
| **Creative** | <!-- e.g., Side projects, learning -->        |

---

## Email Rules

Emails matching these patterns trigger an **immediate Telegram notification**:

| Sender Pattern    | Action   | Reason                        |
|:------------------|:---------|:------------------------------|
| `school-example`  | urgent   | Example: kid's school          |
| `boss@company`    | urgent   | Example: work contact          |
| `bank-alerts`     | urgent   | Example: financial alerts      |

All other emails are summarized and included in the **morning briefing**.

> To add new rules: insert into the `email_rules` database table or
> (future) use `/addrule sender@example.com urgent` via Telegram.

---

## Preferences

| Key                    | Value                                    |
|:-----------------------|:-----------------------------------------|
| `career_tone`          | <!-- e.g., confident, impact-driven -->  |
| `morning_briefing_time`| <!-- e.g., 07:30 -->                     |
| `timezone`             | <!-- e.g., America/New_York -->          |
| `weekly_review_day`    | <!-- e.g., sunday -->                    |

---

## Planka Board Structure

Task boards organized by life domain:

| Board         | Lists                                 |
|:--------------|:--------------------------------------|
| **Career**    | Inbox → In Progress → Blocked → Done |
| **Health**    | Inbox → Habits → Completed           |
| **Family**    | Inbox → This Week → Done             |
| **Finance**   | Inbox → Pending → Resolved           |
| **Creative**  | Ideas → Active → Shipped             |

---

## Career Goals

- Target role:
- Key differentiators:
- Tone:
- The AI should connect daily actions to this goal where relevant

---

## Privacy Requirements

- **All data stays on my server.** No exceptions (unless optional Cloud LLM is enabled).
- **LLM runs locally** (Ollama) by default. Cloud APIs (Groq, OpenAI) are optional alternatives for higher performance.
- **Email access is read-only.** The system cannot send, delete, or modify emails (write capabilities might be added later).
- **Calendar access** can optionally be set to read-write allowing the system to create dates and change events.
- **No public ports.** Everything behind Tailscale VPN.
- **Backups are encrypted** (GPG/AES-256).
