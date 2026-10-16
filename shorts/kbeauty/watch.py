#!/usr/bin/env python3
"""Hands-off mode: watch an inbox folder; every new sub-folder of footage becomes a finished episode.

  inbox/<anything>/clip1.mp4 clip2.mov ... [note.txt]   ->  work/kbeauty/<date>_<folder>/out/*.mp4
Folders are picked up once their files stop changing for `--settle` seconds. Finished folders move to inbox/_done,
failed ones to inbox/_failed with the error log. Sync a phone/Drive folder into the inbox with rclone or Drive for desktop.

usage: watch.py [--inbox DIR] [--interval 30] [--settle 90] [--publish] [--mock]
"""
import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".3gp"}


def ready(folder, settle):
    vids = [p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT]
    if not vids:
        return False
    newest = max(p.stat().st_mtime for p in folder.iterdir())
    return time.time() - newest > settle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inbox", default=str(config.INBOX))
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--settle", type=int, default=90)
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    inbox = Path(a.inbox); inbox.mkdir(parents=True, exist_ok=True)
    done, failed = inbox / "_done", inbox / "_failed"
    done.mkdir(exist_ok=True); failed.mkdir(exist_ok=True)
    print(f"watching {inbox} (drop a folder of clips + optional note.txt)")
    while True:
        for folder in sorted(p for p in inbox.iterdir() if p.is_dir() and not p.name.startswith("_")):
            if not ready(folder, a.settle):
                continue
            print(f"\n=== {folder.name}: starting")
            cmd = [sys.executable, str(HERE / "run.py"), str(folder)] + (["--publish"] if a.publish else []) + (["--mock"] if a.mock else [])
            log = folder / "run.log"
            with open(log, "w", encoding="utf-8") as lf:
                r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, text=True)
            dest = (done if r.returncode == 0 else failed) / folder.name
            if dest.exists():
                dest = dest.with_name(f"{folder.name}_{int(time.time())}")
            shutil.move(str(folder), str(dest))
            print(f"=== {folder.name}: {'done' if r.returncode == 0 else 'FAILED'} -> {dest}")
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
