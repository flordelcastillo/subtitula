"""Punta a punta: dos salas en simultáneo, motor falso, hub real, SSE y exportación."""

import json
import os
import time

from fastapi.testclient import TestClient

from subtitula.config import AppConfig, SessionConfig
from subtitula.hub import create_app


def make_app(tmp_path, wav):
    os.environ["SUBTITULA_FAKE_DELAY"] = "0.05"
    cfg = AppConfig(
        languages=["es", "en", "pt"],
        engine="fake",
        data_dir=tmp_path / "data",
        glossary=["Nerdearla"],
        sessions=[SessionConfig(id=f"sala-{i}", name=f"Sala {i}", source=str(wav), realtime=False) for i in (1, 2)],
    )
    return create_app(cfg, token="secreto", run_workers=True)


def wait_for(client, sid, n, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        caps = client.get(f"/api/sessions/{sid}/captions").json()["captions"]
        if len(caps) >= n:
            return caps
        time.sleep(0.1)
    raise AssertionError(f"{sid}: no llegaron {n} subtítulos")


def test_two_sessions_in_parallel(tmp_path, talk_wav):
    with TestClient(make_app(tmp_path, talk_wav)) as client:
        for sid in ("sala-1", "sala-2"):
            caps = wait_for(client, sid, 4)
            assert [c["seq"] for c in caps] == sorted(c["seq"] for c in caps)
            assert all(c["tr"]["es"].startswith("[es]") for c in caps)
        sessions = client.get("/api/sessions").json()
        assert {s["id"] for s in sessions["sessions"]} == {"sala-1", "sala-2"}
        assert [l["code"] for l in sessions["languages"]] == ["es", "en", "pt"]

        srt = client.get("/api/sessions/sala-1/export.srt?lang=es")
        assert srt.status_code == 200 and "-->" in srt.text and "[es]" in srt.text
        assert client.get("/api/sessions/sala-1/export.txt?lang=pt").text.startswith("[pt]")
        qr = client.get("/api/sessions/sala-1/qr.svg").text
        # Sin xmlns el navegador no lo muestra dentro de un <img> (pasó con el panel y la pantalla).
        assert qr.startswith("<svg") and 'xmlns="http://www.w3.org/2000/svg"' in qr
        metrics = client.get("/metrics").text
        assert '# TYPE subtitula_captions_total gauge' in metrics and 'subtitula_live{sala="sala-1"}' in metrics
        live = client.get("/api/sessions/sala-1/live.txt?lang=es&lines=2").text.splitlines()
        assert len(live) == 2 and all(line.startswith("[es]") for line in live)

        status = client.get("/api/status").json()
        row = next(r for r in status["sessions"] if r["id"] == "sala-1")
        assert row["engine"] == "fake" and row["captions"] >= 4

        # Los subtítulos quedan en disco para exportar aunque se reinicie el servidor.
        lines = (tmp_path / "data" / "sala-1.jsonl").read_text().splitlines()
        assert json.loads(lines[0])["session"] == "sala-1"


def test_ingest_requires_token(tmp_path, talk_wav):
    with TestClient(make_app(tmp_path, talk_wav)) as client:
        cap = {"session": "remota", "seq": 1, "start": 0, "end": 1, "lang": "en", "text": "hi", "tr": {"es": "hola"}}
        assert client.post("/api/ingest/remota", json={"type": "caption", "caption": cap}).status_code == 401
        ok = client.post("/api/ingest/remota", json={"type": "caption", "caption": cap},
                         headers={"Authorization": "Bearer secreto"})
        assert ok.status_code == 200
        # Una sala que no estaba en la config aparece sola cuando su worker publica.
        assert "remota" in {s["id"] for s in client.get("/api/sessions").json()["sessions"]}
        reply = client.post("/api/ingest/remota", json={"type": "status", "status": {"state": "live"}},
                            headers={"Authorization": "Bearer secreto"}).json()
        assert "glossary" in reply


def test_live_glossary_update_reaches_worker(tmp_path, talk_wav):
    app = make_app(tmp_path, talk_wav)
    with TestClient(app) as client:
        r = client.put("/api/sessions/sala-1/glossary", json={"terms": ["Nerdearla", "Thor Schaeff"]},
                       headers={"Authorization": "Bearer secreto"})
        assert r.json()["glossary"] == ["Nerdearla", "Thor Schaeff"]
        assert app.state.hub.workers["sala-1"].glossary == ["Nerdearla", "Thor Schaeff"]


def test_sse_stream_replays_backlog_and_goes_live(tmp_path, talk_wav):
    """Contra un uvicorn real: el TestClient no sabe cortar un stream infinito."""
    import socket
    import threading

    import httpx
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(make_app(tmp_path, talk_wav), port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if httpx.get(f"{base}/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        got = []
        with httpx.stream("GET", f"{base}/api/sessions/sala-2/stream", timeout=15) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    got.append(json.loads(line[6:])["seq"])
                if len(got) >= 4:
                    break
        assert got == sorted(got) and len(set(got)) == 4
        # Reconexión con Last-Event-ID: sólo llega lo posterior.
        with httpx.stream("GET", f"{base}/api/sessions/sala-2/stream", timeout=15,
                          headers={"Last-Event-ID": str(got[1])}) as resp:
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    assert json.loads(line[6:])["seq"] == got[1] + 1
                    break
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_two_stage_publishes_original_then_translation(tmp_path, talk_wav, monkeypatch):
    """Motor en dos etapas: el original sale primero y la traducción actualiza la misma línea."""
    monkeypatch.setenv("SUBTITULA_FAKE_TWO_STAGE", "1")
    app = make_app(tmp_path, talk_wav)
    hub = app.state.hub
    seen: list[dict] = []
    original = hub.caption

    async def spy(cap):
        seen.append(cap.to_dict())
        return await original(cap)

    hub.caption = spy
    with TestClient(app) as client:
        deadline = time.time() + 15
        while time.time() < deadline:
            caps = client.get("/api/sessions/sala-1/captions").json()["captions"]
            if len(caps) >= 4 and not any(c["pending"] for c in caps):
                break
            time.sleep(0.1)
        first = [c for c in seen if c["session"] == "sala-1" and c["seq"] == 1]
        assert first[0]["pending"] is True and first[0]["tr"] == {}
        assert first[-1]["pending"] is False and first[-1]["tr"]["es"].startswith("[es]")
        assert first[-1]["lang"] == "en" and first[-1]["tr_latency_ms"] >= first[-1]["latency_ms"]
        # Sin duplicados: cada número aparece una sola vez, ya traducido.
        seqs = [c["seq"] for c in caps]
        assert seqs == sorted(set(seqs))
        assert all(c["tr"].get("pt") for c in caps)
        status = next(r for r in client.get("/api/status").json()["sessions"] if r["id"] == "sala-1")
        assert status["translation_p50_ms"] is not None

    # Al reiniciar, el archivo se relee quedándose con la última versión de cada línea.
    from subtitula.hub import Hub
    reloaded = Hub(app.state.hub.config)
    caps = reloaded.captions["sala-1"]
    assert [c.seq for c in caps] == sorted({c.seq for c in caps})
    assert all(not c.pending for c in caps)


def test_summary_is_cached_and_generated_once(tmp_path, talk_wav, monkeypatch):
    """"¿Qué me perdí?": una sola generación aunque lo pidan muchos a la vez."""
    import asyncio

    from subtitula.summary import Summarizer

    calls = []

    async def fake_generate(self, name, speaker, captions, lang, minutes):
        calls.append(lang)
        await asyncio.sleep(0.2)
        return {"bullets": [f"resumen en {lang}"], "empty": False, "generated_at": time.time(), "model": "gemma-4"}

    monkeypatch.setattr(Summarizer, "_generate", fake_generate)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with TestClient(make_app(tmp_path, talk_wav)) as client:
        assert client.get("/api/sessions/sala-1/summary?lang=es").status_code == 503  # sin clave, error claro
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(8) as pool:
            replies = list(pool.map(lambda _: client.get("/api/sessions/sala-1/summary?lang=es").json(), range(8)))
        assert all(r["bullets"] == ["resumen en es"] for r in replies)
        assert calls == ["es"]
        client.get("/api/sessions/sala-1/summary?lang=pt")
        assert calls == ["es", "pt"]


def test_glossary_suggestions_need_token_and_key(tmp_path, talk_wav, monkeypatch):
    import subtitula.hub as hubmod

    async def fake_suggest(engine, name, speaker, topic, extra, current):
        return ["ElevenLabs", "Thor Schaeff"]

    monkeypatch.setattr(hubmod, "suggest_glossary", fake_suggest)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with TestClient(make_app(tmp_path, talk_wav)) as client:
        url = "/api/sessions/sala-1/glossary/suggest"
        assert client.post(url, json={}).status_code == 401  # sin token de operación
        auth = {"Authorization": "Bearer secreto"}
        assert client.post(url, json={}, headers=auth).status_code == 503  # sin clave de Gemini
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        monkeypatch.setattr(hubmod.Summarizer, "_engine", lambda self: None)
        reply = client.post(url, json={"text": "charla sobre agentes de voz"}, headers=auth).json()
        assert reply == {"suggested": ["ElevenLabs", "Thor Schaeff"]}


def test_listen_websocket_gets_interpretation_audio(tmp_path, talk_wav):
    """La interpretación hablada llega sólo a quien escucha ese idioma."""
    app = make_app(tmp_path, talk_wav)
    hub = app.state.hub
    with TestClient(app) as client:
        with client.websocket_connect("/api/sessions/sala-1/listen?lang=es") as ws:
            assert ws.receive_json() == {"session": "sala-1", "lang": "es"}
            client.portal.call(hub.speech, "sala-1", "pt", b"\x01\x00" * 10, 24000)  # otro idioma: no llega
            client.portal.call(hub.speech, "sala-1", "es", b"\x02\x00" * 10, 24000)
            assert ws.receive_json() == {"rate": 24000}
            assert ws.receive_bytes() == b"\x02\x00" * 10
            info = next(s for s in client.get("/api/sessions").json()["sessions"] if s["id"] == "sala-1")
            assert info["listeners"] == 1
        deadline = time.time() + 3
        while time.time() < deadline and hub.listeners.get(("sala-1", "es")):
            time.sleep(0.05)
        assert not hub.listeners.get(("sala-1", "es"))
