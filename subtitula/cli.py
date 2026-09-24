"""Línea de comandos.

  subtitula serve                 hub + todos los escenarios de sessions.yaml en un proceso
  subtitula hub                   sólo el hub (vista de audiencia, overlay, panel, API)
  subtitula worker --session ID   un escenario que publica en un hub remoto (--hub URL)
  subtitula file charla.mp3       subtitula un archivo en la terminal y exporta SRT/VTT/TXT
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from .config import SessionConfig, load_config


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default=os.environ.get("SUBTITULA_CONFIG", "config/sessions.yaml"))
    p.add_argument("--glossary", default=os.environ.get("SUBTITULA_GLOSSARY", "config/glossary.yaml"))
    p.add_argument("--engine", help="gemini (por defecto), local o fake")
    p.add_argument("-v", "--verbose", action="store_true")


def _serve(args, run_workers: bool) -> None:
    import uvicorn

    from .hub import create_app

    cfg = load_config(args.config, args.glossary)
    if args.engine:
        cfg.engine = args.engine
    app = create_app(cfg, token=os.environ.get("SUBTITULA_TOKEN", ""), run_workers=run_workers)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info" if args.verbose else "warning")


async def _worker(args) -> None:
    from .engines import create_engine
    from .worker import HttpPublisher, SessionWorker

    cfg = load_config(args.config, args.glossary)
    session = cfg.session(args.session) or SessionConfig(id=args.session, name=args.name or args.session)
    if args.source:
        session.source = args.source
    if not session.source:
        sys.exit(f"La sesión {args.session} no tiene fuente: pasala con --source")
    engine = create_engine(args.engine or cfg.engine)
    publisher = HttpPublisher(args.hub, os.environ.get("SUBTITULA_TOKEN", ""))
    worker = SessionWorker(session, engine, publisher, cfg.languages, [*cfg.glossary])
    print(f"[{session.id}] {session.source} → {args.hub} (motor {engine.name})", flush=True)
    await worker.run()


async def _file(args) -> None:
    from .captions import Caption, to_srt, to_txt, to_vtt
    from .engines import create_engine
    from .worker import SessionWorker

    cfg = load_config(args.config, args.glossary)
    path = Path(args.path)
    session = SessionConfig(id=path.stem, name=args.name or path.stem, source=str(path),
                            language=args.language, realtime=args.realtime)
    languages = args.languages.split(",") if args.languages else cfg.languages
    caps: list[Caption] = []
    show = args.show

    class Printer:
        async def caption(self, cap: Caption) -> None:
            caps.append(cap)
            line = cap.in_lang(show)
            print(f"\033[2m{cap.start:7.1f}s {cap.lang} {cap.latency_ms:5d}ms\033[0m  {line}", flush=True)
            if show == "original" and args.both:
                for lang, text in cap.tr.items():
                    print(f"{'':22}\033[33m{lang}\033[0m  {text}", flush=True)

        async def status(self, session: str, status: dict) -> None:
            return None

    engine = create_engine(args.engine or cfg.engine)
    await SessionWorker(session, engine, Printer(), languages, cfg.glossary).run()
    await engine.close()
    out = Path(args.out or path.parent)
    out.mkdir(parents=True, exist_ok=True)
    for lang in ["original", *languages]:
        for ext, render in (("srt", to_srt), ("vtt", to_vtt), ("txt", to_txt)):
            (out / f"{path.stem}.{lang}.{ext}").write_text(render(caps, lang), encoding="utf-8")
    print(f"\n{len(caps)} subtítulos. Exportados en {out}/{path.stem}.<idioma>.srt|vtt|txt")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="subtitula", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name, help_ in (("serve", "hub + escenarios en un proceso"), ("hub", "sólo el hub")):
        p = sub.add_parser(name, help=help_)
        _common(p)
        p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
        p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))

    p = sub.add_parser("worker", help="un escenario que publica en un hub")
    _common(p)
    p.add_argument("--session", required=True)
    p.add_argument("--hub", default=os.environ.get("SUBTITULA_HUB", "http://localhost:8000"))
    p.add_argument("--source", help="pisa la fuente de sessions.yaml")
    p.add_argument("--name")

    p = sub.add_parser("file", help="subtitular un archivo en la terminal")
    _common(p)
    p.add_argument("path")
    p.add_argument("--name")
    p.add_argument("--language", default="auto")
    p.add_argument("--languages", help="idiomas de salida, ej. es,en,pt")
    p.add_argument("--show", default="original", help="idioma a mostrar en la terminal")
    p.add_argument("--both", action="store_true", help="mostrar también las traducciones")
    p.add_argument("--realtime", action="store_true", help="leer a velocidad real (como un vivo)")
    p.add_argument("--out", help="carpeta para los SRT/VTT/TXT")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.cmd in ("serve", "hub"):
        _serve(args, run_workers=args.cmd == "serve")
    elif args.cmd == "worker":
        asyncio.run(_worker(args))
    elif args.cmd == "file":
        asyncio.run(_file(args))


if __name__ == "__main__":
    main()
