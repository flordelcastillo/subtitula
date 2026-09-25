// Textos de la interfaz del público en español, inglés y portugués.
// El idioma se elige por ?ui=, después por la preferencia guardada y después por el del navegador.
window.I18N = (() => {
  const T = {
    es: {
      "app.title": "Subtítulos en vivo", "title.pick": "Subtítulos en vivo, {event}", "title.live": "{name}, subtítulos en vivo",
      "pick.h1": "Elegí la sala",
      "pick.lead": "Subtítulos en vivo de cada charla, en el idioma original o traducidos. Funciona en el celular, sin instalar nada.",
      "pick.empty": "Todavía no hay salas configuradas.", "rooms": "Salas", "rooms.back": "Volver a las salas",
      "listen": "Escuchar", "listen.in": "Escuchar en {lang}", "listening": "Escuchando", "listen.title": "Escuchar la interpretación con auriculares",
      "langs.label": "Idioma de los subtítulos", "original": "Original", "dual": "Con original",
      "dual.title": "Mostrar el original debajo de la traducción",
      "waiting.start": "Esperando que arranque la charla. Los subtítulos aparecen acá apenas alguien habla.",
      "waiting.lang": "Todavía no hay texto en este idioma. Aparece apenas llegue la primera frase.",
      "recap.btn": "¿Qué me perdí?", "recap.title": "Lo último que se dijo", "recap.close": "Cerrar",
      "recap.close.aria": "Cerrar el resumen", "recap.loading": "Resumiendo los últimos 5 minutos…",
      "recap.empty": "Todavía no se dijo lo suficiente para resumir. Probá en un rato.",
      "recap.meta": "Resumen de los últimos 5 minutos, hecho con {model} {when}.", "recap.now": "recién", "recap.ago": "hace {s} s",
      "recap.error": "No se pudo resumir ahora ({err}). Probá de nuevo en un minuto.",
      "jump": "Volver al vivo", "size.smaller": "Texto más chico", "size.bigger": "Texto más grande", "more": "Más",
      "theme.light": "Tema claro", "theme.dark": "Tema oscuro", "ui": "Interfaz",
      "dl.txt": "Texto de la charla", "dl.srt": "Subtítulos SRT", "dl.vtt": "Subtítulos WebVTT",
      "state.live": "En vivo", "state.connecting": "Esperando audio", "state.reconnecting": "Reconectando la fuente",
      "state.ended": "Terminó", "state.stopped": "Detenida", "state.offline": "Sin transmisión",
      "conn.connecting": "Conectando", "conn.reconnecting": "Reconectando",
      "notfound": "No existe la sala “{sid}”.", "notfound.link": "Ver las salas disponibles",
      "error.h1": "No se pudo cargar", "error.lead": "El servidor de subtítulos no respondió ({err}). Recargá la página en unos segundos.",
      "demo.lead": "Repetición de una corrida real con la Gemini Live API: el audio es el de la charla y los subtítulos aparecen en el momento exacto en que salieron. Para usarlo en vivo,",
      "demo.repo": "instalalo desde el repo", "demo.room": "Sala", "demo.captions": "Subtítulos",
      "demo.play": "Reproducir la charla", "demo.pause": "Pausar", "demo.voice": "Escuchar la interpretación",
      "demo.voicing": "Escuchando la interpretación", "demo.hint": "Elegí una sala y un idioma, y tocá “Reproducir la charla”.",
      "demo.tap": "Tocá “Reproducir la charla”.", "demo.first": "Esperando la primera frase…",
      "demo.recorded": "Grabado el {date} con", "demo.lat": "Demora desde la pausa, p50 / p90: original {o} / {o90}, traducción {t} / {t90}", "demo.errors": "{n} errores",
      "demo.note": "Incluye los ~3 s que tarda en abrir la sesión al principio.",
      "demo.original": "(original)",
    },
    en: {
      "app.title": "Live captions", "title.pick": "Live captions, {event}", "title.live": "{name}, live captions",
      "pick.h1": "Pick a room",
      "pick.lead": "Live captions for every talk, in the original language or translated. Works on your phone, nothing to install.",
      "pick.empty": "No rooms configured yet.", "rooms": "Rooms", "rooms.back": "Back to the rooms",
      "listen": "Listen", "listen.in": "Listen in {lang}", "listening": "Listening", "listen.title": "Listen to the interpretation with headphones",
      "langs.label": "Caption language", "original": "Original", "dual": "With original",
      "dual.title": "Show the original under the translation",
      "waiting.start": "Waiting for the talk to start. Captions appear here as soon as someone speaks.",
      "waiting.lang": "Nothing in this language yet. It appears as soon as the first sentence arrives.",
      "recap.btn": "What did I miss?", "recap.title": "What was just said", "recap.close": "Close",
      "recap.close.aria": "Close the summary", "recap.loading": "Summarizing the last 5 minutes…",
      "recap.empty": "Not enough has been said yet. Try again in a while.",
      "recap.meta": "Summary of the last 5 minutes, made with {model} {when}.", "recap.now": "just now", "recap.ago": "{s} s ago",
      "recap.error": "Could not summarize right now ({err}). Try again in a minute.",
      "jump": "Back to live", "size.smaller": "Smaller text", "size.bigger": "Larger text", "more": "More",
      "theme.light": "Light theme", "theme.dark": "Dark theme", "ui": "Interface",
      "dl.txt": "Talk transcript", "dl.srt": "SRT captions", "dl.vtt": "WebVTT captions",
      "state.live": "Live", "state.connecting": "Waiting for audio", "state.reconnecting": "Reconnecting the source",
      "state.ended": "Ended", "state.stopped": "Stopped", "state.offline": "Off air",
      "conn.connecting": "Connecting", "conn.reconnecting": "Reconnecting",
      "notfound": "There is no room “{sid}”.", "notfound.link": "See the available rooms",
      "error.h1": "Could not load", "error.lead": "The caption server did not respond ({err}). Reload the page in a few seconds.",
      "demo.lead": "Replay of a real run with the Gemini Live API: the audio is the talk itself and the captions appear exactly when they were produced. To use it live,",
      "demo.repo": "install it from the repo", "demo.room": "Room", "demo.captions": "Captions",
      "demo.play": "Play the talk", "demo.pause": "Pause", "demo.voice": "Listen to the interpretation",
      "demo.voicing": "Listening to the interpretation", "demo.hint": "Pick a room and a language, then tap “Play the talk”.",
      "demo.tap": "Tap “Play the talk”.", "demo.first": "Waiting for the first sentence…",
      "demo.recorded": "Recorded on {date} with", "demo.lat": "Delay from the speaker's pause, p50 / p90: original {o} / {o90}, translation {t} / {t90}", "demo.errors": "{n} errors",
      "demo.note": "Includes the ~3 s the session takes to open at the start.",
      "demo.original": "(original)",
    },
    pt: {
      "app.title": "Legendas ao vivo", "title.pick": "Legendas ao vivo, {event}", "title.live": "{name}, legendas ao vivo",
      "pick.h1": "Escolha a sala",
      "pick.lead": "Legendas ao vivo de cada palestra, no idioma original ou traduzidas. Funciona no celular, sem instalar nada.",
      "pick.empty": "Ainda não há salas configuradas.", "rooms": "Salas", "rooms.back": "Voltar às salas",
      "listen": "Ouvir", "listen.in": "Ouvir em {lang}", "listening": "Ouvindo", "listen.title": "Ouvir a interpretação com fones",
      "langs.label": "Idioma das legendas", "original": "Original", "dual": "Com original",
      "dual.title": "Mostrar o original abaixo da tradução",
      "waiting.start": "Esperando a palestra começar. As legendas aparecem aqui assim que alguém fala.",
      "waiting.lang": "Ainda não há texto neste idioma. Aparece assim que chegar a primeira frase.",
      "recap.btn": "O que eu perdi?", "recap.title": "O que acabou de ser dito", "recap.close": "Fechar",
      "recap.close.aria": "Fechar o resumo", "recap.loading": "Resumindo os últimos 5 minutos…",
      "recap.empty": "Ainda não foi dito o suficiente para resumir. Tente daqui a pouco.",
      "recap.meta": "Resumo dos últimos 5 minutos, feito com {model} {when}.", "recap.now": "agora", "recap.ago": "há {s} s",
      "recap.error": "Não foi possível resumir agora ({err}). Tente de novo em um minuto.",
      "jump": "Voltar ao vivo", "size.smaller": "Texto menor", "size.bigger": "Texto maior", "more": "Mais",
      "theme.light": "Tema claro", "theme.dark": "Tema escuro", "ui": "Interface",
      "dl.txt": "Texto da palestra", "dl.srt": "Legendas SRT", "dl.vtt": "Legendas WebVTT",
      "state.live": "Ao vivo", "state.connecting": "Esperando áudio", "state.reconnecting": "Reconectando a fonte",
      "state.ended": "Terminou", "state.stopped": "Parada", "state.offline": "Sem transmissão",
      "conn.connecting": "Conectando", "conn.reconnecting": "Reconectando",
      "notfound": "A sala “{sid}” não existe.", "notfound.link": "Ver as salas disponíveis",
      "error.h1": "Não foi possível carregar", "error.lead": "O servidor de legendas não respondeu ({err}). Recarregue a página em alguns segundos.",
      "demo.lead": "Repetição de uma execução real com a Gemini Live API: o áudio é o da palestra e as legendas aparecem no momento exato em que saíram. Para usar ao vivo,",
      "demo.repo": "instale a partir do repositório", "demo.room": "Sala", "demo.captions": "Legendas",
      "demo.play": "Reproduzir a palestra", "demo.pause": "Pausar", "demo.voice": "Ouvir a interpretação",
      "demo.voicing": "Ouvindo a interpretação", "demo.hint": "Escolha uma sala e um idioma e toque em “Reproduzir a palestra”.",
      "demo.tap": "Toque em “Reproduzir a palestra”.", "demo.first": "Esperando a primeira frase…",
      "demo.recorded": "Gravado em {date} com", "demo.lat": "Atraso desde a pausa, p50 / p90: original {o} / {o90}, tradução {t} / {t90}", "demo.errors": "{n} erros",
      "demo.note": "Inclui os ~3 s que a sessão leva para abrir no início.",
      "demo.original": "(original)",
    },
  };
  const NAMES = { es: "Español", en: "English", pt: "Português" };
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* modo privado */ } },
  };
  const wanted = new URLSearchParams(location.search).get("ui") || store.get("ui") || (navigator.language || "es").slice(0, 2);
  let lang = T[wanted] ? wanted : "es";
  document.documentElement.lang = lang;
  const t = (key, vars = {}) => {
    let s = (T[lang] && T[lang][key]) ?? T.es[key] ?? key;
    for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
    return s;
  };
  // Aplica las claves declaradas en el HTML: data-i18n para el texto y data-i18n-attr="aria-label:clave;title:clave".
  function apply(root) {
    root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      el.dataset.i18nAttr.split(";").forEach((pair) => {
        const [attr, key] = pair.split(":");
        if (attr && key) el.setAttribute(attr.trim(), t(key.trim()));
      });
    });
  }
  function set(code) {
    if (!T[code] || code === lang) return;
    store.set("ui", code);
    const url = new URL(location.href);
    url.searchParams.delete("ui");
    location.href = url.toString();  // la página se rearma en el idioma nuevo
  }
  return { t, apply, set, get lang() { return lang; }, langs: Object.keys(T), names: NAMES };
})();
