# Full Ambient Intelligence -- Unified Roadmap

> Master plan to achieve fully ambient intelligence in openZero.
> Status: DRAFT | Author: conductor | Created: 2026-04-26
> Supersedes the standalone scope of `ambient_intelligence.md` (state-diff engine).
> Companions: `ambient_capture_routing.md`, `multimodal_vision.md`.

---

## 1. Objective

Build one coherent ambient layer where openZero can:

1. Proactively detect meaningful state changes and surface them at quiet moments (state-diff engine).
2. Understand and capture low-context user inputs to the right system without explicit verbs (ambient capture routing).
3. Accept images as first-class input, convert them to structured text, and route through the same intelligence pipeline (multimodal vision).

These three streams are not independent features. They share the same pending-action queue, the same security posture, the same channel-parity rules, and the same delivery model. This artifact treats them as one program.

---

## 2. What Already Changed

The reactive foundation is in place and reusable across all three streams:

- Deterministic intent routing (22 verbs, 11 languages) via `intent_router.py`.
- Crew routing with keyword + LLM fallback and Jaccard-based panels.
- Unified message bus (`bus.ingest()` / `bus.push_all()`) across Telegram, WhatsApp, dashboard.
- Existing scheduler (APScheduler) ready for new periodic jobs.
- Planka, calendar, email, hardware, and conversation data sources already exposed by services.
- Action vocabulary allowlist with `SENSITIVE_ACTIONS` HITL gate.
- Untrusted-content sentinel patterns and `_MUTATING_TAG_RE` stripping (proven in ambient capture security tests).
- Self-audit system and follow-up nudges as adjacent precedents for proactive behaviour.

Three concrete architectural plans are now drafted:

- `ambient_intelligence.md` -- state-diff engine, adapters, rule engine, delivery scheduler.
- `ambient_capture_routing.md` -- decision lanes, plugin model, scoring, HITL flow, learning loop.
- `multimodal_vision.md` -- vision service, llama.cpp multimodal, channel intake, EXIF strip, rate limit.

---

## 3. Remaining Gaps

1. State-diff implementation is not production-wired: adapters, diff engine, rule engine, dispatcher, and quiet-moment delivery queue are planned but not deployed.
2. Ambient capture engine is not yet end-to-end live across all three channels with the unified pending queue.
3. Vision stack is not deployed: dedicated multimodal container, vision preprocessing service, and three-channel intake remain pending.
4. Dashboard control and observability for ambient features are incomplete.
5. Translation and channel parity work is large: every new string in 11 languages, every behaviour change applied to Telegram, WhatsApp, and dashboard simultaneously.
6. End-to-end test coverage for the new ambient and vision paths is not yet green.

---

## 4. Phased Milestones

### Phase A -- Core Safety Foundation

DoD: shared pending-action queue model in place, security baselines implemented, baseline ambient security tests green.

- Unify the existing `SENSITIVE_ACTIONS` HITL queue with the ambient capture pending queue under one Redis namespace and one dashboard surface.
- Promote sentinel-wrapping, control-char stripping, and `_MUTATING_TAG_RE` stripping into shared helpers usable by capture, state-diff, and vision.
- Plugin scope clamps (no delete; HITL on create / overwrite of user-authored content).
- Confirmation-hijack guard (per-channel pending state, monotonic sequence, quote-in-confirm requirement).
- Test corpus: prompt-injection cases targeting capture, state-diff context injection, and vision OCR inputs.

### Phase B -- Ambient Capture v1 (Planka-first)

DoD: low-context phrase routing works on Telegram, WhatsApp, and dashboard with EXECUTE / ASK / TEACH / CHAT lanes; configurable thresholds live; correction feedback captured for learning; rollback and failure messaging reliable.

- `ambient_capture.py` engine and `intent_bus` classifier integrated downstream of `intent_router.py`.
- Plugin set v1: `PlankaCardPlugin`, `PlankaListPlugin`, `PlankaBoardPlugin`, `CalendarEventPlugin`, `ShoppingListPlugin`, `MemoryFactPlugin`, `ReminderPlugin`.
- Tier A through D evidence collection (cheap structural -> LLM tiebreaker only on disagreement).
- AgentsWidget Inference panel: silent / ask / chat thresholds, presets (Cautious / Confident butler / Bold autopilot), pending TTL, learning retention, two-step routing-intelligence reset.
- Cold-start co-creator mode for sparse vaults (`boards < 5 AND cards < 20`).
- Per-channel pending state (Telegram / WhatsApp / dashboard / future voice-edge).
- i18n keys complete in `_EN` and `_DE`; parity gate green.

### Phase C -- Proactive State-Diff v1

DoD: at least Planka + calendar + email + hardware adapters producing signals; rules fire with cooldown and dedup; delivery scheduler respects quiet moments and priority; at least one multi-signal trigger proven end-to-end.

- `services/ambient/` package per `ambient_intelligence.md` section 11.
- Adapters: planka, calendar, email, hardware, conversation, health (file + keyword).
- Rules: `card_stall`, `inbox_overwhelm`, `infra_critical`, `overload_composite`, `sedentary_drift`.
- Quiet-moment detection (no recent message, no imminent calendar event, within active hours).
- Priority-based delivery queue (1 critical immediate; 4-5 fold into next briefing).
- Briefing-queue integration in `morning.py`.
- `AMBIENT_ENABLED` master switch + `AMBIENT_MAX_TRIGGERS_PER_HOUR` global cap.

### Phase D -- Vision Input v1

DoD: multimodal service deployed behind feature flag; image upload/ingest working on Telegram, WhatsApp, and dashboard; images converted into structured textual context; routed through existing crew and action paths; image security constraints enforced.

- `llm-vision` service (Qwen2.5-VL-3B default, Moondream2 fallback for `micro` profile).
- `services/vision.py` with `describe_image()` and mode detection (whiteboard / receipt / generic).
- Channel intake: Telegram `handle_photo`, WhatsApp media handler, dashboard upload.
- Synthetic message format: `[Image: <caption>]\n<user text>` enters the existing pipeline.
- Security: file-size cap, magic-byte MIME validation, EXIF strip via Pillow, rate limit, no disk persistence.

### Phase E -- Unified Ambient Intelligence GA

DoD: capture + proactive + vision converge into one operational system with dashboard observability, per-rule controls, i18n completeness, regression and security suites passing, measurable operator value (useful proactive insights without spam).

- `AmbientWidget.ts` dashboard component: active signals, recent triggers, cooldowns, per-rule toggles.
- Per-pod / per-channel ambient policy (e.g. voice-edge does not deliver low-priority insights at night).
- Telemetry: false-positive rate per rule, capture acceptance rate per plugin, vision success rate.
- Cross-feature glue: capture lessons can feed state-diff context; vision-derived items can route through capture; ambient triggers can request a vision capture ("send me the whiteboard photo when you're done").
- Final i18n parity, accessibility audit, and live regression suite green for all three streams.

---

## 5. Key Risks

1. Alert fatigue and trust erosion from false positives or over-triggering.
2. Injection risk from untrusted board / card / OCR text entering routing or tiebreakers.
3. Learning-system poisoning and stale confirmation hijack if guardrails are incomplete.
4. Resource pressure and latency from polling plus multimodal CPU and RAM load.
5. Channel drift if behaviour or security fixes ship to one interface but not all (agents.md rule 21).
6. i18n quality drift across 11 languages, especially in HITL phrasing and conversational markers.
7. Single-user assumptions becoming unsafe if multi-user / shared-board behaviour is introduced without re-audit.

Each phase's DoD includes the corresponding mitigation: cooldowns and rate limits for #1, sentinel + tag-strip for #2, learning-loop guards for #3, hardware-profile-aware defaults for #4, the channel parity rule for #5, the i18n gate for #6, and an explicit single-user scope clamp for #7.

---

## 6. How This Composes With The Rest Of The Roadmap

- Federated memory (#7) becomes a new evidence source: capture and state-diff can read scoped remote signals under existing share contracts.
- Voice-edge pod (#8) is just another channel; ambient capture, state-diff, and vision behave identically once the SSE protocol is wired.
- Z-to-Z protocol (#9) reuses the ambient pending queue and the federation contract layer; no new trust model.

If you want, the next move is to scaffold Phase A's shared pending-queue helpers and the unified sentinel utility, since both Phase B and Phase C consume them.
