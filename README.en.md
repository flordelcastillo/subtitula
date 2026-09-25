# Subtitula

[![tests](https://github.com/flordelcastillo/subtitula/actions/workflows/tests.yml/badge.svg)](https://github.com/flordelcastillo/subtitula/actions/workflows/tests.yml)
[![license](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

**Open source live captions and simultaneous interpretation for multi-room conferences, built on the Gemini Live API.**

**[Try the demo](https://flordelcastillo.github.io/subtitula/)** (replay of a real run, nothing to install) · [Nerdearla Vibeathon 2026](https://nerdearla26.devpost.com) · [Measured evidence](docs/evidencia) · [Versión en español](README.md)

| The audience, in their language | "What did I miss?" | Room screen with QR | Production dashboard |
|---|---|---|---|
| <img src="docs/img/celular-es.png" width="180" alt="Phone view with an English talk captioned in Spanish"> | <img src="docs/img/que-me-perdi.png" width="180" alt="Summary of the last 5 minutes in English"> | <img src="docs/img/pantalla.png" width="300" alt="Room screen with Spanish and English captions and a QR code"> | <img src="docs/img/panel.png" width="300" alt="Dashboard with two live rooms, latencies and cost"> |

## For Nerdearla

Today the conference captions talks with two commercial tools, one for Spanish transcription and one for live English to Spanish translation, operated by hand. This year there are more than 30 English sessions, many in parallel.

- **One tool for both jobs.** Each room opens a Gemini Live API session that returns the original transcript (accessibility) and the translation at the same time. It works the same for an English talk (Spanish captions) or a Spanish talk (English captions), and adds Portuguese when someone asks for it.
- **Event cost in plain sight.** US$ 2.21 per room-hour per target language, from official prices. For example, 30 talks of 40 minutes translated to Spanish are about 20 room-hours, **roughly US$ 44 in total**. Each extra language costs the same, but only while someone is using it.
- **Same room setup.** The computer wired to the mixing desk opens `/enviar/<room>` in a browser (nothing to install), or the room's stream is pulled (HLS, RTMP, SRT or YouTube). The room TV opens `/pantalla/<room>`, the stream adds `/overlay/<room>` in OBS or vMix, and production watches every room at `/admin`.
- **Never lagging.** Organizers told us lag is the worst experience: they prefer captions that cut and resume over captions 10 s behind. A watchdog reopens any session that stalls or falls more than 6 s behind, live, without carrying the backlog.
- **Replicable.** Another event only edits `config/sessions.yaml` and `config/glossary.yaml`. Apache 2.0.

## The five judging criteria, with evidence

| Criterion | What Subtitula does | Evidence |
|---|---|---|
| **Quality** | Interpretation with Live Translate. Each room's glossary is sent as the recognizer's custom vocabulary, and its canonical spelling is enforced on every track, including the translation. Each language builds its own lines, cut at sentence ends with at most 84 characters (the 2 x 42 subtitling standard). Audience questions asked directly in the target language are echoed. The glossary can be suggested by AI from the talk's title, speaker and abstract | Final SRT files for 2 minutes of each sample talk in [`docs/evidencia/srt`](docs/evidencia/srt). Real example: "if I pipe the audio out on the HDMI, are you able to hear it on the stream?" → "Si saco el audio por el HDMI, ¿puedes escucharlo en la transmisión?" |
| **Latency** | Word by word while the speaker talks. From the speaker's pause to the last word of that sentence: **0.34 s p50 and 0.7 to 0.9 s p90 for the original; 0.29 to 0.34 s p50 and 0.76 to 0.89 s p90 for the translation**. No accumulated drift over 10 continuous minutes (worst minute: 2.1 s p90). If a session still stalls, a watchdog reopens it live | [`docs/evidencia`](docs/evidencia), measured with [`scripts/drift_test.py`](scripts/drift_test.py) over 10 minutes of each sample talk |
| **Scalability** | One stateless worker per room and a hub that only moves text. Unused languages open no session and silence is not streamed. Real cost per room in the dashboard | 4 simultaneous Live sessions against Gemini with 0 errors. Load test with word-by-word updates: 20 rooms and 500 viewers, 4,223 deliveries per second, 4 ms p50 from hub to screen ([Scale](#scale)) |
| **Deployment and operation** | `pip install`, a key in `.env` and `subtitula serve`, or Docker Compose with one container per room. Rooms can send audio from a browser tab, microphone or file. Dashboard with audio level, p50/p90 latency, errors, sessions, lag cuts, cost, QR and a live-editable glossary. OBS/vMix overlay, `live.txt` for titles, chroma background, Prometheus `/metrics`. Room checklist for volunteers | [Operation](#operation-during-the-event) and [What if…](#what-if) |
| **Innovation** | **Listen to the interpretation** with headphones on your phone (Live Translate already generates and bills that voice). **"What did I miss?"**: a summary of the last 5 minutes in your language, made with Gemma 4. On-demand languages and a lag watchdog. Three engines: live, chunked and fully local | [Live demo](https://flordelcastillo.github.io/subtitula/), screenshots and demo video |
| **Accessibility** (the challenge's goal) | Atkinson Hyperlegible type, a high-contrast mode (on by itself when the system asks for it), adjustable text size, light or dark theme, 44 px touch targets, full keyboard operation, interface in Spanish, English or Portuguese following the phone, and spoken interpretation for those who prefer to listen | Audience view reviewed against WCAG 2.2 AA; screenshots in `docs/img` |

## Try it in 2 minutes

Requirements: Python 3.11+, `ffmpeg` and a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey). The [pricing page](https://ai.google.dev/gemini-api/docs/pricing) lists a free tier for Live Translate, but with our free key the session never opened; the [official Live Translate guide](https://github.com/google-gemini/gemini-live-translate-livekit) says the free tier allows about 3 to 5 concurrent connections. Every number in this README was measured on a project with billing enabled (Tier 1).

```bash
git clone https://github.com/flordelcastillo/subtitula && cd subtitula
python -m venv venv && . venv/bin/activate
pip install -e .
echo GEMINI_API_KEY=your-key > .env
subtitula serve
```

Open <http://localhost:8000>. The **"Tu audio"** room receives whatever you send from <http://localhost:8000/enviar/sala-c>: pick "Archivo de audio o video…", upload any talk and watch it captioned in another tab. Two sample rooms loop real 2-minute clips from Nerdearla 2025: [Thor Schaeff, *Building Multilingual Conversational AI Agents*](https://www.youtube.com/watch?v=GkVjMxYi5gA) in English and [Miguel Ángel Durán, *Programming is dead. Long live programming!*](https://www.youtube.com/watch?v=zynI57qVj-U) in Spanish.

Without a key everything runs with the test engine: `subtitula serve --engine fake`. With a free key, the chunked engine works: `--engine gemini`.

Mind the quickstart cost: `subtitula serve` with the sample rooms opens 4 Live sessions at start (two rooms, two target languages each) and keeps 2 after two minutes: about US$ 8.8 per hour at first and US$ 4.4 per hour afterwards, for as long as you leave it running.

| Page | For whom |
|---|---|
| `/` and `/s/<room>?lang=es` | Audience: pick room and language, read, **listen to the interpretation** (live engine, `serve` mode), ask "What did I miss?", change text size and theme, download the talk. The interface follows the phone's language: Spanish, English or Portuguese |
| `/pantalla/<room>?lang=es&lang2=en` | Room TV or projector: large captions in one or two languages plus the QR code |
| `/overlay/<room>?lang=es` | Browser source for OBS or vMix (transparent, or `&bg=00b140` for chroma) |
| `/admin` | Production: status, audio, latency, errors, audience, cost, QR, glossary (with AI suggestions) |
| `/enviar/<room>` | The room computer sends audio from the browser: microphone, desk input or an audio/video file. Single-process mode (`subtitula serve`) only: with Docker Compose, rooms are fed by stream. The browser microphone requires HTTPS or `localhost` (see [Going to production](#going-to-production)) |
| `/api/sessions/<room>/live.txt`, `/metrics` | Title data source for vMix/CasparCG, and Prometheus metrics |

Caption a file from the terminal (prints each line and exports `.srt`, `.vtt` and `.txt` per language):

```bash
subtitula file samples/thor-schaeff-multilingual-agents-en.mp3 --language en --both
```

## Costs

Official prices from the [Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing) (paid tier, 25/09/2026). Each worker computes its cost with the model it used (`subtitula/pricing.py`).

| Engine | What is billed | Per room-hour |
|---|---|---|
| `gemini-live` (default) | Live Translate: US$ 0.0053/min audio in + US$ 0.0315/min audio out, per session (one per target language) | US$ 2.21 per language |
| `gemini` (chunked) | `gemini-3.5-transcribe` at US$ 0.005/min plus Flash-Lite text translation | about US$ 0.65 for all languages (estimate) |
| `local` | No API: faster-whisper and Gemma on your own GPU machine | US$ 0 |

| Scenario | Open Live sessions | Cost |
|---|---|---|
| One English talk with Spanish captions | 1 | US$ 2.21 per hour |
| 5 parallel rooms, one target language | 5 | US$ 11.05 per hour |
| 5 rooms, 2 of them also read in Portuguese | 7 | US$ 15.47 per hour |
| 30 talks of 40 minutes translated to Spanish | 1 per room | about US$ 44 total |

For comparison, plans of Maestra, the most cited commercial live captioning tool, start at US$ 29 for 5 hours (about US$ 5.8 per captioned hour) with live translation billed separately, according to [Sonix](https://sonix.ai/resources/maestra-pricing/) (2026). Subtitula delivers the original and the translation together for US$ 2.21 per hour, or under US$ 0.70 with the chunked engine.

On-demand languages close unused sessions after 2 minutes without audience; long silences (breaks, speaker changes) are not streamed; and the spoken interpretation, already billed, is offered to the audience at no extra cost. The number of simultaneous sessions depends on your AI Studio tier; the [official Live Translate guide](https://github.com/google-gemini/gemini-live-translate-livekit) notes that the entry tier allows few connections.

## What if…

| During the event | What Subtitula does |
|---|---|
| The audio source drops | The worker retries with exponential backoff and the room turns red in `/admin` |
| The translation lags or stops while the original keeps coming | A watchdog checks every session twice per second. If the translation has not advanced for 10 s while the original added ~2 lines, if there is voice but no original, or if a sentence arrived more than 6 s late, it reopens that session live without the backlog. Counted as a "lag cut" |
| The Live session opens but returns nothing | It happened in 2 of 4 session starts during testing: the session connects, receives audio and does not transcribe. With voice coming in and nothing back after 6 s, the watchdog reopens it; same for a translation session that translates nothing while the original advances |
| Gemini errors or the Live session drops | Reopens resuming the context (session resumption); audio waits in a 10 s queue meanwhile, so nothing said is lost |
| A talk lasts hours | Sliding-window context compression and resumption on GoAway |
| Quota runs out or a model is saturated | The chunked engine fails over to the next model on 429 or 503; without cloud, the local engine |
| Someone reloads the page or loses wifi | The browser reconnects; with `Last-Event-ID` it only receives the lines it missed |
| A name is misspelled | Add it to the room glossary in `/admin`: spelling is fixed from the next line on every track, and Live sessions reconnect with the new vocabulary |
| Someone asks in Spanish during an English talk | The Spanish track echoes the question instead of leaving a gap |
| Nobody reads Portuguese | That session waits and costs nothing until someone asks for it |
| The preview model changes | `SUBTITULA_LIVE_MODEL` picks the model; the chunked and local engines keep the same interface |

## How it works

```
 room 1 ─ ffmpeg ─┬─ Live session → es ─┐
                  └─ Live session → pt ─┤
 room 2 ─ ffmpeg ─┬─ Live session → en ─┼─► hub ─ SSE ─► phones, OBS overlay, room screen, dashboard
                  └─ Live session → pt ─┤      ├─ WebSocket ─► spoken interpretation
 room N ─ browser (WebSocket) ─ …      ─┘      └─► data/<room>.jsonl ─► SRT / VTT / TXT
```

- **Live engine** (`subtitula/live.py`). One `gemini-3.5-live-translate-preview` session per room and target language, fed with 100 ms audio blocks. Each session returns the input transcription (taken from one session) and the translation, word by word, plus the translated speech. Config: `translation_config` with `echo_target_language`, input transcription with the glossary as `custom_vocabulary` and the room language as a hint, session resumption and sliding-window compression.
- **One track per language.** The original and each translation build their own lines (sentence end, a comma once the line is long, 84 characters, or 2 s without new words), so Spanish reads as Spanish. The open line grows on screen word by word.
- **Hub** (`subtitula/hub.py`). Only moves text: SSE with `Last-Event-ID`, a WebSocket for the interpretation audio (the phone player keeps a small buffer and skips silences if it falls behind), JSONL persistence and exports.
- **Fallback engines.** Chunked (`subtitula/engines/gemini.py`): a pause-aware segmenter cuts 1 to 5 s chunks, `gemini-3.5-transcribe` returns the original in 2 to 3 s and a model pool (Flash-Lite, Gemma) translates and updates the line in place. Local (`subtitula/engines/local.py`): faster-whisper plus Gemma 4 through Ollama.

## Scale

```bash
subtitula hub --port 8000                                     # once
subtitula worker --session auditorium --hub http://hub:8000   # one per room, on any machine
```

`docker-compose.yml` runs the hub plus one container per room (set `SUBTITULA_TOKEN` in `.env`). Load test without API cost:

```bash
python scripts/loadtest.py --mode live --stages 20 --viewers 25 --seconds 45
```

`live` mode mimics the live engine: three tracks per room whose lines grow every 0.35 s, the most demanding traffic. On an 8-core laptop, in a single process: **20 rooms and 500 viewers, 169 updates per second and 190,050 deliveries (4,223 per second) with no errors; 4 ms p50 and 41 ms p99 from hub to screen**, using 45% of one core including the 500 test clients. Full output in [`docs/evidencia/carga-20-salas-500-personas.txt`](docs/evidencia/carga-20-salas-500-personas.txt).

## Operation during the event

### Going to production

- **Small event (up to 5 or 6 rooms):** one machine running `subtitula serve`. Everything works in this mode, including browser audio from the room computer (`/enviar`) and the spoken interpretation ("Listen").
- **Many rooms or several machines:** `subtitula hub` on one machine and `subtitula worker --session <room>` per room, or Docker Compose with one container per room. Rooms are then fed by stream (HLS, RTMP, SRT or YouTube); browser audio and "Listen" need the worker in the same process as the hub.
- **HTTPS:** browsers only open the microphone on `localhost` or over HTTPS. To use `/enviar` from a room computer on another machine, put the hub behind a proxy with a certificate (for example [Caddy](https://caddyserver.com): `captions.event.org { reverse_proxy localhost:8000 }`, with `flush_interval -1` so SSE is not buffered). File upload works without HTTPS.
- **Token:** `SUBTITULA_TOKEN` protects remote worker ingestion, browser audio and glossary edits. It is mandatory with Docker Compose.

**Before:** load talks in `config/sessions.yaml`; in `/admin` use **Sugerir con IA** per room to get proper nouns and acronyms from the title and abstract, review and save; print or project each room's QR.

**Room checklist (5 minutes):** the room computer is wired to the desk and has `/enviar/<room>` open (or production confirms the stream is green); sound check moves the level meter in `/admin`; a phone scanning the QR shows the test sentence in Spanish; the TV shows `/pantalla/<room>`; the stream has `/overlay/<room>` as a browser source.

**During:** a red row flags a dropped source, 20 s without audio, p90 above 6 s, lag cuts or skipped chunks. `/metrics` feeds Grafana. **After:** download `/api/sessions/<room>/export.srt?lang=es`.

## Configuration

`config/sessions.yaml` lists the rooms (`id`, `name`, `speaker`, `topic`, `source`, `language`, per-room `glossary`); `config/glossary.yaml` holds the shared terms. A glossary entry can carry aliases: `"ElevenLabs = 11 labs, Eleven Laps"` fixes the recognizer's usual misspellings to the canonical form on every track.

| `source` value | Use |
|---|---|
| `samples/talk.mp3` | A file, read at real speed (`loop: true` to repeat) |
| `mic` or `mic:<device>` | The machine's microphone or audio interface |
| `https://…/stream.m3u8` | HLS, Icecast or any URL ffmpeg can open |
| `rtmp://…`, `srt://…`, `udp://…` | Output of an encoder or of the mixing desk |
| `https://www.youtube.com/watch?v=…` | YouTube, live or recorded (uses `yt-dlp`) |
| `browser` | Audio sent from `/enviar/<room>` |

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Gemini API key (or `.env`) |
| `SUBTITULA_ENGINE` | `gemini-live` (default), `gemini`, `local` or `fake` |
| `SUBTITULA_LIVE_MODEL` | Live API model (default `gemini-3.5-live-translate-preview`) |
| `SUBTITULA_ASR_MODEL`, `SUBTITULA_GEMINI_MODEL` | Chunked engine: transcription model and translation model pool |
| `SUBTITULA_TOKEN` | Protects worker ingestion, browser audio and glossary edits |
| `SUBTITULA_PUBLIC_URL` | Public URL encoded in the QR codes |
| `SUBTITULA_ON_DEMAND`, `SUBTITULA_LINGER_S` | On-demand languages (default on, 120 s without audience) |
| `SUBTITULA_PAUSE_AFTER_S`, `SUBTITULA_SILENCE_DBFS` | Silence pause (default 10 s below −50 dBFS) |
| `SUBTITULA_STALL_S`, `SUBTITULA_MAX_LAG_S` | Lag watchdog (default 10 s stalled, 6 s late) |
| `OLLAMA_URL`, `SUBTITULA_OLLAMA_MODEL`, `SUBTITULA_WHISPER_MODEL` | Local engine |

## Development

```bash
pip install -e '.[dev]'
pytest
```

30 tests run in CI on every push, without an API key. Guidance for coding agents and contributors: [AGENTS.md](AGENTS.md).

## How it was built

Built during the vibeathon (24 and 25 September 2026) with [Claude Code](https://claude.com/claude-code) as the coding agent: Florencia set the scope and priorities and made the product decisions; the agent wrote the code, tests and measurement scripts. Every major technical decision came from testing against the real API: moving from per-chunk requests to the Live API when quota and saturation made it unworkable, splitting each language into its own track when line-by-line alignment proved impossible live, and fixing the cost after comparing it with official prices.

**Next:** agenda import to open and close rooms automatically, a published container image, and a Gemma 4 native audio engine for fully offline events (Gemma 4 E2B/E4B/12B transcribe and translate speech locally; the API-hosted Gemma models do not accept audio yet).

## License

[Apache 2.0](LICENSE). The audio clips in `samples/` come from public Nerdearla 2025 talks and are included only as test material.
