"""Probe Sreality detail endpoints for one rental."""
import json, pathlib, time, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; RadarFlatBot/1.0; +https://radarflat.pacificit.solutions)"}
S = pathlib.Path("probe/samples3"); S.mkdir(parents=True, exist_ok=True)
r = requests.get("https://www.sreality.cz/api/v1/estates/search", params={"category_main_cb": 1, "category_type_cb": 2,
     "locality_region_id": 10, "limit": 60, "offset": 0, "lang": "cs"}, headers=H, timeout=30)
d = r.json(); hid = d["results"][0]["hash_id"]
print("search", r.status_code, len(d["results"]), d["pagination"])
for name, url in [("v1", f"https://www.sreality.cz/api/v1/estates/{hid}?lang=cs"),
                  ("v1b", f"https://www.sreality.cz/api/v1/estates/{hid}"),
                  ("cs_v2", f"https://www.sreality.cz/api/cs/v2/estates/{hid}"),
                  ("html", f"https://www.sreality.cz/detail/pronajem/byt/x/praha/{hid}")]:
    x = requests.get(url, headers=H, timeout=30)
    print(name, x.status_code, len(x.content), x.headers.get("content-type"), x.url[:120])
    (S / f"{name}.txt").write_text(x.text[:800_000], encoding="utf-8")
    time.sleep(2)
