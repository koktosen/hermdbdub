/* Setup page: loads /api/setup (prefilled by the agent or earlier visits), saves as you go, validates calendar links,
   geocodes the city, and on Finish applies the config and shows the human checklist. */
(() => {
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  let state = { answers: {}, sources: {}, missing: [] };
  const api = (path, body) => fetch(`/api/setup${path}`, body ? { method: "POST", headers: { "Content-Type": "application/json", "X-Source": "browser" }, body: JSON.stringify(body) } : {}).then((r) => r.json());

  const SOURCE_KEY = { tailnet_kind: "tailnet", tailnet_login_server: "tailnet", rss_text: "rss_feeds", city: "location" };
  const REQUIRED = new Set(["pi_model", "pi_hostname", "pi_password", "wifi_ssid", "city"]);
  function tag(name) {
    const src = state.sources[SOURCE_KEY[name] || name]; const el = $(`[name="${name}"]`)?.closest("label");
    if (!el) return; el.querySelector(".tag")?.remove();
    if (!src && !REQUIRED.has(name)) return;   // optional and untouched: no badge
    const t = document.createElement("span"); t.className = "tag " + (src === "agent" ? "agent" : src ? "you" : "need");
    t.textContent = src === "agent" ? "filled by your assistant" : src ? "filled by you" : "needed"; el.firstChild.after?.(t) || el.append(t);
  }
  function fill() {
    const a = state.answers;
    for (const el of $$("input[name], select[name], textarea[name]")) {
      if (el.type === "checkbox" || el.type === "radio") continue;
      if (a[el.name] !== undefined && el.type !== "password") el.value = a[el.name];
      if (el.type === "password" && a[el.name]) el.placeholder = "saved — leave blank to keep";
      tag(el.name);
    }
    if (a.tailnet) { $("[name=tailnet_kind]").value = a.tailnet.kind || "lan"; $("[name=tailnet_login_server]").value = a.tailnet.login_server || ""; }
    if (a.show) for (const k of ["pages", "dock_tiles", "ticker_rows", "marquees"]) if (a.show[k]) $$(`input[name=${k}]`).forEach((c) => c.checked = a.show[k].includes(c.value));
    if (a.rss_feeds) $("[name=rss_text]").value = a.rss_feeds.map((f) => `${f.name} | ${f.url}`).join("\n");
    if (a.location?.lat) { $("#loc-name").textContent = a.location.name; $("#loc-detail").textContent = `${a.location.lat}, ${a.location.lon} · ${a.timezone || ""}`; $("#bd-city").textContent = a.location.name; }
    if (a.backdrops) ($(`input[name=backdrops][value=${a.backdrops}]`) || {}).checked = true;
    if (a.x_enabled !== undefined) $("[name=x_enabled]").value = String(a.x_enabled);
    renderCals(); progress();
    const agentCount = Object.values(state.sources).filter((s) => s === "agent").length;
    const note = $("#agent-note"); note.hidden = !agentCount; note.textContent = `Your assistant already filled in ${agentCount} thing${agentCount === 1 ? "" : "s"} (marked in blue). You only need to do what's marked "needed".`;
  }
  function progress() {
    const need = state.missing || []; const total = 6, done = total - need.length;
    $("#bar").style.width = `${Math.round(100 * done / total)}%`;
    $("#missing").textContent = need.length ? `Still needed: ${need.map((k) => ({ pi_model: "which board", pi_hostname: "a name for it", pi_password: "a login password", wifi_ssid: "Wi-Fi", city: "your city", calendars: "at least one calendar" }[k] || k)).join(", ")}.` : "Everything needed is here.";
    $("#apply").disabled = need.length > 0;
  }
  async function save(patch) { state = await api("", patch); fill(); }

  // text/select fields save on change
  document.addEventListener("change", (e) => {
    const el = e.target; if (!el.name) return;
    if (el.name === "tailnet_kind" || el.name === "tailnet_login_server") return save({ tailnet: { kind: $("[name=tailnet_kind]").value, login_server: $("[name=tailnet_login_server]").value } });
    if (["pages", "dock_tiles", "ticker_rows", "marquees"].includes(el.name)) return save({ show: Object.fromEntries(["pages", "dock_tiles", "ticker_rows", "marquees"].map((k) => [k, $$(`input[name=${k}]:checked`).map((c) => c.value)])) });
    if (el.name === "rss_text") return save({ rss_feeds: el.value.split("\n").map((l) => l.split("|").map((s) => s.trim())).filter((p) => p[1]).map(([name, url]) => ({ name, url })) });
    if (el.name === "backdrops") return save({ backdrops: el.value });
    if (el.name === "x_enabled") return save({ x_enabled: el.value === "true" });
    if (el.name === "city") return;
    if (el.closest("#cals")) return;
    if (el.value !== "") save({ [el.name]: el.value });
  });

  // geocoding (Open-Meteo, no key)
  let geoTimer;
  $("[name=city]").addEventListener("input", (e) => {
    clearTimeout(geoTimer); const q = e.target.value.trim(); if (q.length < 2) return;
    geoTimer = setTimeout(async () => {
      const r = await fetch(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(q)}&count=5&language=en`).then((r) => r.json()).catch(() => ({}));
      $("#geo").innerHTML = (r.results || []).map((x) => `<button type="button" data-lat="${x.latitude}" data-lon="${x.longitude}" data-tz="${esc(x.timezone)}" data-name="${esc(x.name)}">${esc(x.name)}${x.admin1 ? ", " + esc(x.admin1) : ""} · ${esc(x.country)}</button>`).join("") || `<span class="hint">no match — try another spelling</span>`;
    }, 350);
  });
  $("#geo").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    save({ city: b.dataset.name, timezone: b.dataset.tz, location: { name: b.dataset.name, lat: Number(b.dataset.lat), lon: Number(b.dataset.lon) } }); $("#geo").innerHTML = "";
  });

  // calendars
  function renderCals() {
    const cals = state.answers.calendars?.length ? state.answers.calendars : [{ name: "", url: "" }];
    $("#cals").innerHTML = cals.map((c, i) => `<div class="cal" data-i="${i}"><label>Name <input class="cname" value="${esc(c.name)}" placeholder="Work"></label><label>Private link <input class="curl" value="${c.url === "(set)" ? "" : esc(c.url)}" placeholder="${c.url === "(set)" ? "saved — paste again to replace" : "https://… or webcal://…"}"></label><div class="status ${c.url ? "ok" : "pending"}">${c.url ? "saved" : "waiting for a link"}</div></div>`).join("");
  }
  $("#add-cal").addEventListener("click", () => { $("#cals").insertAdjacentHTML("beforeend", `<div class="cal"><label>Name <input class="cname" placeholder="Personal"></label><label>Private link <input class="curl" placeholder="https://… or webcal://…"></label><div class="status pending">waiting for a link</div></div>`); });
  $("#cals").addEventListener("change", async (e) => {
    const row = e.target.closest(".cal"); const name = $(".cname", row).value.trim(), url = $(".curl", row).value.trim(), st = $(".status", row);
    if (!url || !name) { if (!name && url) st.textContent = "give it a name"; return; }
    st.className = "status pending"; st.textContent = "testing…";
    const v = await api("/validate", { url });
    if (v.ok) { st.className = "status ok"; st.textContent = `✓ ${v.events_14d} events in the next 14 days`; await save({ calendars: [{ name, url }] }); }
    else { st.className = "status bad"; st.textContent = "✗ " + (v.error || "could not read that link"); }
  });

  // finish
  $("#apply").addEventListener("click", async () => {
    $("#apply").disabled = true; $("#apply").textContent = "Building…";
    const r = await api("/apply", {}); const ci = await api("/cloudinit"); const a = state.answers;
    const bad = Object.entries(r.collectors || {}).filter(([, v]) => !v.ok);
    const res = $("#result"); res.hidden = false;
    res.innerHTML = `<h3>${r.ok ? "✓ Your wall is configured on this computer." : "Configured, with warnings."}</h3>
      ${bad.length ? `<p class="bad">${bad.map(([k, v]) => `${k}: ${esc(v.error)}`).join("<br>")}</p>` : `<p>Open <a href="/">the wall</a> in this browser to see it now.</p>`}
      <h3>Next: the small computer</h3>
      <p>Either tell your assistant "set up the wall's Pi" (it does the steps below), or do them yourself:</p>
      <ol>
        <li>Download Raspberry Pi OS Lite for your board: <a href="${esc(ci.image_url)}" target="_blank">${esc(ci.image_family)}</a>, then flash it:<pre>${esc(ci.flash_hint)}</pre></li>
        <li>Copy these two files onto the card's <b>bootfs</b> partition (they log it into <b>${esc(a.wifi_ssid || "your Wi-Fi")}</b> and name it <b>${esc(a.pi_hostname || "wall")}</b>):
          <details><summary>user-data</summary><pre>${esc(ci["user-data"])}</pre></details><details><summary>network-config</summary><pre>${esc(ci["network-config"])}</pre></details></li>
        <li>Put the card in the board, connect HDMI, power it. Wait two minutes.</li>
        <li>From this computer:<pre>scp pi/bootstrap-pi.sh ${esc(a.pi_user || "wall")}@${esc(a.pi_hostname || "wall")}.local:~ &amp;&amp; ssh ${esc(a.pi_user || "wall")}@${esc(a.pi_hostname || "wall")}.local 'bash bootstrap-pi.sh http://${location.hostname}:8470/ &amp;&amp; sudo reboot'</pre></li>
        ${a.tailnet?.kind && a.tailnet.kind !== "lan" ? `<li>Away-from-home: on the board run <pre>${a.tailnet.kind === "headscale" ? `LOGIN_SERVER=${esc(a.tailnet.login_server)} ` : ""}bash tailscale-up.sh</pre> approve the link it prints, then <pre>bash set-url.sh http://&lt;this computer's tailnet address&gt;:8470/</pre></li>` : ""}
      </ol>
      ${a.backdrops === "agent" ? `<h3>Backdrops</h3><p>Tell your assistant: "generate the wall's weather backdrops for ${esc(a.location?.name || "my city")}".</p>` : a.backdrops === "own" ? `<h3>Backdrops</h3><p>Put a 1280-px-wide JPEG at <code>server/web/img/location.jpg</code>, and optionally <code>server/web/img/weather/&lt;clear|partly|overcast|fog|rain|storm&gt;-&lt;day|night&gt;.jpg</code>.</p>` : ""}
      <p class="hint">Everything you typed is stored only on this computer (<code>server/data/setup.json</code>, readable by your user only).</p>`;
    $("#apply").textContent = "Saved"; res.scrollIntoView({ behavior: "smooth" });
  });

  api("").then((s) => { state = s; fill(); });
})();
