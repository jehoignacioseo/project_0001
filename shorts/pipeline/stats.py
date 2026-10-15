#!/usr/bin/env python3
"""Pull view/like/comment counts for every uploaded video and append a daily
snapshot to work/stats.csv, plus channel subscriber count to work/channel.csv.
Uses the same env credentials as upload.py. usage: stats.py [--ids id1,id2]"""
import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

import requests

from upload import API, LOG, access_token

WORK = Path(__file__).resolve().parent.parent / "work"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    tok = access_token()
    h = {"Authorization": f"Bearer {tok}"}
    ids = [i for i in a.ids.split(",") if i]
    if not ids and LOG.exists():
        with open(LOG, encoding="utf-8") as f:
            ids = [r["video_id"] for r in csv.DictReader(f)]
    now = dt.datetime.utcnow().isoformat(timespec="seconds")
    rows = []
    for i in range(0, len(ids), 50):
        r = requests.get(f"{API}/videos", headers=h, timeout=60,
                         params={"part": "statistics,snippet,status", "id": ",".join(ids[i:i + 50])})
        r.raise_for_status()
        for it in r.json().get("items", []):
            st = it["statistics"]
            rows.append([now, it["id"], it["snippet"]["title"][:60], it["status"]["privacyStatus"],
                         st.get("viewCount", 0), st.get("likeCount", 0), st.get("commentCount", 0)])
    p = WORK / "stats.csv"
    new = not p.exists()
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["at", "video_id", "title", "privacy", "views", "likes", "comments"])
        w.writerows(rows)
    r = requests.get(f"{API}/channels", headers=h, params={"part": "statistics", "mine": "true"}, timeout=60)
    r.raise_for_status()
    ch = r.json()["items"][0]["statistics"]
    cp = WORK / "channel.csv"
    new = not cp.exists()
    with open(cp, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["at", "subscribers", "views", "videos"])
        w.writerow([now, ch.get("subscriberCount"), ch.get("viewCount"), ch.get("videoCount")])
    for row in rows:
        print("\t".join(map(str, row)))
    print(f"subscribers={ch.get('subscriberCount')} total_views={ch.get('viewCount')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
