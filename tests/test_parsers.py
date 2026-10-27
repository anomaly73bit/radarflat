import json
from pathlib import Path

from radarflat.geo import parse_address
from radarflat.model import area_from_text, norm_disp
from radarflat.pipeline import dedupe
from radarflat.sources import bezrealitky, idnes, realitymix, sreality

F = Path(__file__).parent / "fixtures"


def read(name):
    return (F / name).read_text(encoding="utf-8")


def test_address():
    a = parse_address("Na Plzeňce, Praha 5 - Smíchov")
    assert (a["street"], a["district"], a["quarter"]) == ("Na Plzeňce", 5, "Smíchov")
    a = parse_address("U Pergamenky, Praha - Holešovice")
    assert (a["street"], a["district"], a["quarter"]) == ("U Pergamenky", 7, "Holešovice")
    a = parse_address("Molákova, Praha 8, Karlín")
    assert (a["street"], a["district"], a["quarter"]) == ("Molákova", 8, "Karlín")
    a = parse_address("Praha 13")
    assert a["district"] == 5 and a["quarter"] == "Stodůlky"


def test_helpers():
    assert area_from_text("bytu 4+1 139 m²") == 139
    assert area_from_text("Pronájem bytu, 3+kk, 56 m²") == 56
    assert norm_disp("DISP_2_KK") == "2+kk"
    assert norm_disp("pronájem bytu 3+1 80 m²") == "3+1"
    assert norm_disp("7+kk") == "6+"


def test_bezrealitky():
    items, total = bezrealitky.parse_list(read("bezrealitky_list.html"), "rent")
    assert total == 1071 and len(items) == 15
    first = items[0]
    assert first["disp"] == "1+kk" and first["area"] == 40 and first["price"] == 22000 and first["lat"]
    d = bezrealitky.parse_detail(read("bezrealitky_detail.html"))
    assert len(d["images"]) == 13 and d["deposit"] == 44000 and d["furnished"] == "yes" and d["description"]


def test_idnes():
    items = idnes.parse_list(read("idnes_list.html"), "rent")
    assert len(items) >= 20
    it = items[0]
    assert it["area"] == 139 and it["disp"] == "4+1" and it["price"] == 44990 and it["quarter"] == "Smíchov"
    d = idnes.parse_detail(read("idnes_detail.html"))
    assert d["penb"] == "G" and len(d["images"]) == 17 and d["lat"] and d["lift"] is True


def test_realitymix():
    items = realitymix.parse_list(read("realitymix_list.html"), "rent")
    assert len(items) == 20
    assert items[0]["price"] == 24900 and items[0]["disp"] == "3+kk" and items[0]["floor"] == 1


def test_sreality():
    data = json.loads(read("sreality_search.json"))
    x = sreality.to_listing(data["results"][0], "rent")
    assert x["district"] == 2 and x["quarter"] == "Vinohrady" and x["area"] == 89 and len(x["images"]) == 15


def test_dedupe():
    base = dict(offer="rent", disp="2+kk", area=54, price_czk=24000, lat=50.07, lon=14.44, street="X", quarter="Q")
    a = {**base, "id": "a", "source": "idnes"}
    b = {**base, "id": "b", "source": "bezrealitky", "price_czk": 24300, "lat": 50.0705}
    c = {**base, "id": "c", "source": "realitymix", "area": 80}
    groups = dedupe([a, b, c])
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]


def test_sreality_detail():
    res = json.loads(read("sreality_detail.json"))["result"]
    d = sreality.parse_detail(res)
    assert d["area"] == 52 and d["floor"] == 9 and d["lift"] is True and d["penb"] == "B"
    assert d["furnished"] == "yes" and d["description"] and len(d["images"]) > 5 and d["loggia"]


def test_realitymix_detail():
    d = realitymix.parse_detail(read("realitymix_detail.html"))
    assert d["lat"] and d["penb"] == "G" and d["construction"] == "panel" and d["condition"] == "very_good"
    assert d["images"] and all("_detail" not in u for u in d["images"])
    assert d["description"] and "Popis nemovitosti" not in d["description"]
