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
