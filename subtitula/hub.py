"""Hub: recibe subtítulos de los workers y los reparte a la audiencia por Server-Sent Events.

El hub no toca audio ni modelos: sólo mueve texto. Por eso uno solo alcanza para decenas de
escenarios y miles de personas, mientras los workers (lo caro) escalan por separado.
"""

from __future__ import annotations

import asyncio
import io
import json
from dataclasses import replace
from datetime import datetime
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import segno
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

from .captions import Caption, to_srt, to_txt, to_vtt
from .config import LANG_NAMES, AppConfig, SessionConfig
from .summary import Summarizer, suggest_glossary

log = logging.getLogger(__name__)

WEB = Path(__file__).parent / "web"
BACKLOG = 40  # subtítulos que recibe quien entra tarde, para tener contexto


class Hub:
    def __init__(self, config: AppConfig, token: str = ""):
        self.config = config
        self.token = token
        self.meta: dict[str, SessionConfig] = {s.id: s for s in config.sessions}
        # Copia de la configuración original: la agenda pisa name/speaker/topic/language en `meta`.
        self.base_meta: dict[str, SessionConfig] = {s.id: replace(s) for s in config.sessions}
        self.current_talk: dict[str, str | None] = {}
        self.glossary: dict[str, list[str]] = {
            s.id: list(dict.fromkeys([*config.glossary, *s.glossary])) for s in config.sessions}
        self.captions: dict[str, list[Caption]] = {}
        self.status: dict[str, dict] = {}
        self.subscribers: dict[str, set[asyncio.Queue]] = {}
        self.listeners: dict[tuple[str, str], set[asyncio.Queue]] = {}  # (sala, idioma) -> audio
        self.demand: dict[tuple[str, str], float] = {}  # (sala, idioma) -> última vez que alguien lo miró
        self.workers: dict = {}  # sólo en modo todo-en-uno: sid -> SessionWorker
        config.data_dir.mkdir(parents=True, exist_ok=True)
        for sid in self.meta:
            self._load(sid)

    # -- persistencia --------------------------------------------------------------------------

    def _path(self, sid: str) -> Path:
        return self.config.data_dir / f"{sid}.jsonl"

    def _load(self, sid: str) -> None:
        path = self._path(sid)
        by_seq: dict[int, Caption] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    cap = Caption.from_dict(json.loads(line))
                except (json.JSONDecodeError, TypeError):
                    continue
                # Una actualización (traducción que llegó después) reemplaza a la versión anterior.
                by_seq[cap.seq] = cap
        self.captions[sid] = [by_seq[k] for k in sorted(by_seq)]

    def ensure(self, sid: str) -> None:
        if sid not in self.meta:
            # Un worker puede publicar una sesión que no estaba en sessions.yaml.
            self.meta[sid] = SessionConfig(id=sid, name=sid)
            self.glossary[sid] = list(self.config.glossary)
            self._load(sid)

    # -- publicación ---------------------------------------------------------------------------

    async def caption(self, cap: Caption) -> int:
        """Publica un subtítulo nuevo o actualiza uno existente. Devuelve el número asignado."""
        self.ensure(cap.session)
        caps = self.captions[cap.session]
        existing = self._find(caps, cap.seq)
        if existing is not None and caps[existing].created_at == cap.created_at:
            caps[existing] = cap
        else:
            # Si el worker se reinició, la numeración sigue desde el último subtítulo guardado.
            if caps and cap.seq <= caps[-1].seq:
                cap.seq = caps[-1].seq + 1
            caps.append(cap)
        with self._path(cap.session).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(cap.to_dict(), ensure_ascii=False) + "\n")
        payload = cap.to_dict()
        for queue in list(self.subscribers.get(cap.session, ())):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Un cliente que no lee (pestaña dormida) no frena a los demás.
                self.subscribers[cap.session].discard(queue)
        return cap.seq

    @staticmethod
    def _find(caps: list[Caption], seq: int) -> int | None:
        # Las actualizaciones llegan pocos segundos después: se busca desde el final.
        for i in range(len(caps) - 1, max(-1, len(caps) - 200), -1):
            if caps[i].seq == seq:
                return i
        return None

    async def status_update(self, sid: str, status: dict) -> dict:
        self.ensure(sid)
        self.status[sid] = status
        return {"glossary": self.glossary[sid], "demand": self.demand_for(sid)}

    def watch(self, sid: str, lang: str) -> None:
        """Una persona está mirando esta sala en este idioma (lo informa la vista al sondear)."""
        if sid in self.meta and lang:
            self.demand[(sid, lang)] = time.time()

    def demand_for(self, sid: str) -> list[str]:
        now = time.time()
        langs = {lang for (s, lang), seen in self.demand.items() if s == sid and now - seen < 45}
        langs |= {lang for (s, lang), queues in self.listeners.items() if s == sid and queues}
        return sorted(langs)

    def set_glossary(self, sid: str, terms: list[str]) -> None:
        self.ensure(sid)
        self.glossary[sid] = list(dict.fromkeys(t.strip() for t in terms if t.strip()))
        worker = self.workers.get(sid)
        if worker:
            worker.set_glossary(self.glossary[sid])

    def check_token(self, value: str | None) -> None:
        if self.token and value != self.token:
            raise HTTPException(status_code=401, detail="token inválido")

    # -- vistas --------------------------------------------------------------------------------

    # -- agenda --------------------------------------------------------------------------------

    def apply_agenda(self, now: datetime | None = None) -> list[str]:
        """Aplica la charla vigente de cada sala: nombre, orador, tema, idioma y glosario.

        Devuelve las salas que cambiaron. Se llama cada pocos segundos desde el hub."""
        changed = []
        now = now or datetime.now()
        self._agenda_now = now  # el mismo reloj para talk_info (y para los tests)
        for sid, base in self.base_meta.items():
            if not base.talks:
                continue
            current, _ = base.current_and_next(now)
            key = current.id if current else None
            if self.current_talk.get(sid, "?") == key:
                continue
            self.current_talk[sid] = key
            meta = self.meta[sid]
            meta.name = current.name if current else base.name
            meta.speaker = (current.speaker if current else "") or base.speaker
            meta.topic = (current.topic if current else "") or base.topic
            language = (current.language if current else "") or base.language
            self.set_glossary(sid, [*self.config.glossary, *base.glossary, *(current.glossary if current else [])])
            worker = self.workers.get(sid)
            if worker and language != meta.language and hasattr(worker, "set_language"):
                worker.set_language(language)
            meta.language = language
            changed.append(sid)
            log.info("[%s] agenda: %s", sid, current.name if current else "sin charla")
        return changed

    def talk_info(self, sid: str, now: datetime | None = None) -> dict:
        base = self.base_meta.get(sid)
        if not base or not base.talks:
            return {}
        now = now or getattr(self, "_agenda_now", None) or datetime.now()
        current, upcoming = base.current_and_next(now)

        def brief(t):
            if not t:
                return None
            start, end = t.window(now)
            return {"id": t.id, "name": t.name, "speaker": t.speaker, "start": start.strftime("%H:%M"),
                    "end": end.strftime("%H:%M")}

        return {"now": brief(current), "next": brief(upcoming)}

    def session_info(self, sid: str) -> dict:
        s = self.meta[sid]
        st = self.status.get(sid, {})
        fresh = st and time.time() - st.get("updated_at", 0) < 10
        return {
            "id": sid,
            "name": s.name,
            "speaker": s.speaker,
            "topic": s.topic,
            "language": s.language,
            "agenda": self.talk_info(sid),
            "state": st.get("state", "offline") if fresh else "offline",
            "viewers": len(self.subscribers.get(sid, ())),
            "listeners": sum(len(qs) for (s, _), qs in self.listeners.items() if s == sid),
            "captions": len(self.captions.get(sid, [])),
            # Idiomas en los que se puede escuchar la interpretación hablada (motor en vivo).
            "speech": st.get("speech_langs", []) if fresh else [],
        }

    def speech(self, sid: str, lang: str, pcm: bytes, rate: int) -> None:
        """Reparte la interpretación hablada a quienes la escuchan en ese idioma."""
        for queue in list(self.listeners.get((sid, lang), ())):
            try:
                queue.put_nowait((rate, pcm))
            except asyncio.QueueFull:
                # Un oyente con mala conexión pierde bloques; no frena a los demás.
                pass


class LocalPublisher:
    """Publicación dentro del mismo proceso (modo todo-en-uno)."""

    def __init__(self, hub: Hub):
        self.hub = hub

    def speech(self, sid: str, lang: str, pcm: bytes, rate: int) -> None:
        self.hub.speech(sid, lang, pcm, rate)

    async def caption(self, caption: Caption) -> int:
        return await self.hub.caption(caption)

    async def status(self, session: str, status: dict) -> dict:
        return await self.hub.status_update(session, status)


def _s(ms: int | None) -> float | None:
    return ms / 1000 if ms is not None else None


def create_app(config: AppConfig, token: str = "", run_workers: bool = False) -> FastAPI:
    hub = Hub(config, token=token)
    summarizer = Summarizer()
    tasks: list[asyncio.Task] = []

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if run_workers:
            from .engines import create_engine
            from .worker import worker_class

            publisher = LocalPublisher(hub)
            for s in config.sessions:
                if not s.source:
                    continue
                engine = create_engine(config.engine)
                worker = worker_class(engine)(s, engine, publisher, config.languages, hub.glossary[s.id])
                hub.workers[s.id] = worker
                tasks.append(asyncio.create_task(worker.run(), name=f"worker-{s.id}"))
            log.info("%d escenarios en marcha con el motor %s", len(tasks), config.engine)

        async def agenda_loop():
            while True:
                try:
                    hub.apply_agenda()
                except Exception as exc:  # noqa: BLE001
                    log.warning("agenda: %s", exc)
                await asyncio.sleep(10)

        if any(s.talks for s in config.sessions):
            tasks.append(asyncio.create_task(agenda_loop(), name="agenda"))
        yield
        for worker in hub.workers.values():
            worker.stop()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="Subtitula", lifespan=lifespan)
    app.state.hub = hub

    # -- páginas -------------------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    @app.get("/s/{sid}", include_in_schema=False)
    async def viewer(sid: str = ""):
        return FileResponse(WEB / "index.html")

    @app.get("/overlay/{sid}", include_in_schema=False)
    async def overlay(sid: str):
        return FileResponse(WEB / "overlay.html")

    @app.get("/pantalla/{sid}", include_in_schema=False)
    async def screen(sid: str):
        return FileResponse(WEB / "pantalla.html")

    @app.get("/admin", include_in_schema=False)
    async def admin():
        return FileResponse(WEB / "admin.html")

    @app.get("/enviar/{sid}", include_in_schema=False)
    async def sender(sid: str):
        return FileResponse(WEB / "enviar.html")

    @app.get("/web/{name}", include_in_schema=False)
    async def static(name: str):
        path = (WEB / name).resolve()
        if path.parent != WEB.resolve() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/healthz", include_in_schema=False)
    async def healthz():
        return {"ok": True}

    # -- API pública ---------------------------------------------------------------------------

    @app.get("/api/sessions")
    async def sessions(watching: str = "", lang: str = ""):
        # La vista y el overlay sondean con la sala y el idioma que muestran: así se sabe qué se usa.
        if watching:
            hub.watch(watching, lang)
        return {
            "event": config.event,
            "languages": [{"code": c, "name": LANG_NAMES.get(c, c)} for c in config.languages],
            "sessions": [hub.session_info(sid) for sid in hub.meta],
        }

    def _get(sid: str) -> list[Caption]:
        if sid not in hub.meta:
            raise HTTPException(404, "sesión inexistente")
        return hub.captions.get(sid, [])

    @app.get("/api/sessions/{sid}/captions")
    async def captions(sid: str, since: int = 0, limit: int = 500):
        caps = [c.to_dict() for c in _get(sid) if c.seq > since][-limit:]
        return {"session": hub.session_info(sid), "captions": caps}

    @app.get("/api/sessions/{sid}/stream")
    async def stream(sid: str, request: Request, since: int | None = None,
                     last_event_id: str | None = Header(default=None)):
        caps = _get(sid)
        # Al reconectar, EventSource manda Last-Event-ID y se reenvía sólo lo que faltó.
        start = since if since is not None else int(last_event_id) if (last_event_id or "").isdigit() else None
        backlog = [c for c in caps if c.seq > start] if start is not None else caps[-BACKLOG:]
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        hub.subscribers.setdefault(sid, set()).add(queue)

        async def events():
            try:
                yield "retry: 2000\n\n"
                for cap in backlog:
                    yield f"id: {cap.seq}\ndata: {json.dumps(cap.to_dict(), ensure_ascii=False)}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        cap = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"  # mantiene viva la conexión a través de proxies
                        continue
                    yield f"id: {cap['seq']}\ndata: {json.dumps(cap, ensure_ascii=False)}\n\n"
            finally:
                hub.subscribers.get(sid, set()).discard(queue)

        return StreamingResponse(events(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/sessions/{sid}/live.txt")
    async def live_txt(sid: str, lang: str = "es", lines: int = 2):
        """Últimas líneas en texto plano: fuente de datos para títulos de vMix o CasparCG."""
        visible = [c for c in _get(sid)[-200:] if c.visible_in(lang) and c.in_lang(lang).strip()]
        text = "\n".join(c.in_lang(lang).strip() for c in visible[-max(1, min(lines, 5)):])
        return PlainTextResponse(text, headers={"Cache-Control": "no-store"})

    @app.get("/api/sessions/{sid}/summary")
    async def summary(sid: str, lang: str = "es", minutes: int = 5):
        """"¿Qué me perdí?": resumen de los últimos minutos en el idioma pedido."""
        caps = _get(sid)
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise HTTPException(503, "El resumen necesita GEMINI_API_KEY")
        s = hub.meta[sid]
        try:
            return await summarizer.summarize(sid, s.name, s.speaker, caps, lang, max(1, min(minutes, 30)))
        except Exception as exc:  # noqa: BLE001
            log.warning("[%s] no se pudo resumir: %s", sid, exc)
            raise HTTPException(503, "No se pudo generar el resumen ahora; probá en un minuto") from exc

    @app.get("/api/sessions/{sid}/export.{fmt}")
    async def export(sid: str, fmt: str, lang: str = "original"):
        caps = _get(sid)
        render = {"srt": to_srt, "vtt": to_vtt, "txt": to_txt}.get(fmt)
        if not render:
            raise HTTPException(400, "formato: srt, vtt o txt")
        media = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}[fmt]
        name = f"{sid}-{lang}.{fmt}"
        return PlainTextResponse(render(caps, lang), media_type=f"{media}; charset=utf-8",
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/sessions/{sid}/qr.svg")
    async def qr(sid: str, request: Request, lang: str = ""):
        _get(sid)
        base = os.environ.get("SUBTITULA_PUBLIC_URL", str(request.base_url)).rstrip("/")
        url = f"{base}/s/{sid}" + (f"?lang={lang}" if lang else "")
        buf = io.BytesIO()
        # Con xmlns y sin declaración XML: así el navegador lo muestra dentro de un <img>.
        segno.make(url, error="m").save(buf, kind="svg", scale=8, border=2, dark="#0b0b0c", light="#ffffff",
                                        xmldecl=False)
        svg = buf.getvalue()
        return Response(svg, media_type="image/svg+xml")

    # -- operación -----------------------------------------------------------------------------

    @app.get("/api/status")
    async def status():
        rows = []
        for sid in hub.meta:
            st = dict(hub.status.get(sid, {}))
            info = hub.session_info(sid)
            # Cada worker calcula su costo con los precios del modelo que usó (subtitula/pricing.py).
            cost = st.get("cost_usd", 0.0)
            audio_h = max(st.get("audio_s", 0) / 3600, 1e-9)
            rows.append({**info, **st, "state": info["state"], "glossary": hub.glossary.get(sid, []),
                         "cost_usd": round(cost, 4),
                         "cost_usd_per_hour": round(cost / audio_h, 3) if st.get("audio_s", 0) > 60 else None})
        return {"event": config.event, "engine": config.engine, "sessions": rows,
                "viewers": sum(r["viewers"] for r in rows), "listeners": sum(r["listeners"] for r in rows),
                "time": time.time()}

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        """Métricas en formato Prometheus, para sumar Subtitula al Grafana del evento."""
        gauges = {
            "subtitula_live": ("1 si la sala está transmitiendo", lambda i, st: 1 if i["state"] == "live" else 0),
            "subtitula_audio_level_dbfs": ("Nivel del audio que entra", lambda i, st: st.get("level_dbfs")),
            "subtitula_latency_p50_seconds": ("Demora del original, p50",
                                              lambda i, st: _s(st.get("latency_p50_ms"))),
            "subtitula_latency_p90_seconds": ("Demora del original, p90",
                                              lambda i, st: _s(st.get("latency_p90_ms"))),
            "subtitula_translation_p50_seconds": ("Demora de la traducción, p50",
                                                  lambda i, st: _s(st.get("translation_p50_ms"))),
            "subtitula_translation_p90_seconds": ("Demora de la traducción, p90",
                                                  lambda i, st: _s(st.get("translation_p90_ms"))),
            "subtitula_captions_total": ("Líneas de subtítulo publicadas", lambda i, st: i["captions"]),
            "subtitula_errors_total": ("Errores de la sala", lambda i, st: st.get("errors", 0)),
            "subtitula_lag_cuts_total": ("Sesiones cortadas y retomadas por atraso", lambda i, st: st.get("lag_cuts", 0)),
            "subtitula_viewers": ("Personas leyendo", lambda i, st: i["viewers"]),
            "subtitula_listeners": ("Personas escuchando la interpretación", lambda i, st: i["listeners"]),
            "subtitula_cost_usd_total": ("Costo acumulado según precios oficiales", lambda i, st: st.get("cost_usd", 0)),
        }
        lines = []
        for name, (help_, value) in gauges.items():
            lines += [f"# HELP {name} {help_}", f"# TYPE {name} gauge"]
            for sid in hub.meta:
                info, st = hub.session_info(sid), hub.status.get(sid, {})
                v = value(info, st)
                if v is not None:
                    lines.append(f'{name}{{sala="{sid}"}} {float(v)}')
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    @app.post("/api/ingest/{sid}")
    async def ingest(sid: str, request: Request, authorization: str | None = Header(default=None)):
        hub.check_token((authorization or "").removeprefix("Bearer ").strip() or None)
        body = await request.json()
        if body.get("type") == "caption":
            return {"ok": True, "seq": await hub.caption(Caption.from_dict(body["caption"]))}
        if body.get("type") == "status":
            return await hub.status_update(sid, body.get("status", {}))
        raise HTTPException(400, "type: caption o status")

    @app.put("/api/sessions/{sid}/glossary")
    async def glossary(sid: str, request: Request, authorization: str | None = Header(default=None)):
        hub.check_token((authorization or "").removeprefix("Bearer ").strip() or None)
        body = await request.json()
        hub.set_glossary(sid, [str(t) for t in body.get("terms", [])])
        return {"glossary": hub.glossary[sid]}

    @app.post("/api/sessions/{sid}/glossary/suggest")
    async def glossary_suggest(sid: str, request: Request, authorization: str | None = Header(default=None)):
        """Sugerencias de glosario a partir de los datos de la charla (se revisan antes de guardar)."""
        hub.check_token((authorization or "").removeprefix("Bearer ").strip() or None)
        _get(sid)
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise HTTPException(503, "Las sugerencias necesitan GEMINI_API_KEY")
        body = await request.json() if await request.body() else {}
        s = hub.meta[sid]
        try:
            terms = await suggest_glossary(summarizer._engine(), s.name, s.speaker, s.topic,
                                           str(body.get("text", "")), hub.glossary.get(sid, []))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(503, "No se pudieron generar sugerencias; probá en un minuto") from exc
        return {"suggested": terms}

    @app.websocket("/api/sessions/{sid}/listen")
    async def listen(ws: WebSocket, sid: str, lang: str = "es"):
        """Interpretación hablada en vivo: PCM s16le mono; el primer mensaje trae la frecuencia."""
        if sid not in hub.meta:
            await ws.close(code=4404)
            return
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=120)
        key = (sid, lang)
        hub.listeners.setdefault(key, set()).add(queue)
        await ws.send_json({"session": sid, "lang": lang})

        async def pump():
            rate_sent = None
            while True:
                rate, pcm = await queue.get()
                if rate != rate_sent:
                    await ws.send_json({"rate": rate})
                    rate_sent = rate
                await ws.send_bytes(pcm)

        async def watch():
            # Detecta el cierre aunque no esté llegando audio (pausa larga, sala en silencio).
            while True:
                if (await ws.receive())["type"] == "websocket.disconnect":
                    return

        tasks = [asyncio.create_task(pump()), asyncio.create_task(watch())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            hub.listeners.get(key, set()).discard(queue)

    @app.websocket("/api/sessions/{sid}/audio")
    async def browser_audio(ws: WebSocket, sid: str, token: str = ""):
        worker = hub.workers.get(sid)
        if hub.token and token != hub.token:
            await ws.close(code=4401)
            return
        if not worker or not worker.queue_source:
            await ws.close(code=4404)
            return
        await ws.accept()
        worker.queue_source.connected += 1
        try:
            while True:
                worker.queue_source.put(await ws.receive_bytes())
        except WebSocketDisconnect:
            pass
        finally:
            worker.queue_source.connected -= 1

    return app


__all__ = ["Hub", "LocalPublisher", "create_app"]
