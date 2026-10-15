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

STYLES = {
    #  name     size  fill             outline        heavy  ypos(portrait, landscape as fraction of H from top)
    "pop":     dict(size=86,  fill=(255, 255, 255), outline=(20, 20, 20), ol=7, heavy=False, y=(0.70, 0.78)),
    "shout":   dict(size=104, fill=(255, 229, 0),   outline=(20, 20, 20), ol=9, heavy=False, y=(0.68, 0.76)),
    "whisper": dict(size=60,  fill=(225, 225, 225), outline=(20, 20, 20), ol=4, heavy=True,  y=(0.70, 0.78)),
    "price":   dict(size=82,  fill=(100, 255, 100), outline=(20, 60, 20), ol=7, heavy=False, y=(0.64, 0.72)),
    "note":    dict(size=48,  fill=(255, 255, 255), outline=(20, 20, 20), ol=4, heavy=True,  y=(0.12, 0.08)),
}


def _font(size, heavy):
    try:
        return ImageFont.truetype(FONT_FILE_HEAVY if heavy else FONT_FILE_BOLD, size)
    except OSError:
        return ImageFont.truetype(FONT_FILE_HEAVY, size)


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


def _measure_line(d, line, font, size):
    w = 0
    for is_e, chunk in _runs(line):
        if is_e:
            im = _emoji_img(chunk, size)
            w += (im.width if im else 0) + int(size * 0.1)
        else:
            l, t, r, b = d.textbbox((0, 0), chunk, font=font)
            w += r - l
    return w


def _wrap(d, text, font, size, max_w):
    words = text.split(" ")
    lines, cur = [], ""
    for wd in words:
        cand = (cur + " " + wd).strip()
        if cur and _measure_line(d, cand, font, size) > max_w:
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
    ol = int(st["ol"] * base * scale_factor)
    font = _font(size, st["heavy"])
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    max_w = int(W * 0.86)
    lines = _wrap(probe, text, font, size, max_w)
    line_h = int(size * 1.25)
    img_w = min(W, max(_measure_line(probe, ln, font, size) for ln in lines) + ol * 2 + 20)
    img_h = line_h * len(lines) + ol * 2 + 20
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = ol + 10
    for ln in lines:
        lw = _measure_line(probe, ln, font, size)
        x = (img_w - lw) // 2
        for is_e, chunk in _runs(ln):
            if is_e:
                im = _emoji_img(chunk, size)
                if im:
                    img.alpha_composite(im, (x, y + (line_h - im.height) // 2 - int(size * 0.05)))
                    x += im.width + int(size * 0.1)
            else:
                # shadow then stroked text
                d.text((x + ol // 2, y + ol // 2 + 3), chunk, font=font, fill=(0, 0, 0, 120),
                       stroke_width=ol, stroke_fill=(0, 0, 0, 120))
                d.text((x, y), chunk, font=font, fill=st["fill"] + (255,),
                       stroke_width=ol, stroke_fill=st["outline"] + (255,))
                l, t, r, b = d.textbbox((0, 0), chunk, font=font)
                x += r - l
        y += line_h
    img.save(path)
    ypos = int(H * st["y"][0 if portrait else 1]) - img_h // 2
    return path, img_w, img_h, ypos
