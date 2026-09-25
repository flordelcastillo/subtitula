<img src="docs/img/logo.svg" width="300" alt="Subtitula">

**Español** · [English](README.en.md)

[![tests](https://github.com/flordelcastillo/subtitula/actions/workflows/tests.yml/badge.svg)](https://github.com/flordelcastillo/subtitula/actions/workflows/tests.yml)
[![licencia](https://img.shields.io/badge/licencia-Apache%202.0-blue)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab)
![Gemini Live API](https://img.shields.io/badge/Gemini-Live%20API-f4b54a)
![34 tests](https://img.shields.io/badge/tests-34-7fd1a8)

**Subtítulos e interpretación simultánea en vivo, open source, para conferencias con muchas salas a la vez.**
*Live captions and simultaneous interpretation for multi-room conferences, open source.*

**[Probá la demo](https://flordelcastillo.github.io/subtitula/)** (repetición de una corrida real, sin instalar nada) · [Vibeathon de Nerdearla 2026](https://nerdearla26.devpost.com) · [Evidencia medida](docs/evidencia) · [Los cinco criterios](#los-cinco-criterios-con-evidencia) · **[English version](README.en.md)**

| El público, en su idioma | "¿Qué me perdí?" | Pantalla de sala con QR | Panel de producción |
|---|---|---|---|
| <img src="docs/img/celular-es.png" width="180" alt="Vista del celular con la charla en inglés subtitulada al español"> | <img src="docs/img/que-me-perdi.png" width="180" alt="Resumen de los últimos 5 minutos en inglés"> | <img src="docs/img/pantalla.png" width="300" alt="Pantalla de sala con subtítulos en español e inglés y código QR"> | <img src="docs/img/panel.png" width="300" alt="Panel de producción con dos salas en vivo, demoras y costo"> |

## Índice

[Para Nerdearla](#para-nerdearla) · [Los cinco criterios](#los-cinco-criterios-con-evidencia) · [Qué resuelve](#qué-resuelve) · [Probarlo en 2 minutos](#probarlo-en-2-minutos) · [Costos](#costos) · [Qué pasa si…](#qué-pasa-si) · [Cómo funciona](#cómo-funciona) · [Configuración](#configuración) · [Escala](#escala) · [Operación](#operación-durante-el-evento) · [Referencia](#referencia-qué-hay-adentro) · [Desarrollo](#desarrollo) · [Cómo se hizo](#cómo-se-hizo)

## Para Nerdearla

Hoy la conferencia usa dos herramientas comerciales, una para transcribir las charlas en español y otra para traducir en vivo las de inglés, con operación manual. Este año son más de 30 sesiones en inglés, muchas en paralelo.

- **Una sola herramienta para las dos cosas.** Cada sala abre una sesión de la Gemini Live API que devuelve el original (transcripción, accesibilidad) y la traducción al mismo tiempo. Sirve igual para una charla en inglés (subtítulos en español) que para una en español (subtítulos en inglés), y suma portugués si alguien lo pide.
- **Costo del evento a la vista.** US$ 2,21 por sala y por hora con un idioma de destino, con precios oficiales. Por ejemplo, 30 charlas de 40 minutos traducidas al español son unas 20 horas, **unos US$ 44 en total**. Cada idioma adicional cuesta lo mismo, pero sólo mientras alguien lo esté usando.
- **El mismo setup de sala.** La compu conectada a la consola abre `/enviar/<sala>` en el navegador, sin instalar nada, o se toma el stream (HLS, RTMP, SRT o YouTube). La tele de la sala abre `/pantalla/<sala>`, el stream suma `/overlay/<sala>` en OBS o vMix y producción mira todas las salas en `/admin`.
- **Replicable.** Para otro evento (Chile, México) alcanza con editar `config/sessions.yaml` y `config/glossary.yaml`. Licencia Apache 2.0: Nerdearla lo puede usar, adaptar y desplegar.

## En pocas palabras

Cada escenario manda su audio (stream, micrófono, encoder o una pestaña del navegador) a la [Gemini Live API](https://ai.google.dev/gemini-api/docs/live), que devuelve palabra por palabra el original y la interpretación a español, inglés y portugués mientras la persona habla. El público escanea un QR y lee los subtítulos en el celular, en el idioma que elija, o escucha la interpretación con auriculares. Producción suma una pantalla por sala, un overlay para OBS/vMix, un panel con el estado de cada sala y la transcripción completa en SRT, VTT o texto al terminar.

## Los cinco criterios, con evidencia

| Criterio | Qué hace Subtitula | Evidencia |
|---|---|---|
| **Calidad** | Interpretación con Live Translate. El glosario de cada sala entra como vocabulario del reconocedor y, además, corrige la ortografía de nombres y términos en todas las pistas, incluida la traducción. Cada idioma arma sus propias líneas, cortadas por oración y con 84 caracteres como máximo (dos renglones de 42, la norma de subtitulado). Las preguntas del público en el idioma de destino se muestran tal cual | SRT completos del original y de cada traducción, de 2 minutos por charla, en [`docs/evidencia/srt`](docs/evidencia/srt). Ejemplo real: "if I pipe the audio out on the HDMI, are you able to hear it on the stream?" → "Si saco el audio por el HDMI, ¿puedes escucharlo en la transmisión?". Tests de glosario y de pistas en `tests/test_live.py` |
| **Latencia** | El texto llega palabra por palabra mientras la persona habla. Desde que el orador hace una pausa hasta que llega la última palabra de la frase: **0,34 s en p50 y 0,7 a 0,9 s en p90 para el original, y 0,29 a 0,34 s en p50 y 0,76 a 0,89 s en p90 para la traducción**. En 10 minutos seguidos no hay atraso acumulado (el peor minuto dio 2,1 s de p90). Si igual una sesión se traba o se atrasa más de 6 s, un vigía la corta y la retoma en vivo: mejor perder una frase que ir 10 s atrás | [`docs/evidencia/`](docs/evidencia), medido con [`scripts/drift_test.py`](scripts/drift_test.py) sobre 10 minutos de cada charla de ejemplo |
| **Escalabilidad** | Un worker por sala sin estado compartido y un hub que sólo mueve texto. Los idiomas sin público no abren sesión y el audio en silencio no se manda. Costo real por sala en el panel | 4 sesiones Live simultáneas contra Gemini con 0 errores. Prueba de carga palabra por palabra: 20 salas y 500 personas, 4.223 entregas por segundo, 4 ms p50 del hub a la pantalla ([Escala](#escala)). US$ 2,2 por idioma y por hora ([Costos](#costos)) |
| **Despliegue y operación** | `pip install`, una clave en `.env` y `subtitula serve`, o Docker Compose con un contenedor por sala. Agenda por sala: título, orador, idioma y glosario cambian solos a la hora de cada charla. La sala puede mandar el audio desde un navegador, sin instalar nada. Panel con vúmetro, demoras p50/p90, errores, sesiones, costo, QR y glosario editable en vivo. Overlay para OBS/vMix, `live.txt` para títulos y fondo de croma | Secciones [Operación](#operación-durante-el-evento) y [Qué pasa si…](#qué-pasa-si) |
| **Innovación** | **Escuchar la interpretación** con auriculares desde el celular (la voz que Live Translate ya genera). **"¿Qué me perdí?"**: resumen de los últimos 5 minutos en tu idioma, con Gemma. Idiomas bajo demanda y vigía de atraso. Tres motores: en vivo, por tramos y 100% local con faster-whisper y Gemma | [Demo pública](https://flordelcastillo.github.io/subtitula/), capturas y video |
| **Accesibilidad** (el objetivo del desafío) | Tipografía Atkinson Hyperlegible, modo de alto contraste (se activa solo si el sistema lo pide), tamaño de letra ajustable, tema claro u oscuro, objetivos táctiles de 44 px, todo operable con teclado, interfaz en español, inglés y portugués según el celular, y la interpretación hablada para quien prefiere escuchar | Revisión contra WCAG 2.2 AA en la vista del público; capturas en `docs/img` |

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

Requisitos: Python 3.11 o superior, `ffmpeg` y una clave de Gemini de [Google AI Studio](https://aistudio.google.com/apikey). Para el motor en vivo conviene un proyecto con facturación activa (Tier 1); más abajo se explica por qué.

```bash
git clone https://github.com/flordelcastillo/subtitula && cd subtitula
python -m venv venv && . venv/bin/activate
pip install -e .
echo GEMINI_API_KEY=tu-clave > .env
subtitula serve
```

El motor por defecto (`gemini-live`) mantiene una sesión abierta por sala e idioma y no hace un pedido por frase, así que no choca con el límite de pedidos por minuto. Según la [página de precios](https://ai.google.dev/gemini-api/docs/pricing), Live Translate tiene un nivel gratuito, pero con nuestra clave gratuita la sesión no llegó a abrir; la guía de Google que se cita abajo dice que ese nivel admite unas 3 a 5 conexiones simultáneas. Las pruebas de este README se hicieron con un proyecto con facturación activa (Tier 1): 4 sesiones simultáneas y 0 errores. Según la [guía de Google para traducir transmisiones con Live Translate](https://github.com/google-gemini/gemini-live-translate-livekit), el nivel inicial admite pocas conexiones simultáneas y un evento con varias salas e idiomas necesita subir de tier; con idiomas bajo demanda se abren sólo las sesiones que alguien usa. Sin clave se puede probar todo con `--engine fake`, y con la clave gratuita anda el motor por tramos (`--engine gemini`). El costo de cada sala se ve en `/admin` (ver [Costos](#costos)).

Abrí <http://localhost:8000>. La sala **"Tu audio"** recibe lo que mandes desde <http://localhost:8000/enviar/sala-c>: elegí "Archivo de audio o video…", subí cualquier charla y mirala subtitulada en otra pestaña. Detecta el idioma sola y abre la sesión Live recién cuando llega audio. Además hay dos salas de ejemplo en loop, con fragmentos reales de Nerdearla 2025: una charla en inglés ([Thor Schaeff, *Building Multilingual Conversational AI Agents*](https://www.youtube.com/watch?v=GkVjMxYi5gA)) y otra en español ([Miguel Ángel Durán, *Programming is dead. Long live programming!*](https://www.youtube.com/watch?v=zynI57qVj-U)).

| Página | Para quién |
|---|---|
| `/` y `/s/<sala>?lang=es` | Público: elige sala e idioma, lee los subtítulos, **escucha la interpretación** con auriculares (motor en vivo, modo `serve`), pide **"¿Qué me perdí?"**, cambia el tamaño de letra y el tema, y descarga la charla. La interfaz sigue el idioma del celular: español, inglés o portugués |
| `/overlay/<sala>?lang=es` | Fuente de navegador en OBS o vMix (fondo transparente, o `&bg=00b140` para croma) |
| `/pantalla/<sala>?lang=es&lang2=en` | Tele o proyector al costado del escenario: subtítulos grandes en uno o dos idiomas y el QR para seguirlos en el celular |
| `/api/sessions/<sala>/live.txt?lang=es` | Las últimas dos líneas en texto plano, como fuente de datos de un título de vMix o CasparCG |
| `/admin` | Producción: estado, audio, latencia, errores, público, costo, QR y glosario por sala |
| `/enviar/<sala>` | La compu de la sala manda el audio desde el navegador: micrófono, placa de la consola o **un archivo de audio o video** para probar sin sala. Sólo en modo `subtitula serve` (un proceso): con Docker Compose las salas entran por stream. El micrófono del navegador exige HTTPS o `localhost` (ver [Puesta en producción](#puesta-en-producción)) |

Sin clave de Gemini se puede ver todo funcionando con el motor de prueba: `subtitula serve --engine fake`.

Ojo con el costo del quickstart: `subtitula serve` con las salas de ejemplo abre 4 sesiones Live al arrancar (dos salas con dos idiomas cada una) y a los 2 minutos deja 2 abiertas. Son unos US$ 8,8 por hora al principio y US$ 4,4 por hora después, mientras lo dejes corriendo.

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

Para comparar: los planes de Maestra, la herramienta comercial de subtitulado en vivo más citada, arrancan en US$ 29 por 5 horas (unos US$ 5,8 por hora de subtitulado) y la traducción en vivo se cobra aparte, según [Sonix](https://sonix.ai/resources/maestra-pricing/) (2026). Subtitula da el original y la traducción juntos por US$ 2,21 la hora, o menos de US$ 0,70 con el motor por tramos.

Tres cosas bajan la cuenta del motor en vivo sin tocar la calidad:

- **Idiomas bajo demanda.** Cada sala mantiene abierta sólo la sesión de su idioma principal. Las demás (por ejemplo, portugués) se abren cuando alguien las lee o las escucha y se cierran a los 2 minutos sin público. En una conferencia de 30 charlas con tres idiomas, la mayoría de esas sesiones no se abre nunca.
- **Pausa en silencio.** Tras 10 s sin voz (cortes, cambio de orador, almuerzo) no se manda audio. Cuando vuelve la voz se reanuda, con medio segundo previo para no perder la primera sílaba.
- **La voz ya está paga.** Live Translate genera y cobra la interpretación hablada aunque no se use. Subtitula la aprovecha: el público la puede escuchar con auriculares sin costo extra.

## Qué pasa si…

| Situación durante el evento | Qué hace Subtitula |
|---|---|
| Se corta la fuente de audio | El worker reintenta con espera exponencial y la fila de la sala se pone roja en `/admin` |
| La traducción se atrasa o deja de avanzar mientras el original sigue | Un vigía revisa cada sesión cada medio segundo. Si la traducción lleva 10 s sin avanzar mientras el original ya sumó dos líneas, si hay voz y no llega el original, o si una frase llegó más de 6 s tarde, corta esa sesión y la reabre en vivo, sin arrastrar el atraso. En el panel queda contado como "corte por atraso" |
| La sesión Live abre pero no devuelve nada | Pasó en 2 de 4 arranques durante las pruebas: la sesión conecta, recibe audio y no transcribe. Si hay voz de entrada y a los 6 s no llegó nada, el vigía la reabre; lo mismo para una sesión de traducción que no traduce mientras el original avanza |
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

### Recorrido de una frase por el código

1. **Entrada** (`subtitula/audio.py`). ffmpeg abre la fuente (archivo, micrófono, HLS, RTMP, SRT, UDP o YouTube) y entrega PCM mono de 16 kHz en bloques de 100 ms. Si la sala es `browser`, el bloque llega por el WebSocket de `/enviar`. Una fuente en vivo que se corta se reintenta con espera exponencial.
2. **Reparto** (`subtitula/live.py`, `LiveSessionWorker._forward`). Tras 10 s por debajo de −50 dBFS deja de enviar (pausa en silencio) y guarda medio segundo de pre-roll para no perder la primera sílaba al reanudar. Cada bloque va a un `LiveTrack` por idioma de destino; una pista sin público está en espera y no abre sesión (`set_demand`, alimentado por el sondeo de las vistas).
3. **Sesión Live** (`LiveTrack.run`). Abre `gemini-3.5-live-translate-preview` con `translation_config` (eco del idioma de destino), transcripción de entrada con el glosario como vocabulario, session resumption y compresión de contexto. Recibe tres flujos: `input_transcription` (el original, sólo desde la sesión principal), `output_transcription` (la traducción) y `inline_data` (la voz interpretada).
4. **Líneas** (`TrackBuilder`). Cada pista arma sus líneas: corta al terminar una oración (también si el fin viene dentro de un fragmento), en una coma si ya es larga, a los 84 caracteres o tras 2 s sin palabras. `glossary.py` corrige la ortografía canónica y los alias antes de publicar. La demora se mide desde la última pausa del orador (`_pause_lag`).
5. **Publicación** (`worker.py` → `hub.py`). Cada actualización de línea llega a `Hub.caption`, que la guarda en `data/<sala>.jsonl` y la reparte por Server-Sent Events. La vista (`web/viewer.js`) repinta la línea con el mismo número de secuencia, así crece palabra por palabra.
6. **Voz** (`Hub.speech`). Los bloques PCM de la interpretación van al WebSocket `/listen` de quien esté escuchando ese idioma; el celular los reproduce con `AudioContext`, con un colchón chico y salteando silencios si se atrasa.
7. **Vigilancia** (`_watchdog`, cada 0,5 s). Reabre la sesión que abrió muda (6 s con voz sin texto), la que no traduce mientras el original avanza, o la que entregó una frase más de 6 s tarde. Cada 2 s el worker publica su estado (audio, demoras, errores, costo con `pricing.py`) y recibe del hub el glosario vigente y la demanda de idiomas.
8. **Agenda** (`Hub.apply_agenda`, cada 10 s). Cuando el reloj entra en una charla, cambia nombre, orador, tema, glosario (en caliente) e idioma (reabriendo las sesiones).
9. **Salida**. `export.srt|vtt|txt` reconstruye cada pista desde el `.jsonl` con cues de 0,8 s como mínimo; `summary` resume los últimos minutos con Gemma; `/metrics` expone lo mismo que el panel.

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

**Agenda por sala.** Cada sala puede llevar su lista de charlas con horario; el hub cambia solo el nombre, el orador, el tema, el idioma y el glosario cuando el reloj entra en cada franja, la pantalla de sala muestra "Próxima", y al terminar la última charla la sala vuelve a su configuración base. Nadie tiene que tocar nada entre charla y charla.

```yaml
  - id: auditorio
    name: Auditorio
    source: srt://0.0.0.0:9000?mode=listener
    language: es
    talks:
      - { name: Apertura, start: "09:30", end: "10:00", speaker: Ariel Jolo }
      - name: "What's new in AI Audio?"
        start: "12:10"          # hora local; también vale 2026-09-25T12:10
        end: "12:50"
        speaker: Thor Schaeff
        language: en             # las sesiones Live se reabren en inglés
        glossary: ["ElevenLabs = 11 labs", Gemini Live API]
```

`config/glossary.yaml` tiene los términos globales. Durante el evento se corrigen desde `/admin`, sala por sala, sin reiniciar nada: el cambio llega al worker en menos de 2 segundos, aunque corra en otra máquina.

Variables de entorno (todas opcionales salvo la clave):

| Variable | Para qué |
|---|---|
| `GEMINI_API_KEY` | Clave de Gemini (o en `.env`) |
| `SUBTITULA_CONFIG`, `SUBTITULA_GLOSSARY`, `SUBTITULA_DATA` | Rutas de `sessions.yaml`, `glossary.yaml` y la carpeta de los `.jsonl` |
| `SUBTITULA_ENGINE` | `gemini-live` (por defecto), `gemini`, `local` o `fake` |
| `SUBTITULA_LIVE_MODEL` | Modelo de la Live API (por defecto `gemini-3.5-live-translate-preview`) |
| `SUBTITULA_ASR_MODEL`, `SUBTITULA_GEMINI_MODEL`, `SUBTITULA_GEMINI_MODE`, `SUBTITULA_GEMINI_TIMEOUT` | Motor por tramos: modelo de transcripción, pool de traducción (lista separada por coma), `asr` o `single`, timeout |
| `SUBTITULA_SUMMARY_MODEL` | Modelos de "¿Qué me perdí?" (por defecto Gemma 4 y luego flash-lite) |
| `SUBTITULA_TOKEN` | Protege la ingesta de workers, el audio del navegador y el glosario. Obligatorio con Compose |
| `SUBTITULA_PUBLIC_URL` | URL pública que se codifica en los QR y se muestra en la pantalla de sala |
| `SUBTITULA_HUB` | En `subtitula worker`, URL del hub |
| `SUBTITULA_ON_DEMAND`, `SUBTITULA_LINGER_S` | Idiomas bajo demanda (por defecto activado, 120 s sin público) |
| `SUBTITULA_PAUSE_AFTER_S`, `SUBTITULA_SILENCE_DBFS` | Pausa en silencio (10 s por debajo de −50 dBFS) |
| `SUBTITULA_STALL_S`, `SUBTITULA_STALL_CHARS`, `SUBTITULA_MAX_LAG_S`, `SUBTITULA_STARTUP_S` | Vigía: 10 s trabada con 150 caracteres sin traducir, 6 s de atraso, 6 s muda al arrancar |
| `SUBTITULA_PRICE_INPUT_PER_M`, `SUBTITULA_PRICE_OUTPUT_PER_M` | Precio de respaldo (por millón de tokens) para un modelo que no está en `pricing.py` |
| `OLLAMA_URL`, `SUBTITULA_OLLAMA_MODEL`, `SUBTITULA_WHISPER_MODEL`, `SUBTITULA_WHISPER_DEVICE`, `SUBTITULA_WHISPER_COMPUTE` | Motor local |
| `SUBTITULA_FAKE_DELAY`, `SUBTITULA_FAKE_TWO_STAGE` | Motor de prueba: demora simulada y modo en dos etapas |

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

El modo `live` imita al motor en vivo: tres pistas por sala (original y dos traducciones) cuyas líneas crecen de a un grupo de palabras cada 0,35 s, que es el tráfico más exigente. Resultado en una notebook de 8 núcleos, todo en un solo proceso: **20 salas y 500 personas conectadas, 169 actualizaciones por segundo y 190.050 entregas (4.223 por segundo) sin errores; del hub a la pantalla, 4 ms en p50 y 41 ms en p99**, con el 45% de un núcleo contando a los 500 clientes de prueba. La salida completa está en [`docs/evidencia/carga-20-salas-500-personas.txt`](docs/evidencia/carga-20-salas-500-personas.txt). Con **50 salas y 1.000 personas** (400 actualizaciones y 7.962 entregas por segundo) siguió sin errores, con 53 ms en p50 y 234 ms en p99, usando un núcleo entero: ahí conviene pasar a varios workers y un hub por grupo de salas ([`docs/evidencia/carga-50-salas-1000-personas.txt`](docs/evidencia/carga-50-salas-1000-personas.txt)). Con `--mode chunks` (un subtítulo completo cada ~3 s, como el motor por tramos) dio 6 ms en p50 y 18 ms en p99.

Cuánto cuesta: Live Translate cuenta el audio a 25 tokens por segundo, de entrada y de salida (US$ 2,21 por sesión y por hora; ver [Costos](#costos)). El panel muestra el costo real de cada sala a partir de los tokens que informa la API y los precios oficiales de cada modelo. En las pruebas de 10 minutos se midieron US$ 0,37 por sesión, que coincide con el precio publicado.

Para más de 20 o 30 salas o miles de personas: varios workers por máquina, el hub detrás de un proxy con `proxy_buffering off` para SSE, y un CDN delante de las páginas estáticas.

## Operación durante el evento

### Puesta en producción

- **Un evento chico (hasta 5 o 6 salas):** una sola máquina con `subtitula serve`. Todo funciona en ese modo, incluidos el audio desde el navegador de la sala (`/enviar`) y la interpretación hablada ("Escuchar").
- **Muchas salas o varias máquinas:** `subtitula hub` en una y `subtitula worker --session <sala>` por sala, o Docker Compose con un contenedor por sala. En este modo las salas entran por stream (HLS, RTMP, SRT o YouTube); el audio desde el navegador y "Escuchar" necesitan que el worker corra en el mismo proceso que el hub.
- **HTTPS:** el navegador sólo abre el micrófono en `localhost` o por HTTPS. Para que la compu de la sala use `/enviar` desde otra máquina, poné el hub detrás de un proxy con certificado (por ejemplo [Caddy](https://caddyserver.com): `subtitulos.evento.org { reverse_proxy localhost:8000 }` alcanza, con `flush_interval -1` para que el SSE no se encole). Subir un archivo funciona igual sin HTTPS.
- **Token:** `SUBTITULA_TOKEN` protege la ingesta de workers remotos, el envío de audio y la edición del glosario. Con Docker Compose es obligatorio.

**Antes del evento**

1. Cargar las salas en `config/sessions.yaml` con su agenda (`talks`: título, horario, orador, tema, idioma y glosario de cada charla) y el glosario común en `config/glossary.yaml`. Durante el día, el hub aplica cada charla a su hora.
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

## Referencia: qué hay adentro

### Línea de comandos

| Comando | Qué hace |
|---|---|
| `subtitula serve [--engine X] [--port N]` | Hub y todos los escenarios de `sessions.yaml` en un proceso. El modo con todo: audio desde el navegador, voz, agenda |
| `subtitula hub` | Sólo el hub: vistas, panel, API, exportación. Los workers publican en él |
| `subtitula worker --session ID --hub URL [--source S] [--name N]` | Un escenario en cualquier máquina; publica subtítulos y estado en el hub y recibe de él glosario y demanda |
| `subtitula file charla.mp3 [--language en] [--languages es,pt] [--both] [--realtime] [--out DIR]` | Subtitula un archivo en la terminal y deja `.srt`, `.vtt` y `.txt` por idioma; informa demora y tokens |

### Páginas

`/` y `/s/<sala>?lang=es` (público) · `/pantalla/<sala>?lang=es&lang2=en` (tele de la sala) · `/overlay/<sala>?lang=es[&lines=2&size=44&hide=8&pos=top&box=0&bg=00b140]` (OBS/vMix) · `/admin` (producción) · `/enviar/<sala>` (audio desde el navegador).

### API HTTP

| Método y ruta | Qué devuelve o hace |
|---|---|
| `GET /api/sessions?watching=<sala>&lang=<idioma>` | Salas, idiomas del evento, estado, público y agenda de cada una. Los parámetros informan qué idioma se está mirando (idiomas bajo demanda) |
| `GET /api/sessions/<sala>/captions?since=<seq>&limit=<n>` | Historial de subtítulos |
| `GET /api/sessions/<sala>/stream` | Subtítulos en vivo por Server-Sent Events; con `Last-Event-ID` (o `?since=`) reenvía sólo lo que faltó |
| `GET /api/sessions/<sala>/live.txt?lang=es&lines=2` | Las últimas líneas en texto plano, para títulos de vMix o CasparCG |
| `GET /api/sessions/<sala>/summary?lang=es&minutes=5` | "¿Qué me perdí?": viñetas con Gemma; cacheado 60 s por sala e idioma |
| `GET /api/sessions/<sala>/export.srt|vtt|txt?lang=es` | La charla completa de esa pista |
| `GET /api/sessions/<sala>/qr.svg?lang=es` | QR a `/s/<sala>` con la URL pública |
| `PUT /api/sessions/<sala>/glossary` (token) | Reemplaza el glosario de la sala; aplica desde la línea siguiente y reabre las sesiones Live |
| `POST /api/sessions/<sala>/glossary/suggest` (token) | Términos sugeridos por Gemini a partir de título, orador, tema y el texto que se mande |
| `WS /api/sessions/<sala>/listen?lang=es` | Voz de la interpretación: un JSON con `rate` y después bloques PCM s16le |
| `WS /api/sessions/<sala>/audio?token=` | Audio desde el navegador (PCM 16 kHz) para una sala `browser` |
| `POST /api/ingest/<sala>` (token) | Un worker remoto publica un subtítulo o su estado; la respuesta trae glosario y demanda |
| `GET /api/status` | Estado por sala para el panel: nivel de audio, demoras p50/p90, errores, sesiones, cortes, costo |
| `GET /metrics` | Lo mismo en formato Prometheus |
| `GET /healthz` | Vida del proceso |

### Módulos

| Archivo | Qué hace |
|---|---|
| `subtitula/cli.py` | Comandos, carga de `.env` |
| `subtitula/config.py` | `sessions.yaml`, `glossary.yaml`, agenda (`TalkConfig`, `current_and_next`) |
| `subtitula/audio.py` | Fuentes con ffmpeg y cola de audio del navegador |
| `subtitula/live.py` | Motor `gemini-live`: `LiveTrack` (una sesión por idioma), `TrackBuilder` (líneas por pista), `LiveSessionWorker` (demanda, pausa en silencio, vigía, voz) |
| `subtitula/worker.py` | Base común (estado, costo, glosario) y worker por tramos con publicación en orden; `HttpPublisher` para workers remotos |
| `subtitula/segmenter.py` | Corte por pausas para los motores por tramos |
| `subtitula/engines/` | `gemini.py` (transcribe + pool de traducción con failover), `local.py` (faster-whisper + Gemma por Ollama), `fake.py` (tests y carga) |
| `subtitula/hub.py` | FastAPI: SSE, ingesta, voz, demanda, agenda, resumen, exportación, QR, métricas |
| `subtitula/captions.py` | Modelo `Caption`, pistas y exportación SRT/VTT/TXT |
| `subtitula/glossary.py`, `pricing.py`, `summary.py` | Corrección de glosario con alias, precios oficiales por modelo, resumen y sugerencias |
| `subtitula/web/` | `index.html` + `viewer.js` (público), `i18n.js` (es/en/pt), `pantalla.html`, `overlay.html`, `admin.html`, `enviar.html`, `style.css` |
| `demo/` | La demo pública: repetición de una corrida real |

### Scripts de medición

| Script | Para qué |
|---|---|
| `scripts/check_gemini.py` | Prueba la clave y mide transcripción y traducción por modelo |
| `scripts/drift_test.py` | Demora minuto a minuto de una charla larga (la evidencia de 10 minutos) |
| `scripts/loadtest.py --mode live` | Carga: N salas y M personas sin gastar API |
| `scripts/record_replay.py` | Graba una corrida real para la demo y los SRT de evidencia |
| `scripts/probe_live.py` | Sonda de la Live API para ver los eventos crudos |

## Desarrollo

```bash
pip install -e '.[dev]'
pytest
```

Los tests (34, en CI en cada push) cubren:

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
