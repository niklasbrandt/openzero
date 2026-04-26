# Voice-First Ambient Device (Voice-Edge Pod)

> Architectural plan for an always-on, edge-local voice surface for openZero.
> Status: DRAFT | Author: conductor | Created: 2026-04-26
> Companions: `ambient_intelligence.md`, `ambient_capture_routing.md`, `federated_memory.md`.

---

## 1. Problem Statement

Z is conversational over text and reactive over voice (press-to-record). The next interaction-model shift is ambient voice: glance-free, continuous-listen, wake-word-gated, low-latency. The interaction surface stops being a phone and becomes the room.

Concrete scenario: 07:14, making coffee. "Z, what's on my plate today?" A small device on the kitchen counter pulses gently, transcribes locally, sends text-only over Tailscale to openZero, and Z streams a 12-second spoken briefing back through the device's speaker. No screen touched. The dashboard shows the same conversation under `channel="voice-edge"` with full memory and crew context.

This is also the differentiation play vs Apple Intelligence, Rabbit, and Humane: those are cloud-bound, vendor-locked, and crippled. A self-hosted ambient device with full crew, memory, and action vocabulary access changes the trust equation entirely.

---

## 2. Design Principles

1. Edge-only audio. Wake-word, VAD, and Whisper transcription run locally on the Pi. Only text crosses the network.
2. Tailscale-only transport. The device joins the Tailnet; no public route. Same trust model as the rest of openZero.
3. One channel, full context. The pod is just another channel for the message bus. Memory, crews, action vocabulary, HITL, follow-ups, ambient capture all work unchanged.
4. Channel parity (agents.md rule 21). Every channel-touching fix lands for voice-edge too. No degraded clone of the agent.
5. No always-recording cloud. Wake word triggers a bounded recording window. Outside that window, audio is processed in a rolling local buffer that is never persisted.
6. Glance-free first, screen-optional. Small visual feedback ring; never a primary screen. The dashboard remains the rich surface.
7. Reproducible hardware. Build instructions target a known, available BOM. No bespoke PCB in v1.

---

## 3. Architecture Overview

```
+------------------ Edge device (kitchen / desk / bedside) ------------------+
|                                                                            |
|  Mic array  ->  VAD  ->  Wake word detector  ->  Capture window           |
|                              (OpenWakeWord)        (max 12s, VAD-cut)     |
|                                                                            |
|                       |                                                    |
|                       v                                                    |
|                 Local Whisper (faster-whisper, INT8)                       |
|                       |                                                    |
|                       v                                                    |
|                 Edge-side intent prefilter (offline canned commands)       |
|                       |                                                    |
|                       v                                                    |
|                 Voice channel client  ----[Tailscale, bearer]--->  openZero|
|                       ^                                              |     |
|                       |                                              v     |
|                       +-----<--- streaming TTS audio chunks <--- bus.push  |
|                                                                            |
|  LED ring + small speaker (state, partial transcript, response)            |
+----------------------------------------------------------------------------+

                                   |
                                   v
+-------------------- openZero VPS / homelab ---------------------+
|                                                                  |
|   /api/voice/session  (new)        ----- channel="voice-edge"   |
|        SSE: text in, TTS audio chunks out                       |
|                                                                  |
|   message_bus.ingest()  -> router -> crews -> action vocab      |
|   bus.push_all()        -> Telegram / WhatsApp / Dashboard / Voice
|                                                                  |
+------------------------------------------------------------------+
```

Two new components:

- Edge firmware: lives in a sibling repo (`openzero-voice-pod`) or a `git subtree` under `edge/voice-pod/`. **Not part of `docker-compose.yml` and not synced to the VPS by `sync.sh`.** `sync.sh`'s exclude list adds `edge/`, `**/*.gguf`, `**/*.bin`, and ASR/TTS model directories before this artifact ships.
- Voice channel handler (`src/backend/app/api/voice_edge.py`): an SSE endpoint that ingests transcribed text into the existing message bus and streams TTS chunks back. Thin channel adapter, no new agent logic.

---

## 4. Hardware Reference Build

| Component | Choice | Why |
|---|---|---|
| Compute | Raspberry Pi 5, 8 GB | Whisper-small INT8 + OpenWakeWord; mature OS support |
| Microphone | ReSpeaker 4-Mic Linear Array v2 | Beamforming, AEC, far-field; well-supported on Linux |
| Speaker | USB powered speaker (3-5 W) | Cheap, replaceable, no driver work |
| Visual | NeoPixel ring (12 LEDs) on the array | State + partial transcript hints |
| Network | Built-in Wi-Fi + optional Ethernet | Tailscale joins on first boot |
| Power | USB-C 5V/5A | Stable under Whisper inference spikes |
| Enclosure | Off-the-shelf Pi 5 case with mic vent | No custom CAD in v1 |

BOM target: under EUR 200 per pod. Multi-pod households (kitchen + study + bedside) become realistic.

Out of v1 scope: custom PCB, battery, far-field beamforming tuning beyond the array's defaults, multi-room audio routing.

---

## 5. Edge Software Stack

A new directory at the repo root: `edge/voice-pod/`. Its own deployable unit, not part of docker-compose.

```
edge/voice-pod/
	pyproject.toml
	systemd/
		oz-voice-pod.service
	app/
		main.py            # async loop: capture -> wake -> ASR -> session
		audio.py           # ALSA capture + ring buffer + VAD
		wake.py            # OpenWakeWord wrapper, configurable model path
		asr.py             # faster-whisper transcription
		session.py         # SSE client to /api/voice/session
		tts_player.py      # streaming Opus/PCM playback
		ring.py            # NeoPixel state machine
		config.py          # loads /etc/oz-voice-pod/config.yaml
		fallback.py        # offline canned commands + status reporting
		health.py          # local /healthz endpoint for the dashboard
	scripts/
		install.sh         # one-shot installer (apt deps, venv, systemd)
		flash-image.sh     # builds a turnkey Pi image (optional)
	tests/
		test_wake.py
		test_session_protocol.py
		test_fallback.py
```

### 5.1 Audio pipeline

- ALSA capture at 16 kHz mono into a 5-second rolling ring buffer.
- WebRTC VAD gates the wake-word detector (skip silence, save CPU).
- OpenWakeWord with a configurable wake word (default: "Hey Z"). Custom wake words via `.tflite` drops in `/etc/oz-voice-pod/wakewords/`.
- On wake: capture window opens up to 12 seconds, ends on 1.2 seconds of silence (VAD).

### 5.2 ASR

- `faster-whisper` with `tiny.en` INT8 by default on Pi 5; `small.en` is opt-in for desk-class pods (`small.en` INT8 on Pi 5 is 1.0-1.6× real-time on 6 s clips, which cannot meet the sub-1.5 s ASR target). Streaming mode (process while user speaks), `beam_size=1`, `vad_filter=True`, `condition_on_previous_text=False`. Pre-warm in systemd `ExecStartPre`.
- Models live under `/var/lib/oz-voice-pod/models/`, downloaded once at install. Install script verifies SHA-256 against a pinned manifest and uses TLS-pinned download URLs.
- Transcription is fully local. The transcript is the only thing sent over the network.
- `services/voice.py` (the existing Whisper transcription wrapper) is **not** used by the voice-edge channel -- ASR is fully edge-local; the backend never receives audio for transcription.

### 5.3 Session protocol

The pod opens an HTTP/2 + SSE connection to `/api/voice/session`. The `pod_id` and bearer token are sent in headers (never query string -- query strings are logged by Traefik and would leak the pod identity into access logs):

```
Authorization: Bearer <pod-token>
X-OZ-Pod-Id: <pod_id>
X-OZ-Wake-Nonce: <backend-issued, monotonic per session>
```

The backend issues a session-scoped wake-nonce on session open and increments it per utterance; pods echo it on every utterance envelope. Utterances are bound to (`pod_id`, `wake_nonce`) -- a compromised host on the Tailnet cannot submit utterances claiming an arbitrary `pod_id` without the nonce.

Utterance envelope:

```json
{
	"type": "utterance",
	"transcript": "what is on my plate today",
	"lang": "en",
	"confidence": 0.91,
	"wake_nonce": 42,
	"captured_at": "2026-04-26T07:14:33Z"
}
```

The `confidence` field is **pod-asserted and advisory only**. The backend never gates authorisation on it.

The backend replies with typed events:

| Event | Payload | Pod behaviour |
|---|---|---|
| `state` | `{state: "thinking"\|"speaking"\|"idle"}` | LED ring colour |
| `text_delta` | `{chunk: "..."}` | Optional on-device caption (deferred to v2) |
| `tts_chunk` | base64 PCM/Opus audio | Append to playback queue |
| `tts_end` | `{}` | Drain and return to idle |
| `action` | `{kind: "led_blink", ...}` | Visual confirmation hooks |
| `error` | `{code, message_key, lang}` | Localised spoken error via cached canned audio |

Versioned via `oz-voice-pod-protocol/v1`.

### 5.4 Visual state machine

The LED ring is the only feedback when the agent is silent.

| State | Pattern |
|---|---|
| Idle | All off, single dim breathing dot |
| Listening (post-wake) | Soft accent-colour pulse |
| Thinking | Slow rotating arc |
| Speaking | Audio-level reactive band |
| HITL pending | Two amber dots opposite each other |
| Error | Three short red blinks plus spoken error key |
| Offline (no Tailscale) | Slow red breathing |

Colours come from the same HSLA tokens as the dashboard. The pod fetches the active accent and its H/S/L primitives via `GET /api/voice/pods/{id}/theme` (returns `{accent: {h,s,l}, secondary: {h,s,l}, tertiary: {h,s,l}}`) on session open and on the `theme.changed` SSE event piggybacked on the existing voice session (no separate push channel, no separate auth surface). The pod applies the canonical `hslToRgb` helper documented in `docs/artifacts/DESIGN.md` §2.4 to drive 8-bit NeoPixel values. Theme persistence is server-side (a prerequisite -- today the dashboard stores theme browser-locally only).

### 5.5 Offline fallback

When Tailscale is down or the backend is unreachable:

- Wake word still works locally.
- A short offline canned-command set (configurable, max 10 commands) executes via local intent matching: "what's the time", "are you there", "reconnect now". Rate-limited to 3/min per pod; minimum confidence floor (0.85) required, so TV audio cannot trigger `reconnect now` on loop.
- Status announcements via cached canned audio in **the pod's configured language plus English** as v1 fallback; if cached audio is missing in the user's locked language the pod stays silent and LED-blinks rather than speaking the wrong language. Phase V4 expands to all populated language dicts.

### 5.6 Privacy posture

- No raw audio written to disk except a rolling 60-second debug ring buffer in tmpfs, disabled by default. Pod refuses to start if `/var/lib/oz-voice-pod/debug` is on a non-tmpfs mount and `debug_audio_ring=true` (filesystem-audit test in CI).
- Wake-word detector activations are not logged.
- Captured audio is held in memory for the Whisper call only; on transcript completion the buffer is zeroed.
- Hardware-friendly mute: `/etc/oz-voice-pod/muted` flag plus a physical GPIO button take precedence; LED ring shows a steady muted indicator that is **visually distinct** from the idle breathing dot (different colour AND pattern, not colour-only); mic closed at the ALSA layer. The mute flag short-circuits the audio pipeline before Whisper is ever invoked (software-observable: PCM read returns silence + no Whisper invocation log entry).
- Pod's local `/healthz` binds `127.0.0.1` only -- never reachable on the LAN.
- Every transcript passes through `services/security/sanitisers.py::_sanitize_for_log` before any error path writes it to logs or Sentry.

---

## 6. Backend Voice Channel

### 6.1 New API surface

```
POST /api/voice/session     SSE
GET  /api/voice/pods        list registered pods
POST /api/voice/pods        register a pod (operator only)
DELETE /api/voice/pods/{id} revoke a pod
GET  /api/voice/pods/{id}/health
```

### 6.2 Pod identity

Per-pod bearer token issued during registration, plus Tailscale ACLs ensuring pods can only reach `/api/voice/*`. Each pod has a stable `pod_id`, a friendly name (`kitchen`, `study`), and an optional location label injected into prompts as low-priority context.

### 6.3 Channel handler

`src/backend/app/api/voice_edge.py` is a thin adapter:

1. Receive utterance JSON.
2. `bus.ingest(channel="voice-edge", text=transcript, conversation_id=pod_id, lang=...)`.
3. Stream the agent's reply through the existing reply pipeline.
4. As text chunks land in `bus.push()`, render through `tts.synthesize_stream()` and emit `tts_chunk` events.
5. On any sensitive action, emit `state="hitl_pending"` plus a localised spoken prompt; confirmations come back as the next utterance from the same pod.

The handler imports nothing crew-specific. It uses the bus, TTS service, and `bus.push_all()` registration only.

### 6.4 TTS streaming

`services/tts.py` today is one-shot (`generate_speech(text) -> bytes`). Streaming is implemented as **sentence-chunked synthesis**: the channel handler splits the LLM stream on punctuation, calls the existing `generate_speech` per sentence, and emits each as a `tts_chunk` event. This avoids a non-trivial upstream protocol change while still meeting the latency budget. Voice and language are pod-scoped.

**TTS sanitiser pass.** Before any text reaches `generate_speech`, the channel handler strips: `[AUDIT:...]` action tags, markdown formatting, raw URLs (replaced with "a link"), parentheticals, and any literal action verbs from the 22-verb × 11-language allowlist (so a Planka card title containing "DELETE" cannot be vocalised as a self-instruction). Output is hard-capped at `VOICE_EDGE_MAX_REPLY_SECONDS` (~30 s by default).

**Adaptive Opus chunk size.** Start at 200 ms frames for low first-byte latency, grow to 400 ms after the first chunk is acknowledged. Audio bypasses JSON SSE wrapping (binary framing on a parallel SSE event type) to avoid base64 inflation.

### 6.5 Channel parity hooks

Per agents.md rule 21 (which is extended to enumerate `voice-edge` alongside Telegram, WhatsApp, and dashboard once this artifact ships):

- Streaming timeout, stall detection, error recovery: same code path as Telegram and WhatsApp.
- HITL pending queue: voice replies use `tr('voice_hitl_prompt', "I'd like to do {action}. Yes or no?")` and accept the next utterance as confirmation, scoped to (`pod_id`, `wake_nonce`) plus 90-second TTL. The HITL store reuses the unified pending-queue Redis namespace (`pending:voice:<pod_id>` prefix), not a parallel implementation.
- Spoken HITL relaxes capture's quote-in-confirm rule (ASR rarely produces verbatim matches): numeric pick ("option two") or yes/no with a re-stated phrase ("say 'confirm delete' to proceed") for sensitive actions. The relaxation is documented; non-sensitive actions still require a quote-or-synonym match.
- Voice does **not** auto-receive `bus.push_all()`. The message bus introduces a channel-class registry (`text` vs `audio`); voice-edge is `audio` and only receives explicitly audio-routable replies.
- The `[AMBIENT_TRIGGER]` system-prompt prefix from the unified ambient roadmap is honoured here too; ambient deliveries route to **one** pod (most-recently-used or operator-elected), never broadcast.
- Long replies cut at ~30 seconds of speech with "want me to continue?" follow-up. Cached canned "one moment" filler plays on chunk-timeout instead of silence.
- `SHARE_SCOPE` and `REVOKE_SHARE` are **dashboard-only** (federation §9.3); voice cannot confirm them. v1 spoken HITL covers `SCHEDULE_CREW`, `LEARN`, `ADD_PERSON` only.

---

## 7. Conversation Model

### 7.1 Wake -> intent -> reply

A single utterance is one full message-bus turn. The pod does not maintain its own thread; the bus does, keyed on `pod_id`.

### 7.2 Multi-turn without re-wake

If the agent's reply ends with a question, the pod auto-opens a follow-up capture window (5 s) without requiring another wake word. SSE event: `{ "type": "expect_followup", "ttl": 5 }`.

**Auto-followup is suppressed when any pending action is in `SENSITIVE_ACTIONS`.** Sensitive HITL confirmations always require a fresh wake word so a hostile caller cannot exploit the open window to confirm an action via shouted bystander noise.

### 7.3 Cross-channel continuity

Everything goes through `bus.ingest()`. Starting a thought on the kitchen pod and continuing on Telegram is supported via the unified `GlobalMessage` view. The pod's `conversation_id` is the same identifier the dashboard already uses for cross-channel grouping.

### 7.4 Barge-in (deferred to v2)

True interruption while Z speaks ("Z, stop") needs AEC tuning the ReSpeaker supports but requires profiling. v1 ships without barge-in; mute button or letting Z finish.

---

## 8. Multi-Pod Households

### 8.1 Arbitration

When wake fires on multiple pods within ~600 ms, each sends a `wake_intent` with measured signal level. The backend uses a Redis `SETNX` on `wake:<utterance_window>` (multi-worker safe) to elect a winner within a 300 ms arbitration window, and tells the others to suppress with `wake_arbitration_lost`. Pods show a "listening" LED **immediately** on local wake (optimistic) and only suppress on `wake_arbitration_lost` to avoid perceived lag. Server-side decision; pods do not coordinate peer-to-peer.

**Threat-model caveat.** Signal level is pod-self-asserted; a compromised pod could claim 1.0 to win arbitration. v1 accepts this in a **single-trusted-operator earshot** threat model. Speaker-ID and trust-scored arbitration are deferred to V5.

**Arbitrated wake conversation continuity.** When the arbitrated winner is not the most-recently-used pod for the same operator, the conversation_id follows the operator (most-recent active conversation within N minutes), not the pod. Otherwise context fragments across rooms.

### 8.2 Per-pod voice and language

Each pod can be configured with its own voice and language. Bedside pod can speak low-energy slow English; kitchen pod fast German. Backend reads pod metadata when synthesising.

**Detected-language wins.** When the user's detected language disagrees with the pod's configured language, the detected language takes precedence (agent-rules.md "Language Lock"); pod-configured voice is the fallback only when detection is uncertain.

### 8.3 Pod-aware context

When a request arrives from `kitchen`, the system prompt gains: `"This message arrived from the 'kitchen' pod."` Z can use this to bias responses without forcing inference.

---

## 9. Security and Trust

### 9.1 Threat model

- Stolen pod: off-Tailnet immediately stops working; revoking the bearer token disables it permanently.
- Hostile speaker in earshot: sensitive actions remain HITL-gated; **same-pod-within-TTL prevents cross-pod hijack only, not same-room bystander hijack**. v1 accepts this as a single-trusted-operator earshot threat model. Mitigations: auto-followup suppression on sensitive pending (§7.2), the spoken "say 'confirm <verb>' to proceed" requirement (§6.5), a physical GPIO confirmation button option for users with bystander concerns, and speaker-ID deferred to V5.
- Bystander privacy: hardware mute cuts mic at the ALSA layer; LED ring shows non-revertible muted state until released; muted indicator is visually distinct from idle (colour AND pattern).
- Wake-word collision: configurable wake word; minimum confidence threshold required.
- Replay of utterances: backend-issued wake-nonce is monotonic per session; backend rejects out-of-order or duplicate nonces.
- Pod-asserted `confidence` is advisory only; backend never gates authorisation on it.

### 9.2 Action vocabulary on voice

Voice gets the same allowlist as every other channel. No `DELETE_*`, no surprise execution. The voice channel handler enforces the allowlist **before** ingest (not just at action-execute time). Sensitive actions confirmable by spoken HITL: `SCHEDULE_CREW`, `LEARN`, `ADD_PERSON`. `SHARE_SCOPE` and `REVOKE_SHARE` are explicitly **not** confirmable via voice -- federation contracts are dashboard-only in v1 (see `federated_memory.md` §9.3).

### 9.3 Audit

Every utterance creates a `GlobalMessage` row tagged with `channel="voice-edge"` and `pod_id`. Dashboard filter for the last N utterances per pod.

---

## 10. Configuration

### 10.1 Backend

`src/backend/app/config.py`:

```python
VOICE_EDGE_ENABLED: bool = False
VOICE_EDGE_TTS_VOICE_DEFAULT: str = "neutral"
VOICE_EDGE_HITL_TTL_S: int = 90                  # mirrors capture pending TTL; if the operator changes the AgentsWidget slider, voice tracks it via the unified pending namespace
VOICE_EDGE_MAX_REPLY_SECONDS: int = 30
VOICE_EDGE_RATE_LIMIT_PER_MIN: int = 30           # per-pod; separate global ceiling enforced via the LLM scheduler
VOICE_EDGE_RATE_LIMIT_GLOBAL_PER_MIN: int = 60    # protects micro profile from N-pod overload
VOICE_EDGE_OFFLINE_CMD_RATE_LIMIT_PER_MIN: int = 3
VOICE_EDGE_OFFLINE_CMD_MIN_CONFIDENCE: float = 0.85
VOICE_EDGE_WAKE_FALSE_POSITIVE_FLOOR: float = 0.5  # max false-wakes per hour CI threshold
VOICE_EDGE_TOKEN_KEK: str = ""                    # per-instance KEK for at-rest pod-token encryption
```

Mirror in `.env.example` and `config.example.yaml`.

### 10.2 Pod

`/etc/oz-voice-pod/config.yaml`:

```yaml
backend_url: "https://oz.<tailnet>.ts.net"
pod_id: "kitchen"
auth_token_file: "/etc/oz-voice-pod/token"
wake_word: "hey-z"
language: "en"
asr_model: "small.en"
voice: "neutral"
mute_gpio: 17
ring_gpio: 18
debug_audio_ring: false
```

### 10.3 BUILD.md

New phase: "Voice-Edge Pod -- adding an ambient device".

1. Flash a Pi OS Lite image, or use the optional `flash-image.sh` turnkey image.
2. Install Tailscale and join the Tailnet.
3. Run `edge/voice-pod/scripts/install.sh` (apt deps, venv, model download, systemd unit).
4. From the openZero dashboard, register the pod and copy its token to `/etc/oz-voice-pod/token`.
5. `systemctl enable --now oz-voice-pod`. Say "Hey Z, are you there?" -- expect a spoken confirmation.

---

## 11. Dashboard

A new `VoicePodsManager.ts` Shadow DOM component. Mandatory boilerplate: `${ACCESSIBILITY_STYLES}`, `${BUTTON_STYLES}`, `${SECTION_HEADER_STYLES}`, `${SCROLLBAR_STYLES}`, `tr()` (loaded in `connectedCallback`), local `.sr-only`, `:focus-visible`, `@media (prefers-reduced-motion: reduce)`, `@media (forced-colors: active)`, HSLA `var(--token, fallback)`, `rem` spacing, `.h-icon` / `.status-dot` / `.empty-state` classes, native `<button>`/`<input>`/`<dialog>` first.

Sections:

1. Registered pods -- name, location, language, voice, last-seen, online indicator (paired with text label and `tr('online','Online')` -- never colour-only), revoke button.
2. Add pod -- form generating a token plus setup snippet; **two-step confirm before token issuance, following the canonical `AgentsWidget` `*-step1` / `*-confirm` red HSLA-border pattern**. Token-reveal modal uses `role="dialog"` with focus trap, ESC dismiss, return-focus, copy-to-clipboard with `aria-live` "Token copied", then masked.
3. Per-pod settings -- voice, language, wake word, mute schedule (native `<input type="time">`, locale-aware via `tr()`).
4. Recent utterances -- per-pod feed of last 50 transcripts with `role="log"` + `aria-live="polite"`, each with `<time datetime>` for screen readers. Reuses `${SCROLLBAR_STYLES}`.
5. Health -- ASR latency, wake-detection rate, network round-trip per pod. Health-pulse animations honour `prefers-reduced-motion`.

All user-visible strings (visible text, `aria-label`, `placeholder`, `title`) go through `this.tr('key', 'English fallback')` with new keys at minimum in `src/backend/app/services/i18n/en.py` and `de.py`. `pytest tests/test_i18n_coverage.py -v` is a Phase V2 DoD line. The `error.message_key` returned by `/api/voice/session` resolves via the same `_TRANSLATIONS` dicts (no parallel "voice strings" dict).

---

## 12. Phased Implementation

### Phase V0 -- Backend voice channel (no hardware)

DoD: a curl client posting transcripts to `/api/voice/session` gets a streamed reply with TTS chunks. Phase A of `full_ambient_intelligence_roadmap.md` (shared sanitiser module + unified pending queue + channel-class registry) is a prerequisite.

- New router `api/voice_edge.py` plus SSE protocol `oz-voice-pod-protocol/v1`.
- `services/tts.py` sentence-chunked synthesis (no upstream protocol change required).
- Pod registry tables (`voice_pods`, `voice_pod_audit`) via the repo's startup-DDL pattern; **no Alembic**. Pod tokens encrypted at rest with `VOICE_EDGE_TOKEN_KEK`.
- `bus.ingest` signature extension to accept `lang` and `conversation_id` (coordinated cross-artifact PR; prerequisite shared with federation).
- `MessageBus.commit_reply` channel-class registry (`text` vs `audio`); voice-edge is `audio`.
- Tailnet-source-IP middleware (`app/api/_deps.py`) shared with federation.
- LLM scheduler priority lane: `voice > interactive_text > capture_tiebreaker > ambient_trigger > vision`.
- `pod_id` always in `X-OZ-Pod-Id` header; never in URL query string. Backend rejects requests with `pod_id` query param.
- `GET /api/voice/pods/{id}/theme` endpoint and server-side theme persistence (prerequisite -- today theme is browser-local only).
- Channel-parity audit: streaming timeout, HITL chunking, ambient capture all working with a synthetic client. agents.md rule 21 updated to enumerate `voice-edge` alongside Telegram/WhatsApp/dashboard.
- Tests: protocol contract, HITL via voice channel (including auto-followup suppression on sensitive pending), rate limiting (per-pod and global), auth, wake-nonce replay rejection, `pod_id`-in-query-string rejection, `confidence`-as-advisory-only.

### Phase V1 -- Edge firmware (single pod)

DoD: a Pi 5 + ReSpeaker pod can be set up via the install script and reliably wake -> transcribe -> reply at the latency targets below.

- `edge/voice-pod/` package complete in a sibling repo (or `git subtree`); main repo's `sync.sh` excludes the directory.
- `install.sh` works on a fresh Pi OS Lite image. Tailscale auth-key is **not** baked into a distributed image -- operators run `tailscale up` interactively (the alternative leaks a Tailnet credential in any image redistributed).
- OpenWakeWord with default "Hey Z" model (`.tflite` vendored or downloaded with checksum manifest).
- faster-whisper INT8 **`tiny.en`** by default on Pi 5 (the only configuration that meets latency targets); `small.en` opt-in with documented latency penalty.
- LED ring state machine; muted state visually distinct from idle.
- Mute GPIO plus ALSA-level mic close, with software-observable assertion (no Whisper invocation while muted).
- Offline canned-command fallback with cached TTS in EN and DE; rate-limited and confidence-floor gated.
- `/healthz` binds `127.0.0.1` only.
- Pod refuses to start if `debug_audio_ring=true` and `/var/lib/oz-voice-pod/debug` is on a non-tmpfs mount.
- Latency targets on Pi 5 (best-effort, hardware-loop nightly only -- not a per-PR CI gate; see Test Strategy):
	- Wake -> first audio byte over local LAN: under 2.5 s P95.
	- Wake -> first audio byte over Tailscale to a remote VPS: under 3.5 s P95.
	- ASR wall-clock latency for a 6-second utterance under streaming mode: under 1.0 s P95 with `tiny.en`.
- Wake-word false-positive rate on the recorded false-positive corpus: under `VOICE_EDGE_WAKE_FALSE_POSITIVE_FLOOR` (default 0.5/hr).

### Phase V2 -- Multi-pod + dashboard

DoD: two pods in one home arbitrate cleanly; the dashboard surfaces them.

- `VoicePodsManager.ts` component.
- Per-pod settings persisted in Postgres.
- Wake arbitration server-side.
- Recent utterances feed wired to existing `GlobalMessage` view.
- i18n keys complete in `_EN` and `_DE`.
- Per-pod health endpoint feeding the dashboard.

### Phase V3 -- Reliability and polish

DoD: a non-technical operator can install a second pod in under 30 minutes; the device handles backend outages without going silent.

- Turnkey Pi image (`flash-image.sh`) with Tailscale enrolment via auth key.
- Backend disconnect handling: pod announces offline state, retries with exponential backoff, surfaces in dashboard.
- Crash-loop watchdog (systemd `Restart=always` plus rate limit plus dashboard alert via the self-audit channel).
- Rolling tmpfs debug ring buffer for support, default off, never persisted to SD card.
- Hardware self-test command ("Hey Z, run pod check") that walks mic, speaker, ring, and round-trip.

### Phase V4 -- Multi-language and multi-voice

DoD: pods can speak the user's full set of supported languages; operator can switch a pod's voice from the dashboard.

- TTS voice catalogue surfaced per-pod.
- Multilingual Whisper option (`small` instead of `small.en`).
- Pod respects user's i18n choice on a per-pod basis.

### Phase V5 -- Future hooks (deferred)

Captured to avoid box-out:

- Barge-in (AEC tuning).
- Speaker identification (multi-user households where pods route to the right operator's Z; needs voice enrolment with explicit consent).
- Local LLM execution on the pod (small fast-tier model on the Pi for offline answers; only worthwhile when Pi-class hardware can run a useful model).
- Custom PCB and battery for portable pods.
- Multi-room synchronised audio responses.

---

## 13. Test Strategy

| Layer | Test |
|---|---|
| Protocol | Contract test for the SSE event schema; backwards-compat per protocol version |
| Channel parity | `tests/test_live_regression.py` extension: voice channel hits the same checklist as Telegram, WhatsApp, dashboard |
| Wake word | Recorded false-positive corpus (TV news, kitchen noise, music) -- minimum precision; recorded true-positive corpus -- minimum recall |
| Privacy | Filesystem audit asserts no audio files persist after a session; `/var/lib` path mode 0700 |
| Offline | Pull network and confirm canned fallbacks fire; LED ring transitions to offline pattern |
| HITL | Spoken sensitive action -> spoken confirmation flow round-trip in `_EN` and `_DE` |
| Multi-pod | Two-pod fixture: parallel wake, arbitration picks loudest, the other stays idle |
| Security | Reject non-Tailnet IPs, revoked tokens, replayed sessions; existing 268-test prompt injection suite extended with a "voice-channel injection" class (transcripts engineered to look like action tags must be stripped) |
| i18n | All new strings present in `_EN` and `_DE`; voice fallback canned audio exists for every error key |

---

## 14. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Wake-word false positives in noisy rooms | Configurable wake word, minimum confidence, optional press-to-talk override on GPIO button |
| Whisper latency on Pi 5 too high for natural feel | Default `small.en` INT8; allow downgrade to `tiny.en`; surface ASR latency per pod in dashboard |
| Bystanders speaking sensitive things into an open mic | Hardware mute, scheduled mute hours, sensitive actions HITL-only, audit feed |
| Operator forgets a pod is muted -> "Z is broken" support load | LED ring always shows muted state; dashboard pod row shows muted badge; spoken self-test acknowledges mute |
| Network jitter causes audio stutter | TTS chunks buffered 250 ms before playback; Opus over PCM; on chunk timeout, pod plays cached "one moment" filler instead of silence |
| Channel drift -- voice gets a degraded subset | Channel parity gate in CI; every PR touching `telegram_bot.py`, `whatsapp.py`, or `dashboard.py` must also be inspected for voice-edge implications |
| Ambient device fatigue -- the device never quite stops listening feels invasive | Breathing dot communicates open mic non-intrusively; documented privacy posture in BUILD.md; mute-by-schedule built in |
| Hardware availability volatility (Pi 5 stock) | Pod firmware is hardware-agnostic above the audio layer; document known-good alternatives (Pi 4 8 GB, Orange Pi 5, x86 mini PCs) |

---

## 15. Definition of Done (Program-Level)

- A single operator can stand up a Pi 5 + ReSpeaker pod from scratch in under 30 minutes using BUILD.md.
- Saying "Hey Z" anywhere in the room reliably wakes the pod, transcripts arrive at the backend with under 1.5 s ASR latency on Pi 5, and Z's spoken reply begins within 3 s end-to-end on a local Tailnet.
- The voice channel passes the same regression suite as Telegram, WhatsApp, and the dashboard, including HITL, ambient capture, federation attribution, and crew panels.
- Sensitive actions (`SCHEDULE_CREW`, `LEARN`, `ADD_PERSON`, `SHARE_SCOPE`) require spoken HITL confirmation from the originating pod and respect the 90-second TTL.
- The mute button silences the mic at the ALSA layer with a visible LED state; sound never reaches Whisper while muted.
- Pulling the network produces a localised spoken "openZero is offline, retrying" within 3 seconds and the LED ring transitions to the offline pattern.
- Two pods in one home arbitrate cleanly; only one answers any given wake.
- The dashboard shows registered pods, their health, recent utterances, and per-pod settings, all i18n-complete in `_EN` and `_DE`, all WCAG 2.1 AA.

---

## 16. How This Plugs Into The Rest Of The Roadmap

- #1 Ambient intelligence -- proactive triggers can choose voice as a delivery channel for low-priority but timely insights at quiet moments ("by the way, the calendar looks heavy tomorrow"), gated by per-pod schedules.
- #7 Federated memory -- a pod stays on a single instance; the per-pod system-prompt context line keeps federated reads scoped correctly.
- #9 Z-to-Z protocol -- once two operators each have a pod, the protocol layer can negotiate a meeting in the background while you're cooking dinner; the pod just speaks the result.
- #11 Digital twin threshold -- the most natural interaction surface for "what would I do here?" is voice, asked in passing. Voice-first lowers the friction enough to make the twin useful daily rather than ceremonial.

---

## Appendix R -- Review Revisions (2026-04-26)

Multi-specialist review (security, backend, infra, qa, ui-builder, perf, ai-engineer, researcher) folded into the body above. Tracked open items:

### Cross-cutting prerequisites (block V0)

- **i18n location.** Keys live in `src/backend/app/services/i18n/{code}.py`; agents.md rule 19 pointer corrected in same PR.
- **Phase A of unified ambient roadmap** (shared sanitiser module + unified pending queue + channel-class registry on the message bus) must land first.
- **`bus.ingest` signature extension** (`lang`, `conversation_id`) coordinated cross-artifact PR.
- **Tailnet-source-IP middleware** shared with federation in `app/api/_deps.py`.
- **`HARDWARE_PROFILE` enum prerequisite** for profile-aware rate-limit defaults.
- **`sync.sh` exclude list** must add `edge/`, `**/*.gguf`, `**/*.bin`, ASR/TTS model dirs **before** any voice-edge code lands. Pod firmware lives in a sibling repo or `git subtree`, never synced to VPS.
- **agents.md rule 21** extended to enumerate `voice-edge`.
- **No Alembic.** All "Alembic migration" references removed; uses `Base.metadata.create_all` + raw startup DDL.

### Security tightenings (folded above)

- `pod_id` in headers, never URL query string (closes Traefik access-log leak).
- Backend-issued wake-nonce binds each utterance to (`pod_id`, monotonic seq); compromised host on Tailnet cannot submit utterances claiming arbitrary `pod_id`.
- `confidence` is advisory only; backend never gates auth on a pod-supplied number.
- Auto-followup window suppressed when any pending action is in `SENSITIVE_ACTIONS` (closes wake-bypass primitive).
- `SHARE_SCOPE` removed from spoken HITL list; federation contracts are dashboard-only in v1 (resolves cross-artifact conflict with `federated_memory.md` §9.3).
- Wake arbitration via Redis `SETNX` (multi-worker safe); 300 ms window with optimistic local-LED feedback.
- Pod-self-asserted signal level: v1 single-trusted-operator threat model documented; trust-scored arbitration deferred to V5.
- Hostile bystander same-room hijack: explicitly accepted as v1 limitation; mitigations enumerated (auto-followup suppression, "say 'confirm <verb>'" challenge, optional GPIO confirm button, speaker-ID deferred to V5).
- Offline canned-command DoS: rate-limited 3/min, min-confidence 0.85.
- mTLS removed from architecture diagram; bearer over Tailscale only.
- Pod tokens encrypted at rest with `VOICE_EDGE_TOKEN_KEK`.
- Model integrity: SHA-256 manifest verification, TLS-pinned download URLs.
- TTS sanitiser pass strips `[AUDIT:...]`, markdown, URLs, parentheticals, action verbs from 22-verb × 11-language allowlist before synthesis (closes spoken-self-instruction vector).
- Every transcript passes through `_sanitize_for_log` before any error path.
- Mute state visually distinct from idle (colour AND pattern, not colour-only).
- `/healthz` binds `127.0.0.1` only.
- FS-audit test asserts `debug_audio_ring=true` requires tmpfs mount.
- HITL relaxation for spoken confirms documented (numeric pick or "say 'confirm <verb>'" instead of capture's quote-in-confirm rule).

### Backend feasibility

- `services/tts.py` does not support streaming today; sentence-chunked synthesis used instead.
- `services/voice.py` (existing Whisper transcription wrapper) is **not** used by voice-edge; ASR is fully edge-local.
- `MessageBus.commit_reply` cross-channel sync currently builds HTML; channel-class registry (`text` vs `audio`) introduced as part of Phase A prerequisite.
- HITL pending uses unified Redis namespace (`pending:voice:<pod_id>` prefix), not parallel implementation.
- `bus.push_all()` does not auto-deliver to voice-edge (channel-class filter).

### Infra

- `/api/voice/session` Traefik route: streaming-friendly config, `compress=false`, no buffering on this route.
- BUILD.md "Voice-Edge Pod" phase expanded: Tailscale auth-key generation walkthrough, GPIO wiring notes, mic permissions (`audio` group), token rotation procedure (without re-imaging), offline-mirror story for HuggingFace model downloads, image-distribution story (private channel; auth-key never embedded).
- Backend↔pod protocol-version compatibility matrix tracked alongside backend image tag.
- Per-profile defaults: on `micro` (Pi 5 VPS) the rate limit and pod count caps are tighter than `performance`.

### QA

- Latency targets (P95 wake -> first byte 2.5 s LAN / 3.5 s Tailscale, ASR 1.0 s for 6 s utterance with `tiny.en`) restated as **nightly hardware-loop runner**, not per-PR CI. Resolves the prior contradiction.
- Wake precision/recall thresholds explicit (false-positive floor `VOICE_EDGE_WAKE_FALSE_POSITIVE_FLOOR=0.5/hr`, recall corpus floor 0.95).
- Pure-software test path: ALSA `snd-aloop` virtual device + recorded WAV corpus + faster-whisper mocked at `asr.py` boundary in CI.
- Two-pod fixture uses two simulated audio sources via `snd-aloop` slots.
- Test for: `pod_id`-in-query rejection, wake-nonce replay rejection, `confidence`-as-advisory, auto-followup suppression on sensitive pending, `SHARE_SCOPE` rejection on voice channel, TV-noise offline-command DoS rate-limit, mute-state visual-distinct, `/healthz` 127.0.0.1-only bind, FS-audit (tmpfs), `_sanitize_for_log` on every transcript, TTS sanitiser pass.
- New "voice-channel injection" class added to `tests/test_security_prompt_injection.py` (target +20 cases minimum). Reference suite by file/name, not the volatile total.
- Cached canned audio corpus: source, license, parity-check pipeline documented as a test artifact under `tests/fixtures/voice_edge/canned/{lang}/`.
- 11-language canned-audio claim moved from §5.5 to V4 DoD; V1 ships EN+DE only.

### Performance

- ASR: `tiny.en` INT8 streaming mode, `beam_size=1`, `vad_filter=True`, pre-warm in `ExecStartPre`.
- VAD silence threshold reduced to 600-800 ms with utterance-completion classifier as a more aggressive end-pointer.
- Adaptive Opus chunk size (200 ms initial, grow to 400 ms after first ack); binary framing instead of base64-in-JSON.
- Wake arbitration window compressed to 300 ms; optimistic local-LED feedback to mask perceived lag.
- LLM scheduler priority lane: voice highest; reserve 1 of 2 `--parallel` slots for voice; default to fast-tier (3B) for voice unless escalation.
- Per-pod rate-limit + separate global ceiling (`VOICE_EDGE_RATE_LIMIT_GLOBAL_PER_MIN`) so one chatty pod cannot starve another and N-pod load on `micro` is bounded.

### Dashboard / a11y / i18n (folded into §11)

- Mandatory boilerplate enumerated.
- Two-step confirm follows canonical `AgentsWidget` red HSLA-border pattern.
- Token-reveal modal: `role="dialog"`, focus trap, ESC, return-focus, copy-with-aria-live, then mask.
- Recent utterances: `role="log"` + `aria-live="polite"` + `<time datetime>`.
- Online indicator pairs colour with text/icon (forced-colors safety).
- Mute schedule uses native `<input type="time">`.
- Health-pulse animations honour `prefers-reduced-motion`.
- Error `message_key` resolved via shared `_TRANSLATIONS` dicts (no parallel "voice strings" dict).
- "11 languages" claim replaced with "all populated language dicts; `_EN`+`_DE` is the CI-blocking gate".

### AI / persona / crew

- New `agent-rules.md` section: **Voice Channel Output** -- no markdown, no bullets, no URLs read literally, no AUDIT tags, neutral-Z for HITL confirms, hard 30 s cap, language follows detected user input not pod config.
- New `agent-rules.md` section: **Multi-Pod Suppression** -- ambient deliveries route to one pod, never broadcast.
- **Language Lock** extended: detected-language wins over pod-configured language; pod voice is fallback only when detection is uncertain.
- Spoken HITL phrasing uses `tr('voice_hitl_prompt', "I'd like to do {action}. Yes or no?")`; example English text never hardcoded.
- System-prompt prefix `[CHANNEL=voice-edge POD=<name> LANG=<code>]` injected so Z auto-adopts spoken-format rules.
- TTS quality validation per language (Phase V1 smoke-test one canonical phrase per language to catch robotic/inconsistent voices).
- Spoken numbers, dates, ISO timestamps, and AUDIT tags stripped in the TTS sanitiser pass before synthesis.
- Arbitrated wake conversation_id follows operator (most-recent active conversation within N minutes), not pod, to prevent context fragmentation across rooms.

### Cross-artifact consistency

- `SHARE_SCOPE` ownership: federation `services/agent_actions.py` (dashboard-only); voice-edge does not confirm.
- HITL TTL unified: voice-edge `VOICE_EDGE_HITL_TTL_S` defaults match capture's pending TTL; both observe the AgentsWidget operator slider (capture decides, voice tracks).
- Cached canned audio in 11 languages claim moved to V4 DoD.
- mTLS removed (Tailscale + bearer only, matches federation).
- Edge firmware sibling-repo decision noted in BUILD.md.
- agents.md rule 21 enumeration now includes `voice-edge`.

