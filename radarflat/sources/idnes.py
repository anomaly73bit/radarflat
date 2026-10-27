"""Reality.iDNES.cz — HTML list pages (/s/…/byty/praha/?page=N, 0-based) and detail pages."""
from __future__ import annotations

import html as htmllib
import json
import re

from ..geo import fold, in_prague, parse_address
from ..model import area_from_text, blank, furnished, norm_disp, to_int
from .base import Source, log

BASE = "https://reality.idnes.cz"
OFFER_SLUG = {"rent": "pronajem", "sale": "prodej"}

_ITEM = re.compile(r'<div class="c-products__item">(.*?)</article>', re.S)
_HREF = re.compile(r'href="(https://reality\.idnes\.cz/detail/[^"]+/([0-9a-f]{24})/)"')
_TAGS = re.compile(r"<[^>]+>")


def text(s: str | None) -> str:
    if not s:
        return ""
    s = htmllib.unescape(_TAGS.sub(" ", s)).replace("‍", "").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_list(html: str, offer: str) -> list[dict]:
    out = []
    for m in _ITEM.finditer(html):
        block = m.group(1)
        h = _HREF.search(block)
        if not h:
            continue
        url, sid = h.group(1), h.group(2)
        title = text(re.search(r'<h2 class="c-products__title">(.*?)</h2>', block, re.S).group(1)) \
            if '<h2 class="c-products__title">' in block else ""
        info = re.search(r'<p class="c-products__info">(.*?)</p>', block, re.S)
        price = re.search(r'<p class="c-products__price">(.*?)</p>', block, re.S)
        thumb = re.search(r'data-src="([^"]+)"', block)
        d = blank("idnes", sid, url, offer)
        d.update(parse_address(text(info.group(1)) if info else None))
        ptxt = text(price.group(1)) if price else ""
        d.update(title=title.capitalize() or None, disp=norm_disp(title), area=area_from_text(title),
                 price=_price(ptxt), currency="EUR" if "€" in ptxt or "EUR" in ptxt else "CZK",
                 images=[thumb.group(1)] if thumb else [])
        out.append(d)
    return out


def _price(t: str) -> int | None:
    if not t or "dohod" in fold(t) or "info" in fold(t):
        return None
    m = re.search(r"(\d[\d ]*)", t.replace(" ", " "))
    return to_int(m.group(1)) if m else None


def _yes(dd: str) -> bool | None:
    if "icon--check" in dd:
        return True
    f = fold(text(dd))
    if not f:
        return None
    if f.startswith("ne"):
        return False
    return True


def parse_detail(html: str) -> dict:
    if "b-detail__title" not in html:
        return {}
    pairs = {}
    for dl in re.findall(r'<dl>(.*?)</dl>', html, re.S):
        for dt, dd in re.findall(r"<dt>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", dl, re.S):
            pairs[fold(text(dt))] = dd
    g = lambda *keys: next((pairs[k] for k in keys if k in pairs), None)  # noqa: E731
    out: dict = {"detail_done": True}
    title = re.search(r'<h1 class="b-detail__title">(.*?)</h1>', html, re.S)
    if title:
        out["title"] = text(title.group(1))
        out["disp"] = norm_disp(out["title"])
    info = re.search(r'<p class="b-detail__info">(.*?)</p>', html, re.S)
    if info:
        out.update({k: v for k, v in parse_address(text(info.group(1))).items() if v})
    if (v := g("uzitna plocha", "plocha")):
        out["area"] = area_from_text(v + " m2") or to_int(text(v))
    if (v := g("cena")):
        out["price"] = _price(text(v))
    if (v := g("podlazi")):
        m = re.search(r"(-?\d+)\.\s*(?:patro|podlazi)", fold(text(v)))
        out["floor"] = int(m.group(1)) if m else (0 if "prizemi" in fold(text(v)) else None)
    if (v := g("pocet podlazi budovy", "pocet podlazi")):
        out["floors_total"] = to_int(text(v))
    for key, field in (("vytah", "lift"), ("balkon", "balcony"), ("terasa", "terrace"), ("lodzie", "loggia"),
                       ("sklep", "cellar"), ("parkovani", "parking"), ("garaz", "garage")):
        if key in pairs:
            out[field] = _yes(pairs[key])
    if (v := g("vybaveni", "vybaveno")):
        out["furnished"] = furnished(text(v))
    if (v := g("stav bytu", "stav budovy")):
        out["condition"] = _condition(text(v))
    if (v := g("konstrukce budovy")):
        f = fold(text(v))
        out["construction"] = ("brick" if "cihl" in f else "panel" if "panel" in f else "skeleton" if "skelet" in f
                               else "mixed" if "smisen" in f else "wood" if "drev" in f else "other")
    if (v := g("vlastnictvi")):
        f = fold(text(v))
        out["ownership"] = "personal" if "osob" in f else "cooperative" if "druz" in f else "municipal" if "obec" in f or "stat" in f else None
    if (v := g("penb")):
        m = re.match(r"\s*([A-G])\b", text(v))
        out["penb"] = m.group(1) if m else None
    if (v := g("topeni")):
        out["heating"] = text(v)[:60]
    if (v := g("datum nastehovani")):
        m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text(v))
        out["available_from"] = f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None
    if (v := g("kauce", "vratna kauce")):
        out["deposit"] = to_int(text(v))
    if (v := g("poplatky", "naklady na bydleni", "poplatky za sluzby")):
        out["charges"] = to_int(text(v))
    desc = re.search(r'<div class="b-desc[^"]*">(.*?)</div>', html, re.S)
    if desc:
        body = re.sub(r"<h2>.*?</h2>", "", desc.group(1), flags=re.S)
        out["description"] = text(body.replace("<br>", "\n"))[:4000] or None
    imgs = re.findall(r'<a href="(https://sta-reality2\.1gr\.cz/[^"]+)"[^>]*data-fancybox="images"', html)
    if imgs:
        out["images"] = list(dict.fromkeys(imgs))
    out.update(_coords(html))
    out["private"] = False if "/makler/detail/" in html or "/rk/" in html else None
    return out


def _condition(t: str) -> str | None:
    f = fold(t)
    if "novostav" in f or f == "novy":
        return "new"
    if "po rekonstr" in f:
        return "renovated"
    if "velmi dobr" in f:
        return "very_good"
    if "dobr" in f:
        return "good"
    if "pred rekonstr" in f or "spatn" in f:
        return "needs_renovation"
    if "ve vystav" in f or "projekt" in f:
        return "under_construction"
    return None


def _coords(html: str) -> dict:
    """The map widget ships GeoJSON: a Point for the house, or a LineString for the street."""
    for m in re.finditer(r'"geometry"\s*:\s*(\{.*?\})\s*,\s*"properties"', html, re.S):
        try:
            geo = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        c = geo.get("coordinates")
        if geo.get("type") == "Point" and c:
            lon, lat = c[0], c[1]
        elif geo.get("type") == "LineString" and c:
            mid = c[len(c) // 2]
            lon, lat = mid[0], mid[1]
        else:
            continue
        if in_prague(lat, lon):
            return {"lat": round(lat, 6), "lon": round(lon, 6)}
    return {}


class Idnes(Source):
    name = "idnes"
    label = "iDNES Reality"

    def listings(self, offer):
        seen: set[str] = set()
        url = f"{BASE}/s/{OFFER_SLUG[offer]}/byty/praha/"
        for page in range(self.max_pages()):
            r = self.client.get(url, params={"page": page} if page else None)
            items = parse_list(r.text, offer)
            fresh = [i for i in items if i["source_id"] not in seen]
            if not fresh:
                break
            for it in fresh:
                seen.add(it["source_id"])
                yield it
        log.info("idnes %s: %d listings", offer, len(seen))

    def detail(self, listing):
        r = self.client.get(listing["url"])
        if r.status_code in (404, 410) or "/detail/" not in r.url:
            return None
        return parse_detail(r.text)
