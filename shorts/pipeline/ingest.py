#!/usr/bin/env python3
"""Ingest raw clips from a folder: probe each, write clips.json, and build a
contact sheet (one frame per second, max 12 per clip) so the editor can look at
the footage without opening video files.

usage: ingest.py <raw_folder> [--out work/<episode_id>]
"""
import argparse
import json
import sys
from pathlib import Path

from common import WORK, ensure_dir, ffprobe, run

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".3gp"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    raw = Path(args.raw)
    out = ensure_dir(args.out or WORK / raw.name)
    sheets = ensure_dir(out / "frames")
    clips = []
    for p in sorted(raw.iterdir()):
        if p.suffix.lower() not in VIDEO_EXT:
            continue
        info = ffprobe(p)
        n = max(1, min(12, int(info["duration"])))
        step = max(info["duration"] / n, 0.5)
        sheet = sheets / f"{p.stem}.jpg"
        # one frame every `step` seconds, tiled 4 per row, thumbnails 270px wide
        run([
            "ffmpeg", "-y", "-v", "error", "-i", str(p),
            "-vf", f"fps=1/{step:.3f},scale=270:-2,tile=4x{(n + 3) // 4}",
            "-frames:v", "1", "-q:v", "4", str(sheet),
        ])
        info["frames_sheet"] = str(sheet)
        info["frame_step"] = round(step, 3)
        clips.append(info)
        print(f"{p.name}: {info['duration']:.1f}s {info['width']}x{info['height']} "
              f"{'portrait' if info['portrait'] else 'landscape'} audio={info['has_audio']}")
    (out / "clips.json").write_text(json.dumps(clips, indent=2, ensure_ascii=False))
    print(f"wrote {out / 'clips.json'} ({len(clips)} clips)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
