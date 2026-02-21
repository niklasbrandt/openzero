#  Recurring Plans

> Automated routines that keep me organized, accountable, and aware.
> Each plan runs on a schedule via APScheduler and delivers results via Telegram.

---

## Daily — Morning Briefing

**Schedule:** Mon–Fri at 06:00 (Your Timezone)
**Trigger:** APScheduler `CronTrigger` or `/daily` command
**Delivery:** Telegram message

### What it includes:
1. **Greeting** for the day
2. **Unread email summary** — urgent ones highlighted first
3. **Today's priorities** — pulled from Planka + AI recommendation
4. **Quick context** — any memories or notes relevant to today

### Tone:
Not a list dump. The AI frames it like a strategic briefing:
> "3 emails overnight. One from elementary school — needs attention before 10.
> The rest can wait. Today's priority: Work and then buy a birthday gift for your daughter."

### Implementation (`app/tasks/morning.py`):

```python
from app.services.gmail import fetch_unread_emails
from app.services.llm import chat
from app.api.telegram import send_notification
from datetime import datetime

async def morning_briefing() -> str:
    """Generate and send the morning briefing."""

    # 1. Unread email summary
    emails = await fetch_unread_emails(max_results=10)
    email_lines = "\n".join(
        [f"- {e['from']}: {e['subject']}" for e in emails]
    ) or "No unread emails."

    # 2. Build prompt for LLM
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""Today is {today}.

Here are the unread emails:
{email_lines}

Generate a concise morning briefing that includes:
1. A greeting for the day
2. Summary of important emails (highlight urgent ones)
3. Any recommended priorities for today

Keep it under 300 words. Use bullet points."""

    briefing = await chat(prompt)

    # 3. Send via messenger
    await send_notification(f"️ *Morning Briefing*\n\n{briefing}")
    return briefing
```

---

## Weekly — Review & Reset

**Schedule:** Sunday at 10:00 (Your Timezone)
**Trigger:** APScheduler `CronTrigger` or `/weekly` command
**Delivery:** Telegram message

### What it includes:
1. **Wins** — what went well this week
2. **Stagnation** — projects that haven't moved (listed out explicitly if there are many)
3. **Balance Check** — career / health / family / creative balance
4. **Next Week Focus** — top 3 priorities for the coming week

### Tone:
Like a board meeting with yourself. Honest but encouraging:
> "Career: momentum. Health: slipping. You said running matters to you —
> this is the week to restart. One run. That's it."

### Implementation (`app/tasks/weekly.py`):

```python
from app.services.llm import chat
from app.api.telegram import send_notification

async def weekly_review() -> str:
    """Analyze the week and send a structured report."""

    # TODO: Pull actual data from Planka and Postgres
    prompt = """You are reviewing my week. Based on the following data, generate a
structured weekly review with these sections:

1. **Wins** — what went well
2. **Stagnation** — projects that haven't moved (list them if there are many)
3. **Balance Check** — career/health/family/creative balance
4. **Next Week Focus** — top 3 priorities

Be honest but encouraging. Use bullet points. Under 400 words."""

    review = await chat(prompt)
    await send_notification(f" *Weekly Review*\n\n{review}")
    return review
```

---

## Monthly — Big Picture Check

**Schedule:** 1st of every month at 10:00 (Your Timezone)
**Trigger:** APScheduler `CronTrigger` or `/monthly` command
**Delivery:** Telegram message

### What it includes:
1. **Goal Progress** — where do I stand on my major goals?
2. **Domain Balance** — which life domains got attention, which were neglected?
3. **Memory Highlights** — notable memories stored this month
4. **System Health** — backup status, server uptime, any issues
5. **Next Month Intent** — one sentence per domain: what I want to achieve

### Implementation (`app/tasks/monthly.py`):

```python
from app.services.llm import chat
from app.services.memory import semantic_search
from app.api.telegram import send_notification
from datetime import datetime

async def monthly_review() -> str:
    """Generate a monthly big-picture review."""

    month = datetime.now().strftime("%B %Y")

    # TODO: Pull actual data from Planka, Postgres, Qdrant
    prompt = f"""You are conducting a monthly review for {month}.

Generate a structured monthly review with these sections:

1. **Goal Progress** — status of major goals across all life domains
2. **Domain Balance** — career / health / family / finance / creative
3. **Highlights** — notable achievements or decisions this month
4. **System Health** — any operational notes
5. **Next Month Intent** — one clear intention per domain

Be reflective but forward-looking. Under 500 words."""

    review = await chat(prompt)
    await send_notification(f" *Monthly Review — {month}*\n\n{review}")
    return review
```

### Scheduler Registration (add to `app/tasks/scheduler.py`):

```python
# Monthly Review — 1st of every month at 10:00
scheduler.add_job(
    monthly_review,
    CronTrigger(day=1, hour=10, minute=0),
    id="monthly_review",
    replace_existing=True,
)
```
