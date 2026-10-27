/* Shared helpers for the list and detail pages. */
(function () {
  const L = (window.I18N && window.I18N[RF.lang]) || {};
  const LOCALE = { it: "it-IT", en: "en-GB", cs: "cs-CZ" }[RF.lang] || "cs-CZ";
  const nf = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });

  RF.t = (key, vars) => {
    let s = L[key] != null ? String(L[key]) : key;
    if (vars) for (const k in vars) s = s.split("{" + k + "}").join(vars[k]);
    return s;
  };
  RF.num = (n) => (n == null ? "" : nf.format(n));
  RF.czk = (n) => (n == null ? "—" : nf.format(n) + " Kč");
  RF.esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  RF.sources = { bezrealitky: "Bezrealitky", idnes: "iDNES Reality", realitymix: "RealityMix", sreality: "Sreality" };
  RF.disp = (d) => (d === "atypical" ? RF.t("atypical") : d === "room" ? RF.t("room") : d || "");

  RF.FLAGS = [["L", "lift"], ["B", "balcony"], ["T", "terrace"], ["G", "loggia"], ["C", "cellar"],
    ["P", "parking"], ["R", "garage"], ["D", "pets"], ["O", "private"]];
  RF.flagWords = (f) => {
    const out = [];
    for (const [ch, key] of RF.FLAGS) if (f.includes(ch)) out.push(RF.t(key).toLowerCase());
    if (f.includes("F")) out.push(RF.t("furnished_yes"));
    else if (f.includes("f")) out.push(RF.t("furnished_partly"));
    else if (f.includes("u")) out.push(RF.t("furnished_no"));
    return out;
  };

  /* Street-name plate (red) + house-number plate (blue) for the district. */
  RF.plates = (quarter, district) => {
    let h = "";
    if (quarter) h += `<span class="plate plate--street"><span>${RF.esc(quarter)}</span></span>`;
    if (district) h += `<span class="plate plate--number" title="Praha ${district}"><span>${district}</span></span>`;
    return h;
  };

  RF.isNew = (fs) => {
    if (!fs) return false;
    const d = new Date(fs + "T00:00:00");
    return Date.now() - d.getTime() < 2 * 86400000;
  };

  RF.shard = (id) => (fnv(id) & 0xff).toString(16).padStart(2, "0");

  RF.date = (iso) => {
    if (!iso) return "";
    const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
    return d.toLocaleDateString(LOCALE, { day: "numeric", month: "long", year: "numeric" });
  };
  RF.dateTime = (iso) => new Date(iso).toLocaleString(LOCALE, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

  RF.flatUrl = (id) => `${RF.home}flat/?id=${encodeURIComponent(id)}`;

  /* FNV-1a 32-bit over UTF-8, same as radarflat.pipeline.shard_of: the detail shard file name. */
  function fnv(str) {
    let h = 0x811c9dc5;
    for (const b of new TextEncoder().encode(str)) { h ^= b; h = Math.imul(h, 0x01000193) >>> 0; }
    return h >>> 0;
  }
  RF._fnv = fnv;

  /* Keep the current query string when switching language. */
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-keep-query]");
    if (a && location.search) a.href = a.getAttribute("href").split("?")[0] + location.search;
  });
})();
