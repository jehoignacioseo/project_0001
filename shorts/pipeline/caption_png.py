"""Render a caption as a transparent PNG with PIL: Korean/English text with a
thick outline + real color emoji (Noto Color Emoji). Used instead of ASS so
emoji stay in color. Returns (png_path, width, height)."""
import re
from PIL import Image, ImageDraw, ImageFont

from common import FONT_FILE_BOLD, FONT_FILE_HEAVY, FONT_FILE_EMOJI

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D\U000020E3\U0001F900-\U0001F9FF\U00002300-\U000023FF]+"
)

from pathlib import Path
FONTS = Path(__file__).resolve().parent / "fonts"
# font roster: (hangul file, latin/other file). Pretendard covers both scripts.
_PB = str(FONTS / "Pretendard-Black.otf")
# (hangul, latin, symbol) files; subset web fonts lack ₩ and friends, so symbols fall back to Pretendard
F_BLACKHAN = (str(FONTS / "BlackHanSans-korean.woff"), str(FONTS / "BlackHanSans-latin.woff"), _PB)
F_PRETENDARD = (_PB, _PB, _PB)
F_PRETENDARD_XB = (str(FONTS / "Pretendard-ExtraBold.otf"),) * 3
F_JUA = (str(FONTS / "Jua-korean.woff"), str(FONTS / "Jua-latin.woff"), _PB)

STYLES = {
    #  name     size  fill             outline        font          outline px  ypos(portrait, landscape) fraction of H
    "pop":     dict(size=88,  fill=(255, 255, 255), outline=(10, 10, 10), font=F_PRETENDARD,    ol=10, y=(0.70, 0.78)),
    "shout":   dict(size=108, fill=(255, 229, 0),   outline=(10, 10, 10), font=F_BLACKHAN,      ol=12, y=(0.68, 0.76)),
    "whisper": dict(size=72,  fill=(255, 255, 255), outline=(10, 10, 10), font=F_JUA,           ol=8,  y=(0.70, 0.78)),
    "price":   dict(size=88,  fill=(120, 255, 120), outline=(10, 40, 10), font=F_PRETENDARD,    ol=10, y=(0.64, 0.72)),
    "note":    dict(size=50,  fill=(255, 255, 255), outline=(10, 10, 10), font=F_PRETENDARD_XB, ol=6,  y=(0.12, 0.08)),
}

HANGUL_RE = re.compile("[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7AF]")
LATIN_RE = re.compile(r"[A-Za-z0-9 .,!?'\"()\-:;/%&+#*=…]")
_FONT_CACHE = {}


def _font_file(file, size):
    key = (file, size)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = ImageFont.truetype(file, size)
        except OSError:
            _FONT_CACHE[key] = ImageFont.truetype(FONT_FILE_HEAVY, size)
    return _FONT_CACHE[key]


def _fonts(spec, size):
    """Return (hangul_font, latin_font, symbol_font) for a style's font spec."""
    return tuple(_font_file(f, size) for f in spec)


def _cls(ch):
    if HANGUL_RE.match(ch):
        return 0
    if LATIN_RE.match(ch):
        return 1
    return 2


def _script_runs(chunk):
    """Split a non-emoji chunk into [(font_index, text)] runs."""
    out, cur, cur_c = [], "", None
    for ch in chunk:
        c = _cls(ch)
        if cur and c != cur_c:
            out.append((cur_c, cur)); cur = ""
        cur += ch; cur_c = c
    if cur:
        out.append((cur_c, cur))
    return out


_EMOJI_FONT = None


def _emoji_font():
    global _EMOJI_FONT
    if _EMOJI_FONT is None:
        _EMOJI_FONT = ImageFont.truetype(FONT_FILE_EMOJI, 109)
    return _EMOJI_FONT


def _runs(text):
    """Split into [(is_emoji, chunk)]."""
    out, pos = [], 0
    for m in EMOJI_RE.finditer(text):
        if m.start() > pos:
            out.append((False, text[pos:m.start()]))
        out.append((True, m.group()))
        pos = m.end()
    if pos < len(text):
        out.append((False, text[pos:]))
    return out


def _emoji_img(chunk, size):
    """Render emoji chunk with color font at native 109px, then scale to `size`."""
    ef = _emoji_font()
    tmp = Image.new("RGBA", (109 * max(1, len(chunk)) + 20, 140), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    d.text((5, 5), chunk, font=ef, embedded_color=True)
    bbox = tmp.getbbox()
    if not bbox:
        return None
    tmp = tmp.crop(bbox)
    scale = size / 109.0 * 1.05
    return tmp.resize((max(1, int(tmp.width * scale)), max(1, int(tmp.height * scale))), Image.LANCZOS)


def _measure_line(d, line, fonts, size):
    w = 0
    for is_e, chunk in _runs(line):
        if is_e:
            im = _emoji_img(chunk, size)
            w += (im.width if im else 0) + int(size * 0.1)
        else:
            for ci, part in _script_runs(chunk):
                l, t, r, b = d.textbbox((0, 0), part, font=fonts[ci])
                w += r - l
    return w


def _wrap(d, text, fonts, size, max_w):
    words = text.split(" ")
    lines, cur = [], ""
    for wd in words:
        cand = (cur + " " + wd).strip()
        if cur and _measure_line(d, cand, fonts, size) > max_w:
            lines.append(cur)
            cur = wd
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def render_caption(path, text, style, W, H, portrait, scale_factor=1.0):
    st = STYLES.get(style, STYLES["pop"])
    base = (H if portrait else W) / 1920.0
    size = int(st["size"] * base * scale_factor)
    ol = max(2, int(st["ol"] * base * scale_factor))
    fonts = _fonts(st["font"], size)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    max_w = int(W * 0.88)
    lines = _wrap(probe, text, fonts, size, max_w)
    line_h = int(size * 1.22)
    img_w = min(W, max(_measure_line(probe, ln, fonts, size) for ln in lines) + ol * 2 + 24)
    img_h = line_h * len(lines) + ol * 2 + 24
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = ol + 12
    for ln in lines:
        lw = _measure_line(probe, ln, fonts, size)
        x = (img_w - lw) // 2
        for is_e, chunk in _runs(ln):
            if is_e:
                im = _emoji_img(chunk, size)
                if im:
                    img.alpha_composite(im, (x, y + (line_h - im.height) // 2 - int(size * 0.05)))
                    x += im.width + int(size * 0.1)
                continue
            for ci, part in _script_runs(chunk):
                f = fonts[ci]
                d.text((x + ol // 2, y + ol // 2 + 4), part, font=f, fill=(0, 0, 0, 110),
                       stroke_width=ol, stroke_fill=(0, 0, 0, 110))
                d.text((x, y), part, font=f, fill=st["fill"] + (255,),
                       stroke_width=ol, stroke_fill=st["outline"] + (255,))
                l, t, r, b = d.textbbox((0, 0), part, font=f)
                x += r - l
        y += line_h
    img.save(path)
    ypos = int(H * st["y"][0 if portrait else 1]) - img_h // 2
    return path, img_w, img_h, ypos
