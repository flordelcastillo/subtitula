# Subtitula

Subtítulos y traducción simultánea en vivo, open source, para conferencias con muchos escenarios a la vez.

Cada escenario manda su audio (stream, micrófono, encoder o una pestaña del navegador) a la [Gemini Live API](https://ai.google.dev/gemini-api/docs/live), que devuelve palabra por palabra el original y la interpretación a español, inglés y portugués, mientras la persona habla. El público escanea un QR y lee los subtítulos en el celular, en el idioma que elija. Producción suma un overlay para OBS/vMix, un panel con el estado de cada sala y la transcripción completa en SRT, VTT o texto al terminar.

Hecho para la [Vibeathon de Nerdearla 2026](https://nerdearla26.devpost.com). Licencia Apache 2.0.

> **English summary.** Subtitula is an open source live captioning and simultaneous interpretation system for multi-track conferences. Each stage streams its audio into one Gemini Live API session per target language (`gemini-3.5-live-translate-preview`): the original transcript and the translation arrive word by word while the speaker talks, typically 0.3 to 1 s after they pause. Each language is its own caption track, split into natural sentences of at most 84 characters. Phones can also play the spoken interpretation that Live Translate already generates (headphones on, no extra cost), and a "What did I miss?" button summarizes the last 5 minutes in the reader's language with Gemma. Secondary languages open a Live session only while someone reads or listens to them, and long silences are not streamed. Measured over 10 continuous minutes per talk: 0.34 s p50 / under 0.9 s p90 from the speaker's pause to the last translated word, with no accumulated drift ([evidence](docs/evidencia)). A lightweight hub fans captions out over Server-Sent Events to phones (pick stage + language), an OBS/vMix overlay and a production dashboard (audio level, latency p50/p90, errors, live sessions, real cost per room from official prices). Transcripts export to SRT/VTT/TXT. Scale by running one worker container per stage. Fallback engines: chunked `gemini-3.5-transcribe` + Flash-Lite/Gemma translation, and fully local faster-whisper + Gemma via Ollama.

## Los cinco criterios, con evidencia

| Criterio | Qué hace Subtitula | Evidencia |
|---|---|---|
| **Calidad** | Interpretación con Live Translate. El glosario de cada sala entra como vocabulario del reconocedor y, además, corrige la ortografía de nombres y términos en todas las pistas, incluida la traducción. Cada idioma arma sus propias líneas, cortadas por oración y con 84 caracteres como máximo (dos renglones de 42, la norma de subtitulado). Las preguntas del público en el idioma de destino se muestran tal cual | Ejemplo real: "if I pipe the audio out on the HDMI, are you able to hear it on the stream?" → "Si saco el audio por el HDMI, ¿puedes escucharlo en la transmisión?". Tests de glosario y de pistas en `tests/test_live.py` |
| **Latencia** | El texto llega palabra por palabra mientras la persona habla. Desde que el orador hace una pausa hasta que llega la última palabra de la frase: **0,34 s en p50 y 0,7 a 0,9 s en p90 para el original, y 0,29 a 0,34 s en p50 y 0,76 a 0,89 s en p90 para la traducción**. En 10 minutos seguidos no hay atraso acumulado (el peor minuto dio 2,1 s de p90) | [`docs/evidencia/`](docs/evidencia), medido con [`scripts/drift_test.py`](scripts/drift_test.py) sobre 10 minutos de cada charla de ejemplo |
| **Escalabilidad** | Un worker por sala sin estado compartido y un hub que sólo mueve texto. Los idiomas sin público no abren sesión y el audio en silencio no se manda. Costo real por sala en el panel | 4 sesiones Live simultáneas contra Gemini con 0 errores. Prueba de carga palabra por palabra: 20 salas y 500 personas, 4.179 entregas por segundo, 7 ms p50 del hub a la pantalla ([Escala](#escala)). US$ 2,2 por idioma y por hora ([Costos](#costos)) |
| **Despliegue y operación** | `pip install`, una clave en `.env` y `subtitula serve`, o Docker Compose con un contenedor por sala. La sala puede mandar el audio desde un navegador, sin instalar nada. Panel con vúmetro, demoras p50/p90, errores, sesiones, costo, QR y glosario editable en vivo. Overlay para OBS/vMix, `live.txt` para títulos y fondo de croma | Secciones [Operación](#operación-durante-el-evento) y [Qué pasa si…](#qué-pasa-si) |
| **Innovación** | **Escuchar la interpretación** con auriculares desde el celular (la voz que Live Translate ya genera). **"¿Qué me perdí?"**: resumen de los últimos 5 minutos en tu idioma, con Gemma. Idiomas bajo demanda. Tres motores: en vivo, por tramos y 100% local con faster-whisper y Gemma | Capturas y video demo |

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

El motor por defecto (`gemini-live`) mantiene una sesión abierta por sala e idioma y no hace un pedido por frase, así que no choca con el límite de pedidos por minuto. Live Translate no tiene plan gratuito: hace falta un proyecto con facturación activa en AI Studio. Las pruebas de este README se hicieron así, con 4 sesiones simultáneas y 0 errores. Según la [guía de Google para traducir transmisiones con Live Translate](https://github.com/google-gemini/gemini-live-translate-livekit), el nivel inicial admite pocas conexiones simultáneas y un evento con varias salas e idiomas necesita subir de tier; con idiomas bajo demanda se abren sólo las sesiones que alguien usa. Sin clave se puede probar todo con `--engine fake`, y con la clave gratuita anda el motor por tramos (`--engine gemini`). El costo de cada sala se ve en `/admin` (ver [Costos](#costos)).

Abrí <http://localhost:8000>. Hay dos salas de ejemplo, en loop, con fragmentos reales de Nerdearla 2025: una charla en inglés ([Thor Schaeff, *Building Multilingual Conversational AI Agents*](https://www.youtube.com/watch?v=GkVjMxYi5gA)) y otra en español ([Miguel Ángel Durán, *Programming is dead. Long live programming!*](https://www.youtube.com/watch?v=zynI57qVj-U)).

| Página | Para quién |
|---|---|
| `/` y `/s/<sala>?lang=es` | Público: elige sala e idioma, lee los subtítulos, **escucha la interpretación** con auriculares, pide **"¿Qué me perdí?"**, cambia el tamaño de letra y el tema, y descarga la charla |
| `/overlay/<sala>?lang=es` | Fuente de navegador en OBS o vMix (fondo transparente, o `&bg=00b140` para croma) |
| `/pantalla/<sala>?lang=es&lang2=en` | Tele o proyector al costado del escenario: subtítulos grandes en uno o dos idiomas y el QR para seguirlos en el celular |
| `/api/sessions/<sala>/live.txt?lang=es` | Las últimas dos líneas en texto plano, como fuente de datos de un título de vMix o CasparCG |
| `/admin` | Producción: estado, audio, latencia, errores, público, costo, QR y glosario por sala |
| `/enviar/<sala>` | La compu de la sala manda el audio desde el navegador |

Sin clave de Gemini se puede ver todo funcionando con el motor de prueba: `subtitula serve --engine fake`.

### Subtitular un archivo desde la terminal

```bash
subtitula file samples/thor-schaeff-multilingual-agents-en.mp3 --language en --both
```

Muestra cada línea del original (en blanco) y de cada traducción (en amarillo), deja `.srt`, `.vtt` y `.txt` por idioma al lado del archivo y al final informa la demora medida y los tokens usados. Con esto se hicieron los subtítulos en inglés del video demo.

## Costos

Precios oficiales de la [página de precios de la Gemini API](https://ai.google.dev/gemini-api/docs/pricing) (plan pago, 25/09/2026). Cada worker calcula su costo con el modelo que usó y el panel lo muestra por sala (`subtitula/pricing.py`).

| Motor | Qué se paga | Por sala-hora |
|---|---|---|
| `gemini-live` (por defecto) | Live Translate: US$ 0,0053/min de audio de entrada + US$ 0,0315/min de audio de salida, por cada sesión (una por idioma de destino) | US$ 2,21 por idioma |
| `gemini` (por tramos) | `gemini-3.5-transcribe` a US$ 0,005/min (audio de entrada y texto de salida), más la traducción de texto con flash-lite a los idiomas del evento | unos US$ 0,65 para todos los idiomas (estimado: US$ 0,30 de transcripción y ~US$ 0,35 de traducción) |
| `local` | Nada de API: faster-whisper y Gemma en una máquina propia con GPU | US$ 0 |

Tres cosas bajan la cuenta del motor en vivo sin tocar la calidad:

- **Idiomas bajo demanda.** Cada sala mantiene abierta sólo la sesión de su idioma principal. Las demás (por ejemplo, portugués) se abren cuando alguien las lee o las escucha y se cierran a los 2 minutos sin público. En una conferencia de 30 charlas con tres idiomas, la mayoría de esas sesiones no se abre nunca.
- **Pausa en silencio.** Tras 10 s sin voz (cortes, cambio de orador, almuerzo) no se manda audio. Cuando vuelve la voz se reanuda, con medio segundo previo para no perder la primera sílaba.
- **La voz ya está paga.** Live Translate genera y cobra la interpretación hablada aunque no se use. Subtitula la aprovecha: el público la puede escuchar con auriculares sin costo extra.

## Qué pasa si…

| Situación durante el evento | Qué hace Subtitula |
|---|---|
| Se corta la fuente de audio | El worker reintenta con espera exponencial y la fila de la sala se pone roja en `/admin` |
| Gemini devuelve un error o la sesión Live se cae | La sesión se reabre retomando el contexto (session resumption); si el retome falló, abre una nueva. El panel cuenta las reconexiones |
| La charla dura horas | La sesión usa compresión de contexto con ventana deslizante y retoma cuando el servidor pide reconectar |
| Se acaba la cuota o un modelo está saturado | El motor por tramos pasa al modelo siguiente del pool ante un 429 o un 503. Sin nube, está el motor local |
| Alguien recarga la página o se le corta el wifi | El navegador reconecta solo; con `Last-Event-ID` recibe sólo las líneas que se perdió |
| Un nombre sale mal escrito | Se agrega al glosario de la sala desde `/admin`: la ortografía se corrige desde la línea siguiente en todas las pistas y las sesiones Live se reconectan con el vocabulario nuevo |
| Alguien pregunta en español en una charla en inglés | La sesión repite la pregunta tal cual en la pista en español, en lugar de dejar un hueco |
| Nadie está leyendo en portugués | La sesión de portugués queda en espera y no cobra hasta que alguien la pide |
| La sala queda en silencio | No se manda audio a la API; el panel lo muestra como "en pausa por silencio" |
| La compu de la sala no tiene nada instalado | Se abre `/enviar/<sala>` en el navegador y se elige la entrada de audio de la consola |

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
- **Demora medida.** El panel muestra cuánto tarda en llegar la última palabra de una frase desde que el orador hace una pausa. Se mide así porque no necesita marcas de tiempo externas y se puede ver en vivo durante el evento. En 10 minutos seguidos de cada charla de ejemplo: original 0,34 s en p50 y 0,7 a 0,9 s en p90; traducción 0,29 a 0,34 s en p50 y 0,76 a 0,89 s en p90, sin atraso acumulado minuto a minuto ([`docs/evidencia/`](docs/evidencia)). Al arrancar la sesión, la primera frase tarda unos 3 s.

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
ollama pull gemma4:e4b
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

Prueba de carga incluida, que no gasta API:

```bash
python scripts/loadtest.py --mode live --stages 20 --viewers 25 --seconds 45
```

El modo `live` imita al motor en vivo: tres pistas por sala (original y dos traducciones) cuyas líneas crecen de a un grupo de palabras cada 0,35 s, que es el tráfico más exigente. Resultado en una notebook de 8 núcleos, todo en un solo proceso: **20 salas y 500 personas conectadas, 168 actualizaciones por segundo y 188.050 entregas (4.179 por segundo) sin errores; del hub a la pantalla, 7 ms en p50 y 112 ms en p99**, con el 65% de un núcleo contando a los 500 clientes de prueba. Con `--mode chunks` (un subtítulo completo cada ~3 s, como el motor por tramos) dio 6 ms en p50 y 18 ms en p99.

Cuánto cuesta: Live Translate cuenta el audio a 25 tokens por segundo, de entrada y de salida (US$ 2,21 por sesión y por hora; ver [Costos](#costos)). El panel muestra el costo real de cada sala a partir de los tokens que informa la API y los precios oficiales de cada modelo. En las pruebas de 10 minutos se midieron US$ 0,37 por sesión, que coincide con el precio publicado.

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
