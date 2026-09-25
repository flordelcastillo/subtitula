// Vista de audiencia: elegir sala e idioma, y leer los subtítulos en vivo por Server-Sent Events.
(() => {
  const app = document.getElementById("app");
  const { t } = window.I18N;
  const store = {
    get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* modo privado */ } },
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const langName = { es: "Español", en: "English", pt: "Português", fr: "Français", de: "Deutsch", it: "Italiano" };
  const stateText = (state) => t(`state.${state}`);

  const theme = store.get("theme", "dark");
  document.documentElement.dataset.theme = theme;
  // Alto contraste: se guarda la preferencia y, si el sistema lo pide, se activa solo.
  const highContrast = store.get("contrast", matchMedia("(prefers-contrast: more)").matches ? "high" : "") === "high";
  if (highContrast) document.documentElement.dataset.contrast = "high";

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
    window.I18N.apply(app);
    const list = app.querySelector(".rooms");
    const load = async () => {
      const data = await api("/api/sessions");
      document.title = t("title.pick", { event: data.event });
      if (!data.sessions.length) {
        list.innerHTML = `<li class="empty">${esc(t("pick.empty"))}</li>`;
        return;
      }
      list.innerHTML = data.sessions.map((s) => `
        <li><a href="/s/${encodeURIComponent(s.id)}">
          <span class="dot ${dotClass(s.state)}" aria-hidden="true"></span>
          <span class="room-name">${esc(s.name)}</span>
          <span class="room-meta">${[s.speaker, stateText(s.state)].filter(Boolean).map(esc).join(", ")}</span>
        </a></li>`).join("");
    };
    await load();
    setInterval(load, 15000);
  }

  // -- vista de subtítulos ---------------------------------------------------------------------
  async function renderView(sid) {
    app.replaceChildren(document.getElementById("t-view").content.cloneNode(true));
    window.I18N.apply(app);
    const $ = (sel) => app.querySelector(sel);
    const main = $("main.captions");
    const params = new URLSearchParams(location.search);
    const data = await api("/api/sessions");
    const session = data.sessions.find((s) => s.id === sid);
    if (!session) {
      main.innerHTML = `<p class="waiting">${esc(t("notfound", { sid }))} <a href="/">${esc(t("notfound.link"))}</a>.</p>`;
      return;
    }
    $(".name").textContent = session.name;
    document.title = t("title.live", { name: session.name });

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
    const options = [...codes.map((c) => ({ code: c, name: langName[c] || c })), { code: "original", name: t("original") }];
    langs.innerHTML = options.map((o) => `<button class="btn" data-lang="${o.code}" lang="${o.code === "original" ? "" : o.code}">${esc(o.name)}</button>`).join("")
      + `<button class="btn" id="dual" title="${esc(t("dual.title"))}">${esc(t("dual"))}</button>`;
    let ping = () => {};  // se define más abajo, cuando existe la conexión
    const syncButtons = () => {
      langs.querySelectorAll("[data-lang]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
      $("#dual").setAttribute("aria-pressed", String(dual));
      // En el motor en vivo cada idioma corta sus propias líneas: no hay un original línea a línea.
      $("#dual").hidden = lang === "original" || tracked;
      $("#theme").textContent = document.documentElement.dataset.theme === "light" ? t("theme.dark") : t("theme.light");
      $("#contrast").setAttribute("aria-pressed", String(document.documentElement.dataset.contrast === "high"));
      const canListen = speechLangs.includes(lang);
      $("#listen").hidden = !canListen;
      $("#listen").setAttribute("aria-pressed", String(player.on));
      $("#listen").textContent = player.on ? t("listening") : t("listen.in", { lang: langName[lang] || lang });
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
      else { lang = b.dataset.lang; store.set("lang", lang); ping(); }
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
      } else if (b.id === "contrast") {
        const on = document.documentElement.dataset.contrast !== "high";
        if (on) document.documentElement.dataset.contrast = "high"; else delete document.documentElement.dataset.contrast;
        store.set("contrast", on ? "high" : "normal");
        b.setAttribute("aria-pressed", String(on));
      }
    });

    function renderDownloads() {
      const q = `lang=${encodeURIComponent(lang)}`;
      const label = lang === "original" ? t("original").toLowerCase() : (langName[lang] || lang);
      $(".dl .files").innerHTML = [["txt", t("dl.txt")], ["srt", t("dl.srt")], ["vtt", t("dl.vtt")]]
        .map(([fmt, name]) => `<a href="/api/sessions/${encodeURIComponent(sid)}/export.${fmt}?${q}" download>${esc(name)} (${esc(label)})</a>`).join("");
      // Idioma de la interfaz (los subtítulos se eligen arriba).
      $(".dl .ui-langs").innerHTML = window.I18N.langs.map((c) =>
        `<button class="menu-item" data-ui="${c}" aria-pressed="${c === window.I18N.lang}" lang="${c}">${esc(window.I18N.names[c])}</button>`).join("");
    }
    $(".dl").addEventListener("click", (e) => { const b = e.target.closest("[data-ui]"); if (b) window.I18N.set(b.dataset.ui); });

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
        main.innerHTML = `<p class="waiting">${esc(t("waiting.lang"))}</p>`;
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
      if (node) {
        // La línea crece palabra por palabra: si se estaba siguiendo el vivo, queda a la vista.
        const stick = following();
        paint(node, c);
        if (stick) scrollToEnd();
        return;
      }
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

    // "¿Qué me perdí?": resumen de los últimos 5 minutos en el idioma elegido.
    const recap = $("#recap-panel"), recapBody = recap.querySelector(".recap-body");
    const recapLang = () => (lang === "original" ? session.language || "es" : lang);
    async function openRecap() {
      recap.hidden = false;
      recapBody.innerHTML = `<p class="meta">${esc(t("recap.loading"))}</p>`;
      try {
        const r = await fetch(`/api/sessions/${encodeURIComponent(sid)}/summary?lang=${encodeURIComponent(recapLang())}&minutes=5`);
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || r.status);
        if (d.empty || !d.bullets.length) {
          recapBody.innerHTML = `<p class="meta">${esc(t("recap.empty"))}</p>`;
          return;
        }
        const ago = Math.max(0, Math.round(Date.now() / 1000 - d.generated_at));
        const model = d.model.startsWith("gemma") ? "Gemma" : "Gemini";
        recapBody.innerHTML = `<ul>${d.bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`
          + `<p class="meta">${esc(t("recap.meta", { model, when: ago < 5 ? t("recap.now") : t("recap.ago", { s: ago }) }))}</p>`;
      } catch (err) {
        recapBody.innerHTML = `<p class="meta">${esc(t("recap.error", { err: err.message }))}</p>`;
      }
    }
    // El foco entra al panel al abrirlo y vuelve al botón al cerrarlo; Escape también lo cierra.
    const closeRecap = () => { recap.hidden = true; $("#recap").focus(); };
    $("#recap").addEventListener("click", () => { if (recap.hidden) { openRecap(); $("#recap-close").focus(); } else closeRecap(); });
    $("#recap-close").addEventListener("click", closeRecap);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !recap.hidden) closeRecap(); });
    window.addEventListener("scroll", () => { if (following()) $("#jump").hidden = true; }, { passive: true });

    // El pie ocupa una o dos filas según el idioma: los subtítulos dejan siempre ese espacio libre.
    const foot = $("footer.foot");
    const reserve = () => document.documentElement.style.setProperty("--foot-h", `${foot.offsetHeight}px`);
    new ResizeObserver(reserve).observe(foot);
    reserve();

    // Conexión
    const conn = $("#conn"), connText = $("#conn-text");
    let stageState = session.state;
    const setConn = (ok) => {
      const state = ok ? stageState : "reconnecting";
      conn.className = `dot ${ok ? dotClass(stageState) : "bad"}`;
      connText.textContent = ok ? stateText(state) : t("conn.reconnecting");
    };
    const es = new EventSource(`/api/sessions/${encodeURIComponent(sid)}/stream`);
    es.onopen = () => setConn(true);
    es.onerror = () => setConn(false);
    es.onmessage = (e) => add(JSON.parse(e.data));
    // El sondeo dice qué sala e idioma se está mirando: los idiomas sin público no abren sesión.
    ping = async () => {
      try {
        const d = await api(`/api/sessions?watching=${encodeURIComponent(sid)}&lang=${encodeURIComponent(lang)}`);
        const info = d.sessions.find((s) => s.id === sid);
        stageState = info?.state || "offline";
        const langsNow = info?.speech || [];
        if (langsNow.join() !== speechLangs.join()) { speechLangs = langsNow; syncButtons(); }
        setConn(es.readyState === EventSource.OPEN);
      } catch { /* la próxima vuelta reintenta */ }
    };
    setInterval(ping, 10000);
    ping();

    syncButtons();
  }

  const m = location.pathname.match(/^\/s\/([^/]+)/);
  (m ? renderView(decodeURIComponent(m[1])) : renderPick()).catch((err) => {
    app.innerHTML = `<section class="pick"><h1>${esc(t("error.h1"))}</h1><p class="lead">${esc(t("error.lead", { err: err.message }))}</p></section>`;
  });
})();
