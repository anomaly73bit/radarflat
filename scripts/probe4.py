"""iDNES 429 behaviour with the bot UA, and one RealityMix detail page."""
import json, pathlib, time, requests
S = pathlib.Path("probe/samples4"); S.mkdir(parents=True, exist_ok=True)
BOT = "Mozilla/5.0 (compatible; RadarFlatBot/1.0; +https://radarflat.pacificit.solutions)"
BROWSER = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
rep = []
for ua_name, ua in (("bot", BOT), ("browser", BROWSER)):
    for i in range(3):
        r = requests.get("https://reality.idnes.cz/s/pronajem/byty/praha/", headers={"User-Agent": ua}, timeout=30)
        rep.append({"ua": ua_name, "try": i, "status": r.status_code, "retry_after": r.headers.get("retry-after"),
                    "server": r.headers.get("server"), "head": r.text[:300]})
        time.sleep(8)
st = [json.loads(l) for l in open("state/listings.jsonl")]
rm = next(r for r in st if r["source"] == "realitymix" and r.get("detail_done"))
r = requests.get(rm["url"], headers={"User-Agent": BOT}, timeout=30)
(S / "realitymix_detail.html").write_text(r.text, encoding="utf-8")
rep.append({"realitymix": rm["url"], "status": r.status_code})
(S / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False))
