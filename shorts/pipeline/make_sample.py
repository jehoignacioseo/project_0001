#!/usr/bin/env python3
"""Create synthetic phone-style test clips (portrait, with tone audio) so the
pipeline can be validated before real footage arrives."""
import sys
from pathlib import Path

from common import ensure_dir, run

COLORS = ["0x2b6cb0", "0xc05621", "0x2f855a", "0x805ad5", "0xb83280", "0x975a16"]
LABELS = ["entrance", "pick", "price tag", "cook", "first bite", "empty bowl"]


def main(dst="../work/sample_raw"):
    d = ensure_dir(Path(__file__).resolve().parent / dst)
    for i, (c, lbl) in enumerate(zip(COLORS, LABELS)):
        out = d / f"clip{i + 1}.mp4"
        run(["ffmpeg", "-y", "-v", "error",
             "-f", "lavfi", "-i", f"color=c={c}:s=1080x1920:d=8:r=30",
             "-f", "lavfi", "-i", f"sine=frequency={220 * (i + 1)}:duration=8",
             "-vf", (f"drawtext=text='{lbl} %{{pts\\:hms}}':fontsize=90:fontcolor=white:"
                     f"x=(w-text_w)/2:y=(h-text_h)/2:fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf,"
                     f"drawbox=x=200:y=1200:w=680:h=300:color=white@0.3:t=fill"),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-shortest", str(out)])
        print(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
