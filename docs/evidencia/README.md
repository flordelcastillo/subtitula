# Evidencia · Evidence

Mediciones reproducibles contra la API real, con el comando que las generó. *Reproducible measurements against the real API, with the command that produced each one.*

## Demora minuto a minuto (10 minutos por charla) · Minute-by-minute delay

| Archivo · File | Charla · Talk | Comando · Command |
|---|---|---|
| `atraso-10min-thor-en-es.json` | Thor Schaeff, Nerdearla 2025, minutos 10 a 20, inglés → español | `python scripts/drift_test.py thor10.mp3 --language en --targets es` |
| `atraso-10min-midudev-es-en.json` | Miguel Ángel Durán, Nerdearla 2025, minutos 10 a 20, español → inglés | `python scripts/drift_test.py midu10.mp3 --language es --targets en` |

Resultado · Result (motor `gemini-live`, 25/09/2026):

| | Original p50 | Original p90 | Traducción p50 · Translation p50 | Traducción p90 · Translation p90 | Errores · Errors | Costo · Cost |
|---|---|---|---|---|---|---|
| en → es | 0,34 s | 0,90 s | 0,34 s | 0,89 s | 0 | US$ 0,37 |
| es → en | 0,34 s | 0,69 s | 0,29 s | 0,76 s | 0 | US$ 0,37 |

Cada JSON trae la tabla por minuto (`por_minuto`): no hay atraso acumulado, el peor minuto dio 2,1 s de p90. *Each JSON holds the per-minute table; there is no accumulated drift, the worst minute was 2.1 s p90.*

**Qué mide la demora · What the delay measures.** Es el tiempo entre que el orador hace una pausa (300 ms o más de silencio) y que llega la última palabra de la frase que estaba diciendo. Se mide sólo en las frases que cierran hasta 4 s después de una pausa y antes de que el orador retome; una frase larga sin pausas no se mide (`frases_medidas` en cada minuto dice cuántas entraron). No mide de punta a punta contra las marcas de tiempo del video; por eso es comparable entre corridas y se puede ver en vivo en `/admin`, pero no es un "lag" contra el audio original. La primera frase de cada sesión suma los ~3 s de apertura. *It is the time from the speaker's pause (300 ms or more of silence) to the last word of that sentence. Only sentences that close within 4 s of a pause and before the speaker resumes are measured (`frases_medidas` gives the count per minute). It is not an end-to-end lag against the video's timestamps; it is comparable across runs and visible live in `/admin`. The first sentence of each session includes the ~3 s session start.*

## Calidad · Quality

`srt/`: los subtítulos finales de 2 minutos de cada charla de ejemplo, del original y de cada traducción, tal como los exporta `/api/sessions/<sala>/export.srt`. Se generaron con `scripts/record_replay.py`, la misma corrida que alimenta la [demo pública](https://flordelcastillo.github.io/subtitula/). *Final SRT files for 2 minutes of each sample talk, original and each translation, as exported by the API; produced by `scripts/record_replay.py`, the same run that feeds the public demo.*

Los clips de `samples/` están cortados en un límite de oración. En una prueba anterior, el clip en español arrancaba en mitad de una frase ("O sea, no sé, pero…") y el reconocedor escribió las primeras palabras en portugués aunque se le indicó `language_codes=["es"]`; una charla real empieza con silencio y un saludo, no en medio de una palabra. *The sample clips are cut at a sentence boundary: in an earlier run, the Spanish clip started mid-sentence and the recognizer wrote the first words in Portuguese despite the `es` language hint; a real talk starts with silence and a greeting, not mid-word.*

Los JSON de esa corrida están en `demo/data/`: cada actualización de subtítulo con su posición en el audio, más `stats` (p50, p90, errores, reconexiones, costo). *The JSON files of that run live in `demo/data/`.* La reconexión que figura en `stats` es la que pide el propio servidor de la Live API (`GoAway`) cerca del final de la sesión; se retoma con el contexto y sin perder audio. *The one reconnection in `stats` is the server-requested `GoAway` near the end of the session; it resumes with context and no audio loss.*

## Carga · Load

`carga-20-salas-500-personas.txt`: salida de `python scripts/loadtest.py --mode live --stages 20 --viewers 25 --seconds 45` en una notebook de 8 núcleos, todo en un solo proceso (hub más los 500 clientes de prueba). *Output of the load test on an 8-core laptop, hub and the 500 test clients in one process.*

## Cómo reproducir · How to reproduce

```bash
pip install -e '.[dev]'
echo GEMINI_API_KEY=... > .env
python scripts/drift_test.py <charla.mp3> --language en --targets es --out resultado.json
python scripts/record_replay.py samples/thor-schaeff-multilingual-agents-en.mp3 --id sala-a --name "..." --language en --targets es,pt --out demo/data
python scripts/loadtest.py --mode live --stages 20 --viewers 25 --seconds 45
```
