#!/usr/bin/env python3
"""Render an episode.json into a Short (1080x1920) and/or a long-form (1920x1080).

usage: render.py <episode.json> [--shorts] [--longform] [--out dir]

episode.json (see episode_schema.md):
  segments[]: {src, in, out, speed?, captions[]: {t, d, text, style?}}
  captions t/d are relative to the segment start (after speed change).
"""
import argparse
import json
import math
import sys
from pathlib import Path

from caption_png import render_caption
from common import FONT_DIR, ensure_dir, ffprobe, run
from overlays import day_badge, end_card, progress_bar, score_card, title_card

SHORT_W, SHORT_H = 1080, 1920
LONG_W, LONG_H = 1920, 1080
FPS = 30
END_CARD_SEC = 3.0


def _vf_fit(src_portrait, W, H, portrait_out, crop_x=0.5, crop_y=0.5, zoom=1.0):
    """Video filter that fits any source into WxH.
    Same orientation -> scale+crop (crop_x/crop_y 0..1 pick the window).
    Landscape source into portrait output -> scale to fill height and crop a
    window horizontally (crop_x), optional zoom. Portrait into landscape ->
    blurred background fill."""
    if src_portrait == portrait_out or (not src_portrait and portrait_out):
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"scale=iw*{zoom}:ih*{zoom},"
                f"crop={W}:{H}:(in_w-out_w)*{crop_x}:(in_h-out_h)*{crop_y},setsar=1,fps={FPS}")
    # blurred fill
    return (f"split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma=40,eq=brightness=-0.15[bgb];"
            f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS}")


def _normalize_segment(seg, idx, tmp, W, H, portrait_out, ep_dir):
    src = Path(seg["src"])
    if not src.is_absolute():
        src = ep_dir / src
    info = ffprobe(src)
    speed = float(seg.get("speed", 1.0))
    t_in = float(seg.get("in", 0))
    t_out = float(seg.get("out", info["duration"]))
    out = tmp / f"seg{idx:02d}.mp4"
    vf = _vf_fit(info["portrait"], W, H, portrait_out,
                 float(seg.get("crop_x", 0.5)), float(seg.get("crop_y", 0.5)), float(seg.get("zoom", 1.0)))
    if speed != 1.0:
        vf += f",setpts=PTS/{speed}"
    af = f"atempo={min(max(speed, 0.5), 2.0)}" if speed != 1.0 else "anull"
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{t_in:.3f}", "-to", f"{t_out:.3f}", "-i", str(src)]
    if not info["has_audio"]:
        cmd += ["-f", "lavfi", "-t", f"{(t_out - t_in) / speed:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-filter_complex", f"[0:v]{vf}[v];[{0 if info['has_audio'] else 1}:a]{af},aresample=48000[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest", str(out)]
    run(cmd)
    return out, (t_out - t_in) / speed


def _concat(parts, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in parts))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(out)])
    return out


def _sting(tmp):
    """Generate a short 'pop' sound effect for the opening (no external assets)."""
    p = tmp / "sting.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
         "sine=frequency=880:duration=0.12,afade=t=out:st=0.04:d=0.08,volume=0.5",
         "-ar", "48000", "-ac", "2", str(p)])
    return p


def render(ep, ep_dir, out_dir, mode):
    portrait = mode == "shorts"
    W, H = (SHORT_W, SHORT_H) if portrait else (LONG_W, LONG_H)
    scale = (H if portrait else W) / 1920.0
    tmp = ensure_dir(out_dir / f"tmp_{mode}")
    segs = ep.get("longform_segments") or ep["segments"] if mode == "longform" else ep["segments"]

    parts, captions, t = [], [], 0.0
    if mode == "longform":
        tc = tmp / "title.png"
        title_card(str(tc), ep["title_en"], f"{ep['series']} #{ep['number']}/{ep['total']}  ·  {ep['title_ko']}", W, H)
        tcv = tmp / "title.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", "2.5", "-i", str(tc),
             "-f", "lavfi", "-t", "2.5", "-i", "anullsrc=r=48000:cl=stereo",
             "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(tcv)])
        parts.append(tcv)
        t += 2.5
    for i, seg in enumerate(segs):
        p, dur = _normalize_segment(seg, i, tmp, W, H, portrait, ep_dir)
        parts.append(p)
        for c in seg.get("captions", []):
            captions.append({"start": t + float(c["t"]), "end": t + float(c["t"]) + float(c.get("d", 2.0)),
                             "text": c["text"], "style": c.get("style", "pop")})
        t += dur
    body_end = t
    base = _concat(parts, tmp / "body.mp4")

    # --- overlays -------------------------------------------------------
    tag = f"{ep['series']} #{ep['number']:02d}/{ep['total']}"
    badge = day_badge(str(tmp / "badge.png"), ep["day"], tag, scale)
    prog = progress_bar(str(tmp / "prog.png"), ep["number"], ep["total"], W, scale)
    card = score_card(str(tmp / "score.png"), ep["score"], ep.get("comment", ""), ep["price"], W, scale)
    endc = end_card(str(tmp / "end.png"), ep.get("next", ""), ep.get("cta", "Follow for the next one"), W, H, scale)
    score_at = float(ep.get("longform_score_at", max(0.0, body_end - 7.0))) if mode == "longform" else float(ep.get("score_at", max(0.0, body_end - 7.0)))
    score_d = float(ep.get("score_duration", 4.0))
    total = body_end + END_CARD_SEC
    sting = _sting(tmp)
    badge_x, badge_y = int(40 * scale), int(60 * scale) + 14
    card_y = f"H-h-{int(300 * scale)}" if portrait else f"H-h-{int(60 * scale)}"

    # overlay list: (png, x_expr, y_expr, start, end)
    ov = [(badge, str(badge_x), str(badge_y), 0, total), (prog, "0", "0", 0, total),
          (card, "(W-w)/2", card_y, score_at, score_at + score_d)]
    POP = 0.1
    for i, c in enumerate(captions):
        png, cw, ch, cy = render_caption(str(tmp / f"cap{i:02d}.png"), c["text"], c["style"], W, H, portrait)
        if c["style"] != "note":
            # two-stage pop: smaller for the first 0.1s then full size
            small, sw, sh, sy = render_caption(str(tmp / f"cap{i:02d}s.png"), c["text"], c["style"], W, H, portrait, 0.88)
            ov.append((small, "(W-w)/2", str(sy), c["start"], c["start"] + POP))
            ov.append((png, "(W-w)/2", str(cy), c["start"] + POP, c["end"]))
        else:
            ov.append((png, "(W-w)/2", str(cy), c["start"], c["end"]))
    ov.append((endc, "0", "0", body_end, total))

    inputs = ["-i", str(base)]
    chain = f"[0:v]tpad=stop_mode=clone:stop_duration={END_CARD_SEC}[v0];"
    cur = "v0"
    for i, (png, x, y, s0, s1) in enumerate(ov):
        inputs += ["-i", png]
        nxt = f"v{i + 1}"
        chain += f"[{cur}][{i + 1}:v]overlay={x}:{y}:enable='between(t,{s0:.3f},{s1:.3f})'[{nxt}];"
        cur = nxt
    inputs += ["-i", str(sting)]
    sting_idx = len(ov) + 1
    chain += (f"[{cur}]format=yuv420p[vout];"
              f"[0:a]apad=pad_dur={END_CARD_SEC},loudnorm=I=-16:TP=-1.5:LRA=11[a0];"
              f"[{sting_idx}:a]adelay=0|0[st];[a0][st]amix=inputs=2:duration=first:normalize=0[aout]")
    out = out_dir / f"{ep['id']}_{mode}.mp4"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", chain, "-map", "[vout]", "-map", "[aout]",
         "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)])
    # thumbnail: frame at 1.0s with the hook caption burnt in
    run(["ffmpeg", "-y", "-v", "error", "-ss", "1.0", "-i", str(out), "-frames:v", "1", "-q:v", "2",
         str(out_dir / f"{ep['id']}_{mode}_thumb.jpg")])
    print(f"{mode}: {out} ({total:.1f}s, {len(captions)} captions)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--shorts", action="store_true")
    ap.add_argument("--longform", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    ep_path = Path(a.episode)
    ep = json.loads(ep_path.read_text(encoding="utf-8"))
    ep_dir = ep_path.resolve().parent
    out_dir = ensure_dir(Path(a.out).resolve() if a.out else (ep_dir / "out").resolve())
    if not a.shorts and not a.longform:
        a.shorts = a.longform = True
    if a.shorts:
        render(ep, ep_dir, out_dir, "shorts")
    if a.longform:
        render(ep, ep_dir, out_dir, "longform")
    return 0


if __name__ == "__main__":
    sys.exit(main())
