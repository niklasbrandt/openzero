# Semantic Routing + Multi-Crew Synthesis -- Design Spec

Status: draft, awaiting operator sign-off before implementation.
Supersedes the keyword cascade in `services/crews.py::resolve_active_crew(s)`
and the `keywords` / `keywords_i18n` fields in `agent/crews.yaml`.

Author: ai-engineer mode. Implementation owner: backend agent.

---

## 0. Design Principles (non-negotiable)

1. **Substrate, not surface.** Routing is derived from each crew's identity
   (`name + description + characters`). Operator never tags, classifies, or
   maintains keyword lists.
2. **Language-agnostic by construction.** Embeddings carry semantic intent
   across DE/EN/any future language. No per-language regex tables.
3. **Z is sovereign.** Crews are advisors. Z has the final word, always.
4. **No example-prompt leakage.** Crew profiles are built from declarative
   identity fields only -- never from example prompts, sample outputs, or
   anything the LLM authored (operator's anti-hallucination constraint).
5. **No preamble, no recap.** Crew drafts and Z syntheses speak directly,
   matching the user's register and language.

---

## 1. Routing Algorithm

Single inbound message `M` with `lang_hint` (user's configured locale), the
last `H` history turns, and the channel.

```
route(M, history, lang, channel):

  # ---- L0: hard bypasses (kept from current router.py) ----
  if FAST_PATH(M):                 return Z_DIRECT  (greeting/ack)
  if AUDIT_INTENT(M):              return AUDIT_DETERMINISTIC
  if RECALL_HISTORY(M):            return RECALL_DETERMINISTIC
  if STRUCTURAL_INTENT(M, lang):   return Z_DIRECT  (intent_router handles it)
  if OPERATIONAL_QUERY(M):         return Z_DIRECT  (was-it-done questions)

  # ---- L1: explicit crew naming (operator override) ----
  named = detect_explicit_mention(M, registry)
      pattern: /\b(?:hey|hi|hallo|ok|@)?\s*(crew_id|crew_short_name)\s*(?:crew)?\b/i
      where crew_short_name is registry-supplied alias set
              (e.g. "nutrition"->Recipe, "rezept", "kueche", "fitness", "sport")
  if named:                        return PRIMARY=named, SECONDARY=[]

  # ---- L2: semantic match ----
  q = embed(M)                                            # 384-dim MiniLM
  scores = sorted([(cid, cosine(q, profile_vec[cid]))
                   for cid in chat_routable_crews()],
                  desc by score)

  # Continuity bias: +0.05 to the crew whose attribution appears in
  # the immediately preceding Z reply IF M contains follow-up signals
  # (it, das, again, nochmal, weiter, more).
  scores = apply_continuity_bias(scores, history, M)

  top, second, third = scores[0:3]

  if top.score < T_MATCH (=0.55):           return Z_DIRECT  (no crew good enough)

  primary = top.cid
  panel   = [primary]
  for c in (second, third):
      if c.score >= T_OPT_IN (=0.48)
         and (top.score - c.score) <= GAP (=0.08)
         and not in registry[primary].panel_exclude:
          panel.append(c.cid)
  panel = panel[:MAX_CREWS (=3)]

  # ---- L3: debate flag ----
  debate = (
      len(panel) >= 2
      and contains_decision_verb(M)   # should / shall I / soll ich / lohnt sich
      and crew_domains_diverge(panel) # e.g. fitness + recipe + life on same Q
  )

  return PRIMARY=primary, PANEL=panel, DEBATE=debate
```

`chat_routable_crews()` = registry minus crews with `routing_disabled: true`
(scheduled-only or substrate-internal crews, see section 7).

`detect_explicit_mention` runs on lowercased text, against `id` plus a small
registry-curated alias list per crew. No fuzzy matching -- explicit naming
must be unambiguous; if the alias does not match, we fall through to
semantic scoring (which will usually still pick the same crew).

---

## 2. Embedding Strategy

- **Model:** reuse `sentence-transformers/all-MiniLM-L6-v2` already loaded by
  `services/memory.py::get_embedder()`. 384-dim, ~22 MB, already in the
  container, no extra dependency. Multilingual quality is adequate for DE/EN
  routing (we measure against a corpus of held-out messages -- see section 10).
  If a future audit shows DE recall <0.85, swap to
  `paraphrase-multilingual-MiniLM-L12-v2` behind the same `encode_async()`
  call. The dimension change is the only migration cost (recompute profiles).
- **Profile text per crew** (deterministic, no LLM call):

  ```
  {name}. {description}. Characters: {char1.name} - {char1.role}; {char2.name} - {char2.role}; ...
  ```

  Empty / missing fields are skipped. No instructions, no example prompts,
  no agent-rules. Pure identity surface.
- **Cache:** `crew_registry._profile_vectors: dict[str, np.ndarray]`. Built
  on `CrewRegistry.load()` -- replaces the current `_precache_keywords`
  step. Rebuilt on every YAML reload (the same hook that triggers
  `_compute_panel_candidates`). Vectors live in process memory; no Qdrant
  collection -- ~30 crews x 384 floats is trivial.
- **Latency budget per inbound message:**
  - Embedding `M`: ~6 ms on CPU (MiniLM, single sentence).
  - Cosine vs 30 profiles: <1 ms (numpy dot product).
  - Total routing overhead: <10 ms. Well inside the existing
    `ResponseBudget` headroom.
- **Fallback if embedder unavailable** (Qdrant container down, ST import
  fails): routing returns `Z_DIRECT` with a one-line warning logged once
  per minute. We do NOT fall back to keyword routing -- that path is being
  deleted. Z handles every message directly until the embedder recovers.
  Operator visibility via `/health/embedder`.

---

## 3. Thresholds (concrete defaults, with justification)

| Constant      | Value | Meaning                                                | Why this value                                                                |
|---------------|-------|--------------------------------------------------------|-------------------------------------------------------------------------------|
| `T_MATCH`     | 0.55  | Minimum cosine for the top crew to engage at all       | MiniLM "clearly on-topic" floor in our domain probes; below this Z is better. |
| `T_OPT_IN`    | 0.48  | Minimum cosine for a secondary crew to join the panel  | Permits "fitness + recipe" overlap on meal-timing questions without noise.    |
| `GAP`         | 0.08  | Max gap between top and a co-opting secondary          | Prevents a clearly-dominant crew (0.78) being diluted by a tangent (0.50).    |
| `MAX_CREWS`   | 3     | Hard cap on panel size                                 | 4+ produces wall-of-text; 3 already rare in practice.                         |
| `CONT_BIAS`   | +0.05 | Boost on previous crew when follow-up signals present  | Smaller than `GAP`, so it cannot override a clearly better new domain.        |
| `DEBATE_GAP`  | <0.06 | Two panel crews must be within this gap to debate      | Forces parity; one dominant crew = synthesis, not debate.                     |

These are starting values. The eval harness in section 10 produces a
`config.yaml` block so the operator can tune without a code change:

```yaml
semantic_routing:
  t_match: 0.55
  t_opt_in: 0.48
  gap: 0.08
  max_crews: 3
  continuity_bias: 0.05
  debate_gap: 0.06
```

---

## 4. Multi-Crew Execution

- **Parallel.** Each panel crew runs concurrently via `asyncio.gather`.
  Serial would compound latency (each crew is a full LLM call, ~1.5-4 s
  local). The 3-crew cap keeps GPU contention manageable on single-peer
  deployments.
- **Per-crew token budget.** Hard cap of **180 output tokens per crew**
  (roughly 2-4 natural-prose sentences). Enforced both via prompt
  (`max 4 sentences`) and `max_tokens` on the LLM request. Total panel
  spend: ~540 tokens -> Z then has ~1500 tokens left in the synthesis
  call inside the existing per-response ceiling.
- **Cross-awareness prompt injection** (delivered to every panel crew):

  ```
  You are <crew.name>.
  This message is being answered by a panel of crews. The other crews
  contributing in parallel are: <other_crew.names>.
  Cover ONLY your own domain. Do not speak for the others.
  Z will merge all drafts into one reply -- do not greet, do not recap
  the question, do not repeat shared context.
  Answer in the user's language (<lang>).
  Maximum 4 sentences. Direct, natural prose, no bullet headers.
  If your domain has nothing useful to add, output the single token: SKIP.
  ```

  `SKIP` outputs are dropped before synthesis -- prevents forced filler
  when a crew opted in on a borderline semantic score.
- **No ACTION tags from panel crews** while in multi-crew mode. ACTION
  emission is suspended for panel members; only single-crew runs may emit
  Planka tags. Rationale: action attribution becomes ambiguous when three
  crews speak, and Z's synthesis pass cannot reliably preserve tag
  positioning. Panel crews still persist their domain output via the
  existing crew-board mechanism (background, after synthesis returns).
- **Streaming.** Panel crews stream into hidden buffers; the user sees
  only Z's synthesis stream. A status line ("Fitness and Recipe weighing
  in...") is sent via `status_callback` while panels run.

---

## 5. Z Synthesis Prompt

Triggered after all panel drafts return (or after a single crew returns,
to enforce the no-preamble style globally).

```
You are Z. Below are <N> domain notes from your crews about the user's
message. Merge them into ONE cohesive reply that honours the user's
long-term context and current session.

User message:
<M>

Crew notes:
[Recipe] <draft_1>
[Fitness] <draft_2>
[Life]   <draft_3>

Long-term context (top relevant memories):
<memory_snippets>

Recent session (last 6 turns):
<short_history>

Rules:
- Respond in the user's language: <lang>.
- No preamble. No "Here is what I found". No restating the question.
- Natural prose. You MAY use a section-prefix style when domains are
  genuinely distinct ("Fitness: ...\n\nRecipe: ..."), but prefer a
  woven paragraph when the domains interact.
- If two crews disagree, name the disagreement in one sentence, then
  give YOUR call with a one-line reason rooted in the user's stated
  goals or constraints.
- Tone: match the user. Concise. Substantive. No filler.
- Do not name the crews unless using the section-prefix style.
- Hard limit: 6 sentences total unless the user explicitly asked for depth.
```

The "long-term context" injection reuses the existing memory retrieval
path (`services/memory.search`) keyed on `M`. The "recent session"
slice is the last 6 turns, already maintained per channel.

---

## 6. Workspace + Signal Interpreter Absorption into Z Core

Both crews collapse into always-on Z behaviours, not separately routable
crews. They get `routing_disabled: true` in YAML and their behaviour
moves into `services/z_core.py` (new module).

### 6.1 `workspace` -> Z's structural skills

The workspace crew's value is its ACTION-tag emission for
PROJECT/BOARD/LIST/CARD construction. That is **already** baked into Z's
`ACTION_TAG_DOCS` (see `services/llm.py`). The crew is redundant.

Migration:
- Move the workspace crew's `instructions` block (the methodology hints:
  Kanban vs Scrum vs GTD column choice, "blueprint topology" advice)
  into `agent-rules.md` under a new `## Workspace Construction Heuristics`
  section. Z reads agent-rules in its system prompt; it now reasons
  about workspace structure directly.
- Delete the crew entry from `crews.yaml`.
- Leave the `intent_router.py` structural verbs in place -- they remain
  Z's deterministic fast path for explicit "create board X" commands.
- No new ACTION tag wiring needed; Z already has CREATE_PROJECT,
  CREATE_BOARD, CREATE_LIST, CREATE_TASK.

### 6.2 `signal_interpreter` -> Z's HITL proposal mode

The signal interpreter exists to turn ambient events into single,
operator-confirmable proposals. This is **how Z should behave by default**
on every ambient signal -- not a separate crew the router has to find.

Migration:
- Move the signal interpreter's INTERPRETATION RULES and OUTPUT FORMAT
  into `agent-rules.md` under `## Ambient Signal Handling`. Z applies this
  format automatically whenever the inbound payload carries
  `source = ambient` (already a field on the message bus envelope).
- Delete the crew entry from `crews.yaml`.
- The HITL confirmation flow (proposal -> user confirms -> action
  executes) is already implemented in the pending-actions pipeline.
  No new code -- just stop routing to a crew and let Z follow the
  inlined rules.

### 6.3 Resulting architecture

`z_core.py` exports two pure functions used by `router.py`:

- `z_core.build_system_prompt(payload, context)` -- injects the
  workspace heuristics and ambient-signal rules conditionally based on
  payload type, alongside the existing personality / agent-rules block.
- `z_core.is_ambient_signal(payload)` -- triggers the HITL output
  format for non-interactive signals.

This is *inline behaviour*, not tool-style sub-skills. Tool-style would
add a routing decision Z has to make per turn -- exactly the kind of
surface we just deleted.

---

## 7. Crew YAML Schema Changes

### Removed fields

- `keywords` -- delete from every crew entry.
- `keywords_i18n` -- delete from every crew entry.
- `panel_exclude` -- delete; replaced by semantic gating (if two crews
  routinely co-fire when they shouldn't, raise `T_OPT_IN` for that pair
  via a new `coactivation_exclude` registry, but ship without it).

### Required fields (unchanged)

- `id`, `name`, `description`, `group`, `type`, `instructions`,
  `characters`.

### New optional fields

| Field                | Type    | Purpose                                                                              |
|----------------------|---------|--------------------------------------------------------------------------------------|
| `routing_disabled`   | bool    | If true, crew runs only on schedule -- never routable from chat. Default false.      |
| `aliases`            | list    | Short names the user might say ("rezept", "sport"). Used by explicit-mention path.   |
| `tone_hint`          | string  | Free-text register hint passed to the per-crew prompt ("professional coach, warm").  |
| `coach_mode`         | bool    | When true, crew may ask one clarifying question before answering. Default false.     |
| `min_semantic_score` | float   | Per-crew override of `T_MATCH`. Use sparingly -- only when a domain bleeds.          |

### Schema migration

Update `docs/schemas/crews.schema.json`: mark `keywords` and
`keywords_i18n` as deprecated (still parsed for one release, ignored at
runtime) so existing operator YAMLs keep loading. Drop them entirely in
the release after.

---

## 8. Crew Shortlist -- Keep / Merge / Cut

Opinionated. Based on the operator's stated direction (Recipe + Fitness
as proactive coaches, Z absorbing workspace/signal/general).

### KEEP (chat-routable, semantic profile worth its weight)

- `research`        -- deep-dive, contrarian audits. Distinct domain.
- `recipe`          -- renamed from `nutrition`. `coach_mode: true`,
                       `tone_hint: "precise culinary coach, metric-first"`.
- `fitness`         -- `coach_mode: true`,
                       `tone_hint: "adaptive performance coach, no pep talk"`.
- `coach`           -- KEEP and FIX. Currently dead because keywords were
                       weak. Under semantic routing it will fire on goal
                       statements, avoidance, time pressure, value framing.
                       Rewrite `description` to load the embedding with
                       those concepts: *"Surfaces when the user expresses
                       goals, plans, value conflicts, time pressure, or
                       avoidance. Audits alignment between stated vision
                       and current action."*
- `health`          -- biometric / wellbeing. Distinct from fitness (data
                       vs programming).
- `life`            -- separation / reconstruction. Personal, high-stakes.
- `dependents`      -- child development. Highly specific.
- `residence`       -- IoT / utilities. Specific.
- `travels`         -- trip logistics. Specific.
- `security`        -- OPSEC. Specific.
- `meeting`         -- transcription / action extraction. Specific.
- `legal`           -- contract risk. Specific.
- `idea`            -- predator-lens. Specific.
- `market-intel`    -- competitive. Specific.
- `leads`           -- CRM funnel. Specific.
- `content`         -- brand voice. Specific.
- `lessons`         -- pedagogy. Specific.
- `edu-communication` -- parent liaison. Specific.

### KEEP but `routing_disabled: true` (substrate-internal, scheduled only)

- `contradiction_detector` -- runs on memory ingestion, not user chat.
- `domain_inference`       -- runs on the ATLAS template hint pipeline.

### CUT (operator's instinct is right)

- `general`  -- redundant. Z is the general assistant by definition.
- `flow`     -- the deep-work scheduling output is bullet-list noise that
                never fires from chat. Move its weekly briefing duty into
                a scheduled job (no crew wrapper needed) and delete the
                routable entry. If operator disagrees, gate it behind
                `routing_disabled: true` and keep only the weekly run.
- `workspace`          -- absorbed into Z core (section 6.1).
- `signal_interpreter` -- absorbed into Z core (section 6.2).

### Result

22 crews now, ~17 chat-routable after the cut. Cleaner semantic space ->
fewer co-activation collisions, sharper top-1 scores.

---

## 9. Debate Mode -- Edge Cases

Debate is *valuable* on:
- "Should I run tomorrow morning or skip for sleep?" -> fitness vs health.
- "Worth signing this client at this rate?" -> leads vs life vs idea.
- "Move to Lisbon next year?" -> travels vs life vs residence.

Debate becomes *noise* on:
- Information requests ("how many calories in 200g chicken?").
- Single-step tasks ("create a board called Q3").
- Reflective check-ins ("I feel tired").

### Rule: DEBATE OFF when ANY of:

1. `M` lacks a decision verb in the user's language. Decision-verb
   lexicon (small, multilingual, maintained alongside `intent_router`'s
   structural verbs): EN {should, shall, ought, worth, better, vs,
   versus, or}, DE {soll, sollte, lohnt, besser, oder, statt}, ES {debo,
   deber\u00eda, mejor, o}, FR {dois, devrais, mieux, ou}.
2. Top two panel scores diverge by more than `DEBATE_GAP` (0.06). One
   crew clearly owns the question.
3. The message is shorter than 5 tokens (no substance to debate).
4. The user explicitly asked for a single recommendation ("just tell me
   what to do", "kurz und knapp").

When debate is OFF, panel still runs but Z synthesizes a single
recommendation without surfacing internal disagreement.

When debate is ON, the Z synthesis prompt switches to a debate-aware
variant: it names the tension in one sentence, gives Z's verdict, and
anchors the verdict in a user-context fact (from memory or recent
session).

---

## 10. Failure Modes + Mitigations

| Failure                                        | Mitigation                                                                                                                                                      |
|------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Embedder service down (ST import, OOM, Qdrant) | Routing returns `Z_DIRECT` for every message. Log once/min, surface in `/health/embedder`. No keyword fallback -- that path is deleted.                          |
| All scores below `T_MATCH`                     | Z handles directly. This is the *correct* outcome, not a failure. Increment a metric (`router.no_match_total`) so we can spot domain gaps.                      |
| Two crews tie within `GAP` but `< T_OPT_IN`    | Take only the top one. Don't drag in a sub-threshold tie just because it's close.                                                                               |
| Rare language (e.g. Polish) user message       | MiniLM has cross-lingual signal but degrades. Mitigation: if `lang_hint` is outside {en,de,fr,es,it,pt,nl}, lower `T_MATCH` by 0.05 (the embedder is noisier; we accept more false positives over routing nothing). |
| Very short message ("ja", "ok", "thanks")      | Handled before routing by the existing FAST_PATH bypass. Never reaches embedding.                                                                               |
| User explicitly names a non-existent crew      | `detect_explicit_mention` fails silently and falls through to semantic. Z's reply may include a one-liner "no crew called X -- I can route to Recipe or Fitness, which fits?" only when score < `T_MATCH`. Never when semantic still picks something good. |
| Adversarial embedding-confusing message        | The embedder runs on the raw user text (already capped at 500 chars upstream by `_MAX_RE_INPUT`-equivalent). No prompt-injection vector via routing because the embedding is never fed back to the LLM. The crew prompt is constructed from registry data, not user text. |
| Profile vector cache stale after YAML reload   | `CrewRegistry.load()` rebuilds vectors before swapping the registry pointer. Atomic swap avoids partial-cache reads.                                            |
| Eval drift over time                           | Ship a held-out eval set in `tests/test_semantic_routing.py`: 80 messages (40 EN, 40 DE), each labelled with expected primary crew. Fails CI if top-1 accuracy < 0.80 or any message routes to a deleted crew. |

---

## 11. Implementation Order (for the backend agent, not part of the spec)

1. Add `services/z_core.py`; inline workspace + signal-interpreter rules
   into `agent-rules.md`; delete those two crews from YAML.
2. Add embedding profile cache to `CrewRegistry`; expose
   `score_crews_for(text, lang) -> list[(cid, score)]`.
3. Rewrite `resolve_active_crews` to use the algorithm in section 1.
   Keep `resolve_active_crew` as a thin wrapper returning `panel[0]` for
   any caller still on the single-crew API.
4. Implement parallel panel execution and Z synthesis in
   `router.py::route_message_stream`, behind a `SEMANTIC_ROUTING_ENABLED`
   flag for one release so we can A/B against keyword routing.
5. Delete `keywords` / `keywords_i18n` from every crew in
   `agent.example/crews.yaml` and `agent/crews.yaml`; cut `general`,
   `flow`. Apply schema deprecation note.
6. Update `coach` description per section 8.
7. Add `tests/test_semantic_routing.py` eval harness.
8. Flip the flag, monitor for one week, then delete the keyword path
   and the deprecated YAML fields.

---

## 12. Open Questions for Operator

1. **`flow` total cut vs scheduled-only.** Recommend full cut. Confirm?
2. **`coach` `coach_mode: true`** -- allowed to ask one clarifying
   question when the goal statement is vague? Or always answer directly?
3. **Debate visibility** -- when Z arbitrates a disagreement, surface
   the disagreement to the user ("Fitness says A, Health says B; I'd go
   with A because ...") or hide it and just give the verdict?
   Recommendation: surface it briefly. The visible reasoning is part of
   the substrate's value.
4. **`recipe` rename** -- confirm `id: "recipe"` and that we migrate
   existing Planka board `Nutrition` -> `Recipe` (or keep board name
   stable for continuity).
