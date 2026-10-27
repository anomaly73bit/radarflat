"""Sreality.cz — JSON search API (/api/v1/estates/search).

Sreality's robots.txt disallows every crawler except search engines ("User-agent: * / Disallow: /").
The source is therefore OFF in config/sources.yaml; turning it on requires both `enabled: true`
and `respect_robots_txt: false` for this source, and is the operator's own decision.
"""
from __future__ import annotations

from ..geo import canonical_quarter, district_of_quarter
from ..model import blank, norm_disp
from .base import Source, log

API = "https://www.sreality.cz/api/v1/estates/search"
TYPE = {"rent": 2, "sale": 1}
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
    imgs = [("https:" + i["advert_image_sdn_url"] if i["advert_image_sdn_url"].startswith("//") else i["advert_image_sdn_url"])
            + "?fl=res,1024,768,1" for i in e.get("advert_images_all") or [] if i.get("advert_image_sdn_url")]
    name = e.get("advert_name") or ""
    d.update(
        disp=norm_disp(sub), area=_area(name), price=int(e["price_czk"]) if e.get("price_czk") else None,
        currency="CZK", district=dist, quarter=quarter, street=loc.get("street"),
        address=", ".join(x for x in (loc.get("street"), loc.get("district"), loc.get("citypart")) if x),
        lat=loc.get("gps_lat"), lon=loc.get("gps_lon"), images=imgs, title=name, private=None,
    )
    return d


def _area(name: str):
    import re
    m = re.search(r"(\d+)\s*m²", name)
    return int(m.group(1)) if m else None


class Sreality(Source):
    name = "sreality"
    label = "Sreality"
    needs_detail = False

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
