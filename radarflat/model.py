"""Normalized listing record and helpers shared by all sources."""
from __future__ import annotations

import re

from .geo import fold

# Every listing is a plain dict with these keys (None when unknown).
FIELDS = [
    "id", "source", "source_id", "url", "offer",          # offer: rent | sale
    "disp", "area", "price", "currency", "price_czk", "charges", "deposit",
    "district", "quarter", "street", "address", "lat", "lon",
    "floor", "floors_total", "lift", "balcony", "terrace", "loggia", "cellar", "parking", "garage",
    "furnished",                                            # yes | partly | no
    "condition", "construction", "ownership", "penb", "heating", "available_from", "pets",
    "private",                                              # True = no agency (bez RK)
    "title", "description", "images", "detail_done",
]

DISPOSITIONS = ["1+kk", "1+1", "2+kk", "2+1", "3+kk", "3+1", "4+kk", "4+1", "5+kk", "5+1", "6+", "atypical", "room"]

_DISP_RX = re.compile(r"(\d)\s*\+\s*(kk|1)", re.I)


def norm_disp(text: str | None) -> str | None:
    if not text:
        return None
    t = str(text).replace("DISP_", "").replace("_", "+").lower()
    m = _DISP_RX.search(t)
    if m:
        n, k = int(m.group(1)), m.group(2).lower()
        return "6+" if n >= 6 else f"{n}+{k}"
    f = fold(t)
    if "atyp" in f or "undefined" in f or "ostatni" in f:
        return "atypical"
    if "pokoj" in f or "room" in f:
        return "room"
    if re.search(r"\b6\b|6 a vic|6\+", f):
        return "6+"
    return None


def to_num(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(" ", " ").replace("‍", "").replace("&nbsp;", " ")
    m = re.search(r"\d[\d ]*(?:[.,]\d+)?", s)
    if not m:
        return None
    return float(m.group(0).replace(" ", "").replace(",", "."))


def to_int(v) -> int | None:
    n = to_num(v)
    return int(round(n)) if n is not None else None


def area_from_text(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"(?<![\d+])(\d{1,4}(?:[.,]\d+)?)\s*m\s*(?:²|2|<sup>2)", text.replace(" ", " "))
    return to_int(m.group(1)) if m else None


def furnished(text: str | None) -> str | None:
    f = fold(text or "")
    if not f:
        return None
    if "castec" in f or "partly" in f:
        return "partly"
    if f.startswith("ne") or "nevybav" in f or f in ("false", "unfurnished"):
        return "no"
    if "vybav" in f or f in ("true", "ano", "yes"):
        return "yes"
    return None


def blank(source: str, source_id: str, url: str, offer: str) -> dict:
    d = {k: None for k in FIELDS}
    d.update(id=f"{source}-{source_id}", source=source, source_id=str(source_id), url=url, offer=offer,
             images=[], detail_done=False)
    return d


def merge(base: dict, extra: dict) -> dict:
    """Fill base with non-empty values from extra (extra wins when it has a value)."""
    for k, v in extra.items():
        if v is None or v == [] or v == "":
            continue
        base[k] = v
    return base
