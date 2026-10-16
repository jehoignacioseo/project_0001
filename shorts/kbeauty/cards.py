"""PNG overlays for the K-beauty renderer: hook title band, info cards (price / product / ingredients /
fact / verdict), cover image. Built on the pipeline's caption_png font + emoji helpers."""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from caption_png import F_BLACKHAN, F_PRETENDARD, F_PRETENDARD_XB, _fonts  # noqa: E402
from overlays import _mixed_text_fonts, _mixed_w_fonts  # noqa: E402

import config  # noqa: E402

ACCENT = {"price": (120, 255, 120), "product": (255, 180, 210), "ingredients": (120, 240, 220),
          "fact": (255, 229, 0), "verdict": (255, 255, 255)}


def _fit(d, text, spec, size, max_w, floor=28):
    while size > floor and _mixed_w_fonts(d, text, _fonts(spec, size), size) > max_w:
        size -= 2
    return size


def title_band(path, lines, W=config.W, H=config.H):
    """Hook band: rounded translucent box near the top safe zone, 1-2 lines, first line yellow."""
    pad, maxw = 40, int(W * 0.90)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    sizes = [_fit(probe, t, F_BLACKHAN, 128, maxw - pad * 2) for t in lines]
    h = sum(int(s * 1.18) for s in sizes) + pad * 2
    img = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bw = min(maxw, max(_mixed_w_fonts(probe, t, _fonts(F_BLACKHAN, s), s) for t, s in zip(lines, sizes)) + pad * 2)
    x0 = (W - bw) // 2
    d.rounded_rectangle((x0, 0, x0 + bw, h - 1), radius=34, fill=(10, 10, 10, 200))
    y = pad
    for i, (t, s) in enumerate(zip(lines, sizes)):
        fs = _fonts(F_BLACKHAN, s)
        w = _mixed_w_fonts(d, t, fs, s)
        _mixed_text_fonts(img, d, ((W - w) // 2, y), t, fs, s, (255, 229, 0, 255) if i == 0 else (255, 255, 255, 255))
        y += int(s * 1.18)
    img.save(path)
    return path, img.height


def info_card(path, kind, title, lines, W=config.W):
    """Rounded card, title in the accent colour, 1-4 lines. Returns (path, height)."""
    acc = ACCENT.get(kind, (255, 229, 0))
    cw, pad = int(W * 0.86), 48
    t_size, l_size = 54, 70
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    l_sizes = [_fit(probe, t, F_PRETENDARD, l_size, cw - pad * 2, 30) for t in lines]
    h = pad + int(t_size * 1.3) + sum(int(s * 1.35) for s in l_sizes) + pad
    img = Image.new("RGBA", (cw, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, cw - 1, h - 1), radius=40, fill=(12, 12, 12, 210), outline=acc + (255,), width=5)
    d.rounded_rectangle((0, 0, 14, h - 1), radius=7, fill=acc + (255,))
    y = pad - 6
    ft = _fonts(F_PRETENDARD_XB, t_size)
    _mixed_text_fonts(img, d, (pad, y), title.upper(), ft, t_size, acc + (255,))
    y += int(t_size * 1.3)
    for t, s in zip(lines, l_sizes):
        fl = _fonts(F_PRETENDARD, s)
        _mixed_text_fonts(img, d, (pad, y), t, fl, s, (255, 255, 255, 255))
        y += int(s * 1.35)
    img.save(path)
    return path, h


def cta_card(path, text, W=config.W):
    """Bottom CTA pill ('Comment your skin type 👇'), shown over the last cut."""
    size = 54
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    size = _fit(probe, text, F_PRETENDARD, size, int(W * 0.84))
    fs = _fonts(F_PRETENDARD, size)
    w = _mixed_w_fonts(probe, text, fs, size) + 80
    h = int(size * 1.9)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(255, 229, 0, 235))
    _mixed_text_fonts(img, d, (40, (h - int(size * 1.2)) // 2), text, fs, size, (15, 15, 15, 255))
    img.save(path)
    return path, w, h


def cover(path, frame_jpg, lines, W=config.W, H=config.H):
    """Thumbnail: the hook frame, darkened, with 1-2 huge lines in the centre."""
    img = Image.open(frame_jpg).convert("RGB")
    img = img.resize((W, int(img.height * W / img.width)))
    if img.height < H:
        bg = img.resize((W, H)).filter(ImageFilter.GaussianBlur(30))
        bg.paste(img, (0, (H - img.height) // 2)); img = bg
    else:
        img = img.crop((0, (img.height - H) // 2, W, (img.height - H) // 2 + H))
    img = Image.eval(img, lambda v: int(v * 0.72)).convert("RGBA")
    d = ImageDraw.Draw(img)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    sizes = [_fit(probe, t, F_BLACKHAN, 170, int(W * 0.9)) for t in lines]
    total = sum(int(s * 1.15) for s in sizes)
    y = (H - total) // 2
    for i, (t, s) in enumerate(zip(lines, sizes)):
        fs = _fonts(F_BLACKHAN, s)
        w = _mixed_w_fonts(d, t, fs, s)
        for dx, dy in ((-6, 6), (6, 6), (-6, -6), (6, -6), (0, 8)):
            _mixed_text_fonts(img, d, ((W - w) // 2 + dx, y + dy), t, fs, s, (0, 0, 0, 255))
        _mixed_text_fonts(img, d, ((W - w) // 2, y), t, fs, s, (255, 229, 0, 255) if i == 0 else (255, 255, 255, 255))
        y += int(s * 1.15)
    img.convert("RGB").save(path, quality=92)
    return path


def top_bar(path, lines, W=config.W, bar_h=280):
    """Fixed black title bar for the top of the frame. lines: [(text, 'yellow'|'white'|'small')].
    First line in Black Han Sans, the rest in Pretendard ExtraBold; everything is sized to fit the bar."""
    img = Image.new("RGBA", (W, bar_h), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    cols = {"yellow": (255, 229, 0, 255), "white": (255, 255, 255, 255), "small": (200, 200, 200, 255)}
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    maxw = int(W * 0.90)
    n = max(1, len(lines))
    specs, sizes = [], []
    for i, (t, c) in enumerate(lines):
        spec = F_BLACKHAN if i == 0 else F_PRETENDARD_XB
        cap = int(bar_h * (0.46 if i == 0 else 0.24) / (1 if n <= 2 else 1.25))
        sizes.append(_fit(probe, t, spec, cap, maxw, 24)); specs.append(spec)
    total = sum(int(s * 1.18) for s in sizes)
    y = (bar_h - total) // 2
    for (t, c), spec, sz in zip(lines, specs, sizes):
        fs = _fonts(spec, sz)
        w = _mixed_w_fonts(d, t, fs, sz)
        _mixed_text_fonts(img, d, ((W - w) // 2, y), t, fs, sz, cols.get(c, cols["white"]))
        y += int(sz * 1.18)
    d.rectangle((0, bar_h - 6, W, bar_h), fill=(255, 229, 0, 255))     # thin accent rule
    img.save(path)
    return path


def label_pill(path, text, W=config.W):
    """Small source label for inserted images ('Product image · Picky')."""
    size = 34
    fs = _fonts(F_PRETENDARD_XB, size)
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w = _mixed_w_fonts(probe, text, fs, size) + 56
    h = int(size * 1.9)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=(0, 0, 0, 175))
    _mixed_text_fonts(img, d, (28, (h - int(size * 1.2)) // 2), text, fs, size, (255, 255, 255, 255))
    img.save(path)
    return path, w, h


def review_card(path, rev, W=config.W, VH=config.H):
    """Full-window review slide: dark gradient, star row, big quote, author line, source footer."""
    img = Image.new("RGBA", (W, VH), (0, 0, 0, 255))
    top, bot = (24, 22, 40), (8, 8, 12)
    for yy in range(VH):                                   # vertical gradient
        f = yy / VH
        ImageDraw.Draw(img).line((0, yy, W, yy), fill=tuple(int(top[i] * (1 - f) + bot[i] * f) for i in range(3)) + (255,))
    d = ImageDraw.Draw(img)
    cw, pad = int(W * 0.86), 56
    quote = rev.get("quote", "")
    q_size = 60
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    def wrap(text, spec, size, max_w):
        words, lines, cur = text.split(), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if cur and _mixed_w_fonts(probe, trial, _fonts(spec, size), size) > max_w:
                lines.append(cur); cur = wd
            else:
                cur = trial
        if cur:
            lines.append(cur)
        return lines
    qlines = wrap("“" + quote + "”", F_PRETENDARD, q_size, cw - pad * 2)
    while len(qlines) > 5 and q_size > 40:
        q_size -= 4; qlines = wrap("“" + quote + "”", F_PRETENDARD, q_size, cw - pad * 2)
    stars_h, auth_h, foot_h = 70, 52, 44
    ch = pad + stars_h + 20 + len(qlines) * int(q_size * 1.3) + 28 + auth_h + pad
    x0, y0 = (W - cw) // 2, int(VH * 0.40) - ch // 2
    d.rounded_rectangle((x0, y0, x0 + cw, y0 + ch), radius=44, fill=(255, 255, 255, 242))
    y = y0 + pad
    rating = float(rev.get("rating", 5))
    for k in range(5):
        _star(d, x0 + pad + 30 + k * 66, y + 30, 28, (255, 180, 0, 255) if k < int(round(rating)) else (215, 215, 220, 255))
    y += stars_h + 20
    fq = _fonts(F_PRETENDARD, q_size)
    for ln in qlines:
        _mixed_text_fonts(img, d, (x0 + pad, y), ln, fq, q_size, (20, 20, 24, 255))
        y += int(q_size * 1.3)
    y += 28
    fa = _fonts(F_PRETENDARD_XB, 40)
    author = f"— {rev.get('author', 'reviewer')}" + (f" · {rev['skin_type']}" if rev.get("skin_type") else "")
    _mixed_text_fonts(img, d, (x0 + pad, y), author, fa, 40, (110, 110, 120, 255))
    src = rev.get("source", "")
    if src:
        ff = _fonts(F_PRETENDARD_XB, 36)
        w = _mixed_w_fonts(d, src, ff, 36)
        _mixed_text_fonts(img, d, ((W - w) // 2, y0 + ch + 36), src, ff, 36, (210, 210, 220, 255))
    img.convert("RGB").save(path, quality=95)
    return path


def _star(d, cx, cy, r, fill):
    """Five-point star polygon (fonts in the roster have no ★ glyph)."""
    import math
    pts = []
    for k in range(10):
        rad = r if k % 2 == 0 else r * 0.45
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    d.polygon(pts, fill=fill)
