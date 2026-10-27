"""Sreality.cz — JSON search API (/api/v1/estates/search).

Detail: /api/v1/estates/<hash_id>.

Sreality's robots.txt disallows every crawler except search engines ("User-agent: * / Disallow: /").
The owner chose to use it anyway (config/sources.yaml: enabled + respect_robots_txt: false).
"""
from __future__ import annotations

import re

from ..geo import canonical_quarter, district_of_quarter, fold
from ..model import blank, furnished, norm_disp, to_int
from .base import Source, log

API = "https://www.sreality.cz/api/v1/estates/search"
DETAIL = "https://www.sreality.cz/api/v1/estates/{}"
TYPE = {"rent": 2, "sale": 1}
# The image CDN only serves a whitelist of sizes; these two are the ones Sreality itself uses.
FULL = "?fl=res,1920,1080,1|wrm,/watermark/sreality.png,10|shr,,20|jpg,90"
THUMB = "?fl=res,400,300,3|shr,,20|jpg,90"
TYPE_SLUG = {"rent": "pronajem", "sale": "prodej"}


def to_listing(e: dict, offer: str) -> dict:
    loc = e.get("locality") or {}
    sub = (e.get("category_sub_cb") or {}).get("name") or ""
    hid = e["hash_id"]
    slug = "-".join(x for x in (loc.get("city_seo_name"), loc.get("citypart_seo_name"), loc.get("street_seo_name")) if x)
    url = f"https://www.sreality.cz/detail/{TYPE_SLUG[offer]}/byt/{sub or 'atypicky'}/{slug or 'praha'}/{hid}"
    d = blank("sreality", hid, url, offer)
    quarter = canonical_quarter(loc.get("citypart") or loc.get("ward"))
    dist = district_of_quarter(quarter)
    if dist is None and (loc.get("district") or "").startswith("Praha "):
        try:
            n = int(loc["district"].split()[1])
            dist = n if n <= 10 else None
        except (ValueError, IndexError):
            pass
    imgs = [_img(i["advert_image_sdn_url"]) for i in e.get("advert_images_all") or [] if i.get("advert_image_sdn_url")]
    name = e.get("advert_name") or ""
    d.update(
        disp=norm_disp(sub), area=_area(name), price=int(e["price_czk"]) if e.get("price_czk") else None,
        currency="CZK", district=dist, quarter=quarter, street=loc.get("street"),
        address=", ".join(x for x in (loc.get("street"), loc.get("district"), loc.get("citypart")) if x),
        lat=loc.get("gps_lat"), lon=loc.get("gps_lon"), images=imgs, title=name, private=None,
    )
    return d


def _img(u: str) -> str:
    return ("https:" + u if u.startswith("//") else u).split("?")[0] + FULL


def _name(v) -> str:
    return (v or {}).get("name") or "" if isinstance(v, dict) else ""


def parse_detail(res: dict) -> dict:
    from .idnes import _condition
    out: dict = {"detail_done": True}
    out["description"] = (res.get("advert_description") or "").strip()[:4000] or None
    imgs = [_img(i["url"]) for i in sorted(res.get("advert_images") or [], key=lambda i: i.get("order") or 0) if i.get("url")]
    if imgs:
        out["images"] = imgs
    out["area"] = res.get("usable_area") or res.get("floor_area")
    fn = res.get("floor_number")
    out["floor"] = fn - 1 if isinstance(fn, int) else None          # Sreality counts above-ground floors (1 = ground)
    out["floors_total"] = res.get("floors")
    out["lift"] = {1: True, 2: False}.get((res.get("elevator") or {}).get("value"))
    for k in ("balcony", "terrace", "loggia", "cellar", "garage"):
        out[k] = bool(res.get(k)) or None
    out["parking"] = bool(res.get("parking") or res.get("parking_lots")) or None
    fu = fold(_name(res.get("furnished")))
    out["furnished"] = "partly" if "castec" in fu else "yes" if fu.startswith("ano") else "no" if fu.startswith("ne") else None
    out["condition"] = _condition(_name(res.get("building_condition")))
    bt = fold(_name(res.get("building_type")))
    out["construction"] = ("brick" if "cihl" in bt else "panel" if "panel" in bt else "skeleton" if "skelet" in bt
                           else "mixed" if "smis" in bt else "wood" if "drev" in bt else ("other" if bt and "vyber" not in bt else None))
    ow = fold(_name(res.get("ownership")))
    out["ownership"] = "personal" if "osob" in ow else "cooperative" if "druz" in ow else "municipal" if "stat" in ow or "obec" in ow else None
    m = re.match(r"\s*([A-G])\b", _name(res.get("energy_efficiency_rating_cb")))
    out["penb"] = m.group(1) if m else None
    out["available_from"] = res.get("ready_date") or None
    out["deposit"] = to_int(res.get("refundable_deposit")) or None
    out["charges"] = to_int(res.get("cost_of_living")) or None
    if res.get("price_czk"):
        out["price"] = int(res["price_czk"])
        out["currency"] = "CZK"
    loc = res.get("locality") or {}
    if loc.get("gps_lat"):
        out["lat"], out["lon"] = loc["gps_lat"], loc["gps_lon"]
    out["private"] = False if res.get("premise") else None
    out["title"] = res.get("advert_name")
    return out


def _area(name: str):
    m = re.search(r"(\d+)\s*m²", name)
    return int(m.group(1)) if m else None


class Sreality(Source):
    name = "sreality"
    label = "Sreality"

    def listings(self, offer):
        limit, offset, total, n = 60, 0, None, 0
        while total is None or offset < total:
            r = self.client.get(API, params={"category_main_cb": 1, "category_type_cb": TYPE[offer],
                                             "locality_region_id": 10, "limit": limit, "offset": offset, "lang": "cs"})
            data = r.json()
            total = (data.get("pagination") or {}).get("total") or 0
            res = data.get("results") or []
            if not res:
                break
            for e in res:
                n += 1
                yield to_listing(e, offer)
            offset += limit
            if offset > 60 * self.max_pages():
                break
        log.info("sreality %s: %d listings", offer, n)

    def detail(self, listing):
        r = self.client.get(DETAIL.format(listing["source_id"]), params={"lang": "cs"})
        if r.status_code in (404, 410):
            return None
        data = r.json()
        res = data.get("result") if isinstance(data, dict) else None
        if not res:
            return None if data.get("status_code") in (404, 410) else {}
        return parse_detail(res)
