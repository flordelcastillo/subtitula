# Subtitula

Subtítulos y traducción simultánea en vivo, open source, para conferencias con muchos escenarios a la vez.

Cada escenario manda su audio (stream, micrófono, encoder o una pestaña del navegador) a la [Gemini Live API](https://ai.google.dev/gemini-api/docs/live), que devuelve palabra por palabra el original y la interpretación a español, inglés y portugués, mientras la persona habla. El público escanea un QR y lee los subtítulos en el celular, en el idioma que elija. Producción suma un overlay para OBS/vMix, un panel con el estado de cada sala y la transcripción completa en SRT, VTT o texto al terminar.

Hecho para la [Vibeathon de Nerdearla 2026](https://nerdearla.devpost.com). Licencia Apache 2.0.

> **English summary.** Subtitula is an open source live captioning and simultaneous interpretation system for multi-track conferences. Each stage streams its audio into one Gemini Live API session per target language (`gemini-3.5-live-translate-preview`): the original transcript and the translation arrive word by word while the speaker talks, typically 0.3 to 1 s after they pause. Each language is its own caption track, split into natural sentences of at most 84 characters. A lightweight hub fans captions out over Server-Sent Events to phones (pick stage + language), an OBS/vMix overlay and a production dashboard (audio level, latency p50/p90, errors, live sessions, measured cost). Transcripts export to SRT/VTT/TXT. Scale by running one worker container per stage. Fallback engines: chunked `gemini-3.5-transcribe` + Flash-Lite/Gemma translation, and fully local faster-whisper + Gemma via Ollama.

## Qué resuelve

| Pedido de la vibeathon | Cómo lo resuelve Subtitula |
|---|---|
| Audio en vivo de al menos una fuente | Archivo, micrófono, HLS/Icecast, RTMP/SRT/UDP desde OBS o vMix, YouTube en vivo, o el navegador de la sala (`/enviar/<sala>`) |
| Transcripción en tiempo real del original | Palabra por palabra con la Gemini Live API; la línea crece en pantalla mientras la persona habla |
| Traducción inglés → español (y español → inglés) | Interpretación simultánea con `gemini-3.5-live-translate-preview`, una sesión por idioma de destino; si alguien pregunta directamente en el idioma de destino, se muestra tal cual |
| Mostrar los subtítulos | Vista web para el público, overlay para el stream y la terminal (`subtitula file`) |
| Dos o más sesiones en simultáneo | Un worker independiente por sala; probado con 2 salas en vivo (4 sesiones Live) contra Gemini y con 20 salas y 500 personas conectadas en la prueba de carga (ver [Escala](#escala)) |
| Opcionales | Portugués, glosario editable en vivo, exportación SRT/VTT/TXT, overlay para OBS/vMix y panel de monitoreo |

## Probarlo en 2 minutos

Requisitos: Python 3.11 o superior, `ffmpeg` y una clave de Gemini de [Google AI Studio](https://aistudio.google.com/apikey).

```bash
git clone https://github.com/flordelcastillo/subtitula && cd subtitula
python -m venv venv && . venv/bin/activate
pip install -e .
echo GEMINI_API_KEY=tu-clave > .env
subtitula serve
```

El motor por defecto (`gemini-live`) mantiene una sesión abierta por sala e idioma y no hace un pedido por frase, así que no choca con el límite de pedidos por minuto. En las pruebas, dos salas con dos idiomas cada una (4 sesiones) anduvieron con una clave común. Para un evento con muchas salas conviene activar la facturación del proyecto en AI Studio: sube el límite de sesiones simultáneas. Las dos salas de ejemplo gastaron US$ 0,002 cada una en el primer minuto, según los tokens que informó la API.

Abrí <http://localhost:8000>. Hay dos salas de ejemplo, en loop, con fragmentos reales de Nerdearla 2025: una charla en inglés ([Thor Schaeff, *Building Multilingual Conversational AI Agents*](https://www.youtube.com/watch?v=GkVjMxYi5gA)) y otra en español ([Miguel Ángel Durán, *Programming is dead. Long live programming!*](https://www.youtube.com/watch?v=zynI57qVj-U)).

| Página | Para quién |
|---|---|
| `/` y `/s/<sala>?lang=es` | Público: elige sala e idioma, cambia el tamaño de letra, tema claro u oscuro, descarga la charla |
| `/overlay/<sala>?lang=es` | Fuente de navegador en OBS o vMix (fondo transparente) |
| `/admin` | Producción: estado, audio, latencia, errores, público, costo, QR y glosario por sala |
| `/enviar/<sala>` | La compu de la sala manda el audio desde el navegador |

Sin clave de Gemini se puede ver todo funcionando con el motor de prueba: `subtitula serve --engine fake`.

### Subtitular un archivo desde la terminal

```bash
subtitula file samples/thor-schaeff-multilingual-agents-en.mp3 --language en --both
```

Muestra cada línea del original (en blanco) y de cada traducción (en amarillo), deja `.srt`, `.vtt` y `.txt` por idioma al lado del archivo y al final informa la demora medida y los tokens usados. Con esto se hicieron los subtítulos en inglés del video demo.

## Cómo funciona

```
 escenario 1 ─ ffmpeg ─┬─ sesión Live → es ─┐
                       └─ sesión Live → pt ─┤
 escenario 2 ─ ffmpeg ─┬─ sesión Live → en ─┼─► hub ─ SSE ─► celulares, overlay OBS, panel
                       └─ sesión Live → pt ─┤      └─► data/<sala>.jsonl ─► SRT / VTT / TXT
 escenario N ─ navegador (WebSocket) ─ …    ─┘
```

**Ingesta.** ffmpeg lleva cualquier fuente a PCM mono de 16 kHz. Si una fuente en vivo se corta, el worker reconecta con espera exponencial y lo avisa en el panel.

**Motor en vivo** (`subtitula/live.py`, `gemini-live`, por defecto). Cada sala abre una sesión de `gemini-3.5-live-translate-preview` por idioma de destino y le manda el audio en bloques de 100 ms. Cada sesión devuelve dos flujos de texto: la transcripción del original (se toma de una sola sesión) y la interpretación a su idioma. El glosario entra como `custom_vocabulary` del reconocedor y, si la sala tiene idioma conocido, se le indica para que no confunda las primeras palabras.

- **Una pista por idioma.** El original y cada traducción arman sus propias líneas: se cortan al terminar una oración (aunque el fin de oración venga en medio de un fragmento), en una coma si la línea ya es larga, a los 84 caracteres (dos renglones de 42, la norma de subtitulado) o tras 2 s sin palabras nuevas. Así el español se lee en frases de español y no como inglés partido en los lugares del inglés. La línea abierta crece en pantalla palabra por palabra.
- **Preguntas en otro idioma.** Con `echo_target_language`, si alguien habla directamente en el idioma de destino (por ejemplo, una pregunta del público en español durante una charla en inglés), la sesión la repite tal cual en lugar de dejar un hueco.
- **Sesiones largas.** La sesión usa compresión de contexto con ventana deslizante para aguantar una charla entera y, si el servidor la corta, se reabre retomando el contexto (session resumption).
- **Demora medida.** El panel muestra cuánto tarda en llegar la última palabra de una frase desde que el orador hace una pausa. En las pruebas con las dos charlas de ejemplo: 0,3 a 0,5 s en p50 y 0,6 a 0,8 s en p90 para el original, y 0,3 a 0,4 s en p50 y 0,9 a 1,1 s en p90 para la traducción. Al arrancar, la primera frase tarda unos 3 s.

Los motores siguientes quedan como alternativa (`--engine gemini`, `--engine local`).

**Segmentador** (`subtitula/segmenter.py`, motores por tramos). Mide la energía en frames de 30 ms contra un piso de ruido que se adapta a la sala. Cierra un tramo cuando el orador hace una pausa de 300 ms después de al menos 1,2 s de habla. Si nadie hace pausa, corta a los 5 s en el frame más silencioso del último segundo y medio, así nunca parte una palabra. Los tramos sin voz (aplausos, silencio, música) no se mandan al modelo y no cuestan nada.

**Motor por tramos** (`subtitula/engines/gemini.py`, `--engine gemini`). Trabaja en dos etapas:

1. **Original.** `gemini-3.5-transcribe`, el modelo de Gemini dedicado a transcripción, pasa el tramo a texto en unos 2 a 3 segundos. El glosario de la sala entra como `custom_vocabulary` del reconocedor, así que *Nerdearla*, *kubectl* o el nombre de quien habla se reconocen bien desde el audio. El modo `SMART` saca muletillas y repeticiones. El original se publica apenas vuelve.
2. **Traducción.** Un modelo de texto traduce ese tramo a los idiomas del evento, con el título de la charla, el glosario y los tramos anteriores como contexto. Cuando termina, la línea que el público ya estaba leyendo se actualiza en su lugar. Mientras tanto se muestra el original atenuado, así nunca queda un hueco. El overlay del stream, en cambio, espera la traducción.

Cada etapa usa un pool de modelos (por defecto `gemini-flash-lite-latest`, `gemini-3.1-flash-lite` y `gemma-4-26b-a4b-it` para traducir). Si un modelo responde 429 (sin cuota) o 503 (saturado), queda en espera y el pedido pasa al siguiente. Con `SUBTITULA_GEMINI_MODE=single` se usa una sola llamada de audio a JSON con transcripción y traducciones.

Se procesan hasta 3 tramos en paralelo y se publican siempre en orden. Si el modelo no da abasto, el worker saltea un tramo antes que acumular atraso (y lo muestra en el panel). En un vivo, llegar tarde es peor que perder una frase. Leyendo un archivo, en cambio, espera y reintenta.

**Hub** (`subtitula/hub.py`). Sólo mueve texto. Guarda cada subtítulo en `data/<sala>.jsonl` y lo reparte por Server-Sent Events. Quien entra tarde recibe las últimas 40 líneas; quien pierde la conexión reconecta con `Last-Event-ID` y recibe sólo lo que le faltó.

**Motor local** (`subtitula/engines/local.py`). Para correr 100% offline: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) transcribe y [Gemma](https://ai.google.dev/gemma) traduce vía [Ollama](https://ollama.com).

```bash
pip install -e '.[local]'
ollama pull gemma3:4b
OLLAMA_URL=http://localhost:11434 subtitula serve --engine local
```

Para tiempo real en varias salas hace falta GPU. En una CPU de notebook, el modelo `small` tarda unos 7 s por tramo.

## Configuración

`config/sessions.yaml`:

```yaml
event: Nerdearla 2026
languages: [es, en, pt]        # idiomas de salida
engine: gemini
sessions:
  - id: auditorio
    name: "Keynote de apertura"
    speaker: Nombre Apellido
    topic: Kubernetes, observabilidad
    source: srt://0.0.0.0:9000?mode=listener   # OBS/vMix mandan por SRT
    language: en                               # o auto
    glossary: [OpenTelemetry, Grafana]
```

Fuentes posibles en `source`:

| Valor | Uso |
|---|---|
| `samples/charla.mp3` | Archivo (se lee a velocidad real; `loop: true` para repetir) |
| `mic` o `mic:<dispositivo>` | Micrófono o placa de audio de la máquina |
| `https://…/stream.m3u8` | HLS, Icecast o cualquier URL que abra ffmpeg |
| `rtmp://…`, `srt://…`, `udp://…` | Salida de un encoder o de la consola de sonido |
| `https://www.youtube.com/watch?v=…` | YouTube en vivo o grabado (usa `yt-dlp`) |
| `browser` | Audio desde la página `/enviar/<sala>` |

`config/glossary.yaml` tiene los términos globales. Durante el evento se corrigen desde `/admin`, sala por sala, sin reiniciar nada: el cambio llega al worker en menos de 2 segundos, aunque corra en otra máquina.

Variables de entorno:

| Variable | Para qué |
|---|---|
| `GEMINI_API_KEY` | Clave de Gemini |
| `SUBTITULA_LIVE_MODEL` | Modelo de la Live API (por defecto `gemini-3.5-live-translate-preview`) |
| `SUBTITULA_ASR_MODEL` | Modelo(s) de transcripción, separados por coma (por defecto `gemini-3.5-transcribe`) |
| `SUBTITULA_GEMINI_MODEL` | Modelos de traducción, separados por coma, en orden de preferencia |
| `SUBTITULA_GEMINI_MODE` | `asr` (dos etapas, por defecto) o `single` (una llamada de audio a JSON) |
| `SUBTITULA_TOKEN` | Protege la ingesta de workers, el envío de audio y el glosario |
| `SUBTITULA_PUBLIC_URL` | URL pública que se codifica en los QR |
| `SUBTITULA_PRICE_INPUT_PER_M`, `SUBTITULA_PRICE_OUTPUT_PER_M` | Precio por millón de tokens, para el costo del panel |
| `SUBTITULA_ENGINE` | `gemini-live` (por defecto), `gemini`, `local` o `fake` |

## Escala

Lo caro (audio y modelo) vive en los workers, uno por sala y sin estado compartido. El hub sólo reparte texto. Por eso escalar es sumar workers:

```bash
subtitula hub --port 8000                                    # una vez
subtitula worker --session auditorio --hub http://hub:8000   # uno por sala, en cualquier máquina
```

`docker-compose.yml` levanta el hub y un contenedor por sala. Para sumar una sala se copia un bloque `worker-*`:

```bash
cp .env.example .env   # completar GEMINI_API_KEY y SUBTITULA_TOKEN
docker compose up --build
```

Prueba de carga incluida, que no gasta API porque usa el motor de prueba con la misma forma de tráfico que Gemini:

```bash
python scripts/loadtest.py --stages 20 --viewers 25 --seconds 45
```

Resultado en una notebook de 8 núcleos: 20 salas y 500 personas conectadas, 6.375 entregas sin tramos salteados ni errores. La entrega hub → pantalla fue de 6 ms en p50 y 18 ms en p99, con el 27% de un núcleo, todo en un solo proceso.

Cuánto cuesta: Gemini cuenta el audio a 32 tokens por segundo, unos 115 mil tokens por hora de charla, más el texto del prompt y la respuesta. El panel muestra el costo real de cada sala a partir de los tokens que informa la API, así que no hace falta estimarlo.

Para más de 20 o 30 salas o miles de personas: varios workers por máquina, el hub detrás de un proxy con `proxy_buffering off` para SSE, y un CDN delante de las páginas estáticas.

## Operación durante el evento

1. Antes de abrir, `/admin` con todas las salas en verde y el vúmetro moviéndose.
2. Proyectar o imprimir el QR de cada sala (link *QR* en el panel). Apunta a `/s/<sala>`.
3. En OBS o vMix, agregar una fuente de navegador con `/overlay/<sala>?lang=es` (1920×1080). Parámetros: `lines`, `size`, `hide`, `pos=top`, `box=0`.
4. Si un nombre sale mal escrito, se agrega al glosario de la sala desde el panel y se corrige en el próximo tramo.
5. Una fila en rojo avisa de fuente caída, más de 20 s sin audio, latencia p90 por encima de 6 s o tramos salteados.
6. Al terminar, la charla se descarga en `/api/sessions/<sala>/export.srt?lang=es` (o `.vtt` o `.txt`, en cualquier idioma).

## Desarrollo

```bash
pip install -e '.[dev]'
pytest
```

Los tests cubren el segmentador con audio sintético, las exportaciones, dos salas en paralelo de punta a punta, el motor en dos etapas (original primero, traducción que actualiza la misma línea), el armado de pistas del motor en vivo (cortes por oración, tope de 84 caracteres, exportación por pista, demora medida), la reconexión SSE con `Last-Event-ID`, el token de ingesta y la actualización del glosario en vivo.

## Licencia

[Apache 2.0](LICENSE). Los fragmentos de audio en `samples/` son de charlas públicas de Nerdearla 2025 y se incluyen sólo como material de prueba.
