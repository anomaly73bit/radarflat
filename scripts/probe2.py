"""Second probe round: robots of more sources, detail pages, extra list URLs."""
import json
import pathlib
import re
import time

import requests

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
H = {"User-Agent": UA, "Accept-Language": "cs,en;q=0.8"}
S = pathlib.Path("probe/samples2")
S.mkdir(parents=True, exist_ok=True)
report = {}


def get(name, url, ext="html", method="GET", body=None):
    rec = {"url": url}
    try:
        r = (requests.post(url, json=body, headers=H, timeout=30) if method == "POST"
             else requests.get(url, headers=H, timeout=30))
        rec.update(status=r.status_code, final_url=r.url, size=len(r.content),
                   content_type=r.headers.get("content-type"))
        (S / f"{name}.{ext}").write_text(r.text[:600_000], encoding="utf-8")
        report[name] = rec
        print(name, r.status_code, len(r.content), r.url[:100])
        time.sleep(2)
        return r
    except Exception as exc:  # noqa: BLE001
        rec["error"] = repr(exc)
        report[name] = rec
        print(name, "ERR", exc)
        return None


for host in ["api.bezrealitky.cz", "www.realingo.cz", "reality.bazos.cz", "www.eurobydleni.cz",
             "www.mmreality.cz", "www.remax-czech.cz", "www.century21.cz", "www.ceskereality.cz",
             "www.reality.cz", "www.flatzone.cz", "www.svobodni-pronajem.cz"]:
    get("robots_" + host.replace(".", "_"), f"https://{host}/robots.txt", "txt")

for i, u in enumerate([
    "https://realitymix.cz/reality/byty/pronajem/praha",
    "https://realitymix.cz/reality/byty/pronajem/praha/hlavni-mesto-praha",
    "https://realitymix.cz/reality/byty/prodej/praha",
]):
    get(f"realitymix_{i}", u)

get("bazos_list", "https://reality.bazos.cz/pronajmu/byt/praha/")
get("realingo_list", "https://www.realingo.cz/pronajem/byty/praha/")
get("ceskereality_list", "https://www.ceskereality.cz/pronajem/byty/praha/")

# iDNES detail page
lst = (pathlib.Path("probe/samples/idnes_html.html")).read_text(encoding="utf-8")
m = re.search(r'href="(https://reality\.idnes\.cz/detail/[^"]+)"', lst)
if m:
    get("idnes_detail", m.group(1))
get("idnes_sale_list", "https://reality.idnes.cz/s/prodej/byty/praha/")
get("idnes_page2", "https://reality.idnes.cz/s/pronajem/byty/praha/?page=1")

# Bezrealitky: full detail + sale count
DETAIL = """
query Advert($id: ID!, $locale: Locale!) {
  advert(id: $id) {
    id uri offerType estateType disposition surface surfaceLand price charges serviceCharges utilityCharges
    deposit currency address(locale:$locale) street houseNumber city(locale:$locale) cityDistrict(locale:$locale)
    zip gps { lat lng } description(locale:$locale) descriptionEnglish
    publicImages { url(filter:RECORD_MAIN) order }
    floor etage totalFloors ownership condition construction penb equipped
    balcony balconySurface terrace terraceSurface loggia cellar parking garage lift garden
    availableFrom timeActivated timeOrder reserved isPausedBySystem isPausedByUser
    tags(locale:$locale)
  }
}
"""
g = json.loads((pathlib.Path("probe/samples/bezrealitky_graphql.json")).read_text())
bid = g["data"]["listAdverts"]["list"][0]["id"]
get("bez_detail", "https://api.bezrealitky.cz/graphql/", "json", "POST",
    {"operationName": "Advert", "query": DETAIL, "variables": {"id": bid, "locale": "CS"}})
COUNT = """query C($offerType:[OfferType],$estateType:[EstateType],$regionOsmIds:[ID]){
 listAdverts(offerType:$offerType,estateType:$estateType,regionOsmIds:$regionOsmIds,limit:1){totalCount}}"""
get("bez_sale_count", "https://api.bezrealitky.cz/graphql/", "json", "POST",
    {"query": COUNT, "variables": {"offerType": ["PRODEJ"], "estateType": ["BYT"], "regionOsmIds": ["R435514"]}})
get("bez_html_detail", f"https://www.bezrealitky.cz/nemovitosti-byty-domy/{g['data']['listAdverts']['list'][0]['uri']}")

(pathlib.Path("probe") / "report2.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
