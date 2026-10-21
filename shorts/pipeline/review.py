#!/usr/bin/env python3
"""Daily channel review: stats snapshot + new comments + what to change next.

Writes work/reports/<date>.md and prints it. Needs the same YT_* credentials as upload.py
(plus the youtube.force-ssl scope for comments). Usage:
  python3 review.py --check            # only prove the connection: prints channel name + counts
  python3 review.py                    # snapshot stats, pull comments, write the report
  python3 review.py --reply VIDEO_ID COMMENT_ID "text"   # answer one comment
"""
import argparse
import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import requests

from upload import API, LOG, access_token

WORK = Path(__file__).resolve().parent.parent / "work"
REPORTS = WORK / "reports"
SEEN = WORK / "comments_seen.json"


def get(h, path, **params):
    r = requests.get(f"{API}/{path}", headers=h, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def channel(h):
    it = get(h, "channels", part="snippet,statistics", mine="true")["items"][0]
    return it["snippet"]["title"], it["snippet"].get("customUrl", ""), it["statistics"]


def uploaded_ids():
    if not LOG.exists():
        return []
    with open(LOG, encoding="utf-8") as f:
        return [r["video_id"] for r in csv.DictReader(f)]


def stats_history():
    """{video_id: [(at, views, likes, comments), ...]} from work/stats.csv"""
    hist = defaultdict(list)
    p = WORK / "stats.csv"
    if p.exists():
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                hist[r["video_id"]].append((r["at"], int(r["views"]), int(r["likes"]), int(r["comments"])))
    return hist


def comments(h, vid):
    out, token = [], None
    while True:
        try:
            d = get(h, "commentThreads", part="snippet", videoId=vid, maxResults=100, order="time",
                    textFormat="plainText", **({"pageToken": token} if token else {}))
        except requests.HTTPError as e:
            print(f"comments unavailable for {vid}: {e.response.status_code} (needs youtube.force-ssl scope?)",
                  file=sys.stderr)
            return out
        for t in d.get("items", []):
            c = t["snippet"]["topLevelComment"]["snippet"]
            out.append({"id": t["id"], "video": vid, "author": c["authorDisplayName"], "text": c["textDisplay"],
                        "likes": c.get("likeCount", 0), "at": c["publishedAt"], "replies": t["snippet"]["totalReplyCount"]})
        token = d.get("nextPageToken")
        if not token:
            return out


def reply(h, parent_id, text):
    r = requests.post(f"{API}/comments", headers=h, params={"part": "snippet"},
                      json={"snippet": {"parentId": parent_id, "textOriginal": text}}, timeout=60)
    r.raise_for_status()
    return r.json()["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--reply", nargs=3, metavar=("VIDEO_ID", "COMMENT_ID", "TEXT"))
    a = ap.parse_args()
    h = {"Authorization": f"Bearer {access_token()}"}
    name, handle, cst = channel(h)
    if a.check:
        print(f"channel: {name} {handle}  subscribers={cst.get('subscriberCount')} "
              f"views={cst.get('viewCount')} videos={cst.get('videoCount')}")
        return 0
    if a.reply:
        vid, cid, text = a.reply
        print("replied", reply(h, cid, text))
        return 0

    # 1) stats snapshot (same rows as stats.py)
    import stats  # noqa: E402  (reuses its CSV writers)
    sys.argv = ["stats.py"]
    stats.main()
    hist = stats_history()
    ids = uploaded_ids()
    today = dt.date.today().isoformat()
    lines = [f"# Channel review {today} — {name} {handle}",
             f"subscribers {cst.get('subscriberCount')} · total views {cst.get('viewCount')} · videos {cst.get('videoCount')}", ""]

    # 2) per-video: latest numbers, 24h delta, views per day since upload
    rows = []
    for vid in ids:
        hs = hist.get(vid, [])
        if not hs:
            continue
        at, v, l, c = hs[-1]
        prev = next((x for x in reversed(hs[:-1]) if (dt.datetime.fromisoformat(at) - dt.datetime.fromisoformat(x[0])).total_seconds() >= 20 * 3600), None)
        d24 = v - prev[1] if prev else None
        rows.append((vid, v, l, c, d24, hs[0][0][:10]))
    rows.sort(key=lambda r: -(r[4] if r[4] is not None else r[1]))
    lines.append("## Videos (sorted by last-24h views)")
    lines.append("| video | views | likes | comments | +24h | first seen |")
    lines.append("|---|---|---|---|---|---|")
    for vid, v, l, c, d24, first in rows:
        lines.append(f"| https://youtube.com/shorts/{vid} | {v} | {l} | {c} | {d24 if d24 is not None else '-'} | {first} |")
    lines.append("")

    # 3) new comments since last run
    seen = set(json.loads(SEEN.read_text())) if SEEN.exists() else set()
    new = []
    for vid in ids:
        for cm in comments(h, vid):
            if cm["id"] not in seen:
                new.append(cm); seen.add(cm["id"])
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(sorted(seen)))
    lines.append(f"## New comments ({len(new)})")
    for cm in sorted(new, key=lambda x: -x["likes"])[:40]:
        lines.append(f"- [{cm['video']}] {cm['author']} (+{cm['likes']}): {cm['text'][:200]}  `{cm['id']}`")
    lines.append("")

    # 4) signals to act on (simple rules; the session reading this decides the actual change)
    sig = []
    if rows:
        top, bottom = rows[0], rows[-1]
        if len(rows) >= 3 and top[1] >= 3 * max(1, bottom[1]):
            sig.append(f"Top video has {top[1]} views vs {bottom[1]} for the weakest: compare hooks/first 2s and topics, copy what the top one does.")
        flat = [r for r in rows if r[4] is not None and r[4] == 0 and r[1] < 500]
        if flat:
            sig.append(f"{len(flat)} video(s) gained 0 views in 24h: Shorts stopped testing them; change the hook text/thumbnail frame on the next episode rather than re-posting.")
    asks = [cm for cm in new if "?" in cm["text"]]
    if asks:
        sig.append(f"{len(asks)} new comment(s) ask a question: answer them today (replies within 24h lift the comment count the algorithm reads).")
    req = [cm for cm in new if any(k in cm["text"].lower() for k in ("try", "please", "should", "먹어", "해줘", "추천"))]
    if req:
        sig.append(f"{len(req)} comment(s) request a dish/place: put the most-liked request into the next shoot list.")
    lines.append("## Signals")
    lines += [f"- {s}" for s in sig] or ["- nothing stands out yet; keep the daily cadence."]
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"{today}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
