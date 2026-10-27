"""RealityMix.cz — HTML list pages (/reality/byty/<offer>/praha?stranka=N) and detail pages."""
from __future__ import annotations

import re

from ..geo import fold, in_prague, parse_address
from ..model import area_from_text, blank, furnished, norm_disp, to_int, to_num
from .base import Source, log
from .idnes import _condition, text

BASE = "https://realitymix.cz"
OFFER_SLUG = {"rent": "pronajem", "sale": "prodej"}

_ITEM = re.compile(r'<li class="w-full advert-item" data-advert-id="(\d+)">(.*?)(?=<li class="w-full advert-item"|</ul>\s*</div>\s*<div[^>]*pagination|$)', re.S)


def parse_list(html: str, offer: str) -> list[dict]:
    out = []
    for sid, block in _ITEM.findall(html):
        a = re.search(r'<h2[^>]*>\s*<a href="([^"]+)"[^>]*>\s*<span>(.*?)</span>', block, re.S)
        if not a:
            continue
        url, title = a.group(1), text(a.group(2))
        f = fold(title)
        if "byt" not in f or "pokoj" in f and "byt" not in f:
            continue
        addr = re.search(r'</h2>\s*<p[^>]*>(.*?)</p>', block, re.S)
        price = re.search(r'<div class="text-xl font-extrabold[^"]*">\s*<span>(.*?)</span>', block, re.S)
        imgs = re.findall(r'<img class="absolute inset-0[^"]*"[^>]*src="(https://st\.realitymix\.cz/[^"]+)"', block)
        floor = re.search(r'alt="Podlaží"[^>]*/>\s*<span>\s*(-?\d+)\s*/\s*(\d+)', block)
        d = blank("realitymix", sid, url, offer)
        d.update(parse_address(text(addr.group(1)) if addr else None))
        ptxt = text(price.group(1)) if price else ""
        d.update(title=title, disp=norm_disp(title), area=area_from_text(title),
                 price=None if "dohod" in fold(ptxt) else to_int(ptxt),
                 currency="EUR" if "€" in ptxt or "eur" in fold(ptxt) else "CZK",
                 images=list(dict.fromkeys(imgs)),
                 floor=int(floor.group(1)) if floor else None,
                 floors_total=int(floor.group(2)) if floor else None)
        out.append(d)
    return out


def parse_detail(html: str) -> dict:
    out: dict = {"detail_done": True}
    pairs: dict[str, str] = {}
    for k, v in re.findall(r"<(?:dt|th)[^>]*>(.*?)</(?:dt|th)>\s*<(?:dd|td)[^>]*>(.*?)</(?:dd|td)>", html, re.S):
        pairs.setdefault(fold(text(k)).rstrip(":"), text(v))
    for k, v in re.findall(r'<li[^>]*>\s*<span[^>]*>([^<]{2,40}?):?\s*</span>\s*<(?:span|strong)[^>]*>(.*?)</(?:span|strong)>', html, re.S):
        pairs.setdefault(fold(text(k)).rstrip(":"), text(v))
    g = lambda *ks: next((pairs[k] for k in ks if k in pairs and pairs[k]), None)  # noqa: E731
    if (v := g("celkova plocha", "uzitna plocha", "plocha")):
        out["area"] = to_int(v)
    if (v := g("dispozice")):
        out["disp"] = norm_disp(v)
    if (v := g("podlazi", "patro")):
        m = re.search(r"(-?\d+)", v)
        out["floor"] = int(m.group(1)) if m else None
    if (v := g("pocet podlazi", "pocet podlazi v objektu")):
        out["floors_total"] = to_int(v)
    if (v := g("vybaveni", "vybavenost")):
        out["furnished"] = furnished(v)
    if (v := g("stav objektu", "stav")):
        out["condition"] = _condition(v)
    if (v := g("druh objektu", "konstrukce", "stavba")):
        f = fold(v)
        out["construction"] = ("brick" if "cihl" in f else "panel" if "panel" in f else "skeleton" if "skelet" in f
                               else "mixed" if "smis" in f else None)
    if (v := g("vlastnictvi")):
        f = fold(v)
        out["ownership"] = "personal" if "osob" in f else "cooperative" if "druz" in f else None
    if (v := g("energeticka narocnost", "energeticka narocnost budovy", "penb")):
        m = re.search(r"\b([A-G])\b", v)
        out["penb"] = m.group(1) if m else None
    for key, field in (("vytah", "lift"), ("balkon", "balcony"), ("terasa", "terrace"), ("lodzie", "loggia"),
                       ("sklep", "cellar"), ("parkovani", "parking"), ("garaz", "garage")):
        if key in pairs:
            out[field] = not fold(pairs[key]).startswith("ne")
    if (v := g("kauce", "vratna kauce")):
        out["deposit"] = to_int(v)
    desc = (re.search(r'<div class="advert-description__text-inner-inner">(.*?)</div>', html, re.S)
            or re.search(r'<div[^>]+itemprop="description"[^>]*>(.*?)</div>', html, re.S))
    if desc:
        out["description"] = text(desc.group(1).replace("<br>", "\n").replace("<br />", "\n"))[:4000] or None
    full = re.findall(r'(https?://st\.realitymix\.cz/i/\d+/\d+/nab_\d+\.jpe?g)', html)
    small = re.findall(r'(https?://st\.realitymix\.cz/i/\d+/\d+/nab_\d+_detail\.jpe?g)', html)
    imgs = [u.replace("http://", "https://") for u in (full or small)]
    if imgs:
        out["images"] = list(dict.fromkeys(imgs))[:40]
    lat = re.search(r'(?:lat|latitude)["\']?\s*[:=]\s*["\']?(50\.\d{3,})', html)
    lon = re.search(r'(?:lng|lon|longitude)["\']?\s*[:=]\s*["\']?(14\.\d{3,})', html)
    if lat and lon and in_prague(to_num(lat.group(1)), to_num(lon.group(1))):
        out["lat"], out["lon"] = float(lat.group(1)), float(lon.group(1))
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if h1:
        out["title"] = text(h1.group(1))
        out.setdefault("disp", norm_disp(out["title"]))
        out.setdefault("area", area_from_text(out["title"]))
    out["private"] = False
    return out


class Realitymix(Source):
    name = "realitymix"
    label = "RealityMix"

    def listings(self, offer):
        seen: set[str] = set()
        url = f"{BASE}/reality/byty/{OFFER_SLUG[offer]}/praha"
        for page in range(1, self.max_pages() + 1):
            r = self.client.get(url, params={"stranka": page} if page > 1 else None)
            items = parse_list(r.text, offer)
            fresh = [i for i in items if i["source_id"] not in seen]
            if not fresh:
                break
            for it in fresh:
                seen.add(it["source_id"])
                yield it
        log.info("realitymix %s: %d listings", offer, len(seen))

    def detail(self, listing):
        r = self.client.get(listing["url"])
        if r.status_code in (404, 410):
            return None
        return parse_detail(r.text)
