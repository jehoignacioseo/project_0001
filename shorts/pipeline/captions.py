"""Build an ASS subtitle file with playful caption styles.

Styles (use in episode.json caption "style"):
  pop     : big white rounded font, pops in (default)
  shout   : yellow, bigger, bounces
  whisper : smaller grey, fades
  price   : green money style
  note    : small white at top (context: place, time)
"""
from common import FONT_BOLD, FONT_HEAVY, ass_escape, fmt_ass_time

# PlayRes is the canvas; positions scale with the video.
HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: pop,{fb},{fs_pop},&H00FFFFFF,&H00FFFFFF,&H00141414,&H80000000,-1,0,0,0,100,100,0,0,1,{ol},3,2,60,60,{mv_pop},1
Style: shout,{fb},{fs_shout},&H0000E5FF,&H00FFFFFF,&H00141414,&H80000000,-1,0,0,0,100,100,0,0,1,{ol2},4,5,60,60,{mv_shout},1
Style: whisper,{fh},{fs_whisper},&H00DDDDDD,&H00FFFFFF,&H00141414,&H80000000,-1,-1,0,0,100,100,0,0,1,{ol_s},2,2,80,80,{mv_pop},1
Style: price,{fb},{fs_price},&H0064FF64,&H00FFFFFF,&H00143C14,&H80000000,-1,0,0,0,100,100,0,0,1,{ol},3,2,60,60,{mv_price},1
Style: note,{fh},{fs_note},&H00FFFFFF,&H00FFFFFF,&H00141414,&H80000000,-1,0,0,0,100,100,0,0,1,{ol_s},2,8,60,60,{mv_note},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

ANIM = {
    # pop in from 60% then settle, with quick fade
    "pop": r"{\fad(80,120)\fscx60\fscy60\t(0,140,\fscx108\fscy108)\t(140,220,\fscx100\fscy100)}",
    # bounce: overshoot bigger
    "shout": r"{\fad(60,120)\fscx40\fscy40\t(0,120,\fscx120\fscy120)\t(120,260,\fscx100\fscy100)}",
    "whisper": r"{\fad(250,250)}",
    "price": r"{\fad(80,120)\fscx70\fscy70\t(0,160,\fscx105\fscy105)\t(160,240,\fscx100\fscy100)}",
    "note": r"{\fad(150,150)}",
}


def build_ass(captions, w, h, portrait=True):
    """captions: list of dict(start, end, text, style) with absolute seconds."""
    base = h if portrait else w
    scale = base / 1920.0
    hdr = HEADER.format(
        w=w, h=h, fb=FONT_BOLD, fh=FONT_HEAVY,
        fs_pop=int(86 * scale), fs_shout=int(104 * scale), fs_whisper=int(62 * scale),
        fs_price=int(82 * scale), fs_note=int(50 * scale),
        ol=int(7 * scale), ol2=int(9 * scale), ol_s=int(4 * scale),
        mv_pop=int((430 if portrait else 140) * scale),
        mv_shout=int((480 if portrait else 170) * scale),
        mv_price=int((560 if portrait else 230) * scale),
        mv_note=int((230 if portrait else 70) * scale),
    )
    lines = []
    for c in captions:
        style = c.get("style", "pop")
        if style not in ANIM:
            style = "pop"
        text = ANIM[style] + ass_escape(c["text"])
        lines.append(
            f"Dialogue: 0,{fmt_ass_time(c['start'])},{fmt_ass_time(c['end'])},{style},,0,0,0,,{text}"
        )
    return hdr + "\n".join(lines) + "\n"
