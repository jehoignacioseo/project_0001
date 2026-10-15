"""Shared helpers for the Shorts pipeline: ffprobe, paths, fonts."""
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path(os.environ.get("SHORTS_WORK", ROOT.parent / "work"))
FONT_DIR = Path("/usr/share/fonts")
FONT_BOLD = "NanumSquareRound Bold"       # fun rounded Korean display font
FONT_HEAVY = "Noto Sans CJK KR Bold"       # fallback with full CJK coverage
FONT_FILE_BOLD = "/usr/share/fonts/truetype/nanum/NanumSquareRoundB.ttf"
FONT_FILE_HEAVY = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_FILE_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"


def run(cmd, quiet=True):
    """Run a command list; raise with stderr on failure."""
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"command failed ({res.returncode}): {' '.join(map(str, cmd))}\n{res.stderr[-3000:]}")
    return res.stdout if quiet else res


def ffprobe(path):
    """Return dict with duration, width, height, rotation, fps, has_audio."""
    out = run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ])
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise ValueError(f"no video stream in {path}")
    rotation = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    if "tags" in v and "rotate" in v["tags"]:
        rotation = int(v["tags"]["rotate"])
    w, h = int(v["width"]), int(v["height"])
    if rotation % 180 != 0:
        w, h = h, w
    num, den = v.get("r_frame_rate", "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    return {
        "path": str(path),
        "duration": float(info["format"].get("duration", v.get("duration", 0)) or 0),
        "width": w,
        "height": h,
        "portrait": h >= w,
        "fps": round(fps, 3),
        "has_audio": a is not None,
    }


def ensure_dir(p):
    Path(p).mkdir(parents=True, exist_ok=True)
    return Path(p)


def clean_dir(p):
    p = Path(p)
    if p.exists():
        shutil.rmtree(p)
    return ensure_dir(p)


def ass_escape(text):
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def fmt_ass_time(sec):
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"
