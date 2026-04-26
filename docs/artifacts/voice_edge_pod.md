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
|                 Voice channel client  ----[Tailscale, mTLS]---->  openZero |
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

- Edge firmware (`edge/voice-pod/`): a small Python service on the Pi that owns mic, wake word, ASR, LED ring, and the bidirectional voice session.
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

- `faster-whisper` with `small.en` INT8 by default; configurable to `tiny.en` on Pi 4 or to multilingual variants.
- Models live under `/var/lib/oz-voice-pod/models/`, downloaded once at install.
- Transcription is fully local. The transcript is the only thing sent over the network.

### 5.3 Session protocol

The pod opens an HTTP/2 + SSE connection to `/api/voice/session?pod_id=<id>` and streams a JSON envelope:

```json
{
	"type": "utterance",
	"transcript": "what is on my plate today",
	"lang": "en",
	"confidence": 0.91,
	"captured_at": "2026-04-26T07:14:33Z"
}
```

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

Colours come from the same HSLA tokens as the dashboard. The pod fetches the active accent on boot and on theme change push.

### 5.5 Offline fallback

When Tailscale is down or the backend is unreachable:

- Wake word still works locally.
- A short offline canned-command set (configurable, max 10 commands) executes via local intent matching: "what's the time", "are you there", "reconnect now".
- Status announced ("openZero is offline, retrying") via pre-cached TTS audio in 11 languages.

### 5.6 Privacy posture

- No raw audio written to disk except a rolling 60-second debug ring buffer in tmpfs, disabled by default.
- Wake-word detector activations are not logged.
- Captured audio is held in memory for the Whisper call only; on transcript completion the buffer is zeroed.
- Hardware-friendly mute: `/etc/oz-voice-pod/muted` flag plus a physical GPIO button take precedence; LED ring shows steady muted indicator; mic closed at the ALSA layer.

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

`services/tts.py` already supports synthesis. Add `synthesize_stream(text_stream, voice, lang)` yielding Opus chunks as text arrives. Voice and language are pod-scoped.

### 6.5 Channel parity hooks

Per agents.md rule 21:

- Streaming timeout, stall detection, error recovery: same code path as Telegram and WhatsApp.
- HITL pending queue: voice replies "I'd like to do X. Yes or no?" and accepts the next utterance as confirmation, scoped to `pod_id` plus 90-second TTL.
- Ambient capture lanes (EXECUTE / ASK / TEACH / CHAT) work unchanged with phrasing tuned for spoken confirms.
- Long replies cut at ~30 seconds of speech with "want me to continue?" follow-up.

---

## 7. Conversation Model

### 7.1 Wake -> intent -> reply

A single utterance is one full message-bus turn. The pod does not maintain its own thread; the bus does, keyed on `pod_id`.

### 7.2 Multi-turn without re-wake

If the agent's reply ends with a question, the pod auto-opens a follow-up capture window (5 s) without requiring another wake word. SSE event: `{ "type": "expect_followup", "ttl": 5 }`.

### 7.3 Cross-channel continuity

Everything goes through `bus.ingest()`. Starting a thought on the kitchen pod and continuing on Telegram is supported via the unified `GlobalMessage` view. The pod's `conversation_id` is the same identifier the dashboard already uses for cross-channel grouping.

### 7.4 Barge-in (deferred to v2)

True interruption while Z speaks ("Z, stop") needs AEC tuning the ReSpeaker supports but requires profiling. v1 ships without barge-in; mute button or letting Z finish.

---

## 8. Multi-Pod Households

### 8.1 Arbitration

When wake fires on multiple pods within ~600 ms, each sends a `wake_intent` with measured signal level. The backend picks the loudest within a 1-second window and tells the others to suppress with `wake_arbitration_lost`. Server-side decision; pods do not coordinate peer-to-peer.

### 8.2 Per-pod voice and language

Each pod can be configured with its own voice and language. Bedside pod can speak low-energy slow English; kitchen pod fast German. Backend reads pod metadata when synthesising.

### 8.3 Pod-aware context

When a request arrives from `kitchen`, the system prompt gains: `"This message arrived from the 'kitchen' pod."` Z can use this to bias responses without forcing inference.

---

## 9. Security and Trust

### 9.1 Threat model

- Stolen pod: off-Tailnet immediately stops working; revoking the bearer token disables it permanently.
- Hostile speaker in earshot: sensitive actions remain HITL-gated; confirmation must come from the same pod within TTL. A second voice cannot bypass HITL because confirmations require the original pending action to exist.
- Bystander privacy: hardware mute cuts mic at the ALSA layer; LED ring shows non-revertible muted state until released.
- Wake-word collision: configurable wake word; minimum confidence threshold required.
- Replay of utterances: each session carries a monotonic nonce; backend rejects duplicates.

### 9.2 Action vocabulary on voice

Voice gets the same allowlist as every other channel. No `DELETE_*`, no surprise execution. Sensitive actions (`SCHEDULE_CREW`, `LEARN`, `ADD_PERSON`, `SHARE_SCOPE`) require spoken HITL confirmation.

### 9.3 Audit

Every utterance creates a `GlobalMessage` row tagged with `channel="voice-edge"` and `pod_id`. Dashboard filter for the last N utterances per pod.

---

## 10. Configuration

### 10.1 Backend

`src/backend/app/config.py`:

```python
VOICE_EDGE_ENABLED: bool = False
VOICE_EDGE_TTS_VOICE_DEFAULT: str = "neutral"
VOICE_EDGE_HITL_TTL_S: int = 90
VOICE_EDGE_MAX_REPLY_SECONDS: int = 30
VOICE_EDGE_RATE_LIMIT_PER_MIN: int = 30
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

A new `VoicePodsManager.ts` Shadow DOM component (existing conventions: `${ACCESSIBILITY_STYLES}`, `tr()`, HSLA tokens, no hardcoded English).

Sections:

1. Registered pods -- name, location, language, voice, last-seen, online indicator, revoke button.
2. Add pod -- form generating a token plus setup snippet; two-step confirm before token issuance.
3. Per-pod settings -- voice, language, wake word, mute schedule (e.g. silent after 23:00).
4. Recent utterances -- per-pod feed of last 50 transcripts, reusing the existing message timeline component (live region, keyboard nav).
5. Health -- ASR latency, wake-detection rate, network round-trip per pod.

All strings in `_EN` and `_DE` first; the i18n parity gate enforces propagation.

---

## 12. Phased Implementation

### Phase V0 -- Backend voice channel (no hardware)

DoD: a curl client posting transcripts to `/api/voice/session` gets a streamed reply with TTS chunks.

- New router `api/voice_edge.py` plus SSE protocol.
- `services/tts.py` gains `synthesize_stream`.
- Pod registry tables and CRUD endpoints.
- `bus.ingest` accepts `channel="voice-edge"` end-to-end.
- Channel-parity audit: streaming timeout, HITL chunking, ambient capture all working with a synthetic client.
- Tests: protocol contract, HITL via voice channel, rate limiting, auth.

### Phase V1 -- Edge firmware (single pod)

DoD: a Pi 5 + ReSpeaker pod can be set up via the install script and reliably wake -> transcribe -> reply at low latency.

- `edge/voice-pod/` package complete.
- `install.sh` works on a fresh Pi OS Lite image.
- OpenWakeWord with default "Hey Z" model.
- faster-whisper INT8 small.en model.
- LED ring state machine.
- Mute GPIO plus ALSA-level mic close.
- Offline canned-command fallback with cached TTS in EN and DE.
- Latency target on Pi 5: wake -> first audio byte from backend under 2.0 s on local LAN, under 3.0 s over Tailscale to a remote VPS (best-effort, not a hard CI gate).

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
