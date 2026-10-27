"""Prague geography: cadastral areas (čtvrti) -> one of the 10 traditional districts (Praha 1–10)."""
from __future__ import annotations

import re
import unicodedata

# Each cadastral area is assigned to the obvod it mostly lies in (some areas are split).
_DISTRICTS = {
    1: "Staré Město, Josefov, Malá Strana, Hradčany, Nové Město",
    2: "Vinohrady, Vyšehrad, Nusle",
    3: "Žižkov",
    4: "Michle, Krč, Podolí, Braník, Hodkovičky, Lhotka, Kunratice, Chodov, Háje, Šeberov, "
       "Libuš, Písnice, Komořany, Modřany, Cholupice, Točná, Újezd u Průhonic, Újezd",
    5: "Smíchov, Košíře, Motol, Jinonice, Radlice, Hlubočepy, Zličín, Řeporyje, Stodůlky, Třebonice, "
       "Sobín, Lochkov, Slivenec, Radotín, Velká Chuchle, Malá Chuchle, Zbraslav, Lipence, Lahovice, "
       "Holyně, Malá Strana-Smíchov, Butovice, Nové Butovice",
    6: "Dejvice, Bubeneč, Střešovice, Břevnov, Veleslavín, Vokovice, Ruzyně, Liboc, Lysolaje, Suchdol, "
       "Sedlec, Nebušice, Přední Kopanina, Řepy",
    7: "Holešovice, Troja",
    8: "Karlín, Libeň, Kobylisy, Bohnice, Čimice, Ďáblice, Dolní Chabry, Březiněves",
    9: "Vysočany, Prosek, Střížkov, Letňany, Kbely, Čakovice, Miškovice, Třeboradice, Vinoř, Satalice, "
       "Hloubětín, Kyje, Hostavice, Černý Most, Horní Počernice, Klánovice, Újezd nad Lesy, Běchovice, "
       "Dolní Počernice, Hrdlořezy, Koloděje",
    10: "Vršovice, Strašnice, Malešice, Záběhlice, Hostivař, Uhříněves, Petrovice, Horní Měcholupy, "
        "Dolní Měcholupy, Štěrboholy, Dubeč, Pitkovice, Benice, Kolovraty, Lipany, Královice, Nedvězí, "
        "Křeslice, Hájek u Uhříněvsi",
}

# Numbered municipal parts (Praha 11–22) -> traditional district + representative quarter
_MUNICIPAL = {11: (4, "Chodov"), 12: (4, "Modřany"), 13: (5, "Stodůlky"), 14: (9, "Černý Most"),
              15: (10, "Hostivař"), 16: (5, "Radotín"), 17: (6, "Řepy"), 18: (9, "Letňany"),
              19: (9, "Kbely"), 20: (9, "Horní Počernice"), 21: (9, "Újezd nad Lesy"),
              22: (10, "Uhříněves")}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


QUARTER_DISTRICT: dict[str, tuple[int, str]] = {}
for _d, _names in _DISTRICTS.items():
    for _n in (x.strip() for x in _names.split(",")):
        QUARTER_DISTRICT[fold(_n)] = (_d, _n)

QUARTERS = sorted({v[1] for v in QUARTER_DISTRICT.values()}, key=fold)


def district_of_quarter(quarter: str | None) -> int | None:
    if not quarter:
        return None
    hit = QUARTER_DISTRICT.get(fold(quarter))
    return hit[0] if hit else None


def canonical_quarter(quarter: str | None) -> str | None:
    if not quarter:
        return None
    hit = QUARTER_DISTRICT.get(fold(quarter))
    return hit[1] if hit else quarter.strip()


_PRAHA_N = re.compile(r"Praha\s*(\d{1,2})", re.I)


def parse_address(text: str | None) -> dict:
    """Parse strings like 'Na Plzeňce, Praha 5 - Smíchov', 'U Pergamenky, Praha - Holešovice',
    'Molákova, Praha 8, Karlín'. Returns street, district (1–10), quarter."""
    out = {"street": None, "district": None, "quarter": None, "address": (text or "").strip() or None}
    if not text:
        return out
    t = re.sub(r"\s+", " ", text.replace(" ", " ")).strip()
    parts = [p.strip(" -–") for p in re.split(r",| – | - ", t) if p.strip(" -–")]
    num = None
    quarter = None
    street_parts = []
    for p in parts:
        m = _PRAHA_N.search(p)
        if m:
            num = int(m.group(1))
            rest = _PRAHA_N.sub("", p).strip(" -–")
            if rest:
                quarter = rest
            continue
        if fold(p) in ("praha", "hlavni mesto praha", "praha-mesto"):
            continue
        if fold(p).startswith("praha "):
            p = p[6:]
        if QUARTER_DISTRICT.get(fold(p)) and quarter is None:
            quarter = p
        elif quarter is None and num is not None and not street_parts:
            quarter = p
        else:
            street_parts.append(p)
    # "ul. X" prefix
    if street_parts:
        out["street"] = re.sub(r"^ul\.\s*", "", street_parts[0]).strip() or None
    quarter = canonical_quarter(quarter)
    district = district_of_quarter(quarter)
    if district is None and num:
        if num <= 10:
            district = num
        elif num in _MUNICIPAL:
            district, q = _MUNICIPAL[num]
            quarter = quarter or q
    out["district"] = district
    out["quarter"] = quarter
    return out


def in_prague(lat, lon) -> bool:
    return lat is not None and lon is not None and 49.94 <= lat <= 50.18 and 14.22 <= lon <= 14.71
