/* Detail page: /flat/?id=<id> loads data/d/<shard>.json and shows one flat. */
(function () {
  const t = RF.t;
  const $ = (s) => document.querySelector(s);
  const id = new URLSearchParams(location.search).get("id") || "";
  let imgs = [], cur = 0;

  if (document.referrer && new URL(document.referrer).origin === location.origin && history.length > 1) {
    $("#back").addEventListener("click", (e) => { e.preventDefault(); history.back(); });
  }

  async function boot() {
    if (!id) return notFound();
    try {
      const r = await fetch(`${RF.base}/data/d/${RF.shard(id)}.json?v=${Math.floor(Date.now() / 600000)}`);
      if (!r.ok) return notFound();
      const rec = (await r.json())[id];
      if (!rec) return notFound();
      show(rec);
    } catch (e) {
      console.error(e);
      $("#state").textContent = t("load_error");
    }
  }
  function notFound() { $("#state").textContent = t("not_found"); }

  function show(r) {
    $("#state").hidden = true;
    $("#flat").hidden = false;
    const rent = r.offer === "rent";
    const title = [RF.disp(r.disp), r.area ? `${r.area} m²` : "", r.street].filter(Boolean).join(", ");
    document.title = `${title} — RadarFlat`;
    $("#d-title").textContent = title || r.title || "";
    $("#d-plates").innerHTML = RF.plates(r.quarter, r.district);
    $("#d-price").innerHTML = RF.czk(r.price_czk) + (rent ? `<span class="per">${t("per_month")}</span>` : "");
    const sub = [];
    if (r.currency === "EUR" && r.price) sub.push(`${RF.num(r.price)} €`);
    if (rent && r.charges) sub.push(`+ ${RF.czk(r.charges)} ${t("charges").toLowerCase()}`);
    if (r.price_m2) sub.push(`${RF.num(r.price_m2)} Kč${t("per_m2")}`);
    $("#d-sub").textContent = sub.join(", ");
    const badges = [];
    if (RF.isNew(r.first_seen)) badges.push(`<span class="badge badge--new">${t("new")}</span>`);
    const hist = r.history || [];
    const peak = Math.max(...hist.map((h) => h[1]), r.price_czk || 0);
    if (peak > r.price_czk) badges.push(`<span class="badge badge--drop">${t("drop", { n: Math.round(100 * (peak - r.price_czk) / peak) })}</span>`);
    if (r.price_m2 && r.quarter_median_m2 && r.quarter) {
      const dv = Math.round(100 * (r.price_m2 - r.quarter_median_m2) / r.quarter_median_m2);
      if (Math.abs(dv) >= 5) badges.push(`<span class="dev ${dv < 0 ? "below" : "above"}">${t(dv < 0 ? "dev_below" : "dev_above", { n: Math.abs(dv), q: RF.esc(r.quarter) })}</span>`);
    }
    $("#d-badges").innerHTML = badges.join(" ");

    // gallery
    imgs = (r.images || []).filter(Boolean);
    const thumbs = $("#g-thumbs");
    thumbs.innerHTML = imgs.map((u, i) => `<button type="button" data-i="${i}" aria-label="${i + 1}/${imgs.length}"><img src="${RF.esc(u)}" alt="" loading="lazy" referrerpolicy="no-referrer"></button>`).join("");
    thumbs.addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) go(+b.dataset.i); });
    $("#g-prev").addEventListener("click", () => go(cur - 1));
    $("#g-next").addEventListener("click", () => go(cur + 1));
    document.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") go(cur - 1);
      if (e.key === "ArrowRight") go(cur + 1);
    });
    if (imgs.length) go(0); else document.querySelector(".gallery").hidden = true;
    if (imgs.length < 2) document.querySelectorAll(".g-nav").forEach((b) => (b.hidden = true));

    // facts
    const yn = (v) => (v == null ? null : v ? t("v_yes") : t("v_no"));
    const code = (prefix, v) => (v ? (window.I18N[RF.lang][prefix + "_" + v] || v) : null);
    const floor = r.floor == null ? null : (r.floor === 0 ? t("ground_floor") : `${r.floor}.`) + (r.floors_total ? ` / ${r.floors_total}` : "");
    const rows = [
      [t("price"), RF.czk(r.price_czk) + (rent ? t("per_month") : "")],
      [t("charges"), r.charges ? RF.czk(r.charges) : null],
      [t("deposit"), r.deposit ? RF.czk(r.deposit) : null],
      [t("price_m2"), r.price_m2 ? `${RF.num(r.price_m2)} Kč` : null],
      [t("quarter_median"), r.quarter_median_m2 ? `${RF.num(r.quarter_median_m2)} Kč${t("per_m2")}` : null],
      [t("layout"), RF.disp(r.disp)],
      [t("area"), r.area ? `${r.area} m²` : null],
      [t("floor_h"), floor],
      [t("lift"), yn(r.lift)],
      [t("balcony"), yn(r.balcony)],
      [t("terrace"), r.terrace ? t("v_yes") : null],
      [t("loggia"), r.loggia ? t("v_yes") : null],
      [t("cellar"), r.cellar ? t("v_yes") : null],
      [t("parking"), r.parking ? t("v_yes") : null],
      [t("garage"), r.garage ? t("v_yes") : null],
      [t("furnished"), r.furnished ? t("furnished_" + r.furnished) : null],
      [t("condition"), code("condition", r.condition)],
      [t("construction"), code("construction", r.construction)],
      [t("ownership"), code("ownership", r.ownership)],
      [t("penb"), r.penb],
      [t("heating"), code("heating", r.heating)],
      [t("available_from"), r.available_from ? RF.date(r.available_from) : null],
      [t("pets"), yn(r.pets)],
      [t("private"), r.private ? t("v_yes") : null],
      [t("first_seen"), RF.date(r.first_seen)],
    ].filter((x) => x[1]);
    $("#d-facts").innerHTML = rows.map(([k, v]) => `<div><dt>${RF.esc(k)}</dt><dd>${RF.esc(v)}</dd></div>`).join("");

    const desc = (r.description || "").trim();
    $("#d-desc").innerHTML = desc ? desc.split(/\n{2,}|\n/).map((p) => `<p>${RF.esc(p)}</p>`).join("") : `<p class="note">—</p>`;
    $("#d-desc").lang = "cs";

    const open = $("#d-open");
    open.href = r.url;
    open.textContent = t("open_original", { s: RF.sources[r.source] || r.source });
    if ((r.also_on || []).length) {
      $("#d-also").innerHTML = `<h2>${t("same_flat_elsewhere")}</h2><ul class="also">` + r.also_on.map((a) =>
        `<li><a href="${RF.esc(a.url)}" target="_blank" rel="noopener nofollow">${RF.esc(RF.sources[a.source] || a.source)}</a> <span>${RF.czk(a.price_czk)}</span></li>`).join("") + "</ul>";
    }

    // map
    if (r.lat && window.L) {
      const m = L.map("d-map", { scrollWheelZoom: false }).setView([r.lat, r.lon], 15);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(m);
      L.circle([r.lat, r.lon], { radius: 120, color: "var(--blue)", weight: 2, fillOpacity: 0.12 }).addTo(m);
    } else {
      $("#d-map").hidden = true;
    }

    // price history
    $("#d-history").innerHTML = (hist.length ? hist : [[r.first_seen, r.price_czk]]).slice().reverse()
      .map(([d, p]) => `<li><span>${RF.date(d)}</span> <strong>${RF.czk(p)}</strong></li>`).join("");
  }

  function go(i) {
    if (!imgs.length) return;
    cur = (i + imgs.length) % imgs.length;
    const img = $("#g-img");
    img.referrerPolicy = "no-referrer";
    img.src = imgs[cur];
    $("#g-cap").textContent = `${cur + 1} / ${imgs.length}`;
    document.querySelectorAll("#g-thumbs button").forEach((b, j) => b.setAttribute("aria-current", String(j === cur)));
  }

  boot();
})();
