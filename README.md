# Subtitula

[![tests](https://github.com/flordelcastillo/subtitula/actions/workflows/tests.yml/badge.svg)](https://github.com/flordelcastillo/subtitula/actions/workflows/tests.yml)
[![licencia](https://img.shields.io/badge/licencia-Apache%202.0-blue)](LICENSE)

**Subtítulos e interpretación simultánea en vivo, open source, para conferencias con muchas salas a la vez.**
*Live captions and simultaneous interpretation for multi-room conferences, open source.*

**[Probá la demo](https://flordelcastillo.github.io/subtitula/)** (repetición de una corrida real, sin instalar nada) · [Vibeathon de Nerdearla 2026](https://nerdearla26.devpost.com) · [Evidencia medida](docs/evidencia) · [Los cinco criterios](#los-cinco-criterios-con-evidencia) · **[English version](README.en.md)**

| El público, en su idioma | "¿Qué me perdí?" | Pantalla de sala con QR | Panel de producción |
|---|---|---|---|
| <img src="docs/img/celular-es.png" width="180" alt="Vista del celular con la charla en inglés subtitulada al español"> | <img src="docs/img/que-me-perdi.png" width="180" alt="Resumen de los últimos 5 minutos en inglés"> | <img src="docs/img/pantalla.png" width="300" alt="Pantalla de sala con subtítulos en español e inglés y código QR"> | <img src="docs/img/panel.png" width="300" alt="Panel de producción con dos salas en vivo, demoras y costo"> |

## Para Nerdearla

Hoy la conferencia usa dos herramientas comerciales, una para transcribir las charlas en español y otra para traducir en vivo las de inglés, con operación manual. Este año son más de 30 sesiones en inglés, muchas en paralelo.

- **Una sola herramienta para las dos cosas.** Cada sala abre una sesión de la Gemini Live API que devuelve el original (transcripción, accesibilidad) y la traducción al mismo tiempo. Sirve igual para una charla en inglés (subtítulos en español) que para una en español (subtítulos en inglés), y suma portugués si alguien lo pide.
- **Costo del evento a la vista.** US$ 2,21 por sala y por hora con un idioma de destino, con precios oficiales. Por ejemplo, 30 charlas de 40 minutos traducidas al español son unas 20 horas, **unos US$ 44 en total**. Cada idioma adicional cuesta lo mismo, pero sólo mientras alguien lo esté usando.
- **El mismo setup de sala.** La compu conectada a la consola abre `/enviar/<sala>` en el navegador, sin instalar nada, o se toma el stream (HLS, RTMP, SRT o YouTube). La tele de la sala abre `/pantalla/<sala>`, el stream suma `/overlay/<sala>` en OBS o vMix y producción mira todas las salas en `/admin`.
- **Replicable.** Para otro evento (Chile, México) alcanza con editar `config/sessions.yaml` y `config/glossary.yaml`. Licencia Apache 2.0: Nerdearla lo puede usar, adaptar y desplegar.

## En pocas palabras

Cada escenario manda su audio (stream, micrófono, encoder o una pestaña del navegador) a la [Gemini Live API](https://ai.google.dev/gemini-api/docs/live), que devuelve palabra por palabra el original y la interpretación a español, inglés y portugués mientras la persona habla. El público escanea un QR y lee los subtítulos en el celular, en el idioma que elija, o escucha la interpretación con auriculares. Producción suma una pantalla por sala, un overlay para OBS/vMix, un panel con el estado de cada sala y la transcripción completa en SRT, VTT o texto al terminar.

## English summary

Subtitula is an open source live captioning and simultaneous interpretation system for multi-track conferences. Each stage streams its audio into one Gemini Live API session per target language (`gemini-3.5-live-translate-preview`): the original transcript and the translation arrive word by word while the speaker talks, typically 0.3 to 1 s after they pause. Each language is its own caption track, split into natural sentences of at most 84 characters. Phones can also play the spoken interpretation that Live Translate already generates (headphones on, no extra cost), and a "What did I miss?" button summarizes the last 5 minutes in the reader's language with Gemma. Secondary languages open a Live session only while someone reads or listens to them, and long silences are not streamed. Measured over 10 continuous minutes per talk: 0.34 s p50 / under 0.9 s p90 from the speaker's pause to the last translated word, with no accumulated drift ([evidence](docs/evidencia)). A lightweight hub fans captions out over Server-Sent Events to phones (pick stage + language), an OBS/vMix overlay and a production dashboard (audio level, latency p50/p90, errors, live sessions, real cost per room from official prices). Transcripts export to SRT/VTT/TXT. Scale by running one worker container per stage. Fallback engines: chunked `gemini-3.5-transcribe` + Flash-Lite/Gemma translation, and fully local faster-whisper + Gemma via Ollama.

## Los cinco criterios, con evidencia

| Criterio | Qué hace Subtitula | Evidencia |
|---|---|---|
| **Calidad** | Interpretación con Live Translate. El glosario de cada sala entra como vocabulario del reconocedor y, además, corrige la ortografía de nombres y términos en todas las pistas, incluida la traducción. Cada idioma arma sus propias líneas, cortadas por oración y con 84 caracteres como máximo (dos renglones de 42, la norma de subtitulado). Las preguntas del público en el idioma de destino se muestran tal cual | Ejemplo real: "if I pipe the audio out on the HDMI, are you able to hear it on the stream?" → "Si saco el audio por el HDMI, ¿puedes escucharlo en la transmisión?". Tests de glosario y de pistas en `tests/test_live.py` |
| **Latencia** | El texto llega palabra por palabra mientras la persona habla. Desde que el orador hace una pausa hasta que llega la última palabra de la frase: **0,34 s en p50 y 0,7 a 0,9 s en p90 para el original, y 0,29 a 0,34 s en p50 y 0,76 a 0,89 s en p90 para la traducción**. En 10 minutos seguidos no hay atraso acumulado (el peor minuto dio 2,1 s de p90). Si igual una sesión se traba o se atrasa más de 6 s, un vigía la corta y la retoma en vivo: mejor perder una frase que ir 10 s atrás | [`docs/evidencia/`](docs/evidencia), medido con [`scripts/drift_test.py`](scripts/drift_test.py) sobre 10 minutos de cada charla de ejemplo |
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

Abrí <http://localhost:8000>. La sala **"Tu audio"** recibe lo que mandes desde <http://localhost:8000/enviar/sala-c>: elegí "Archivo de audio o video…", subí cualquier charla y mirala subtitulada en otra pestaña. Detecta el idioma sola y abre la sesión Live recién cuando llega audio. Además hay dos salas de ejemplo en loop, con fragmentos reales de Nerdearla 2025: una charla en inglés ([Thor Schaeff, *Building Multilingual Conversational AI Agents*](https://www.youtube.com/watch?v=GkVjMxYi5gA)) y otra en español ([Miguel Ángel Durán, *Programming is dead. Long live programming!*](https://www.youtube.com/watch?v=zynI57qVj-U)).

| Página | Para quién |
|---|---|
| `/` y `/s/<sala>?lang=es` | Público: elige sala e idioma, lee los subtítulos, **escucha la interpretación** con auriculares, pide **"¿Qué me perdí?"**, cambia el tamaño de letra y el tema, y descarga la charla |
| `/overlay/<sala>?lang=es` | Fuente de navegador en OBS o vMix (fondo transparente, o `&bg=00b140` para croma) |
| `/pantalla/<sala>?lang=es&lang2=en` | Tele o proyector al costado del escenario: subtítulos grandes en uno o dos idiomas y el QR para seguirlos en el celular |
| `/api/sessions/<sala>/live.txt?lang=es` | Las últimas dos líneas en texto plano, como fuente de datos de un título de vMix o CasparCG |
| `/admin` | Producción: estado, audio, latencia, errores, público, costo, QR y glosario por sala |
| `/enviar/<sala>` | La compu de la sala manda el audio desde el navegador: micrófono, placa de la consola o **un archivo de audio o video** para probar sin sala |

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

Cuánto sale un evento:

| Escenario | Sesiones Live abiertas | Costo |
|---|---|---|
| Una charla en inglés con subtítulos en español | 1 | US$ 2,21 por hora |
| 5 salas en paralelo con un idioma de destino | 5 | US$ 11,05 por hora |
| 5 salas, y en 2 de ellas alguien lee también en portugués | 7 | US$ 15,47 por hora |
| 30 charlas de 40 minutos traducidas al español (~20 horas de sala) | 1 por sala | unos US$ 44 en total |

El límite de sesiones simultáneas depende del tier del proyecto en AI Studio. La [guía oficial de Live Translate](https://github.com/google-gemini/gemini-live-translate-livekit) advierte que el nivel inicial admite pocas conexiones. Con idiomas bajo demanda, sólo cuentan las sesiones que alguien está usando.

Tres cosas bajan la cuenta del motor en vivo sin tocar la calidad:

- **Idiomas bajo demanda.** Cada sala mantiene abierta sólo la sesión de su idioma principal. Las demás (por ejemplo, portugués) se abren cuando alguien las lee o las escucha y se cierran a los 2 minutos sin público. En una conferencia de 30 charlas con tres idiomas, la mayoría de esas sesiones no se abre nunca.
- **Pausa en silencio.** Tras 10 s sin voz (cortes, cambio de orador, almuerzo) no se manda audio. Cuando vuelve la voz se reanuda, con medio segundo previo para no perder la primera sílaba.
- **La voz ya está paga.** Live Translate genera y cobra la interpretación hablada aunque no se use. Subtitula la aprovecha: el público la puede escuchar con auriculares sin costo extra.

## Qué pasa si…

| Situación durante el evento | Qué hace Subtitula |
|---|---|
| Se corta la fuente de audio | El worker reintenta con espera exponencial y la fila de la sala se pone roja en `/admin` |
| La traducción se atrasa o deja de avanzar mientras el original sigue | Un vigía revisa cada sesión cada medio segundo. Si la traducción lleva 10 s sin avanzar mientras el original ya sumó dos líneas, si hay voz y no llega el original, o si una frase llegó más de 6 s tarde, corta esa sesión y la reabre en vivo, sin arrastrar el atraso. En el panel queda contado como "corte por atraso" |
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
- **Sesiones largas.** La sesión usa compresión de contexto con ventana deslizante para aguantar una charla entera y, si el servidor la corta, se reabre retomando el contexto (session resumption). Mientras se reconecta, el audio espera en una cola de hasta 10 s y se manda apenas vuelve la sesión, así que no se pierde lo que se dijo.
- **Modelo preview.** `gemini-3.5-live-translate-preview` es un modelo en preview. El nombre se cambia con `SUBTITULA_LIVE_MODEL`, y si el modelo falla o cambia, el motor por tramos (`--engine gemini`) y el local (`--engine local`) siguen andando con la misma interfaz.
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

**Antes del evento**

1. Cargar las charlas en `config/sessions.yaml` (título, orador, tema, idioma y fuente) y el glosario común en `config/glossary.yaml`.
2. En `/admin`, **Sugerir con IA** en cada sala: Gemini propone nombres propios, productos y siglas a partir del título, el orador y la descripción de la agenda. Se revisan y se guardan.
3. Imprimir o proyectar el QR de cada sala (link *QR* en el panel o `/pantalla/<sala>`). Apunta a `/s/<sala>`.

**Checklist de sala (para la persona voluntaria, 5 minutos)**

- [ ] La compu de la sala está conectada a la salida de la consola y tiene abierta `/enviar/<sala>` con esa entrada elegida, o producción confirma que la fuente de la sala (stream, SRT, RTMP) está en verde.
- [ ] Prueba de sonido: alguien habla al micrófono y el vúmetro de la sala se mueve en `/admin`.
- [ ] En un celular, escanear el QR, elegir español y ver aparecer la frase de prueba.
- [ ] La tele de la sala muestra `/pantalla/<sala>?lang=es&lang2=en`.
- [ ] Si la sala va al stream: en OBS o vMix, fuente de navegador con `/overlay/<sala>?lang=es` (1920×1080; parámetros `lines`, `size`, `hide`, `pos=top`, `box=0`, `bg=00b140`).

**Durante la charla**

- Una fila en rojo en `/admin` avisa de una fuente caída, más de 20 s sin audio, una demora p90 por encima de 6 s, cortes por atraso o tramos salteados.
- Si un nombre sale mal escrito, se corrige en el glosario de la sala desde el panel: aplica desde la línea siguiente.
- `/metrics` expone lo mismo que el panel en formato Prometheus, para sumarlo al Grafana del evento.

**Al terminar**, la charla se descarga en `/api/sessions/<sala>/export.srt?lang=es` (o `.vtt` o `.txt`, en cualquier idioma), lista para subir con el video.

## Desarrollo

```bash
pip install -e '.[dev]'
pytest
```

Los tests (29, en CI en cada push) cubren:

- el segmentador con audio sintético y las exportaciones;
- dos salas en paralelo de punta a punta y el motor en dos etapas;
- las pistas del motor en vivo (cortes por oración, tope de 84 caracteres, exportación por pista, demora medida);
- idiomas bajo demanda, pausa en silencio, voz por WebSocket y "¿Qué me perdí?";
- la corrección de glosario y su recarga en caliente;
- la reconexión SSE con `Last-Event-ID`, el token de ingesta y el QR.

Las instrucciones para agentes de código y para contribuir están en [AGENTS.md](AGENTS.md).

## Cómo se hizo

Subtitula se construyó durante la vibeathon, el 24 y 25 de septiembre de 2026, con [Claude Code](https://claude.com/claude-code) como agente de programación. Florencia definió el alcance y las prioridades y tomó las decisiones de producto. El agente escribió el código, los tests y los scripts de medición. Cada decisión técnica importante salió de probar contra la API real:

- pasar de un pedido por tramo a la Live API cuando la cuota y la saturación la volvieron inviable;
- separar cada idioma en su propia pista cuando alinear la traducción con el original resultó imposible en vivo;
- corregir el costo cuando se comparó contra los precios oficiales.

## Licencia

[Apache 2.0](LICENSE). Los fragmentos de audio en `samples/` son de charlas públicas de Nerdearla 2025 y se incluyen sólo como material de prueba.
