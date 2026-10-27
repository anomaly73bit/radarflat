/* List page: load listings.json, filter, sort, render cards and the map. */
(function () {
  const t = RF.t;
  const $ = (s, el = document) => el.querySelector(s);
  const form = $("#filters");
  const cardsEl = $("#cards");
  const PAGE = 36;
  let all = [], meta = {}, shown = PAGE, results = [], offer = "r";
  let map, cluster, markersById = new Map(), mapReady = false;

  /* ---------- URL <-> form ---------- */
  function readUrl() {
    const p = new URLSearchParams(location.search);
    offer = p.get("o") === "s" ? "s" : "r";
    for (const el of form.elements) {
      if (!el.name) continue;
      if (el.type === "checkbox") el.checked = p.getAll(el.name).includes(el.value);
      else if (p.has(el.name)) el.value = p.get(el.name);
    }
  }
  function writeUrl() {
    const p = new URLSearchParams();
    if (offer === "s") p.set("o", "s");
    for (const el of form.elements) {
      if (!el.name) continue;
      if (el.type === "checkbox") { if (el.checked) p.append(el.name, el.value); }
      else if (el.value && !(el.name === "sort" && el.value === "new")) p.set(el.name, el.value);
    }
    const qs = p.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : ""));
  }
  function filters() {
    const fd = new FormData(form);
    const num = (k) => (fd.get(k) ? Number(fd.get(k)) : null);
    return {
      pmin: num("pmin"), pmax: num("pmax"), amin: num("amin"), amax: num("amax"),
      d: fd.getAll("d"), q: fd.get("q") || "", n: fd.get("n") ? Number(fd.get("n")) : null,
      x: fd.getAll("x"), isNew: !!fd.get("new"), drop: !!fd.get("drop"), deal: !!fd.get("deal"),
      inmap: !!fd.get("inmap"), sort: fd.get("sort") || "new",
    };
  }

  /* ---------- filtering ---------- */
  function apply(resetPaging = true) {
    const f = filters();
    const bounds = f.inmap && mapReady ? map.getBounds() : null;
    results = all.filter((l) => {
      if (l.o !== offer) return false;
      if (f.pmin != null && l.p < f.pmin) return false;
      if (f.pmax != null && l.p > f.pmax) return false;
      if (f.amin != null && (l.a == null || l.a < f.amin)) return false;
      if (f.amax != null && (l.a == null || l.a > f.amax)) return false;
      if (f.d.length && !f.d.includes(l.d)) return false;
      if (f.q && l.q !== f.q) return false;
      if (f.n && l.n !== f.n) return false;
      for (const x of f.x) if (!l.f.includes(x)) return false;
      if (f.isNew && !RF.isNew(l.fs)) return false;
      if (f.drop && !l.dr) return false;
      if (f.deal && !(l.dv != null && l.dv < 0)) return false;
      if (bounds && !(l.la && bounds.contains([l.la, l.lo]))) return false;
      return true;
    });
    const by = {
      new: (a, b) => (b.fs || "").localeCompare(a.fs || ""),
      pa: (a, b) => a.p - b.p,
      pd: (a, b) => b.p - a.p,
      m2: (a, b) => (a.m ?? 1e12) - (b.m ?? 1e12),
      ad: (a, b) => (b.a ?? 0) - (a.a ?? 0),
      deal: (a, b) => (a.dv ?? 1e9) - (b.dv ?? 1e9),
    }[f.sort] || ((a, b) => 0);
    results.sort(by);
    if (resetPaging) shown = PAGE;
    render();
    if (!f.inmap) updateMap();
    writeUrl();
    const active = [f.pmin, f.pmax, f.amin, f.amax, f.q, f.n].filter((v) => v != null && v !== "").length
      + f.d.length + f.x.length + [f.isNew, f.drop, f.deal, f.inmap].filter(Boolean).length;
    $("#filter-count").textContent = active ? `(${active})` : "";
  }

  /* ---------- cards ---------- */
  function card(l) {
    const unit = l.o === "r" ? `<span class="per">${t("per_month")}</span>` : "";
    const spec = [RF.disp(l.d), l.a ? `${l.a} m²` : "", floorText(l.fl)].filter(Boolean).join(", ");
    const sub = [];
    if (l.c && l.o === "r") sub.push(`+ ${RF.czk(l.c)}`);
    if (l.m) sub.push(`${RF.num(l.m)} Kč${t("per_m2")}`);
    let dev = "";
    if (l.dv != null && Math.abs(l.dv) >= 5 && l.q)
      dev = `<p class="dev ${l.dv < 0 ? "below" : "above"}">${t(l.dv < 0 ? "dev_below" : "dev_above", { n: Math.abs(l.dv), q: RF.esc(l.q) })}</p>`;
    const badges = [];
    if (RF.isNew(l.fs)) badges.push(`<span class="badge badge--new">${t("new")}</span>`);
    if (l.dr) badges.push(`<span class="badge badge--drop">${t("drop", { n: l.dr })}</span>`);
    const feats = RF.flagWords(l.f).join(", ");
    const src = RF.sources[l.src] + (l.x ? ", " + (l.x === 1 ? t("also_on_1") : t("also_on", { n: l.x })) : "");
    const img = l.t
      ? `<img src="${RF.esc(l.t)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove()">`
      : "";
    return `<li class="card" data-id="${RF.esc(l.i)}"><a href="${RF.flatUrl(l.i)}">
      <div class="ph">${img}<div class="badges">${badges.join("")}</div></div>
      <div class="body">
        <p class="price">${RF.czk(l.p)}${unit}</p>
        <p class="spec">${RF.esc(spec)}</p>
        ${sub.length ? `<p class="subprice">${sub.join(", ")}</p>` : ""}
        <p class="plates">${RF.plates(l.q, l.n)}${l.s ? `<span class="street">${RF.esc(l.s)}</span>` : ""}</p>
        ${dev}
        ${feats ? `<p class="feat">${RF.esc(feats)}</p>` : ""}
        <p class="src">${RF.esc(src)}</p>
      </div></a></li>`;
  }
  function floorText(fl) {
    if (fl == null) return "";
    return fl === 0 ? t("ground_floor") : `${fl}. ${t("floor")}`;
  }
  function render() {
    const total = all.filter((l) => l.o === offer).length;
    $("#heading").textContent = t(offer === "r" ? "heading_rent" : "heading_sale", { n: RF.num(total) });
    const newCount = all.filter((l) => l.o === offer && RF.isNew(l.fs) && l.fs === today()).length;
    const subBits = [];
    if (newCount) subBits.push(t("new_today", { n: RF.num(newCount) }));
    if (meta.updated) subBits.push(t("updated", { t: RF.dateTime(meta.updated) }));
    $("#sub").textContent = subBits.join(". ");
    $("#count").textContent = t("results", { n: RF.num(results.length) });
    cardsEl.innerHTML = results.slice(0, shown).map(card).join("");
    $("#empty").hidden = results.length > 0;
    $("#more").hidden = results.length <= shown;
    document.querySelectorAll(".offer-switch button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.offer === offer)));
  }
  const today = () => new Date().toISOString().slice(0, 10);

  /* ---------- map ---------- */
  function initMap() {
    if (!window.L) return;
    map = L.map("map", { zoomControl: true, scrollWheelZoom: true }).setView([50.0755, 14.4378], 12);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 48, chunkedLoading: true });
    map.addLayer(cluster);
    map.on("moveend", () => { if (form.elements.inmap.checked) apply(); });
    mapReady = true;
  }
  function priceLabel(l) {
    if (l.o === "r") return l.p >= 100000 ? Math.round(l.p / 1000) + "k" : (l.p / 1000).toFixed(l.p < 10000 ? 1 : 0).replace(".0", "") + "k";
    return l.p >= 1e6 ? (l.p / 1e6).toFixed(1).replace(".0", "") + "M" : Math.round(l.p / 1000) + "k";
  }
  function updateMap() {
    if (!mapReady) return;
    cluster.clearLayers();
    markersById.clear();
    const ms = [];
    for (const l of results) {
      if (!l.la) continue;
      const m = L.marker([l.la, l.lo], {
        icon: L.divIcon({ className: "pin" + (l.dv != null && l.dv <= -10 ? " pin--deal" : ""), html: `<span>${priceLabel(l)}</span>`, iconSize: null }),
        keyboard: false,
      });
      m.bindPopup(() => `<a class="pop" href="${RF.flatUrl(l.i)}">${l.t ? `<img src="${RF.esc(l.t)}" alt="" referrerpolicy="no-referrer">` : ""}
        <strong>${RF.czk(l.p)}</strong><span>${RF.esc([RF.disp(l.d), l.a ? l.a + " m²" : "", l.q].filter(Boolean).join(", "))}</span></a>`, { minWidth: 200 });
      ms.push(m);
      markersById.set(l.i, m);
    }
    cluster.addLayers(ms);
  }

  /* ---------- events ---------- */
  let timer;
  form.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(apply, 180); });
  form.addEventListener("change", () => { clearTimeout(timer); apply(); });
  form.addEventListener("reset", () => setTimeout(() => apply(), 0));
  form.addEventListener("submit", (e) => e.preventDefault());
  $("#more").addEventListener("click", () => { shown += PAGE; render(); });
  document.querySelectorAll(".offer-switch button").forEach((b) => b.addEventListener("click", () => {
    offer = b.dataset.offer;
    apply();
  }));
  const fab = $("#toggle-map");
  fab.addEventListener("click", () => {
    const on = document.body.classList.toggle("map-open");
    fab.textContent = on ? fab.dataset.list : fab.dataset.map;
    if (on && map) setTimeout(() => map.invalidateSize(), 50);
  });
  if (matchMedia("(max-width: 900px)").matches) $("#filters-wrap").open = false;

  /* ---------- boot ---------- */
  async function boot() {
    readUrl();
    initMap();
    try {
      const v = Math.floor(Date.now() / 600000);
      const [ls, mt] = await Promise.all([
        fetch(`${RF.base}/data/listings.json?v=${v}`).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }),
        fetch(`${RF.base}/data/meta.json?v=${v}`).then((r) => (r.ok ? r.json() : {})),
      ]);
      all = ls; meta = mt;
      const sel = form.elements.q;
      const wanted = new URLSearchParams(location.search).get("q");
      for (const q of meta.quarters || []) sel.add(new Option(q, q));
      if (wanted) sel.value = wanted;
      apply(false);
    } catch (e) {
      $("#heading").textContent = t("load_error");
      console.error(e);
    }
  }
  boot();
})();
