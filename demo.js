// Demo de repetición: reproduce el audio de la charla y aplica cada actualización de subtítulo
// cuando el audio llega a la posición en la que salió en la corrida real.
(() => {
  const ROOMS = ["sala-a", "sala-b"];
  const { t } = window.I18N;
  window.I18N.apply(document);
  document.querySelector(".ui-langs").innerHTML = window.I18N.langs.map((c) =>
    `<button class="btn" data-ui="${c}" aria-pressed="${c === window.I18N.lang}" lang="${c}">${window.I18N.names[c]}</button>`).join("");
  const NAMES = { es: "Español", en: "English", pt: "Português" };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const $ = (id) => document.getElementById(id);
  const audio = $("audio"), main = document.querySelector("main.captions");
  const data = {};
  let room = ROOMS[0], lang = "es", voice = false, idx = 0, lines = new Map(), lastT = 0;

  const tracksOf = (d) => [...d.targets, d.language];
  const visible = (c) => c.track === lang;

  function renderRooms() {
    $("rooms").innerHTML = `<span class="label">${esc(t("demo.room"))}</span>` + ROOMS.filter((r) => data[r]).map((r) => {
      const d = data[r];
      const route = `${d.language.toUpperCase()} → ${d.targets.map((t) => t.toUpperCase()).join("/")}`;
      return `<button class="btn" data-room="${r}" aria-pressed="${r === room}" title="${esc(d.name)}">${esc(d.speaker.split(" (")[0])}, ${route}</button>`;
    }).join("");
    const d = data[room];
    $("langs").innerHTML = `<span class="label">${esc(t("demo.captions"))}</span>` + tracksOf(d).map((code) =>
      `<button class="btn" data-lang="${code}" aria-pressed="${code === lang}">${NAMES[code]}${code === d.language ? ` ${t("demo.original")}` : ""}</button>`).join("");
    const canVoice = Boolean(d.speech[lang]);
    $("voice").hidden = !canVoice;
    if (!canVoice) voice = false;
    $("voice").setAttribute("aria-pressed", String(voice));
    $("voice").textContent = voice ? t("demo.voicing") : t("demo.voice");
    const s = d.stats, ms = (v) => (v == null ? "–" : `${(v / 1000).toFixed(2)} s`);
    $("stats").innerHTML = `<span>${esc(d.name)}</span><span>${esc(t("demo.recorded", { date: d.recorded_at }))} <code>${esc(d.model)}</code></span>`
      + `<span>${esc(t("demo.lat", { o: ms(s.latency_p50_ms), o90: ms(s.latency_p90_ms), t: ms(s.translation_p50_ms), t90: ms(s.translation_p90_ms) }))}</span>`
      + `<span>${esc(t("demo.errors", { n: s.errors }))}</span><span>${esc(t("demo.note"))}</span>`;
  }

  function source() {
    const d = data[room];
    return voice && d.speech[lang] ? `data/${d.speech[lang].replace(".wav", ".mp3")}` : `data/${room}.mp3`;
  }

  function setSource(keepTime) {
    const t = keepTime ? audio.currentTime : 0, playing = !audio.paused;
    audio.src = source();
    audio.currentTime = t;
    if (playing) audio.play();
  }

  function reset() {
    idx = 0;
    lines = new Map();
    main.innerHTML = "";
  }

  function draw() {
    const shown = [...lines.values()].filter(visible).slice(-8);
    main.innerHTML = shown.length ? shown.map((c, i) => {
      const cls = i === shown.length - 1 ? "cap last" : i >= shown.length - 3 ? "cap recent" : "cap";
      return `<p class="${cls}" lang="${esc(c.lang)}">${esc(c.text)}</p>`;
    }).join("") : `<p class="waiting">${esc(audio.paused ? t("demo.tap") : t("demo.first"))}</p>`;
  }

  function tick() {
    const d = data[room];
    const t = audio.currentTime;
    if (t < lastT - 0.5) reset();  // se volvió atrás: se rearma desde el principio
    lastT = t;
    let changed = false;
    while (idx < d.updates.length && d.updates[idx][0] <= t) {
      const c = d.updates[idx][1];
      lines.set(c.seq, c);
      idx++;
      changed = true;
    }
    if (changed) draw();
    $("progress").value = audio.duration ? t / audio.duration : 0;
    requestAnimationFrame(tick);
  }

  document.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.ui) { window.I18N.set(b.dataset.ui); return; }
    if (b.dataset.room && b.dataset.room !== room) {
      room = b.dataset.room;
      lang = data[room].targets[0];
      voice = false;
      audio.pause();
      reset();
      setSource(false);
    } else if (b.dataset.lang) {
      lang = b.dataset.lang;
      if (voice && !data[room].speech[lang]) { voice = false; setSource(true); }
      else if (voice) setSource(true);
      draw();
    } else if (b.id === "voice") {
      voice = !voice;
      setSource(true);
    } else if (b.id === "play") {
      if (audio.paused) audio.play(); else audio.pause();
    }
    renderRooms();
  });
  audio.addEventListener("play", () => { $("play").textContent = t("demo.pause"); draw(); });
  audio.addEventListener("pause", () => { $("play").textContent = t("demo.play"); });

  Promise.all(ROOMS.map((r) => fetch(`data/${r}.json`).then((res) => (res.ok ? res.json() : null)).then((d) => { if (d) data[r] = d; })))
    .then(() => {
      room = ROOMS.find((r) => data[r]);
      lang = data[room].targets[0];
      renderRooms();
      setSource(false);
      requestAnimationFrame(tick);
    });
})();
