import argparse
import json
import logging

from . import pipeline


def main():
    ap = argparse.ArgumentParser(prog="radarflat")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crawl", help="crawl the sources and publish site/data")
    c.add_argument("--sources", nargs="*", help="only these sources")
    c.add_argument("--details", type=int, help="detail pages per source this run (overrides config)")
    sub.add_parser("publish", help="rebuild site/data from state/ without crawling")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if a.cmd == "crawl":
        rep = pipeline.crawl(a.sources, a.details)
        print(json.dumps(rep, indent=1, ensure_ascii=False))
    elif a.cmd == "publish":
        pipeline.publish(pipeline.load_state())


if __name__ == "__main__":
    main()
