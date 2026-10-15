#!/usr/bin/env python3
"""Upload a rendered video to YouTube with the Data API v3 (resumable upload).

Credentials come from environment variables (never from chat):
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN

usage: upload.py <video.mp4> --title "..." --description-file desc.txt
       [--tags a,b,c] [--privacy private|unlisted|public] [--publish-at 2026-10-16T10:00:00Z]
       [--thumbnail thumb.jpg] [--playlist PLAYLIST_ID] [--shorts]
Prints the video id on success and appends a row to uploads.csv.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
from pathlib import Path

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
API = "https://www.googleapis.com/youtube/v3"
LOG = Path(__file__).resolve().parent.parent / "work" / "uploads.csv"


def access_token():
    cid, sec, rt = (os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))
    if not all((cid, sec, rt)):
        sys.exit("missing YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN in environment")
    r = requests.post(TOKEN_URL, data={"client_id": cid, "client_secret": sec,
                                       "refresh_token": rt, "grant_type": "refresh_token"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def upload(path, meta, tok):
    size = os.path.getsize(path)
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
         "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"}
    r = requests.post(f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status", headers=h,
                      data=json.dumps(meta), timeout=60)
    r.raise_for_status()
    loc = r.headers["Location"]
    with open(path, "rb") as f:
        r2 = requests.put(loc, headers={"Authorization": f"Bearer {tok}", "Content-Type": "video/mp4",
                                        "Content-Length": str(size)}, data=f, timeout=3600)
    r2.raise_for_status()
    return r2.json()["id"]


def set_thumbnail(vid, thumb, tok):
    with open(thumb, "rb") as f:
        r = requests.post(f"{UPLOAD_URL.replace('/videos', '/thumbnails/set')}?videoId={vid}",
                          headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"},
                          data=f, timeout=120)
    if r.status_code >= 400:
        print(f"thumbnail not set ({r.status_code}): {r.text[:200]}", file=sys.stderr)


def add_to_playlist(vid, pl, tok):
    body = {"snippet": {"playlistId": pl, "resourceId": {"kind": "youtube#video", "videoId": vid}}}
    r = requests.post(f"{API}/playlistItems?part=snippet", headers={"Authorization": f"Bearer {tok}"},
                      json=body, timeout=60)
    if r.status_code >= 400:
        print(f"playlist add failed ({r.status_code}): {r.text[:200]}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--title", required=True)
    ap.add_argument("--description-file")
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--privacy", default="private")
    ap.add_argument("--publish-at")
    ap.add_argument("--thumbnail")
    ap.add_argument("--playlist")
    ap.add_argument("--shorts", action="store_true", help="append #Shorts to title/description")
    ap.add_argument("--category", default="22")  # People & Blogs; 26 = Howto & Style
    a = ap.parse_args()
    desc = Path(a.description_file).read_text(encoding="utf-8") if a.description_file else a.description
    title = a.title if len(a.title) <= 100 else a.title[:97] + "..."
    if a.shorts and "#shorts" not in (title + desc).lower():
        desc += "\n\n#Shorts"
    status = {"privacyStatus": a.privacy, "selfDeclaredMadeForKids": False}
    if a.publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = a.publish_at
    meta = {"snippet": {"title": title, "description": desc, "categoryId": a.category,
                        "tags": [t.strip() for t in a.tags.split(",") if t.strip()],
                        "defaultLanguage": "en", "defaultAudioLanguage": "ko"},
            "status": status}
    tok = access_token()
    vid = upload(a.video, meta, tok)
    if a.thumbnail and Path(a.thumbnail).exists():
        set_thumbnail(vid, a.thumbnail, tok)
    if a.playlist:
        add_to_playlist(vid, a.playlist, tok)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["uploaded_at", "video_id", "file", "title", "privacy", "publish_at"])
        w.writerow([dt.datetime.utcnow().isoformat(timespec="seconds"), vid, a.video, title,
                    status["privacyStatus"], a.publish_at or ""])
    print(vid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
