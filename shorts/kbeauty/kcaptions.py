"""Karaoke captions (word-by-word highlight synced to the AI voice) as an ASS file rendered by libass.
Current word turns yellow; 2-4 words per line; pop-in on each line; sits in the lower-middle safe zone."""
from pathlib import Path

import config

FONTS_DIR = config.FONTS
MAX_CHARS = 26
MAX_WORDS = 4

HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: K,Pretendard,{fs},&H0000E5FF,&H00FFFFFF,&H00101010,&H96000000,-1,0,0,0,100,100,1,0,1,{ol},3,5,60,60,{mv},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _t(sec):
    sec = max(0.0, sec)
    return f"{int(sec // 3600)}:{int(sec % 3600 // 60):02d}:{sec % 60:05.2f}"


def _chunks(words):
    out, cur, n = [], [], 0
    for w in words:
        if cur and (n + 1 + len(w["w"]) > MAX_CHARS or len(cur) >= MAX_WORDS):
            out.append(cur); cur, n = [], 0
        cur.append(w); n += len(w["w"]) + 1
        if w["w"].endswith((".", "!", "?", ",")) and len(cur) >= 2:
            out.append(cur); cur, n = [], 0
    if cur:
        out.append(cur)
    return out


def build_ass(timed_lines, W=config.W, H=config.H, baseline_y=None):
    """timed_lines: [{words:[{w,s,e}]}] with absolute seconds. Returns ASS text."""
    fs = int(H * 0.043)
    by = int(H * 0.66) if baseline_y is None else int(baseline_y)
    hdr = HEADER.format(w=W, h=H, fs=fs, ol=int(fs * 0.11), mv=H - by)
    ev = []
    for ln in timed_lines:
        chunks = _chunks(ln["words"])
        for ci, ch in enumerate(chunks):
            s, e = ch[0]["s"], ch[-1]["e"] + 0.12
            if ci + 1 < len(chunks):                      # never let two lines sit on screen together
                e = min(e, chunks[ci + 1][0]["s"] - 0.01)
            e = max(e, s + 0.25)
            parts = []
            for i, w in enumerate(ch):
                nxt = ch[i + 1]["s"] if i + 1 < len(ch) else w["e"]
                dur_cs = max(1, int(round((nxt - w["s"]) * 100)))
                parts.append(f"{{\\kf{dur_cs}}}{_esc(w['w']).upper() if _emph(w['w']) else _esc(w['w'])}")
            text = "{\\an2\\fad(40,0)\\fscx92\\fscy92\\t(0,90,\\fscx100\\fscy100)}" + " ".join(parts)
            ev.append(f"Dialogue: 0,{_t(s)},{_t(e)},K,,0,0,0,,{text}")
    return hdr + "\n".join(ev) + "\n"


def _emph(w):
    return w.strip(".,!?").isdigit() or w.startswith(("₩", "$")) or w.strip(".,!?").upper() in ("FREE", "SOLD", "OUT", "STOP")


def _esc(t):
    return t.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def write_ass(timed_lines, path, baseline_y=None):
    Path(path).write_text(build_ass(timed_lines, baseline_y=baseline_y), encoding="utf-8")
    return str(path)
