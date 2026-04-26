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
- Untrusted-content sentinel patterns and `_MUTATING_TAG_RE` stripping live today inside `services/ambient_capture/sanitiser.py` and `services/agent_actions.py`. Phase A consolidates them into a shared `services/security/sanitisers.py` module reusable by capture, state-diff, vision, federation, and voice-edge.
- Self-audit system and follow-up nudges as adjacent precedents for proactive behaviour.
- `services/vision.py` exists today (single-shot describe). Phase D wires it into channels and adds the dedicated multimodal container; it is not a greenfield service rebuild.

Three concrete architectural plans are now drafted:

- `ambient_intelligence.md` -- state-diff engine, adapters, rule engine, delivery scheduler.
- `ambient_capture_routing.md` -- decision lanes, plugin model, scoring, HITL flow, learning loop.
- `multimodal_vision.md` -- vision service, llama.cpp multimodal, channel intake, EXIF strip, rate limit.

---

## 3. Remaining Gaps

1. State-diff implementation is not production-wired: adapters, diff engine, rule engine, dispatcher, and quiet-moment delivery queue are planned but not deployed.
2. Ambient capture engine is not yet end-to-end live across all three channels with the unified pending queue.
3. Dedicated multimodal container (`llm-vision`), three-channel intake, OCR sanitisation, and EXIF/MIME hardening on top of the existing `services/vision.py` are not deployed.
4. Dashboard control and observability for ambient features are incomplete.
5. Translation and channel parity work is large: every new string at minimum in `_EN` and `_DE` (CI-enforced parity across all populated dicts under `services/i18n/`), every behaviour change applied to Telegram, WhatsApp, dashboard, and voice-edge simultaneously (agents.md rule 21 must be extended once voice-edge ships).
6. End-to-end test coverage for the new ambient and vision paths is not yet green.

---

## 4. Phased Milestones

### Phase A -- Core Safety Foundation

DoD: shared pending-action queue model in place, security baselines implemented, baseline ambient security tests (`tests/test_ambient_capture_security.py`) green plus a new state-diff and vision injection class added to `tests/test_security_prompt_injection.py`.

- Unify the existing `SENSITIVE_ACTIONS` HITL pending list (today an in-memory list surfaced via dashboard polling) with the ambient capture Redis pending queue. v1 keeps two stores but exposes one `/api/pending` view; v2 backfills `SENSITIVE_ACTIONS` into the Redis namespace.
- Consolidate sentinel-wrapping, control-char stripping, `_MUTATING_TAG_RE`, and `_sanitize_for_log` into `services/security/sanitisers.py`. Capture, state-diff, vision, federation, and voice-edge all import from this single module.
- Confirmation-hijack guard (channel-scoped pending key, monotonic sequence, quote-in-confirm) is enforced **inside the unified pending-queue helpers**, not at each caller. Helpers reject any write that omits hijack-guard fields.
- Plugin scope clamps (no delete; HITL on create / overwrite of user-authored content).
- Per-rule and per-source-adapter trigger sub-caps (in addition to the global `AMBIENT_MAX_TRIGGERS_PER_HOUR`) so a poisoned email or hostile invite cannot starve real signals.
- Global ambient-stack token budget (system prompt + ambient + federation + vision + memory + personal) with documented eviction order. Default ceiling 6k tokens outside the user turn.
- Test corpus: prompt-injection cases targeting capture, state-diff context injection, vision OCR inputs, and any cross-feature glue hop (capture -> state-diff, vision -> capture, ambient -> vision).

### Phase B -- Ambient Capture v1 (Planka-first)

DoD: low-context phrase routing works on Telegram, WhatsApp, and dashboard with EXECUTE / ASK / TEACH / CHAT lanes; configurable thresholds live; correction feedback captured for learning; rollback and failure messaging reliable.

- `ambient_capture.py` engine and `intent_bus` classifier integrated downstream of `intent_router.py`.
- Plugin set v1: `PlankaCardPlugin`, `PlankaListPlugin`, `PlankaBoardPlugin`, `CalendarEventPlugin`, `ShoppingListPlugin`, `MemoryFactPlugin`, `ReminderPlugin`.
- Tier A through D evidence collection (cheap structural -> LLM tiebreaker only on disagreement).
- AgentsWidget Inference panel: silent / ask / chat thresholds, presets (Cautious / Confident butler / Bold autopilot), pending TTL, learning retention, two-step routing-intelligence reset.
- Cold-start co-creator mode for sparse vaults (`boards < 5 AND cards < 20`).
- Per-channel pending state (Telegram / WhatsApp / dashboard / future voice-edge).
- i18n keys complete in `src/backend/app/services/i18n/en.py` and `de.py`; `pytest tests/test_i18n_coverage.py -v` green is a Phase B DoD.

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

DoD: multimodal service deployed behind feature flag; image upload/ingest working on Telegram, WhatsApp, dashboard, and voice-edge (text-only summary if voice); images converted into structured textual context; routed through existing crew and action paths; image security constraints enforced.

- `llm-vision` compose service (Qwen2.5-VL-3B default; Moondream2 fallback selected by the new `HARDWARE_PROFILE` enum once it lands -- prerequisite). Resource limits per profile; named volume `vision_models` so `sync.sh` does not redownload weights.
- `services/vision.py` (already deployed) gains mode detection (whiteboard / receipt / generic) and OCR text extraction. OCR text is treated as **untrusted** input: passes through `services/security/sanitisers.py` (sentinel-wrap, `_MUTATING_TAG_RE`, control-char strip) **before** entering `bus.ingest`.
- Channel intake: Telegram `handle_photo`, WhatsApp media handler, dashboard upload, and a stubbed voice-edge text-summary path.
- Synthetic message format wraps the caption explicitly: `<<<UNTRUSTED_VISION caption="..." >>>...<<<END_UNTRUSTED>>>\n<user text>`. Captions are never bare-concatenated -- the LLM must always see the trust boundary.
- Security: file-size cap, magic-byte MIME validation (not extension), EXIF strip via Pillow, rate limit (matches `multimodal_vision.md` §5.5), tmpfs-only working dir mode 0700 with FS-audit test, no disk persistence.

### Phase E -- Unified Ambient Intelligence GA

DoD: capture + proactive + vision converge into one operational system with dashboard observability, per-rule controls, i18n completeness, regression and security suites passing, measurable operator value (useful proactive insights without spam).

- `AmbientWidget.ts` dashboard component: active signals, recent triggers, cooldowns, per-rule toggles. Mandatory boilerplate: `${ACCESSIBILITY_STYLES}`, `${BUTTON_STYLES}`, `${SECTION_HEADER_STYLES}`, `${SCROLLBAR_STYLES}`, `tr()` (loaded in `connectedCallback`), local `.sr-only`, `:focus-visible`, `@media (prefers-reduced-motion: reduce)`, `@media (forced-colors: active)`, HSLA `var(--token, fallback)`, `rem` spacing, native HTML elements first, `role="status"` + `aria-live="polite"` for the active-signals feed, `role="switch"` + `aria-checked` for per-rule toggles, 44x44 px touch targets.
- Per-pod / per-channel ambient policy (e.g. voice-edge does not deliver low-priority insights at night). Multi-pod ambient deliveries route to **one** pod (most-recently-used or operator-elected), not all -- never broadcast.
- Briefing-fold collapse rules: if a state-diff trigger overlaps with a scheduled briefing within `ambient_suppress_window_min` (default 30), the ambient delivery is suppressed silently and the insight is folded into the briefing.
- Sentinel-wrap any state-diff text (Planka card titles, calendar event titles, email subjects) before TTS render or LLM-context injection. Spoken output is never raw remote/Planka strings.
- Telemetry: false-positive rate per rule, capture acceptance rate per plugin, vision success rate. Phase E DoD replaces "useful proactive insights without spam" with a measurable target: per-rule false-positive rate below an operator-set threshold over a recorded 7-day fixture.
- Cross-feature glue (capture -> state-diff feedback, vision -> capture, ambient -> vision request) re-applies the sanitiser bundle at every hop -- no transitive trust. Anti-poisoning ceiling and cluster cap from capture extend to state-diff feedback.
- Final i18n parity, accessibility audit, and live regression suite green for all four channels (Telegram, WhatsApp, dashboard, voice-edge).

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

---

## Appendix R -- Review Revisions (2026-04-26)

Multi-specialist review (security, backend, infra, qa, ui-builder, perf, ai-engineer, researcher) produced the following ranked findings. Each is folded into the relevant phase DoD above; this appendix tracks them as discrete open items for code review.

### Cross-cutting prerequisites (block Phase B onward)

1. **i18n file layout.** Translation keys live in `src/backend/app/services/i18n/{code}.py`, not in `services/translations.py` (which only aggregates). Update agents.md rule 19's pointer in the same PR.
2. **`HARDWARE_PROFILE` enum prerequisite.** `config.py` has no profile selector today. Phase D (Moondream2 fallback for `micro`) and `multimodal_vision.md` profile-aware defaults need the enum to land first.
3. **`bus.ingest` signature extension.** Today `(channel, user_text, save=True)`. Phases B and D plus federation and voice-edge all want `lang` and `conversation_id`. Coordinate one signature change across channels in a single PR.
4. **`MessageBus.commit_reply` cross-channel sync** sends HTML to every registered channel. Voice-edge cannot speak HTML; introduce a channel-class registry (`text` vs `audio`) so `push_all` routes correctly.
5. **Alembic does not exist.** Use the repo's existing pattern: `Base.metadata.create_all` + raw startup DDL in `main.py`. Drop every "Alembic migration" reference.
6. **Tailnet-source-IP middleware** shared dependency in `app/api/_deps.py`, reused by federation, voice-edge, and any future inter-instance channel.
7. **`sync.sh` exclude list** must add `edge/`, `**/*.gguf`, `**/*.bin`, vision/ASR model directories before voice-edge or vision lands.

### Security findings

- **Critical:** Phase A unified pending queue must enforce C3 confirmation-hijack guard at the helper layer (channel-scoped key + monotonic seq + quote-in-confirm). State-diff dispatcher and vision lane must not bypass.
- **Critical:** Phase D vision OCR text must pass through the shared sanitiser **before** `bus.ingest`. Without it, an OCR'd `[ACTION:DELETE_BOARD ...]` becomes a vision-borne injection.
- **Critical:** Phase D synthetic format `[Image: <caption>]\n<user text>` is a confused-deputy. Wrap caption in `<<<UNTRUSTED_VISION>>>...<<<END_UNTRUSTED>>>` (matches `ambient_capture_routing.md` §17 C1 pattern).
- **High:** Phase E cross-feature glue paths (capture -> state-diff, vision -> capture, ambient -> vision) re-apply sanitiser at every hop; no transitive trust.
- **High:** Per-rule and per-source-adapter trigger caps (not just a global cap).
- **Medium:** State-diff text rendered to TTS (Phase E voice delivery) must be sanitised first -- spoken self-instruction is a real injection vector if a mic is open.
- **Medium:** Channel parity (rule 21) currently lists Telegram/WhatsApp/dashboard. Extend to voice-edge from Phase A onward and update agents.md.
- **Low:** Vision Phase D `tmpfs only` mode 0700 + FS audit test.

### Backend findings

- Phase A wording "promote sentinel-wrapping into shared helpers" replaced with "consolidate" -- the helpers exist in `services/ambient_capture/sanitiser.py` and `services/agent_actions.py` today; Phase A relocates them to `services/security/sanitisers.py`.
- Phase A "one Redis namespace" claim softened: `SENSITIVE_ACTIONS` is an in-memory list today; v1 keeps two stores behind one dashboard view.
- Phase C must register the quiet-moment scheduler hook concretely in `tasks/scheduler.py` and reference `services/follow_up.py` as the precedent for delivery scheduling.
- Phase D status corrected: `services/vision.py` already exists; phase wires it into channels rather than rebuilding.
- `morning.py` is one of several briefings (`weekly.py`, `monthly.py`, `quarterly.py`, `yearly.py`); Phase C names all consumers of folded triggers explicitly.

### Infra findings

- `llm-vision` compose service spec needed: profile gate, `mem_limit`/`cpus`, internal-only network (no Traefik label -- preserves rule 15), named `vision_models` volume, no public route.
- On `micro` profile, vision is OFF by default OR replaces the text LLM. Concurrent text + vision llama.cpp on Pi 5 8 GB OOMs.
- Traefik upload cap middleware (e.g. `maxbody`) on image-upload routes to prevent disk-fill DoS via WhatsApp media.
- BUILD.md gains a numbered "Enable vision" phase (env vars, model download, profile selection, RAM expectations).

### QA findings

- Phase E DoD "useful proactive insights without spam" replaced by recorded-fixture false-positive rate target.
- Phase D vision tests mock at the `services/vision.py` boundary; multi-GB model artifacts are not pulled in CI.
- Phase A baseline test set enumerated as `tests/test_ambient_capture_security.py` plus a state-diff and vision injection class added to `tests/test_security_prompt_injection.py` (target: +20 cases minimum).
- Phase B failure-injection harness named explicitly (rollback messaging reliability).
- Combinatorial trigger matrix bounded via fixture-recorded scenarios, not exhaustive enumeration.
- Per-tier test policy (per-PR vs nightly vs hardware-loop) documented per phase.

### Performance findings

- Adapter polling tiered: Planka 120 s, calendar 300 s, email IDLE-push, hardware 60 s, conversation event-driven. Redis hash-only diff (`HSET ambient:planka:<board> hash <sha1>`) so unchanged boards skip card fan-out.
- Tier B card-title embedding cache in Redis (`cap:cardvec:<id>`, float16 ~770 B, batched 32-at-a-time on miss, BM25 pre-filter to top 50 before vectorising).
- Split llama.cpp into `llm-text:8080` and `llm-vision:8081` containers. Single LLM scheduler with priority lanes: `voice > interactive_text > capture_tiebreaker > ambient_trigger > vision`.
- Pending queue: TTL 30 min default, hard cap 200 per channel via `LTRIM`, gzipped JSON snapshot storage.
- Quiet-moment detection uses a Redis `last_user_msg_ts` key, not Postgres scan.
- All three new dashboard components (AmbientWidget, FederationManager, VoicePodsManager) lazy-load via `IntersectionObserver`; `vite.config.ts` `manualChunks` puts each in its own chunk.

### Dashboard / a11y / i18n findings

- `AmbientWidget.ts` mandatory boilerplate enumerated in Phase E above.
- Cooldown timers and severity colour coding pair with text/icon (forced-colors safety, rule 12 colour independence).
- Severity colours use `var(--accent-primary, ...)` chains, never hardcoded hex.
- `pytest tests/test_i18n_coverage.py -v` is an explicit DoD line in Phases B and E.
- "11 languages" replaced with "all populated language dicts under `services/i18n/`; `_EN` and `_DE` parity is the CI-blocking gate".

### AI / persona / crew findings

- New `agent-rules.md` section: **Proactive Output Voice** -- ambient deliveries are neutral-Z, in user's locked language, no crew persona, max 2 sentences for non-briefing pings, no rhetorical questions.
- New `agent-rules.md` section: **Ambient Suppression** -- if the same insight is about to appear in a scheduled briefing within 30 min, the ambient delivery is suppressed silently.
- System-prompt prefix for ambient deliveries: `[AMBIENT_TRIGGER kind=<rule_id> priority=<n>]` so the response generator matches tone.
- `crews.yaml` schema additions (under `CrewConfig`): `ambient_eligible`, `ambient_priority`, `ambient_suppress_window_min`, `ambient_max_per_day`, `voice_channel_allowed`, `federation_consume`, `persona_hash`, `briefing_fold_strategy: "absorb" | "replace" | "skip"`. Prerequisite for Phase B.
- Rhetorical-question rule extends to proactive output: "send me the whiteboard photo when you're done" violates the spirit of one-question-one-answer; route via the dashboard prompt instead.

### Cross-artifact consistency

- Phasing taxonomies (Phase 1-5 / Epoch 1-3 / A-E / F0-F5 / V0-V5) need a mapping table in this artifact's body before Phase B ships. Tracked as a follow-up artifact.
- The "supersedes the standalone scope of `ambient_intelligence.md`" claim resolved: this roadmap is the authoritative master plan; `ambient_intelligence.md` becomes the state-diff implementation reference (its own header gains a `Superseded-By:` line in a follow-up edit).
- README "11 languages" claim vs `_EN`+`_DE` CI reality: tightened DoDs above.
- Hardware-profile labels (`micro/standard/performance` vs `Tier A/B/C`): reconciled by the `HARDWARE_PROFILE` enum prerequisite.

