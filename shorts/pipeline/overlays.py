"""PIL-rendered PNG overlays: day badge, progress pill, score card, end card,
title card (long-form intro). All functions return the PNG path."""
from PIL import Image, ImageDraw, ImageFont

from common import FONT_FILE_BOLD, FONT_FILE_HEAVY, FONT_FILE_EMOJI
from caption_png import _runs, _emoji_img


def _mixed_w(d, text, font, size):
    w = 0
    for is_e, ch in _runs(text):
        if is_e:
            im = _emoji_img(ch, size)
            w += (im.width if im else 0) + int(size * 0.1)
        else:
            l, t, r, b = d.textbbox((0, 0), ch, font=font)
            w += r - l
    return w


def _mixed_text(img, d, xy, text, font, size, fill):
    x, y = xy
    for is_e, ch in _runs(text):
        if is_e:
            im = _emoji_img(ch, size)
            if im:
                img.alpha_composite(im, (int(x), int(y) + int(size * 0.08)))
                x += im.width + int(size * 0.1)
        else:
            d.text((x, y), ch, font=font, fill=fill)
            l, t, r, b = d.textbbox((0, 0), ch, font=font)
            x += r - l



from pathlib import Path
_FD = Path(__file__).resolve().parent / "fonts"


def _font(size, heavy=False):
    """heavy=False -> Pretendard Black (display), heavy=True -> Pretendard ExtraBold (text)."""
    f = _FD / ("Pretendard-ExtraBold.otf" if heavy else "Pretendard-Black.otf")
    try:
        return ImageFont.truetype(str(f), size)
    except OSError:
        return ImageFont.truetype(FONT_FILE_HEAVY, size)


def _emoji_font():
    # Noto Color Emoji (CBDT) only renders at its native 109px in PIL
    try:
        return ImageFont.truetype(FONT_FILE_EMOJI, 109)
    except OSError:
        return None


def _rounded(draw, box, radius, fill, outline=None, width=0):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _text_w(draw, text, font):
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    return r - l, b - t


def day_badge(path, day, series_tag, scale=1.0):
    """Top-left pill: 'DAY 05 · S1 #05/33'."""
    f = _font(int(44 * scale))
    img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    text = f"DAY {day:02d}  ·  {series_tag}"
    tw, th = _text_w(d, text, f)
    pad = int(26 * scale)
    img = Image.new("RGBA", (tw + pad * 2, th + pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _rounded(d, (0, 0, img.width - 1, img.height - 1), img.height // 2, (0, 0, 0, 170))
    d.text((pad, pad // 2 - int(4 * scale)), text, font=f, fill=(255, 255, 255, 255))
    img.save(path)
    return path


def progress_bar(path, number, total, width, scale=1.0):
    """Thin progress bar for 'episode number / total' at the very top."""
    h = int(14 * scale)
    img = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, width, h), fill=(255, 255, 255, 60))
    d.rectangle((0, 0, int(width * number / max(total, 1)), h), fill=(255, 214, 0, 230))
    img.save(path)
    return path


def score_card(path, score, comment, price, width, scale=1.0):
    """Bottom card: taste / value / again + one-line comment + price."""
    w = int(width * 0.86)
    f_big = _font(int(64 * scale))
    f_lbl = _font(int(34 * scale))
    f_cmt = _font(int(44 * scale), heavy=True)
    rows = [("TASTE", f"{score['taste']}/10"), ("VALUE", f"{score['value']}/10"), ("AGAIN?", str(score["again"]))]
    h = int(400 * scale)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _rounded(d, (0, 0, w - 1, h - 1), int(40 * scale), (12, 12, 12, 215), outline=(255, 214, 0, 255), width=int(5 * scale))
    col = w // 3
    for i, (lbl, val) in enumerate(rows):
        cx = col * i + col // 2
        lw, _ = _text_w(d, lbl, f_lbl)
        vw, _ = _text_w(d, val, f_big)
        d.text((cx - lw // 2, int(36 * scale)), lbl, font=f_lbl, fill=(255, 214, 0, 255))
        d.text((cx - vw // 2, int(86 * scale)), val, font=f_big, fill=(255, 255, 255, 255))
    # divider
    d.line((int(30 * scale), int(190 * scale), w - int(30 * scale), int(190 * scale)), fill=(255, 255, 255, 60), width=2)
    cw = _mixed_w(d, comment, f_cmt, int(44 * scale))
    _mixed_text(img, d, ((w - cw) // 2, int(215 * scale)), comment, f_cmt, int(44 * scale), (255, 255, 255, 255))
    if price:
        ptxt = f"₩{price['krw']:,}  =  ${price['usd']:.2f}"
        pw, _ = _text_w(d, ptxt, f_lbl)
        d.text(((w - pw) // 2, int(300 * scale)), ptxt, font=f_lbl, fill=(100, 255, 100, 255))
    img.save(path)
    return path


def _wrap(d, text, f, sz, max_w):
    """Greedy word wrap on rendered width (handles emoji runs)."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and _mixed_w(d, trial, f, sz) > max_w:
            lines.append(cur); cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def end_card(path, next_text, cta, width, height, scale=1.0, subscribe="SUBSCRIBE for the next one"):
    """Full-frame translucent end card. With next_text: NEXT + title + CTA.
    Without: the CTA question (wrapped) + a subscribe line."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 150))
    d = ImageDraw.Draw(img)
    max_w = int(width * 0.86)
    rows = []
    if next_text:
        rows.append(("NEXT  ▶", _font(int(48 * scale)), int(48 * scale), (255, 214, 0, 255)))
        for ln in _wrap(d, next_text, _font(int(72 * scale)), int(72 * scale), max_w):
            rows.append((ln, _font(int(72 * scale)), int(72 * scale), (255, 255, 255, 255)))
        rows.append(("", None, int(30 * scale), None))
        for ln in _wrap(d, cta, _font(int(54 * scale), heavy=True), int(54 * scale), max_w):
            rows.append((ln, _font(int(54 * scale), heavy=True), int(54 * scale), (200, 200, 200, 255)))
    else:
        sz = int(74 * scale)
        for ln in _wrap(d, cta, _font(sz), sz, max_w):
            rows.append((ln, _font(sz), sz, (255, 255, 255, 255)))
        rows.append(("", None, int(34 * scale), None))
        for ln in _wrap(d, subscribe, _font(int(50 * scale), heavy=True), int(50 * scale), max_w):
            rows.append((ln, _font(int(50 * scale), heavy=True), int(50 * scale), (255, 214, 0, 255)))
    total_h = sum(int(sz * 1.3) + int(16 * scale) for _, _, sz, _ in rows)
    y = (height - total_h) // 2
    for text, f, sz, col in rows:
        if text:
            tw = _mixed_w(d, text, f, sz)
            _mixed_text(img, d, ((width - tw) // 2, y), text, f, sz, col)
        y += int(sz * 1.3) + int(16 * scale)
    img.save(path)
    return path


def title_card(path, title, subtitle, width, height):
    """Long-form intro card (16:9)."""
    img = Image.new("RGB", (width, height), (14, 14, 14))
    d = ImageDraw.Draw(img)
    size = int(height * 0.11)
    f_t = _font(size)
    tw, th = _text_w(d, title, f_t)
    while tw > width * 0.9 and size > 20:      # shrink until the title fits
        size -= 4
        f_t = _font(size)
        tw, th = _text_w(d, title, f_t)
    f_s = _font(int(height * 0.05), heavy=True)
    sw, sh = _text_w(d, subtitle, f_s)
    d.text(((width - tw) // 2, height * 0.38), title, font=f_t, fill=(255, 214, 0))
    d.text(((width - sw) // 2, height * 0.38 + th + height * 0.04), subtitle, font=f_s, fill=(230, 230, 230))
    img.save(path)
    return path


def title_band(path, lines, width, band_h, scale=1.0):
    """Fixed top title band for Shorts: black bar with up to 3 lines.
    lines: list of (text, color) ; colors: 'white' | 'yellow' | 'small'."""
    from caption_png import _runs, _emoji_img, F_BLACKHAN, F_PRETENDARD_XB, _fonts, _script_runs
    img = Image.new("RGBA", (width, band_h), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    cols = {"white": (255, 255, 255, 255), "yellow": (255, 229, 0, 255), "small": (210, 210, 210, 255)}
    big = [ln for ln in lines if ln[1] != "small"]
    small = [ln for ln in lines if ln[1] == "small"]
    target = int(width * 0.90)
    # each big line gets its own size so every line spans the same width (flush edges)
    def fit(t):
        sz = int(150 * scale)
        while sz > 40 and _mixed_w_fonts(d, t, _fonts(F_BLACKHAN, sz), sz) > target:
            sz -= 2
        return sz
    sizes = [fit(t) for t, _ in big]
    s_size = int(44 * scale)
    fs_small = _fonts(F_PRETENDARD_XB, s_size)
    total_h = sum(int(sz * 1.12) for sz in sizes) + len(small) * int(s_size * 1.4)
    y = (band_h - total_h) // 2
    for (t, c), size in zip(big, sizes):
        fs = _fonts(F_BLACKHAN, size)
        w = _mixed_w_fonts(d, t, fs, size)
        _mixed_text_fonts(img, d, ((width - w) // 2, y), t, fs, size, cols[c])
        y += int(size * 1.12)
    for t, c in small:
        w = _mixed_w_fonts(d, t, fs_small, s_size)
        _mixed_text_fonts(img, d, ((width - w) // 2, y + int(6 * scale)), t, fs_small, s_size, cols["small"])
        y += int(s_size * 1.4)
    img.save(path)
    return path


def bottom_band(path, left_text, right_text, width, band_h, scale=1.0):
    """Thin bottom bar: 'DAY 01 · S1 #01/33' on the left, teaser on the right."""
    from caption_png import F_PRETENDARD, F_PRETENDARD_XB, _fonts
    img = Image.new("RGBA", (width, band_h), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    sz = int(40 * scale)
    pad = int(40 * scale)
    while sz > 20:   # shrink until both texts fit with a gap
        fl = _fonts(F_PRETENDARD, sz)
        fr = _fonts(F_PRETENDARD_XB, sz)
        if _mixed_w_fonts(d, left_text, fl, sz) + _mixed_w_fonts(d, right_text, fr, sz) + pad * 3 <= width:
            break
        sz -= 2
    _mixed_text_fonts(img, d, (pad, (band_h - int(sz * 1.2)) // 2), left_text, fl, sz, (255, 229, 0, 255))
    w = _mixed_w_fonts(d, right_text, fr, sz)
    _mixed_text_fonts(img, d, (width - pad - w, (band_h - int(sz * 1.2)) // 2), right_text, fr, sz, (220, 220, 220, 255))
    img.save(path)
    return path


def _mixed_w_fonts(d, text, fonts, size):
    from caption_png import _runs, _emoji_img, _script_runs
    w = 0
    for is_e, ch in _runs(text):
        if is_e:
            im = _emoji_img(ch, size)
            w += (im.width if im else 0) + int(size * 0.1)
        else:
            for ci, part in _script_runs(ch):
                l, t, r, b = d.textbbox((0, 0), part, font=fonts[ci])
                w += r - l
    return w


def _mixed_text_fonts(img, d, xy, text, fonts, size, fill):
    from caption_png import _runs, _emoji_img, _script_runs
    x, y = xy
    for is_e, ch in _runs(text):
        if is_e:
            im = _emoji_img(ch, size)
            if im:
                img.alpha_composite(im, (int(x), int(y) + int(size * 0.08)))
                x += im.width + int(size * 0.1)
        else:
            for ci, part in _script_runs(ch):
                d.text((x, y), part, font=fonts[ci], fill=fill)
                l, t, r, b = d.textbbox((0, 0), part, font=fonts[ci])
                x += r - l
