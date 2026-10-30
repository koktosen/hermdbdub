/* hermdbw board — vanilla JS, no build step. Polls data/*.json; keys 1-9 / arrows / space switch pages. */
(() => {
  const qs = new URLSearchParams(location.search);
  const ALL_PAGES = ["calendar", "feed", "weather"];
  let PAGES = ALL_PAGES.slice();
  const LABELS = { calendar: "Calendar", feed: "Feed", weather: "Weather" };
  const layout = (key, fallback) => (Array.isArray(data.config?.[key]) ? data.config[key] : fallback);
  const REFRESH_MS = 60_000;
  const SCROLL_PX_PER_S = 14;   // column auto-scroll speed (GPU-composited transform, cheap on the Pi)
  let rotateS = qs.has("rotate") ? Number(qs.get("rotate")) : null; // null = use config
  let paused = false, rotateTimer = null, data = {}, sliding = false;
  let current = qs.get("page") || PAGES[0];
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtT = (d) => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const sameDay = (a, b) => a.toDateString() === b.toDateString();
  const rotation = () => (data.config?.rotate_pages || PAGES).filter((p) => PAGES.includes(p));

  // ---------- navigation (slide transitions) ----------
  function show(page, dir = 1, animate = true) {
    if (!PAGES.includes(page)) return;
    document.body.className = document.body.className.replace(/\bpage-\w+/g, "").trim() + " page-" + page;
    if (page === current && $(`#page-${page}`).classList.contains("active")) return;
    const from = $(`#page-${current}`), to = $(`#page-${page}`);
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("exit-left", "exit-right", "from-left"));
    if (animate && from !== to) {
      to.classList.toggle("from-left", dir < 0);
      void to.offsetWidth; // flush so the start position applies before the transition
      from.classList.remove("active"); from.classList.add(dir > 0 ? "exit-left" : "exit-right");
      to.classList.remove("from-left"); to.classList.add("active");
      sliding = true; setTimeout(() => { sliding = false; from.classList.remove("exit-left", "exit-right"); }, 600);
    } else {
      from.classList.remove("active"); to.classList.add("active");
    }
    current = page;
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
    render(page);
  }
  function step(delta) {
    const list = rotation().includes(current) ? rotation() : PAGES;
    show(list[(list.indexOf(current) + delta + list.length) % list.length], delta);
    scheduleRotate();
  }
  function scheduleRotate() {
    clearTimeout(rotateTimer);
    const s = rotateS ?? data.config?.rotate_seconds ?? 0;
    if (s > 0 && !paused) rotateTimer = setTimeout(() => step(1), s * 1000);
  }
  function applyLayout() {
    const want = layout("pages", ALL_PAGES).filter((p) => ALL_PAGES.includes(p));
    PAGES = want.length ? want : ALL_PAGES.slice();
    if (!PAGES.includes(current)) current = PAGES[0];
    $("#tabs").innerHTML = PAGES.map((p, i) => `<button data-page="${p}"><span class="key">${i + 1}</span>${LABELS[p]}</button>`).join("");
    const cols = layout("feed_columns", ["headlines", "xtrends", "xme", "brief"]);
    document.querySelectorAll("#page-feed .feed-col").forEach((el) => { el.hidden = !cols.includes(el.dataset.col); });
    $(".feed-cols").style.gridTemplateColumns = cols.map((c) => ({ headlines: "1.3fr", xtrends: "1fr", xme: ".95fr", brief: "1fr" }[c] || "1fr")).join(" ");
    const rows = layout("ticker_rows", ["crypto", "stocks"]);
    $("#ticker-crypto").hidden = !rows.includes("crypto"); $("#ticker-stocks").hidden = !rows.includes("stocks");
    const mq = layout("marquees", ["ticker", "news"]);
    $("#mq-ticker").hidden = !mq.includes("ticker"); $("#mq-news").hidden = !mq.includes("news");
    $("#dock").hidden = !layout("dock_tiles", ["upnext"]).length && !mq.length;
    $("#brief-title").textContent = data.config?.agent_name || "Brief";
  }
  applyLayout();
  $("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) { show(b.dataset.page); scheduleRotate(); } });
  // USB numpad / macro pad: digits select pages, 0/Enter = brief, +/- = next/prev, * = pause, / = reload.
  // With NumLock off a numpad sends navigation keys instead, so those are aliased to the same digits.
  const NUMPAD_ALIAS = { End: "1", ArrowDown: "2", PageDown: "3", ArrowLeft: "4", Clear: "5", ArrowRight: "6", Home: "7", ArrowUp: "8", PageUp: "9", Insert: "0", Delete: "." };
  document.addEventListener("keydown", (e) => {
    if (e.key === "+" || e.key === "Add") return step(1);
    if (e.key === "-" || e.key === "Subtract") return step(-1);
    if (e.key === "*" || e.key === "Multiply") { paused = !paused; scheduleRotate(); setStatus(); return; }
    if (e.key === "/" || e.key === "Divide") return location.reload();
    const key = (e.location === 3 && NUMPAD_ALIAS[e.key]) || e.key;   // location 3 = numeric keypad
    const n = Number(key);
    if (n >= 1 && n <= PAGES.length) { show(PAGES[n - 1], PAGES.indexOf(PAGES[n - 1]) >= PAGES.indexOf(current) ? 1 : -1); scheduleRotate(); }
    else if (e.key === "ArrowRight" || e.key === "PageDown") step(1);
    else if (e.key === "ArrowLeft" || e.key === "PageUp") step(-1);
    else if (e.key === " ") { paused = !paused; scheduleRotate(); setStatus(); }
    else if (e.key === "r") location.reload();
  });

  // ---------- clock ----------
  function tickClock() {
    const d = new Date();
    $("#time").textContent = fmtT(d);
    $("#date").textContent = d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" });
    if (current === "calendar") renderNextUp();
  }
  setInterval(tickClock, 1000); tickClock();

  // ---------- data ----------
  let fetchFails = 0;  // consecutive refresh cycles with no reachable server → reload (clears stale connections after a network move)
  async function load(name) {
    try {
      const r = await fetch(`data/${name}.json`, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      data[name] = await r.json(); return true;
    } catch (e) { data[name] = data[name] || { error: String(e) }; return false; }
  }
  async function refresh() {
    const results = await Promise.all(["calendar", "weather", "brief", "ops", "markets", "rss", "xtrends", "xme", "xusage", "fng", "status"].map(load));
    fetchFails = results.some(Boolean) ? 0 : fetchFails + 1;
    if (fetchFails >= 3 && !tk.open && !flashing) location.reload();
    data.config = data.status?.config || data.config;
    applyLayout(); renderWeather(); renderDock(); render(current); setStatus();
    if (!rotateTimer) scheduleRotate();
  }
  setInterval(refresh, REFRESH_MS);
  document.body.classList.add("init"); // no slide on first paint
  refresh().then(() => { $(`#page-${current}`).classList.add("active"); show(current, 1, false); setTimeout(() => document.body.classList.remove("init"), 300); });

  function setFresh() {
    const el = $("#fresh"); const gen = data.status?.generated_at ? new Date(data.status.generated_at) : null;
    if (!gen) { el.className = "fresh dead"; el.lastElementChild.textContent = "no data"; return; }
    const m = Math.round((Date.now() - gen) / 60000);
    el.className = "fresh" + (m > 30 ? " dead" : m > 10 ? " stale" : "");
    el.lastElementChild.textContent = `updated ${fmtT(gen)}` + (m > 10 ? ` · ${m} min ago` : "");
  }
  setInterval(setFresh, 30_000);

  function setStatus() {
    setFresh();
    const st = data.status?.collectors || {};
    const errs = Object.entries(st).filter(([, v]) => !v.ok).map(([k, v]) => `<span class="err">${k}: ${esc(v.error)}</span>`);
    const calErr = Object.entries(data.calendar?.errors || {}).map(([k, v]) => `<span class="err">${k}: ${esc(v)}</span>`);
    const gen = data.status?.generated_at ? new Date(data.status.generated_at) : null;
    $("#status").innerHTML = [
      `hermdbw · data ${gen ? fmtT(gen) : "—"}`,
      paused ? "rotation paused" : "",
      ...errs, ...calErr,
    ].filter(Boolean).join(" · ");
  }

  // ---------- auto-scroll (Web Animations on transform: composited, no per-frame JS) ----------
  const anims = new Map();
  function autoScroll(inner) {
    const outer = inner.parentElement;
    const overflow = inner.scrollHeight - outer.clientHeight;
    const prev = anims.get(inner);
    const prevTime = prev?.currentTime || 0;
    prev?.cancel();
    if (overflow <= 8) { inner.style.transform = ""; anims.delete(inner); return; }
    const a = inner.animate(
      [{ transform: "translateY(0)" }, { transform: "translateY(0)", offset: 0.08 },
       { transform: `translateY(-${overflow}px)`, offset: 0.92 }, { transform: `translateY(-${overflow}px)` }],
      { duration: (overflow / SCROLL_PX_PER_S) * 1000 / 0.84, iterations: Infinity, direction: "alternate", easing: "linear" });
    a.currentTime = prevTime;
    anims.set(inner, a);
  }
  function restartScrollers() { document.querySelectorAll("#page-feed .scroller").forEach(autoScroll); }

  // ---------- moon phase (computed locally, no API) ----------
  const SYNODIC = 29.530588853, NEW_MOON_REF = Date.UTC(2000, 0, 6, 18, 14);
  const moonAge = (d) => (((d - NEW_MOON_REF) / 86400000) % SYNODIC + SYNODIC) % SYNODIC;
  function moonInfo(d = new Date()) {
    const age = moonAge(d), frac = age / SYNODIC;
    const names = ["New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous", "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent"];
    const icons = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"];
    const idx = Math.round(frac * 8) % 8;
    const illum = Math.round((1 - Math.cos(frac * 2 * Math.PI)) / 2 * 100);
    const toFull = ((SYNODIC / 2 - age) + SYNODIC) % SYNODIC, toNew = (SYNODIC - age) % SYNODIC;
    const next = toFull < toNew ? { what: "Full", days: toFull } : { what: "New", days: toNew };
    next.date = new Date(d.getTime() + next.days * 86400000);
    return { name: names[idx], icon: icons[idx], illum, age: Math.round(age), next };
  }
  function renderMoon() {
    const m = moonInfo();
    $("#moon").innerHTML = `<span class="mi">${m.icon}</span><span class="mt"><b>${m.name}</b><span>${m.illum}% lit · day ${m.age}</span><small>${m.next.what} ${m.next.date.toLocaleDateString([], { month: "short", day: "numeric" })} · in ${Math.round(m.next.days)}d</small></span>`;
  }
  renderMoon(); setInterval(renderMoon, 3600_000);

  // ---------- weather strip ----------
  function renderWeather() {
    const w = data.weather;
    const el = $("#weather-strip");
    if (!w || !w.configured) { el.className = "muted"; el.textContent = w?.hint || "weather: not configured"; return; }
    el.className = "";
    const c = w.current;
    const days = (w.daily || []).slice(0, 5).map((d) => {
      const dt = new Date(d.date + "T12:00");
      return `<div class="day"><span>${dt.toLocaleDateString([], { weekday: "short" })}</span><span>${d.icon}</span><b>${d.hi}°</b><span>${d.lo}°</span></div>`;
    }).join("");
    el.innerHTML = `<span class="now">${c.icon} ${c.temp}°</span><span><span class="where">${esc(w.location || "")}</span> · ${esc(c.label)} · feels ${c.feels}° · wind ${c.wind} mph</span>${days}`;
  }

  // ---------- calendar ----------
  function events() { return (data.calendar?.events || []).map((e) => ({ ...e, s: new Date(e.start), e: new Date(e.end) })); }
  function renderNextUp() {
    const now = new Date(), el = $("#next-up");
    const timed = events().filter((e) => !e.all_day);
    const live = timed.find((e) => e.s <= now && e.e > now);
    const next = timed.find((e) => e.s > now);
    const ev = live || next;
    if (!ev) { el.className = "card hero"; el.innerHTML = `<div class="label">Next up</div><div class="title muted">Nothing scheduled</div>`; return; }
    const ms = (live ? ev.e : ev.s) - now, m = Math.floor(ms / 60000), h = Math.floor(m / 60);
    const cd = h >= 24 ? `${Math.floor(h / 24)}d ${h % 24}h` : h ? `${h}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
    el.className = "card hero" + (live ? " now" : m < 15 ? " soon" : "");
    el.innerHTML = `<div class="label">${live ? "Happening now · ends in" : "Next up · in"}</div>
      <div class="countdown">${cd}</div>
      <div class="title"><span class="dot" style="display:inline-block;width:.6em;height:.6em;border-radius:50%;background:${ev.color};margin-right:.4em"></span>${esc(ev.title)}</div>
      <div class="meta">${sameDay(ev.s, now) ? "" : ev.s.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" }) + " · "}${fmtT(ev.s)} – ${fmtT(ev.e)}${ev.location && !/^https?:\/\//i.test(ev.location) ? " · " + esc(ev.location) : ""}${ev.video ? " · 🎥 video call" : ""}</div>`;
  }
  function renderCalendar() {
    const now = new Date(), evs = events();
    const today = evs.filter((e) => sameDay(e.s, now) || (e.all_day && e.s <= now && e.e > now));
    const upcomingToday = today.filter((e) => e.e > now).length;
    const row = (e) => `
      <div class="ev${e.e < now ? " past" : ""}">
        <div class="t">${e.all_day ? "all day" : fmtT(e.s)}</div>
        <div><div class="ttl"><span class="dot" style="background:${e.color}"></span>${esc(e.title)}</div>
        ${e.location && !/^https?:\/\//i.test(e.location) ? `<div class="loc">${esc(e.location)}</div>` : e.video ? `<div class="loc">🎥 video call</div>` : ""}</div>
      </div>`;
    let html = today.map(row).join("");
    if (!today.length) html = `<div class="empty">${data.calendar?.sources?.length ? "Nothing more today." : "No calendar feeds configured — add iCal URLs to config.yaml."}</div>`;
    // When today is (nearly) done, fill the column with the next few days so the space stays useful.
    if (upcomingToday < 4) {
      let shown = today.length;
      for (let i = 1; i <= 7 && shown < 11; i++) {
        const d = new Date(now); d.setDate(now.getDate() + i); d.setHours(0, 0, 0, 0);
        const d2 = new Date(d); d2.setDate(d.getDate() + 1);
        const list = evs.filter((e) => e.s < d2 && e.e > d && (e.s >= d || e.all_day));
        if (!list.length) continue;
        const label = i === 1 ? "Tomorrow" : d.toLocaleDateString([], { weekday: "long" });
        html += `<div class="day-head">${label} <span class="muted">· ${d.toLocaleDateString([], { month: "short", day: "numeric" })}</span></div>`;
        html += list.slice(0, 11 - shown).map(row).join("");
        shown += list.length;
      }
    }
    $("#today-list").innerHTML = html;
    const cols = [], nDays = data.config?.week_days || 5;
    for (let i = 0; i < nDays; i++) {
      const d = new Date(now); d.setDate(now.getDate() + i); d.setHours(0, 0, 0, 0);
      const d2 = new Date(d); d2.setDate(d.getDate() + 1);
      const list = evs.filter((e) => e.s < d2 && e.e > d);
      cols.push(`<div class="day-col${i === 0 ? " today" : ""}">
        <div class="dh"><span>${d.toLocaleDateString([], { weekday: "short" })}</span><b>${d.getDate()}</b></div>
        ${list.slice(0, 12).map((e) => `<div class="chip" style="border-color:${e.color}"><div class="ct">${e.all_day ? "all day" : fmtT(e.s)}</div><div class="cn">${esc(e.title)}</div></div>`).join("")}
        ${list.length > 12 ? `<div class="muted">+${list.length - 12} more</div>` : ""}
      </div>`);
    }
    $("#week-grid").style.gridTemplateColumns = `repeat(${nDays}, 1fr)`;
    $("#week-grid").innerHTML = cols.join("");
    renderNextUp();
  }

  // ---------- markdown-lite ----------
  function md(text) { // headings, bullets, bold, code
    const lines = esc(text).split("\n"); let out = "", inList = false;
    for (const l of lines) {
      const li = l.match(/^\s*[-*•]\s+(.*)/);
      if (li) { if (!inList) { out += "<ul>"; inList = true; } out += `<li>${li[1]}</li>`; continue; }
      if (inList) { out += "</ul>"; inList = false; }
      const h = l.match(/^#{1,3}\s+(.*)/);
      out += h ? `<h3>${h[1]}</h3>` : l + "\n";
    }
    if (inList) out += "</ul>";
    return out.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  }

  // ---------- feed ----------
  const ago = (iso) => {
    if (!iso) return ""; const m = Math.round((Date.now() - new Date(iso)) / 60000);
    return m < 60 ? `${m}m` : m < 1440 ? `${Math.round(m / 60)}h` : `${Math.round(m / 1440)}d`;
  };
  function spark(vals) {
    if (!vals || vals.length < 2) return "";
    const min = Math.min(...vals), max = Math.max(...vals), r = max - min || 1;
    const pts = vals.map((v, i) => `${(i / (vals.length - 1) * 52).toFixed(1)},${(20 - (v - min) / r * 18 + 1).toFixed(1)}`);
    return `<svg viewBox="0 0 52 22"><path d="M${pts.join(" L")}"/></svg>`;
  }
  const fmtPx = (p) => p >= 1000 ? p.toLocaleString([], { maximumFractionDigits: 0 }) : p >= 1 ? p.toFixed(2) : p.toPrecision(3);
  const level = (pct, warn = 75, crit = 90) => (pct >= crit ? "crit" : pct >= warn ? "warn" : "");
  const stCls = (s) => (s === "active" || s === true ? "good" : s === "inactive" || s === false ? "critical" : "warning");

  function renderFeed() {
    const m = data.markets || {};
    const tile = (t) => {
      const dir = t.change_24h > 0 ? "up" : t.change_24h < 0 ? "down" : "";
      const icon = t.logo ? `<img src="${esc(t.logo)}" alt="">` : "";
      return `<div class="tick ${dir}"><span class="sym">${icon}${esc(t.symbol)}</span><span class="chg ${dir}">${t.change_24h == null ? "" : (t.change_24h > 0 ? "+" : "") + t.change_24h.toFixed(1) + "%"}</span><span class="px">$${fmtPx(t.price)}</span>${spark(t.spark)}</div>`;
    };
    $("#ticker-crypto").innerHTML = (m.crypto || []).filter((t) => t.price != null).map(tile).join("") || `<div class="muted">no crypto data</div>`;
    $("#ticker-stocks").innerHTML = (m.stocks || []).filter((t) => t.price != null).map(tile).join("") || `<div class="muted">no stock data</div>`;

    const r = data.rss || {};
    $("#headlines").innerHTML = (r.feeds || []).map((f) => `<div class="src">${esc(f.name)}</div>` +
      f.items.map((i) => `<div class="hl"><span>${esc(i.title)}</span><span class="ago">${ago(i.time)}</span></div>`).join("")).join("") || `<div class="muted">no feeds configured</div>`;

    const x = data.xtrends || {};
    $("#x-stamp").textContent = x.found ? ago(x.generated_at) + " ago" + (x.source ? " · " + esc(x.source) : "") : "";
    $("#xtrends").innerHTML = x.trends?.length
      ? x.trends.map((t) => `<div class="tr"><div><div class="tn">${esc(t.name)}</div>${t.category ? `<div class="tc">${esc(t.category)}</div>` : ""}</div><div class="tp">${esc(t.posts || "")}<small>${esc(t.since || "")}</small></div></div>`).join("")
      : x.found && x.text ? md(x.text) : `<span class="muted">${esc(x.error || x.hint || "no trends yet")}</span>`;

    const xm = data.xme || {};
    $("#xme-title").textContent = xm.me ? `X · @${xm.me} ${xm.source === "timeline" ? "timeline" : "mentions"}` : "X · you";
    $("#xme-stamp").textContent = [xm.found && xm.generated_at ? ago(xm.generated_at) + " ago" : "", xm.usage ? `${xm.usage.today} read${xm.usage.today === 1 ? "" : "s"} today · ${xm.usage.month} this month` : ""].filter(Boolean).join(" · ");
    $("#xme").innerHTML = (xm.posts || []).length
      ? xm.posts.map((p) => `<div class="xp"><div class="who">${esc(p.name || p.handle || "")}<small>@${esc(p.handle || "")} · ${ago(p.time)}</small></div><div class="tx">${esc(p.text)}</div></div>`).join("")
      : `<span class="muted">${esc(xm.error || xm.hint || "no posts yet")}</span>`;

    const b = data.brief || {};
    $("#brief-stamp").textContent = b.found ? b.run_time.slice(0, 16) : "";
    $("#brief-body").innerHTML = b.found ? md(b.text) : `<span class="muted">${esc(b.hint || "no brief yet")}</span>`;

    renderBriefCue();
    requestAnimationFrame(restartScrollers);
  }

  function renderBottomStrip() {
    const t = [], now = new Date(), tiles = layout("dock_tiles", ["upnext", "fng", "hours", "host"]);
    const want = (k) => tiles.includes(k);
    // Up next: the next three timed events across all calendars
    const next = events().filter((e) => !e.all_day && e.e > now).slice(0, 3);
    const cd = (e) => { const m = Math.max(0, Math.round((e.s - now) / 60000)); return e.s <= now ? "now" : m < 60 ? `in ${m}m` : m < 1440 ? `in ${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `in ${Math.round(m / 1440)}d`; };
    if (want("upnext")) t.push(`<div class="mini upnext"><div class="th">up next</div>${next.map((e) => `<div class="ev"><div class="t">${sameDay(e.s, now) ? fmtT(e.s) : e.s.toLocaleDateString([], { weekday: "short" }) + " " + fmtT(e.s)}</div><div class="ttl"><span class="dot" style="background:${e.color}"></span>${esc(e.title)}</div><div class="cd">${cd(e)}</div></div>`).join("") || `<div class="muted">nothing scheduled</div>`}</div>`);
    // Crypto Fear & Greed
    const f = data.fng || {};
    if (want("fng")) t.push(`<div class="mini"><div class="th">crypto fear &amp; greed</div><div class="v">${f.value ?? "–"} <small>${esc(f.label || "")}</small></div><div class="gauge"><i style="left:${f.value ?? 50}%"></i></div></div>`);
    // Next hours of weather
    const w = data.weather || {};
    const hrs = (w.hourly || []).filter((h) => new Date(h.time) >= now).slice(0, 8);
    if (want("hours")) t.push(`<div class="mini"><div class="th">next hours · ${esc(w.location || "")}</div><div class="hours">${hrs.map((h) => `<div><span>${new Date(h.time).toLocaleTimeString([], { hour: "numeric" })}</span><span>${h.icon}</span><b>${h.temp}°</b><span>${h.pop ? h.pop + "%" : ""}</span></div>`).join("") || `<span class="muted">set location in config.yaml</span>`}</div></div>`);
    // host in one line
    const o = data.ops || {}, sys = o.system || {}, svc = Object.entries(o.services || {});
    const onDemand = new Set(o.services_on_demand || []);
    const bad = svc.filter(([n, s]) => s !== "active" && !onDemand.has(n)).map(([n]) => n);
    const gpu = (o.gpus || []).map((g) => `${g.busy}%`).join(" / ");
    if (want("host")) t.push(`<div class="mini"><div class="th">${esc(o.host || "server")}</div><div class="hostline"><span>load <b>${sys.load1 ?? "–"}</b></span><span>mem <b>${sys.mem_used_pct ?? "–"}%</b></span><span>gpu <b>${gpu || "–"}</b></span><span>ts <b>${o.tailscale?.online ?? "–"}</b>/${o.tailscale?.total ?? "–"}</span><span class="st ${bad.length ? "critical" : "good"}">${bad.length ? bad.join(", ") + " down" : "services ok"}</span>${data.xusage?.local ? `<span>X api <b>${data.xusage.local.today}</b> today · ${data.xusage.local.month} mo${data.xusage.official?.project_usage ? ` · X says ${data.xusage.official.project_usage}` : ""}</span>` : ""}</div></div>`);
    $("#bottom-strip").style.gridTemplateColumns = tiles.map((k) => ({ upnext: "1.6fr", fng: ".7fr", hours: "1.5fr", host: ".9fr" }[k] || "1fr")).join(" ");
    $("#bottom-strip").innerHTML = t.join("");
  }

  const mqAnims = new Map();
  function marquee(id, html, pxPerS = 60) {
    const track = document.querySelector(`#${id} .mq-track`);
    if (!html) { track.innerHTML = ""; return; }
    track.innerHTML = html + html; // duplicated so the loop is seamless
    const half = track.scrollWidth / 2;
    const prev = mqAnims.get(id); const t0 = prev?.currentTime || 0; prev?.cancel();
    const a = track.animate([{ transform: "translateX(0)" }, { transform: `translateX(-${half}px)` }], { duration: (half / pxPerS) * 1000, iterations: Infinity, easing: "linear" });
    a.currentTime = t0 % a.effect.getTiming().duration; mqAnims.set(id, a);
  }
  function renderDock() {
    renderBottomStrip();
    const m = data.markets || {};
    const items = [...(m.crypto || []), ...(m.stocks || [])].filter((t) => t.price != null).map((t) => {
      const dir = t.change_24h > 0 ? "up" : t.change_24h < 0 ? "down" : "";
      return `<span class="item"><span class="sym">${esc(t.symbol)}</span> $${fmtPx(t.price)} <span class="${dir}">${t.change_24h == null ? "" : (t.change_24h > 0 ? "+" : "") + t.change_24h.toFixed(1) + "%"}</span></span>`;
    }).join("");
    marquee("mq-ticker", items, 55);
    const news = (data.rss?.feeds || []).flatMap((f) => f.items.slice(0, 4).map((i) => `<span class="item"><span class="src">${esc(f.name)}</span>${esc(i.title)}</span>`)).join("");
    marquee("mq-news", news, 70);
  }

  // ---------- weather page ----------
  function renderWeatherPage() {
    const w = data.weather;
    if (!w?.configured) { $("#wx-label").textContent = w?.hint || "weather not configured"; return; }
    const c = w.current;
    const panel = $("#wx-now");
    const cond = (code) => code === 0 || code === 1 ? "clear" : code === 2 ? "partly" : code === 3 ? "overcast" : code < 50 ? "fog" : code >= 95 ? "storm" : "rain";
    const key = `${cond(c.code ?? 3)}-${c.is_day === false ? "night" : "day"}`;
    const candidate = `img/weather/${key}.jpg`, fallback = data.config?.location_image;
    const apply = (src) => { if (src) { panel.style.backgroundImage = `url(${src})`; panel.classList.add("has-img"); } else { panel.style.backgroundImage = ""; panel.classList.remove("has-img"); } };
    if (panel.dataset.key !== key) { panel.dataset.key = key; const probe = new Image(); probe.onload = () => apply(candidate); probe.onerror = () => apply(fallback); probe.src = candidate; }
    $("#wx-icon").textContent = c.icon; $("#wx-temp").textContent = `${c.temp}°`;
    $("#wx-label").textContent = c.label;
    $("#wx-meta").textContent = `feels ${c.feels}° · wind ${c.wind} mph · humidity ${c.humidity}% · ${w.location}`;
    const now = new Date(), hrs = (w.hourly || []).filter((h) => new Date(h.time) >= new Date(now - 3600e3)).slice(0, 24);
    const box = $("#wx-chart");
    if (!box.clientWidth || !box.clientHeight) { requestAnimationFrame(renderWeatherPage); return; } // laid out next frame
    const W = box.clientWidth, H = box.clientHeight, padL = 44, padR = 20, padT = 52, padB = 46;
    box.dataset.size = `${W}x${H}`;
    const temps = hrs.map((h) => h.temp), lo = Math.min(...temps) - 4, hi = Math.max(...temps) + 4;
    const x = (i) => padL + (i / Math.max(1, hrs.length - 1)) * (W - padL - padR);
    const y = (t) => padT + (1 - (t - lo) / (hi - lo)) * (H - padT - padB);
    const bw = (W - padL - padR) / Math.max(1, hrs.length) * 0.7;
    const bars = hrs.map((h, i) => `<rect class="pop" x="${x(i) - bw / 2}" y="${H - padB - (h.pop / 100) * (H - padT - padB)}" width="${bw}" height="${(h.pop / 100) * (H - padT - padB)}" rx="3"/>`).join("");
    const line = `<path class="temp" d="M${hrs.map((h, i) => `${x(i).toFixed(1)},${y(h.temp).toFixed(1)}`).join(" L")}"/>`;
    const labels = hrs.map((h, i) => i % 3 === 0 ? `<text x="${x(i)}" y="${H - 14}" text-anchor="middle">${new Date(h.time).toLocaleTimeString([], { hour: "numeric" })}</text><text class="t" x="${x(i)}" y="${y(h.temp) - 12}" text-anchor="middle">${h.temp}°</text><text x="${x(i)}" y="${y(h.temp) - 34}" text-anchor="middle" font-size="22">${h.icon}</text>` : "").join("");
    $("#wx-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" style="display:block"><line class="grid" x1="${padL}" x2="${W - padR}" y1="${H - padB}" y2="${H - padB}"/>${bars}${line}${labels}</svg>`;
    $("#wx-days").innerHTML = (w.daily || []).map((d, i) => {
      const dt = new Date(d.date + "T12:00");
      const t = (s) => new Date(s).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      return `<div class="wx-day"><div class="d"><span>${i === 0 ? "Today" : dt.toLocaleDateString([], { weekday: "short" })}</span><span class="muted">${dt.getDate()}</span></div><div class="i">${d.icon}</div><div class="muted" style="font-size:.8rem">${esc(d.label)}</div><span class="hl"><b>${d.hi}°</b><small>${d.lo}°</small>${d.pop ? `<small>☔ ${d.pop}%</small>` : ""}</span><div class="s">↑ ${t(d.sunrise)} · ↓ ${t(d.sunset)}</div></div>`;
    }).join("");
  }

  // ---------- flash alerts (posted by the agent via /api/alert) ----------
  const seenAlerts = new Set(JSON.parse(localStorage.getItem("alertsSeen") || "[]"));
  let flashing = null, flashTimer = null;
  function showAlertBar(alerts) {
    const bar = $("#alert-bar");
    bar.hidden = !alerts.length;
    bar.innerHTML = alerts.map((a) => `<div class="ab ${esc(a.level || "info")}"><b>${esc(a.title)}</b><span>${esc((a.body || "").split("\n")[0].slice(0, 90))}</span></div>`).join("");
  }
  function flashAlert(a) {
    flashing = a; paused = true; clearTimeout(rotateTimer);
    const el = $("#alert-flash"), img = $("#af-img");
    el.className = "alert-flash " + esc(a.level || "info") + (a.image ? "" : " noimg");
    if (a.image) { img.src = a.image; img.hidden = false; } else { img.hidden = true; img.removeAttribute("src"); }
    $("#af-level").textContent = { info: "Heads up", warn: "Reminder", urgent: "Important" }[a.level] || "Heads up";
    $("#af-title").textContent = a.title; $("#af-body").textContent = a.body || "";
    el.hidden = false;
    clearTimeout(flashTimer); flashTimer = setTimeout(endFlash, Math.max(5, a.flash_seconds || 20) * 1000);
  }
  function endFlash() {
    if (!flashing) return;
    seenAlerts.add(flashing.id); localStorage.setItem("alertsSeen", JSON.stringify([...seenAlerts].slice(-200)));
    flashing = null; $("#alert-flash").hidden = true; paused = false; scheduleRotate();
  }
  async function pollAlerts() {
    try {
      const r = await fetch("data/alerts.json", { cache: "no-store" }); if (!r.ok) { showAlertBar([]); return; }
      const now = Date.now() / 1000;
      const alerts = (await r.json()).filter((a) => a.expires > now);
      showAlertBar(alerts);
      if (!flashing && !tk.open) { const fresh = alerts.find((a) => !seenAlerts.has(a.id)); if (fresh) flashAlert(fresh); }
    } catch (e) { /* no alerts file yet */ }
  }
  setInterval(pollAlerts, 5000); setTimeout(pollAlerts, 2000);

  // ---------- morning brief takeover ----------
  const tk = { open: false, anim: null, lastTrigger: 0 };
  const inWindow = () => { const [a, b] = data.brief?.window || [5, 7]; const h = new Date().getHours(); return h >= a && h < b; };
  const viewedKey = () => "briefViewed:" + (data.brief?.run_time || "");
  function renderBriefCue() {
    const ready = inWindow() && data.brief?.found && !localStorage.getItem(viewedKey());
    $(".sadie").classList.toggle("ready", !!ready);
    const stamp = $("#brief-stamp");
    stamp.innerHTML = (data.brief?.found ? esc(data.brief.run_time.slice(0, 16)) : "") + (ready ? `<span class="ready-tag">● brief ready · press 0</span>` : "");
  }
  function openTakeover(playAudio = true) {
    const b = data.brief; if (!b?.found || tk.open) return;
    tk.open = true; paused = true; clearTimeout(rotateTimer);
    const el = $("#takeover"), body = $("#tk-body"), audio = $("#tk-audio");
    const h = new Date().getHours();
    $("#tk-greeting").textContent = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
    $("#tk-date").textContent = new Date().toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }) + " · brief from " + b.run_time.slice(11, 16);
    body.innerHTML = md(b.text); body.style.transform = "";
    el.hidden = false;
    const dur = Math.max(20, (b.duration_s || 30) + 4) * 1000;
    requestAnimationFrame(() => {
      const overflow = body.scrollHeight - body.parentElement.clientHeight;
      tk.anim?.cancel();
      if (overflow > 0) tk.anim = body.animate([{ transform: "translateY(0)" }, { transform: "translateY(0)", offset: 0.15 }, { transform: `translateY(-${overflow}px)` }], { duration: dur, fill: "forwards", easing: "linear" });
    });
    if (playAudio && b.audio) { audio.src = b.audio + "?v=" + encodeURIComponent(b.run_time); audio.currentTime = 0; audio.play().catch(() => {}); }
    clearTimeout(tk.timer); tk.timer = setTimeout(closeTakeover, dur + 2000);
    localStorage.setItem(viewedKey(), "1");
  }
  function closeTakeover() {
    if (!tk.open) return;
    tk.open = false; paused = false; clearTimeout(tk.timer);
    const audio = $("#tk-audio"); audio.pause(); audio.removeAttribute("src"); audio.load();
    tk.anim?.cancel(); $("#takeover").hidden = true;
    renderBriefCue(); scheduleRotate(); setStatus();
  }
  async function pollTrigger() {
    try {
      const r = await fetch("data/trigger.json", { cache: "no-store" }); if (!r.ok) return;
      const t = await r.json();
      if (!tk.lastTrigger) { tk.lastTrigger = t.ts; return; }       // ignore whatever was there at page load
      if (t.ts > tk.lastTrigger) { tk.lastTrigger = t.ts; t.what === "dismiss" ? closeTakeover() : openTakeover(true); }
    } catch (e) { /* server away; try again next tick */ }
  }
  setInterval(pollTrigger, 5000); pollTrigger();
  if (qs.has("takeover")) setTimeout(() => openTakeover(false), 1500); // test hook: ?takeover=1 opens it silently on load
  document.addEventListener("keydown", (e) => {
    const k = (e.location === 3 && NUMPAD_ALIAS[e.key]) || e.key;
    if (k === "0" || k === "Enter" || k === "b") { e.preventDefault(); if (flashing) return endFlash(); tk.open ? closeTakeover() : openTakeover(true); }
    else if (e.key === "Escape") { if (flashing) endFlash(); else if (tk.open) closeTakeover(); }
  }, true);

  let resizeTimer; window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => render(current), 200); });
  if (window.ResizeObserver) new ResizeObserver(() => { // redraw the chart only when its box really changed size
    const box = $("#wx-chart"); if (current === "weather" && box.dataset.size !== `${box.clientWidth}x${box.clientHeight}`) renderWeatherPage();
  }).observe($("#wx-chart"));

  function render(page) {
    if (page === "calendar") renderCalendar();
    else if (page === "feed") renderFeed();
    else if (page === "weather") renderWeatherPage();
  }
})();
// debug: ?debug=1 prints computed layout of the active page into the footer
if (new URLSearchParams(location.search).has("debug")) setTimeout(() => {
  const out = [];
  for (const sel of [".page.active", ".page.active > *", ".page.active .feed-cols", ".page.active .feed-col", ".page.active .scroll"]) {
    const el = document.querySelector(sel); if (!el) { out.push(`${sel}: MISSING`); continue; }
    const cs = getComputedStyle(el), r = el.getBoundingClientRect();
    out.push(`${sel} [${el.id || el.className}]: display=${cs.display} vis=${cs.visibility} op=${cs.opacity} tf=${cs.transform} rect=${Math.round(r.x)},${Math.round(r.y)} ${Math.round(r.width)}x${Math.round(r.height)} overflow=${cs.overflow}`);
  }
  document.getElementById("status").textContent = out.join(" || ");
}, 2500);
