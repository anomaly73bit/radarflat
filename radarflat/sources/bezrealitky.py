"""Bezrealitky.cz — owners without agency. Reads the Next.js data of the public listing pages
(www.bezrealitky.cz/vypis/…) and of each detail page. The GraphQL API host is disallowed by
robots.txt, so it is not used."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ..geo import parse_address
from ..http import next_data
from ..model import blank, norm_disp
from .base import Source, log

BASE = "https://www.bezrealitky.cz"
OFFER_SLUG = {"rent": "nabidka-pronajem", "sale": "nabidka-prodej"}

CONDITION = {"NEW": "new", "VERY_GOOD": "very_good", "GOOD": "good", "AFTER_RECONSTRUCTION": "renovated",
             "BEFORE_RECONSTRUCTION": "needs_renovation", "BAD": "needs_renovation",
             "CONSTRUCTION": "under_construction", "PROJECT": "under_construction", "DEVELOPMENT": "under_construction"}
CONSTRUCTION = {"BRICK": "brick", "PANEL": "panel", "MIXED": "mixed", "SKELET": "skeleton", "WOOD": "wood",
                "STONE": "brick", "LOW_ENERGY": "other", "PREFAB": "panel"}
OWNERSHIP = {"OSOBNI": "personal", "DRUZSTEVNI": "cooperative", "OBECNI": "municipal", "STATNI": "municipal"}
EQUIPPED = {"VYBAVENY": "yes", "CASTECNE": "partly", "NEVYBAVENY": "no"}
HEATING = {"CENTRAL": "central", "GAS": "gas", "ELECTRIC": "electric", "LOCAL": "local", "HEAT_PUMP": "heat_pump",
           "SOLID_FUEL": "solid_fuel", "OTHER": "other"}


def _key(d: dict, prefix: str):
    """Apollo cache keys carry arguments: 'address({"locale":"CS"})'."""
    for k, v in d.items():
        if k == prefix or k.startswith(prefix + "("):
            return v
    return None


def _img(cache: dict, ref) -> str | None:
    if isinstance(ref, dict) and "__ref" in ref:
        ref = cache.get(ref["__ref"], {})
    if not isinstance(ref, dict):
        return None
    for k, v in ref.items():
        if k.startswith("url") and "RECORD_MAIN" in k:
            return v
    return ref.get("url") or _key(ref, "url")


def _ts(v) -> str | None:
    if not v:
        return None
    try:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


class Bezrealitky(Source):
    name = "bezrealitky"
    label = "Bezrealitky"

    def listings(self, offer):
        url = f"{BASE}/vypis/{OFFER_SLUG[offer]}/byt/praha"
        seen: set[str] = set()
        total_pages = None
        page = 1
        while page <= (total_pages or self.max_pages()):
            r = self.client.get(url, params={"page": page} if page > 1 else None)
            items, total = parse_list(r.text, offer)
            if total and total_pages is None:
                total_pages = (total + 14) // 15
            fresh = [i for i in items if i["source_id"] not in seen]
            if not fresh:
                break
            for it in fresh:
                seen.add(it["source_id"])
                yield it
            page += 1
        log.info("bezrealitky %s: %d listings", offer, len(seen))

    def detail(self, listing):
        r = self.client.get(listing["url"])
        if r.status_code in (404, 410):
            return None
        return parse_detail(r.text)


def _advert_to_listing(ad: dict, cache: dict, offer: str) -> dict | None:
    if ad.get("estateType") not in (None, "BYT"):
        return None
    if ad.get("roommate"):
        return None
    uri = ad.get("uri")
    d = blank("bezrealitky", ad["id"], f"{BASE}/nemovitosti-byty-domy/{uri}", offer)
    addr = _key(ad, "address")
    d.update(parse_address(addr))
    gps = ad.get("gps") or {}
    imgs = [u for u in (_img(cache, ref) for ref in (_key(ad, "publicImages") or [])) if u]
    if not imgs and ad.get("mainImage"):
        u = _img(cache, ad["mainImage"])
        imgs = [u] if u else []
    d.update(
        disp=norm_disp(ad.get("disposition")), area=ad.get("surface"), price=ad.get("price"),
        currency=ad.get("currency") or "CZK", charges=ad.get("charges"), lat=gps.get("lat"), lon=gps.get("lng"),
        images=imgs, private=True, pets=ad.get("petFriendly"),
        title=_key(ad, "imageAltText"),
    )
    return d


def parse_list(html: str, offer: str) -> tuple[list[dict], int | None]:
    data = next_data(html)
    if not data:
        return [], None
    cache = data.get("props", {}).get("pageProps", {}).get("apolloCache", {})
    root = cache.get("ROOT_QUERY", {})
    out, total = [], None
    for k, v in root.items():
        if not k.startswith("listAdverts(") or '"discountedOnly":true' in k:
            continue
        total = v.get("totalCount") or total
        for ref in v.get("list", []):
            ad = cache.get(ref.get("__ref", ""), {})
            item = _advert_to_listing(ad, cache, offer) if ad else None
            if item:
                out.append(item)
    return out, total


def parse_detail(html: str) -> dict:
    data = next_data(html)
    ad = (data or {}).get("props", {}).get("pageProps", {}).get("origAdvert")
    if not ad:
        return {}
    if ad.get("active") is False or ad.get("archived"):
        return None  # type: ignore[return-value]
    imgs = [i.get("url") for i in ad.get("publicImages") or [] if i.get("url")]
    gps = ad.get("gps") or {}
    addr = parse_address(ad.get("address"))
    desc = ad.get("descriptionByLocale") or ad.get("description")
    out = {
        "images": imgs, "description": (desc or "").strip()[:4000] or None,
        "price": ad.get("price"), "charges": ad.get("charges"), "deposit": ad.get("deposit"),
        "currency": ad.get("currency"), "area": ad.get("surface"), "disp": norm_disp(ad.get("disposition")),
        "floor": ad.get("etage"), "floors_total": ad.get("totalFloors"), "lift": ad.get("lift"),
        "balcony": bool(ad.get("balcony") or ad.get("balconySurface")) or None,
        "terrace": bool(ad.get("terrace") or ad.get("terraceSurface")) or None,
        "loggia": bool(ad.get("loggia") or ad.get("loggiaSurface")) or None,
        "cellar": bool(ad.get("cellar") or ad.get("cellarSurface")) or None,
        "parking": ad.get("parking") or None, "garage": ad.get("garage") or None,
        "furnished": EQUIPPED.get(ad.get("equipped") or ""), "condition": CONDITION.get(ad.get("condition") or ""),
        "construction": CONSTRUCTION.get(ad.get("construction") or ""),
        "ownership": OWNERSHIP.get(ad.get("ownership") or ""), "penb": ad.get("penb") or None,
        "heating": HEATING.get(ad.get("heating") or ""), "available_from": _ts(ad.get("availableFrom")),
        "pets": ad.get("petFriendly"), "lat": gps.get("lat"), "lon": gps.get("lng"),
        "street": ad.get("street") or addr["street"], "title": ad.get("pageTitle"),
        "detail_done": True,
    }
    if addr["district"]:
        out["district"], out["quarter"] = addr["district"], addr["quarter"]
    return out


def debug_dump(html: str) -> str:  # pragma: no cover - helper for manual inspection
    return json.dumps(next_data(html), ensure_ascii=False)[:2000]
