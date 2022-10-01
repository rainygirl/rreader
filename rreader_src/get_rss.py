import datetime
import feedparser
import json
import os
import shutil
import sys
import time

from .common import p, FEEDS_FILE_NAME
from .config import TIMEZONE


def do(target_category=None, log=False):
    def get_feed_from_rss(category, urls, show_author=False, log=False):

        rslt = {}

        for source, url in urls.items():
            try:
                if log:
                    sys.stdout.write(f"- {url}")

                d = feedparser.parse(url)

                if log:
                    sys.stdout.write(" - Done\n")

            except:
                sys.exit(" - Failed\n" if log else 0)

            for feed in d.entries:

                try:
                    at = (
                        datetime.datetime(*feed.published_parsed[:6])
                        .replace(tzinfo=datetime.timezone.utc)
                        .astimezone(TIMEZONE)
                    )
                except:
                    continue

                pubDate = at.strftime(
                    "%H:%M" if at.date() == datetime.date.today() else "%b %d, %H:%M"
                )

                ts = int(time.mktime(feed.published_parsed))

                entries = {
                    "id": ts,
                    "sourceName": source if not show_author else feed.author,
                    "pubDate": pubDate,
                    "timestamp": ts,
                    "url": feed.link,
                    "title": feed.title,
                }

                rslt[entries["id"]] = entries

        rslt = [val for key, val in sorted(rslt.items(), reverse=True)]

        rslt = {"entries": rslt, "created_at": int(time.time())}

        with open(
            os.path.join(p["path_data"], f"rss_{category}.json"), "w", encoding="utf-8"
        ) as f:
            f.write(json.dumps(rslt, ensure_ascii=False))

        return rslt

    if not os.path.isfile(FEEDS_FILE_NAME):
        shutil.copyfile(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "feeds.json"),
            FEEDS_FILE_NAME,
        )

    with open(FEEDS_FILE_NAME, "r") as fp:
        RSS = json.load(fp)

    if target_category:
        return get_feed_from_rss(
            target_category,
            RSS[target_category]["feeds"],
            show_author=RSS[target_category].get("show_author", False),
            log=log,
        )

    for category, d in RSS.items():
        get_feed_from_rss(
            category, d["feeds"], show_author=d.get("show_author", False), log=log
        )


if __name__ == "__main__":
    do()
