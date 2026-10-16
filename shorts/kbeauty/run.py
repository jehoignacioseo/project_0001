#!/usr/bin/env python3
"""One command: raw footage folder -> finished TikTok / Reels / Shorts videos + metadata (+ optional publish).

usage: run.py <raw_folder> [--note "..."] [--id slug] [--lang en] [--mock] [--fast]
              [--from analyze|research|script|tts|render|qa] [--publish] [--platforms tiktok,reels,shorts]

Stages are resumable: each writes its JSON into work/<id>/ and `--from` restarts at that stage.
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import config

HERE = Path(__file__).resolve().parent
STAGES = ["analyze", "research", "script", "tts", "render", "qa"]


def sh(args):
    print(f"\n$ {' '.join(map(str, args))}", flush=True)
    r = subprocess.run([sys.executable, *map(str, args)], cwd=HERE)
    if r.returncode != 0:
        raise SystemExit(f"stage failed: {args[0]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--note", default="", help="filmer's one-line note (becomes the editor's brief)")
    ap.add_argument("--id", default=None)
    ap.add_argument("--lang", default=config.LANG)
    ap.add_argument("--mock", action="store_true", help="no API calls: canned analysis/script and a silent voice")
    ap.add_argument("--fast", action="store_true", help="faster, lower-quality encode for previews")
    ap.add_argument("--from", dest="start", default="analyze", choices=STAGES)
    ap.add_argument("--platforms", default=",".join(config.PLATFORMS))
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--privacy", default="private")
    a = ap.parse_args()
    raw = Path(a.raw).resolve()
    if not raw.is_dir():
        sys.exit(f"not a folder: {raw}")
    note = a.note
    if not note and (raw / "note.txt").exists():
        note = (raw / "note.txt").read_text(encoding="utf-8").strip()
    eid = a.id or f"{dt.date.today():%Y%m%d}_{raw.name}"
    work = config.WORK / eid
    work.mkdir(parents=True, exist_ok=True)
    (work / "run.json").write_text(json.dumps({"raw": str(raw), "note": note, "id": eid, "lang": a.lang, "mock": a.mock,
                                               "started": dt.datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False, indent=1))
    mock = ["--mock"] if a.mock else []
    todo = STAGES[STAGES.index(a.start):]
    if "analyze" in todo:
        sh(["analyze.py", raw, "--out", work, "--note", note, *mock])
    if "research" in todo:
        sh(["research.py", work, *mock])
    if "script" in todo:
        sh(["script.py", work, "--lang", a.lang, *mock])
    if "tts" in todo:
        sh(["tts.py", work, *mock])
    if "render" in todo:
        sh(["render.py", work, "--platforms", a.platforms, *(["--fast"] if a.fast else [])])
    if "qa" in todo:
        sh(["qa.py", work])
    if a.publish:
        sh(["publish.py", work, "--platforms", a.platforms, "--privacy", a.privacy])
    print(f"\ndone: {work / 'out'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
