#!/usr/bin/env python3
"""Stage 7 - publish the rendered videos.

  shorts : YouTube Data API (reuses pipeline/upload.py; env YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN)
  reels  : Instagram Graph API (env IG_USER_ID, IG_ACCESS_TOKEN, and a public URL for the mp4: --public-base-url or KB_PUBLIC_BASE_URL)
  tiktok : Content Posting API v2, "upload to inbox" (env TIKTOK_ACCESS_TOKEN). The clip lands in the user's TikTok drafts with the
           caption prefilled; direct posting needs an audited app. Alternatively publish through the Higgsfield TikTok connector.

Without credentials the stage writes out/publish_manifest.json (what would be posted, with captions) and exits 0, so the rest of the
pipeline is never blocked.    usage: publish.py work/<id> [--platforms tiktok,reels,shorts] [--privacy private|public] [--dry-run]
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import config

PIPELINE = config.PIPELINE


def publish_shorts(meta, cover, privacy, publish_at=None):
    env = {k: os.environ.get(k) for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN")}
    if not all(env.values()):
        return {"status": "skipped", "reason": "YT_* credentials missing"}
    desc = Path(meta["file"]).with_suffix(".desc.txt")
    desc.write_text(meta["description"], encoding="utf-8")
    cmd = [sys.executable, str(PIPELINE / "upload.py"), meta["file"], "--title", meta["title"], "--description-file", str(desc),
           "--tags", ",".join(meta["tags"]), "--privacy", privacy, "--shorts", "--category", "26"]
    if cover and Path(cover).exists():
        cmd += ["--thumbnail", cover]
    if publish_at:
        cmd += ["--publish-at", publish_at]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"status": "error", "detail": r.stderr[-500:]}
    return {"status": "uploaded", "video_id": r.stdout.strip().splitlines()[-1]}


def publish_reels(meta, public_url):
    import requests
    uid, tok = os.environ.get("IG_USER_ID"), os.environ.get("IG_ACCESS_TOKEN")
    if not (uid and tok and public_url):
        return {"status": "skipped", "reason": "IG_USER_ID / IG_ACCESS_TOKEN / public URL missing"}
    api = "https://graph.facebook.com/v21.0"
    caption = meta["caption"] + "\n\n" + " ".join(f"#{h}" for h in meta["hashtags"])
    r = requests.post(f"{api}/{uid}/media", data={"media_type": "REELS", "video_url": public_url, "caption": caption,
                                                  "share_to_feed": "true", "access_token": tok}, timeout=60)
    r.raise_for_status()
    cid = r.json()["id"]
    for _ in range(40):                                   # wait for Instagram to fetch + transcode
        st = requests.get(f"{api}/{cid}", params={"fields": "status_code", "access_token": tok}, timeout=30).json()
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            return {"status": "error", "detail": st}
        time.sleep(5)
    p = requests.post(f"{api}/{uid}/media_publish", data={"creation_id": cid, "access_token": tok}, timeout=60)
    p.raise_for_status()
    return {"status": "published", "media_id": p.json()["id"]}


def publish_tiktok(meta):
    import requests
    tok = os.environ.get("TIKTOK_ACCESS_TOKEN")
    if not tok:
        return {"status": "skipped", "reason": "TIKTOK_ACCESS_TOKEN missing"}
    path = Path(meta["file"]); size = path.stat().st_size
    chunk = min(size, 64 * 1024 * 1024)
    init = requests.post("https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
                         headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"},
                         json={"source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk,
                                               "total_chunk_count": -(-size // chunk)}}, timeout=60)
    init.raise_for_status()
    d = init.json()["data"]
    with open(path, "rb") as f:
        for i in range(-(-size // chunk)):
            data = f.read(chunk); start = i * chunk
            r = requests.put(d["upload_url"], data=data, timeout=600,
                             headers={"Content-Type": "video/mp4", "Content-Range": f"bytes {start}-{start + len(data) - 1}/{size}"})
            r.raise_for_status()
    caption = meta["caption"] + " " + " ".join(f"#{h}" for h in meta["hashtags"])
    (path.parent / "tiktok_caption.txt").write_text(caption, encoding="utf-8")
    return {"status": "in_inbox", "publish_id": d["publish_id"], "note": "open TikTok > inbox to finish; caption saved next to the mp4"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--platforms", default=",".join(config.PLATFORMS))
    ap.add_argument("--privacy", default="private")
    ap.add_argument("--publish-at", default=None, help="RFC3339 UTC, YouTube scheduled publish")
    ap.add_argument("--public-base-url", default=os.environ.get("KB_PUBLIC_BASE_URL", ""))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    work = Path(a.work)
    out = work / "out"
    tl = json.loads((out / "timeline.json").read_text(encoding="utf-8"))
    qa = json.loads((work / "qa.json").read_text(encoding="utf-8")) if (work / "qa.json").exists() else {"ok": True}
    if not qa.get("ok"):
        sys.exit("QA failed; not publishing. See qa.json")
    results = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "platforms": {}}
    for pf in a.platforms.split(","):
        meta = json.loads((out / f"meta_{pf}.json").read_text(encoding="utf-8"))
        if a.dry_run:
            results["platforms"][pf] = {"status": "dry-run", "meta": meta}; continue
        try:
            if pf == "shorts":
                results["platforms"][pf] = publish_shorts(meta, tl.get("cover"), a.privacy, a.publish_at)
            elif pf == "reels":
                url = f"{a.public_base_url.rstrip('/')}/{Path(meta['file']).name}" if a.public_base_url else ""
                results["platforms"][pf] = publish_reels(meta, url)
            elif pf == "tiktok":
                results["platforms"][pf] = publish_tiktok(meta)
        except Exception as e:  # one platform failing must not block the others
            results["platforms"][pf] = {"status": "error", "detail": str(e)[:500]}
        print(f"{pf}: {results['platforms'][pf].get('status')} {results['platforms'][pf].get('reason', '')}")
    (out / "publish_manifest.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
