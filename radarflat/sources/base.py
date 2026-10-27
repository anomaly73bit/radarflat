from __future__ import annotations

import logging
from typing import Iterator

from ..http import PoliteClient

log = logging.getLogger("radarflat.sources")

OFFERS = ("rent", "sale")


class Source:
    name = "base"
    label = "Base"
    # Fields the list pages already give; detail pages add the rest.
    needs_detail = True

    def __init__(self, client: PoliteClient, cfg: dict):
        self.client = client
        self.cfg = cfg

    def listings(self, offer: str) -> Iterator[dict]:
        raise NotImplementedError

    def detail(self, listing: dict) -> dict | None:
        """Return extra fields, {} when nothing could be parsed, or None when the listing is gone."""
        return {}

    def max_pages(self) -> int:
        return int(self.cfg.get("max_pages", 400))
