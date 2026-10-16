#!/usr/bin/env python3
"""Synthetic K-beauty test footage (portrait phone clips with labels + ambient noise) so the whole
pipeline can be exercised offline before real footage arrives.   usage: make_sample.py [dst]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from common import ensure_dir, run  # noqa: E402

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SHOTS = [("shelf 올리브영", "0x2b3a67", 9), ("closeup Anua pad", "0xc06c84", 8), ("price ₩19,900", "0x355c7d", 7),
         ("texture", "0x6c5b7b", 8), ("apply", "0xf67280", 8), ("rank #1 sticker", "0x99b898", 7)]


def main(dst="../work/kbeauty/sample_raw"):
    d = ensure_dir(Path(__file__).resolve().parent / dst)
    for i, (lbl, col, dur) in enumerate(SHOTS):
        out = d / f"clip{i + 1}.mp4"
        # two "scenes" per clip (colour shifts at the midpoint) so scene detection has something to find
        vf = (f"drawtext=text='{lbl}':fontsize=80:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2:fontfile={FONT},"
              f"drawbox=x=240:y=1250:w=600:h=320:color=white@0.25:t=fill,"
              f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.35:t=fill:enable='gte(t,{dur / 2:.1f})'")
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={col}:s=1080x1920:d={dur}:r=30",
             "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude=0.05:duration={dur}",
             "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest", str(out)])
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
