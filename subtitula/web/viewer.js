// Vista de audiencia: elegir sala e idioma, y leer los subtítulos en vivo por Server-Sent Events.
(() => {
  const app = document.getElementById("app");
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* modo privado */ } },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const langName = { es: "Español", en: "English", pt: "Português", fr: "Français", de: "Deutsch", it: "Italiano" };
  const STATE_TEXT = { live: "En vivo", connecting: "Esperando audio", reconnecting: "Reconectando la fuente", ended: "Terminó", stopped: "Detenida", offline: "Sin transmisión" };

  const theme = store.get("theme", "dark");
  document.documentElement.dataset.theme = theme;

  async function api(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json();
  }

  function dotClass(state) {
    return state === "live" ? "live" : state === "reconnecting" ? "bad" : state === "connecting" ? "warn" : "";
  }

  // -- selector de sala ------------------------------------------------------------------------
  async function renderPick() {
    app.replaceChildren(document.getElementById("t-pick").content.cloneNode(true));
    const list = app.querySelector(".rooms");
    const load = async () => {
      const data = await api("/api/sessions");
      document.title = `Subtítulos en vivo, ${data.event}`;
      if (!data.sessions.length) {
        list.innerHTML = `<li class="empty">Todavía no hay salas configuradas.</li>`;
        return;
      }
      list.innerHTML = data.sessions.map((s) => `
        <li><a href="/s/${encodeURIComponent(s.id)}">
          <span class="dot ${dotClass(s.state)}" aria-hidden="true"></span>
          <span class="room-name">${esc(s.name)}</span>
          <span class="room-meta">${[s.speaker, STATE_TEXT[s.state] || s.state].filter(Boolean).map(esc).join(", ")}</span>
        </a></li>`).join("");
    };
    await load();
    setInterval(load, 15000);
  }

  // -- vista de subtítulos ---------------------------------------------------------------------
  async function renderView(sid) {
    app.replaceChildren(document.getElementById("t-view").content.cloneNode(true));
    const $ = (sel) => app.querySelector(sel);
    const main = $("main.captions");
    const params = new URLSearchParams(location.search);
    const data = await api("/api/sessions");
    const session = data.sessions.find((s) => s.id === sid);
    if (!session) {
      main.innerHTML = `<p class="waiting">No existe la sala “${esc(sid)}”. <a href="/">Ver las salas disponibles</a>.</p>`;
      return;
    }
    $(".name").textContent = session.name;
    document.title = `${session.name}, subtítulos en vivo`;

    const codes = data.languages.map((l) => l.code);
    const browser = (navigator.language || "es").slice(0, 2);
    let lang = params.get("lang") || store.get("lang", codes.includes(browser) ? browser : codes[0] || "original");
    let dual = store.get("dual", "0") === "1";
    let scale = parseFloat(store.get("scale", "1")) || 1;
    const caps = [];

    const applyScale = () => { document.documentElement.style.setProperty("--cap-size", `calc(clamp(1.6rem, 5.2vw, 2.6rem) * ${scale})`); };
    applyScale();

    // Idiomas
    const langs = $(".langs");
    const options = [...codes.map((c) => ({ code: c, name: langName[c] || c })), { code: "original", name: "Original" }];
    langs.innerHTML = options.map((o) => `<button class="btn" data-lang="${o.code}" lang="${o.code === "original" ? "" : o.code}">${esc(o.name)}</button>`).join("")
      + `<button class="btn" id="dual" title="Mostrar el original debajo de la traducción">Con original</button>`;
    const syncButtons = () => {
      langs.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
      $("#dual").setAttribute("aria-pressed", String(dual));
      // En el motor en vivo cada idioma corta sus propias líneas: no hay un original línea a línea.
      $("#dual").hidden = lang === "original" || tracked;
      $("#theme").textContent = document.documentElement.dataset.theme === "light" ? "Oscuro" : "Claro";
      const canListen = speechLangs.includes(lang);
      $("#listen").hidden = !canListen;
      $("#listen").setAttribute("aria-pressed", String(player.on));
      $("#listen").textContent = player.on ? "Escuchando" : "Escuchar";
      if (player.on && (!canListen || player.lang !== lang)) {
        player.stop();
        if (canListen) player.start(sid, lang).catch(() => {});
        syncButtons();
        return;
      }
      renderDownloads();
    };
    langs.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.id === "dual") { dual = !dual; store.set("dual", dual ? "1" : "0"); }
      else { lang = b.dataset.lang; store.set("lang", lang); }
      syncButtons();
      redraw();
    });

    // Interpretación hablada (motor en vivo): se escucha con auriculares mientras se leen los subtítulos.
    let speechLangs = session.speech || [];
    const player = {
      on: false, lang: "", ws: null, ctx: null, next: 0, rate: 24000,
      async start(id, code) {
        this.on = true;
        this.lang = code;
        this.next = 0;
        this.ctx = this.ctx || new AudioContext();
        await this.ctx.resume();  // en iOS sólo arranca dentro de un toque del usuario
        const proto = location.protocol === "https:" ? "wss" : "ws";
        this.ws = new WebSocket(`${proto}://${location.host}/api/sessions/${encodeURIComponent(id)}/listen?lang=${encodeURIComponent(code)}`);
        this.ws.binaryType = "arraybuffer";
        this.ws.onmessage = (e) => {
          if (typeof e.data === "string") { const m = JSON.parse(e.data); if (m.rate) this.rate = m.rate; return; }
          this.play(new Int16Array(e.data));
        };
        this.ws.onclose = () => { if (this.on && this.lang === code) setTimeout(() => this.on && this.lang === code && this.start(id, code), 2000); };
      },
      play(pcm) {
        const ctx = this.ctx;
        const frame = Math.round(this.rate * 0.05);  // bloques de 50 ms
        if (this.next < ctx.currentTime + 0.05) this.next = ctx.currentTime + 0.15;  // colchón chico al (re)arrancar
        for (let i = 0; i < pcm.length; i += frame) {
          const slice = pcm.subarray(i, i + frame);
          let sum = 0;
          for (let j = 0; j < slice.length; j++) sum += slice[j] * slice[j];
          const rms = Math.sqrt(sum / slice.length) / 32768;
          const ahead = this.next - ctx.currentTime;
          // Si se va atrasando, se saltean los silencios; si se atrasó mucho, cualquier bloque.
          if ((ahead > 0.4 && rms < 0.01) || ahead > 3) continue;
          const buf = ctx.createBuffer(1, slice.length, this.rate);
          const ch = buf.getChannelData(0);
          for (let j = 0; j < slice.length; j++) ch[j] = slice[j] / 32768;
          const src = ctx.createBufferSource();
          src.buffer = buf;
          src.connect(ctx.destination);
          src.start(this.next);
          this.next += buf.duration;
        }
      },
      stop() {
        this.on = false;
        this.lang = "";
        if (this.ws) { this.ws.onclose = null; this.ws.close(); this.ws = null; }
        if (this.ctx) this.ctx.suspend();
      },
    };
    $("#listen").addEventListener("click", async () => {
      if (player.on) player.stop();
      else {
        try { await player.start(sid, lang); } catch { player.stop(); }
      }
      syncButtons();
    });

    $(".tools").addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.size) {
        scale = Math.min(2, Math.max(0.6, scale + 0.15 * Number(b.dataset.size)));
        store.set("scale", String(scale));
        applyScale();
      } else if (b.id === "theme") {
        const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
        document.documentElement.dataset.theme = next;
        store.set("theme", next);
        syncButtons();
      }
    });

    function renderDownloads() {
      const q = `lang=${encodeURIComponent(lang)}`;
      const label = lang === "original" ? "original" : (langName[lang] || lang).toLowerCase();
      $(".dl .menu").innerHTML = [["txt", "Texto de la charla"], ["srt", "Subtítulos SRT"], ["vtt", "Subtítulos WebVTT"]]
        .map(([fmt, name]) => `<a href="/api/sessions/${encodeURIComponent(sid)}/export.${fmt}?${q}" download>${name} (${esc(label)})</a>`).join("");
    }

    // Subtítulos
    // Con el motor en vivo cada idioma es una pista propia (c.track); se muestra sólo la elegida.
    let tracked = false;
    const visible = (c) => !c.track || (lang === "original" ? c.original : c.track === lang);
    const textOf = (c) => (c.track || lang === "original" || lang === c.lang ? c.text : (c.tr?.[lang] || c.text));
    // Mientras la traducción no llega se muestra el original atenuado, para no dejar el hueco.
    const waiting = (c) => !c.track && lang !== "original" && lang !== c.lang && !c.tr?.[lang] && c.pending;
    function paint(node, c) {
      const last = node.classList.contains("last"), recent = node.classList.contains("recent");
      node.className = "cap" + (waiting(c) ? " pending" : "") + (last ? " last" : "") + (recent ? " recent" : "");
      node.lang = c.track ? c.lang : lang === "original" || waiting(c) ? c.lang : lang;
      node.dataset.seq = c.seq;
      node.innerHTML = lineHtml(c);
    }
    const lineHtml = (c) => {
      const main = textOf(c);
      const showSrc = !c.track && dual && lang !== "original" && c.lang !== lang && main !== c.text;
      return esc(main) + (showSrc ? `<span class="src" lang="${esc(c.lang)}">${esc(c.text)}</span>` : "");
    };
    const following = () => window.innerHeight + window.scrollY >= document.body.scrollHeight - 80;
    const scrollToEnd = () => window.scrollTo({ top: document.body.scrollHeight });

    function mark() {
      const nodes = main.querySelectorAll(".cap");
      nodes.forEach((n, i) => {
        n.classList.toggle("last", i === nodes.length - 1);
        n.classList.toggle("recent", i >= nodes.length - 3 && i < nodes.length - 1);
      });
    }
    function redraw() {
      const shown = caps.filter(visible);
      if (shown.length) {
        main.replaceChildren(...shown.map((c) => { const p = document.createElement("p"); paint(p, c); return p; }));
      } else if (caps.length) {
        main.innerHTML = `<p class="waiting">Todavía no hay texto en este idioma. Aparece apenas llegue la primera frase.</p>`;
      }
      mark();
      scrollToEnd();
    }
    function add(c) {
      if (c.track && !tracked) { tracked = true; syncButtons(); }
      // Una línea que crece (motor en vivo) o una traducción que llega después reemplaza la que ya estaba.
      const idx = caps.findIndex((x) => x.seq === c.seq);
      if (idx >= 0) caps[idx] = c;
      else {
        if (caps.length && c.seq < caps[caps.length - 1].seq) return;
        caps.push(c);
        // Con charlas de una hora el DOM no necesita guardar todo: la descarga tiene el texto completo.
        if (caps.length > 1200) caps.shift();
      }
      if (!visible(c)) return;
      const node = main.querySelector(`.cap[data-seq="${c.seq}"]`);
      if (node) { paint(node, c); return; }
      const stick = following();
      main.querySelector(".waiting")?.remove();
      const p = document.createElement("p");
      paint(p, c);
      main.append(p);
      const nodes = main.querySelectorAll(".cap");
      if (nodes.length > 400) nodes[0].remove();
      mark();
      if (stick) scrollToEnd(); else $("#jump").hidden = false;
    }

    $("#jump").addEventListener("click", () => { scrollToEnd(); $("#jump").hidden = true; });
    window.addEventListener("scroll", () => { if (following()) $("#jump").hidden = true; }, { passive: true });

    // Conexión
    const conn = $("#conn"), connText = $("#conn-text");
    let stageState = session.state;
    const setConn = (ok) => {
      const state = ok ? stageState : "reconnecting";
      conn.className = `dot ${ok ? dotClass(stageState) : "bad"}`;
      connText.textContent = ok ? (STATE_TEXT[state] || state) : "Reconectando";
    };
    const es = new EventSource(`/api/sessions/${encodeURIComponent(sid)}/stream`);
    es.onopen = () => setConn(true);
    es.onerror = () => setConn(false);
    es.onmessage = (e) => add(JSON.parse(e.data));
    setInterval(async () => {
      try {
        const d = await api("/api/sessions");
        const info = d.sessions.find((s) => s.id === sid);
        stageState = info?.state || "offline";
        const langsNow = info?.speech || [];
        if (langsNow.join() !== speechLangs.join()) { speechLangs = langsNow; syncButtons(); }
        setConn(es.readyState === EventSource.OPEN);
      } catch { /* la próxima vuelta reintenta */ }
    }, 10000);

    syncButtons();
  }

  const m = location.pathname.match(/^\/s\/([^/]+)/);
  (m ? renderView(decodeURIComponent(m[1])) : renderPick()).catch((err) => {
    app.innerHTML = `<section class="pick"><h1>No se pudo cargar</h1><p class="lead">El servidor de subtítulos no respondió (${esc(err.message)}). Recargá la página en unos segundos.</p></section>`;
  });
})();
