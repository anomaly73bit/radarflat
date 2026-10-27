"""crawl → merge into state → details → dedupe → publish JSON for the site."""
from __future__ import annotations

import json
import logging
import math
import re
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from .geo import QUARTERS
from .http import Blocked, PoliteClient
from .model import merge
from .sources import ALL

log = logging.getLogger("radarflat")
ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "listings.jsonl"
RUNS = ROOT / "state" / "runs.json"
SITE_DATA = ROOT / "site" / "data"
PRIORITY = ["bezrealitky", "sreality", "idnes", "realitymix"]   # which copy of a duplicate is shown
LIST_LEVEL = {"price", "currency", "charges", "title"}            # list pages may update these after detail


def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))


def load_state() -> dict[str, dict]:
    if not STATE.exists():
        return {}
    out = {}
    for line in STATE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["id"]] = r
    return out


def save_state(state: dict[str, dict]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(state[k], ensure_ascii=False, sort_keys=True) for k in sorted(state)]
    STATE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def eur_rate(cfg: dict) -> float:
    try:
        client = PoliteClient({**cfg["defaults"], "delay_seconds": [0, 0]})
        r = client.get("https://www.cnb.cz/cs/financni-trhy/devizovy-trh/kurzy-devizoveho-trhu/kurzy-devizoveho-trhu/denni_kurz.txt")
        m = re.search(r"\|EUR\|(\d+,\d+)", r.text)
        if m:
            return float(m.group(1).replace(",", "."))
    except Exception as exc:  # noqa: BLE001
        log.warning("ČNB rate unavailable: %s", exc)
    return float(cfg.get("eur_czk_fallback", 24.3))


# ---------------------------------------------------------------- crawl
def crawl(only_sources: list[str] | None = None, details: int | None = None) -> dict:
    cfg = load_cfg()
    today = date.today().isoformat()
    state = load_state()
    lock = threading.Lock()
    rate = eur_rate(cfg)
    report: dict = {"started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "eur_czk": rate, "sources": {}}

    # drop anything outside the configured offers (e.g. sale listings after switching to rent only)
    for rid in [k for k, r in state.items() if r.get("offer") not in cfg["offers"]]:
        del state[rid]

    enabled = [n for n, s in cfg["sources"].items() if s.get("enabled") and n in ALL
               and (not only_sources or n in only_sources)]

    def run_source(name: str):
        scfg = {**cfg["defaults"], **(cfg["sources"].get(name) or {})}
        src = ALL[name](PoliteClient(scfg), scfg)
        rep = {"listed": 0, "new": 0, "details": 0, "removed_by_detail": 0, "complete_offers": [], "errors": []}
        seen: set[str] = set()
        for offer in cfg["offers"]:
            try:
                for item in src.listings(offer):
                    item["price_czk"] = _czk(item, rate)
                    seen.add(item["id"])
                    with lock:
                        is_new = _absorb(state, item, today)
                    rep["listed"] += 1
                    rep["new"] += int(is_new)
                rep["complete_offers"].append(offer)
            except Blocked as exc:
                rep["errors"].append(f"{offer}: {exc}")
                log.warning("%s %s blocked: %s", name, offer, exc)
            except Exception as exc:  # noqa: BLE001
                rep["errors"].append(f"{offer}: {type(exc).__name__}: {exc}")
                log.exception("%s %s failed", name, offer)
        # missed-run bookkeeping only for offers that completed
        with lock:
            for rid, rec in list(state.items()):
                if rec["source"] != name or rec["offer"] not in rep["complete_offers"]:
                    continue
                if rid in seen:
                    rec["missed"] = 0
                else:
                    rec["missed"] = rec.get("missed", 0) + 1
                    if rec["missed"] >= cfg.get("remove_after_missed_runs", 2):
                        del state[rid]
        # detail pages: newest listings without detail first
        if src.needs_detail:
            budget = details if details is not None else int(scfg.get("details_per_run", 250))
            with lock:
                todo = sorted((r for r in state.values() if r["source"] == name and not r.get("detail_done")),
                              key=lambda r: r.get("first_seen", ""), reverse=True)[:budget]
            for rec in todo:
                try:
                    extra = src.detail(rec)
                except Blocked as exc:
                    rep["errors"].append(f"detail: {exc}")
                    break
                except Exception as exc:  # noqa: BLE001
                    rep["errors"].append(f"detail {rec['id']}: {type(exc).__name__}: {exc}")
                    with lock:
                        rec["detail_done"] = True  # don't retry a page we can't parse every run
                    continue
                with lock:
                    if extra is None:
                        state.pop(rec["id"], None)
                        rep["removed_by_detail"] += 1
                        continue
                    old_price = rec.get("price")
                    merge(rec, extra)
                    rec["detail_done"] = True
                    rec["price_czk"] = _czk(rec, rate)
                    if rec.get("price") != old_price:
                        _history(rec, today)
                rep["details"] += 1
        report["sources"][name] = rep
        log.info("%s done: %s", name, {k: v for k, v in rep.items() if k != "errors"})

    with ThreadPoolExecutor(max_workers=max(1, len(enabled))) as ex:
        list(ex.map(run_source, enabled))

    save_state(state)
    report["finished"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report["active"] = len(state)
    _append_run(report)
    publish(state, report, rate)
    return report


def _czk(item: dict, rate: float) -> int | None:
    p = item.get("price")
    if p is None:
        return None
    return int(round(p * rate)) if (item.get("currency") or "CZK").upper() == "EUR" else int(p)


def _history(rec: dict, today: str) -> None:
    h = rec.setdefault("history", [])
    if rec.get("price_czk") is None:
        return
    if not h or h[-1][1] != rec["price_czk"]:
        if h and h[-1][0] == today:
            h[-1] = [today, rec["price_czk"]]
        else:
            h.append([today, rec["price_czk"]])


def _absorb(state: dict, item: dict, today: str) -> bool:
    rec = state.get(item["id"])
    if rec is None:
        item.update(first_seen=today, last_seen=today, missed=0, history=[])
        _history(item, today)
        state[item["id"]] = item
        return True
    if rec.get("detail_done"):
        upd = {k: v for k, v in item.items() if k in LIST_LEVEL or k == "price_czk"}
        if not rec.get("lat") and item.get("lat"):
            upd.update(lat=item["lat"], lon=item["lon"])
    else:
        upd = {k: v for k, v in item.items() if k not in ("detail_done",)}
    merge(rec, upd)
    rec["last_seen"] = today
    _history(rec, today)
    return False


def _append_run(report: dict) -> None:
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else []
    runs.append(report)
    RUNS.write_text(json.dumps(runs[-60:], indent=1, ensure_ascii=False))


# ---------------------------------------------------------------- dedupe
def _km(a: dict, b: dict) -> float | None:
    if not (a.get("lat") and b.get("lat")):
        return None
    dlat = math.radians(b["lat"] - a["lat"])
    dlon = math.radians(b["lon"] - a["lon"]) * math.cos(math.radians(a["lat"]))
    return 6371 * math.hypot(dlat, dlon)


def same_flat(a: dict, b: dict) -> bool:
    if a["source"] == b["source"] or a["offer"] != b["offer"]:
        return False
    if not (a.get("area") and b.get("area") and a.get("price_czk") and b.get("price_czk")):
        return False
    if abs(a["area"] - b["area"]) > max(2, 0.03 * a["area"]):
        return False
    if a.get("disp") and b.get("disp") and a["disp"] != b["disp"]:
        return False
    if abs(a["price_czk"] - b["price_czk"]) > 0.03 * max(a["price_czk"], b["price_czk"]):
        return False
    km = _km(a, b)
    if km is not None:
        return km < 0.35
    sa, sb = (a.get("street") or "").lower(), (b.get("street") or "").lower()
    if sa and sb:
        return sa == sb
    return bool(a.get("quarter")) and a.get("quarter") == b.get("quarter")


def dedupe(recs: list[dict]) -> list[list[dict]]:
    parent = list(range(len(recs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    buckets: dict[tuple, list[int]] = {}
    for i, r in enumerate(recs):
        if r.get("area"):
            buckets.setdefault((r["offer"], int(r["area"]) // 4), []).append(i)
    for (offer, b), idx in list(buckets.items()):
        cand = idx + buckets.get((offer, b + 1), [])
        for x in range(len(idx)):
            for y in range(x + 1, len(cand)):
                i, j = idx[x], cand[y]
                if i != j and same_flat(recs[i], recs[j]):
                    parent[find(i)] = find(j)
    groups: dict[int, list[dict]] = {}
    for i, r in enumerate(recs):
        groups.setdefault(find(i), []).append(r)
    return list(groups.values())


def _score(r: dict) -> tuple:
    filled = sum(1 for v in r.values() if v not in (None, "", []))
    return (bool(r.get("detail_done")), -PRIORITY.index(r["source"]) if r["source"] in PRIORITY else -9,
            len(r.get("images") or []), filled)


# ---------------------------------------------------------------- publish
def _flags(r: dict) -> str:
    f = ""
    for key, ch in (("lift", "L"), ("balcony", "B"), ("terrace", "T"), ("loggia", "G"), ("cellar", "C"),
                    ("parking", "P"), ("garage", "R"), ("pets", "D"), ("private", "O")):
        if r.get(key):
            f += ch
    if r.get("furnished") == "yes":
        f += "F"
    elif r.get("furnished") == "partly":
        f += "f"
    elif r.get("furnished") == "no":
        f += "u"
    return f


def shard_of(rid: str) -> str:
    """FNV-1a 32-bit of the id, low byte as 2 hex digits (mirrored in site/assets/common.js)."""
    h = 0x811C9DC5
    for b in rid.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h & 0xFF:02x}"


def publish(state: dict[str, dict], report: dict | None = None, rate: float | None = None) -> None:
    offers = load_cfg().get("offers", ["rent", "sale"])
    recs = [r for r in state.values() if r.get("price_czk") and r.get("offer") in offers]
    groups = dedupe(recs)
    # quarter medians of price per m² (primary copies only)
    prim = []
    for g in groups:
        g.sort(key=_score, reverse=True)
        prim.append(g)
    med: dict[tuple, float] = {}
    by: dict[tuple, list[float]] = {}
    for g in prim:
        r = g[0]
        if r.get("area") and r["area"] >= 12 and r.get("quarter"):
            by.setdefault((r["offer"], r["quarter"]), []).append(r["price_czk"] / r["area"])
    for k, vals in by.items():
        if len(vals) >= 5:
            med[k] = statistics.median(vals)

    compact, shards = [], {}
    today = date.today()
    for g in prim:
        r = g[0]
        pm2 = round(r["price_czk"] / r["area"]) if r.get("area") else None
        hist = r.get("history") or []
        peak = max((h[1] for h in hist), default=r["price_czk"])
        drop = round(100 * (peak - r["price_czk"]) / peak) if peak and peak > r["price_czk"] else 0
        m = med.get((r["offer"], r.get("quarter")))
        dev = round(100 * (pm2 - m) / m) if (m and pm2) else None
        first = min((x.get("first_seen") or "9999") for x in g)
        lat, lon = r.get("lat"), r.get("lon")
        if lat is None:
            alt = next((x for x in g if x.get("lat")), None)
            lat, lon = (alt["lat"], alt["lon"]) if alt else (None, None)
        imgs = r.get("images") or next((x["images"] for x in g if x.get("images")), [])
        compact.append({
            "i": r["id"], "o": "r" if r["offer"] == "rent" else "s", "d": r.get("disp"), "a": r.get("area"),
            "p": r["price_czk"], "c": r.get("charges"), "m": pm2, "q": r.get("quarter"), "n": r.get("district"),
            "s": r.get("street"), "la": round(lat, 5) if lat else None, "lo": round(lon, 5) if lon else None,
            "t": imgs[0] if imgs else None, "fs": first, "dr": drop or None, "dv": dev, "f": _flags(r),
            "fl": r.get("floor"), "src": r["source"], "x": len(g) - 1,
        })
        full = {k: v for k, v in r.items() if k not in ("missed",)}
        full["first_seen"] = first
        full["price_m2"] = pm2
        full["quarter_median_m2"] = round(m) if m else None
        full["also_on"] = [{"source": x["source"], "url": x["url"], "price_czk": x["price_czk"]} for x in g[1:]]
        if not full.get("images"):
            full["images"] = imgs
        shards.setdefault(shard_of(r["id"]), {})[r["id"]] = full

    compact.sort(key=lambda c: (c["fs"], c["i"]), reverse=True)
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "d").mkdir(exist_ok=True)
    for old in (SITE_DATA / "d").glob("*.json"):
        if old.stem not in shards:
            old.unlink()
    for sh, items in shards.items():
        (SITE_DATA / "d" / f"{sh}.json").write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    (SITE_DATA / "listings.json").write_text(json.dumps(compact, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    per_source: dict[str, int] = {}
    for r in recs:
        per_source[r["source"]] = per_source.get(r["source"], 0) + 1
    quarters_present = sorted({c["q"] for c in compact if c["q"]}, key=lambda q: (QUARTERS.index(q) if q in QUARTERS else 999, q))
    meta = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "count": len(compact), "rent": sum(1 for c in compact if c["o"] == "r"),
        "sale": sum(1 for c in compact if c["o"] == "s"), "raw": len(recs), "per_source": per_source,
        "new_today": sum(1 for c in compact if c["fs"] == today.isoformat()),
        "quarters": quarters_present, "eur_czk": rate,
        "medians": {f"{o}|{q}": round(v) for (o, q), v in sorted(med.items())},
        "errors": {k: v["errors"] for k, v in (report or {}).get("sources", {}).items() if v.get("errors")},
    }
    (SITE_DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("published %d listings (%d raw)", len(compact), len(recs))
