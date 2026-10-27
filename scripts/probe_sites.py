"""Probe candidate listing sources from the GitHub runner and save raw samples.

Writes probe/report.json and probe/samples/<name>.<ext> (truncated) so the
adapters can be written against real responses.
"""
import json
import pathlib
import time

import requests

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
OUT = pathlib.Path("probe")
SAMPLES = OUT / "samples"
SAMPLES.mkdir(parents=True, exist_ok=True)

BEZ_QUERY = """
query ListAdverts($offerType:[OfferType], $estateType:[EstateType], $regionOsmIds:[ID], $limit:Int, $offset:Int, $locale:Locale!) {
  listAdverts(offerType:$offerType, estateType:$estateType, regionOsmIds:$regionOsmIds, limit:$limit, offset:$offset, order:TIMEORDER_DESC) {
    totalCount
    list { id uri offerType estateType disposition surface price charges currency
           address(locale:$locale) gps { lat lng } mainImage { url(filter:RECORD_THUMB) }
           floor etage ownership condition construction penb equipped balcony terrace lift
           timeActivated }
  }
}
"""

PROBES = [
    ("sreality_v2_rent", "GET",
     "https://www.sreality.cz/api/cs/v2/estates?category_main_cb=1&category_type_cb=2&locality_region_id=10&per_page=5&page=1",
     None, "json"),
    ("sreality_v2_sale", "GET",
     "https://www.sreality.cz/api/cs/v2/estates?category_main_cb=1&category_type_cb=1&locality_region_id=10&per_page=5&page=1",
     None, "json"),
    ("sreality_v1_search", "GET",
     "https://www.sreality.cz/api/v1/estates/search?category_main_cb=1&category_type_cb=2&locality_region_id=10&limit=5&offset=0&lang=cs",
     None, "json"),
    ("sreality_html", "GET", "https://www.sreality.cz/hledani/pronajem/byty/praha", None, "html"),
    ("bezrealitky_graphql", "POST", "https://api.bezrealitky.cz/graphql/",
     {"operationName": "ListAdverts", "query": BEZ_QUERY,
      "variables": {"offerType": ["PRONAJEM"], "estateType": ["BYT"],
                    "regionOsmIds": ["R435514"], "limit": 5, "offset": 0, "locale": "CS"}},
     "json"),
    ("bezrealitky_html", "GET", "https://www.bezrealitky.cz/vypis/nabidka-pronajem/byt/praha", None, "html"),
    ("idnes_html", "GET", "https://reality.idnes.cz/s/pronajem/byty/praha/", None, "html"),
    ("realitymix_html", "GET", "https://realitymix.cz/vypis-nabidek/?form%5Bdruh_objektu_ids%5D%5B%5D=2&form%5Bkraj_ids%5D%5B%5D=19&form%5Btyp_nabidky%5D=2", None, "html"),
    ("ulovdomov_html", "GET", "https://www.ulovdomov.cz/pronajem/bytu/praha", None, "html"),
    ("remax_html", "GET", "https://www.remax-czech.cz/reality/vyhledavani/?regions%5B19%5D=on&types%5B4%5D=on&sale=2", None, "html"),
    ("robots_sreality", "GET", "https://www.sreality.cz/robots.txt", None, "txt"),
    ("robots_bezrealitky", "GET", "https://www.bezrealitky.cz/robots.txt", None, "txt"),
    ("robots_idnes", "GET", "https://reality.idnes.cz/robots.txt", None, "txt"),
    ("robots_realitymix", "GET", "https://realitymix.cz/robots.txt", None, "txt"),
    ("robots_ulovdomov", "GET", "https://www.ulovdomov.cz/robots.txt", None, "txt"),
]

report = {}
for name, method, url, body, ext in PROBES:
    rec = {"url": url, "method": method}
    try:
        headers = {"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"}
        if method == "POST":
            r = requests.post(url, json=body, headers=headers, timeout=30)
        else:
            r = requests.get(url, headers=headers, timeout=30)
        rec.update(status=r.status_code, final_url=r.url,
                   content_type=r.headers.get("content-type"), size=len(r.content),
                   head=r.text[:300])
        (SAMPLES / f"{name}.{ext}").write_text(r.text[:600_000], encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        rec["error"] = repr(exc)
    report[name] = rec
    print(name, rec.get("status"), rec.get("size"), rec.get("error", ""))
    time.sleep(2)

# If the v2 list worked, grab one detail record too.
try:
    lst = json.loads((SAMPLES / "sreality_v2_rent.json").read_text())
    hid = lst["_embedded"]["estates"][0]["hash_id"]
    r = requests.get(f"https://www.sreality.cz/api/cs/v2/estates/{hid}", headers={"User-Agent": UA}, timeout=30)
    (SAMPLES / "sreality_v2_detail.json").write_text(r.text[:600_000], encoding="utf-8")
    report["sreality_v2_detail"] = {"status": r.status_code, "size": len(r.content)}
except Exception as exc:  # noqa: BLE001
    report["sreality_v2_detail"] = {"error": repr(exc)}

(OUT / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
