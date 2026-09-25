# Guía para agentes de código

Instrucciones para agentes (Cline, Claude Code, Codex…) y personas que contribuyan a Subtitula.

## Entorno y verificación

```bash
pip install -e '.[dev]'      # Python 3.11+, necesita ffmpeg en el PATH
pytest -q                    # no usa la API: los tests corren con el motor de prueba
subtitula serve --engine fake   # levanta todo sin clave, en http://localhost:8000
```

Antes de dar un cambio por terminado: `pytest -q` en verde. Si el cambio toca la Live API o los motores de Gemini, probalo también contra la API real con una clave en `.env`:

- `python scripts/check_gemini.py`: transcripción y traducción, por modelo.
- `subtitula file samples/thor-schaeff-multilingual-agents-en.mp3 --language en --both`: la charla de ejemplo por el motor en vivo.
- `python scripts/drift_test.py <archivo> --language en --targets es`: demora minuto a minuto.

## Mapa del código

| Archivo | Qué hace |
|---|---|
| `subtitula/live.py` | Motor por defecto (`gemini-live`): sesiones Live por idioma, pistas, demanda, pausa en silencio, voz |
| `subtitula/worker.py` | Worker por tramos (segmentador → motor → publicación en orden) y base común de estado y costo |
| `subtitula/engines/` | Motores por tramos: `gemini` (transcribe + traducción con pool), `local` (faster-whisper + Gemma), `fake` |
| `subtitula/hub.py` | FastAPI: SSE para el público, ingesta de workers remotos, voz por WebSocket, panel, QR, exportación |
| `subtitula/captions.py` | Modelo de subtítulo, pistas por idioma y exportación SRT/VTT/TXT |
| `subtitula/glossary.py`, `pricing.py`, `summary.py` | Corrección de glosario, precios oficiales por modelo, "¿Qué me perdí?" |
| `subtitula/web/` | Páginas estáticas: público, overlay, pantalla, panel, envío de audio |

## Convenciones

- Comentarios y textos de la interfaz en español rioplatense, en voz activa y sin tecnicismos para el público.
- Una sala no puede tirar abajo a las demás: los errores de una sesión se cuentan en el estado y se reintenta.
- Cualquier número que se publique (latencia, costo, carga) sale de una medición reproducible con un script de `scripts/`, y el resultado va a `docs/evidencia/`.
- Precios: sólo en `subtitula/pricing.py`, con la fuente y la fecha.
- No agregar dependencias sin necesidad. La interfaz no usa frameworks ni pasos de build.
