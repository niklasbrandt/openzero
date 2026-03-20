# openZero Agent behavior log

- Violation: `TypeError` in `telegram_bot.py` due to incorrect `safe_reply` call passing `parse_mode="HTML"`.
- Correction: Removed the `parse_mode` argument in `cmd_crews` and added missing `/crews` command to `dashboard.py` for consistency.
