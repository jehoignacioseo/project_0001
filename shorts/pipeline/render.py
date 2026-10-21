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
from overlays import bottom_band, day_badge, end_card, progress_bar, score_card, title_band, title_card

SHORT_W, SHORT_H = 1080, 1920
TOP_BAND, BOTTOM_BAND = 380, 200   # used when episode has "title_band"
LONG_W, LONG_H = 1920, 1080
FPS = 30
END_CARD_SEC = 3.0
# iPhone HLG/PQ 10-bit footage -> SDR BT.709 8-bit (hable tonemap keeps highlights)
HDR_TO_SDR = ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
              "tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p")


def _vf_fit(src_portrait, W, H, portrait_out, crop_x=0.5, crop_y=0.5, zoom=1.0, fit="crop", pan=None, dur=1.0):
    """Video filter that fits any source into WxH.
    Same orientation -> scale+crop (crop_x/crop_y 0..1 pick the window).
    Landscape source into portrait output -> scale to fill height and crop a
    window horizontally (crop_x), optional zoom. Portrait into landscape ->
    blurred background fill."""
    if fit == "crop" and (src_portrait == portrait_out or (not src_portrait and portrait_out)):
        if pan:   # slow horizontal pan across the frame: pan=[x0, x1] in 0..1 over the segment
            x_expr = f"(in_w-out_w)*({pan[0]}+({pan[1]}-{pan[0]})*min(t/{dur:.3f}\\,1))"
        else:
            x_expr = f"(in_w-out_w)*{crop_x}"
        return (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"scale=iw*{zoom}:ih*{zoom},"
                f"crop={W}:{H}:{x_expr}:(in_h-out_h)*{crop_y},setsar=1,fps={FPS}")
    if fit == "contain" and src_portrait == portrait_out:
        return f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS}"
    # blurred fill
    return (f"split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"gblur=sigma=40,eq=brightness=-0.15[bgb];"
            f"[fg]scale={W}:{H}:force_original_aspect_ratio=decrease[fgs];"
            f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS}")


def _normalize_segment(seg, idx, tmp, W, H, portrait_out, ep_dir, top=0, bottom=0):
    src = Path(seg["src"])
    if not src.is_absolute():
        src = ep_dir / src
    info = ffprobe(src)
    speed = float(seg.get("speed", 1.0))
    t_in = float(seg.get("in", 0))
    t_out = float(seg.get("out", info["duration"]))
    out = tmp / f"seg{idx:02d}.mp4"
    VH = H - top - bottom
    vf = (HDR_TO_SDR + "," if info.get("hdr") else "format=yuv420p,") + _vf_fit(info["portrait"], W, VH, portrait_out,
                 float(seg.get("crop_x", 0.5)), float(seg.get("crop_y", 0.5)), float(seg.get("zoom", 1.0)),
                 seg.get("fit", "crop"), seg.get("pan"), (t_out - t_in) / speed)
    if top or bottom:   # letterbox into the full frame; bands are drawn as overlays later
        vf += f",pad={W}:{H}:0:{top}:black"
    if speed != 1.0:
        vf += f",setpts=PTS/{speed}"
    af = f"atempo={min(max(speed, 0.5), 2.0)}" if speed != 1.0 else "anull"
    amb = float(seg.get("amb_gain_db", 0.0))
    if amb:
        af += f",volume={amb}dB"
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
        title_card(str(tc), ep["title_en"], f"{ep['series']} #{ep['number']}" + (f"/{ep['total']}" if ep.get("total") else "") + f"  ·  {ep['title_ko']}", W, H)
        tcv = tmp / "title.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", "2.5", "-i", str(tc),
             "-f", "lavfi", "-t", "2.5", "-i", "anullsrc=r=48000:cl=stereo",
             "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-c:a", "aac", "-ar", "48000", "-ac", "2", "-shortest", str(tcv)])
        parts.append(tcv)
        t += 2.5
    band = bool(ep.get("title_band")) and portrait
    top, bottom = (TOP_BAND, BOTTOM_BAND) if band else (0, 0)
    for i, seg in enumerate(segs):
        p, dur = _normalize_segment(seg, i, tmp, W, H, portrait, ep_dir, top, bottom)
        parts.append(p)
        for c in seg.get("captions", []):
            captions.append({"start": t + float(c["t"]), "end": t + float(c["t"]) + float(c.get("d", 2.0)),
                             "text": c["text"], "style": c.get("style", "pop"), "sfx": c.get("sfx", "auto")})
        t += dur
    body_end = t
    base = _concat(parts, tmp / "body.mp4")

    # --- overlays -------------------------------------------------------
    tag = ep.get("tag") or (f"{ep['series']} #{ep['number']:02d}/{ep['total']}" if ep.get("total")
                            else f"COMBO #{ep['number']}")
    badge = day_badge(str(tmp / "badge.png"), ep["day"], tag, scale)
    prog = progress_bar(str(tmp / "prog.png"), ep["number"], ep.get("total") or max(ep["number"], 10), W, scale)
    card = score_card(str(tmp / "score.png"), ep["score"], ep.get("comment", ""), ep.get("price", ""), W, scale)
    endc = end_card(str(tmp / "end.png"), ep.get("next"), ep.get("cta", "Follow for the next one"), W, H, scale)
    _sa = ep.get("longform_score_at") if mode == "longform" else ep.get("score_at")
    score_at = float(_sa) if _sa is not None else max(0.0, body_end - 7.0)
    score_d = float(ep.get("score_duration", 4.0))
    total = body_end + END_CARD_SEC
    sting = _sting(tmp)
    badge_x, badge_y = int(40 * scale), int(60 * scale) + 14
    card_y = f"H-h-{int(300 * scale)}" if portrait else f"H-h-{int(60 * scale)}"

    # overlay list: (png, x_expr, y_expr, start, end)
    ov = []
    if band:
        tb = title_band(str(tmp / "tband.png"), [tuple(x) for x in ep["title_band"]], W, top, scale)
        bb = bottom_band(str(tmp / "bband.png"), f"DAY {ep['day']:02d}  ·  {tag}",
                         ep.get("teaser") or (f"NEXT ▶ {ep['next']}" if ep.get("next") else "Comment a combo I should try 👇"),
                         W, bottom, scale)
        ov += [(tb, "0", "0", 0, total), (bb, "0", str(H - bottom), 0, total)]
    else:
        ov += [(badge, str(badge_x), str(badge_y), 0, total), (prog, "0", "0", 0, total)]
    ov.append((card, "(W-w)/2", f"{H - bottom}-h-{int(40 * scale)}" if band else card_y, score_at, score_at + score_d))
    POP = 0.1
    for i, c in enumerate(captions):
        png, cw, ch, cy = render_caption(str(tmp / f"cap{i:02d}.png"), c["text"], c["style"], W, H, portrait)
        if band:   # keep captions inside the video window
            cy = top + int((H - top - bottom) * (0.78 if c["style"] != "note" else 0.06)) - ch // 2
        if c["style"] != "note":
            # two-stage pop: smaller for the first 0.1s then full size
            small, sw, sh, sy = render_caption(str(tmp / f"cap{i:02d}s.png"), c["text"], c["style"], W, H, portrait, 0.88)
            if band:
                sy = top + int((H - top - bottom) * 0.78) - sh // 2
            ov.append((small, "(W-w)/2", str(sy), c["start"], c["start"] + POP))
            ov.append((png, "(W-w)/2", str(cy), c["start"] + POP, c["end"]))
        else:
            ov.append((png, "(W-w)/2", str(cy), c["start"], c["end"]))
    ov.append((endc, "0", "0", body_end, total))

    inputs = ["-i", str(base)]
    chain = f"[0:v]setpts=N/FRAME_RATE/TB,tpad=stop_mode=clone:stop_duration={END_CARD_SEC}[v0];"
    cur = "v0"
    for i, (png, x, y, s0, s1) in enumerate(ov):
        inputs += ["-i", png]
        nxt = f"v{i + 1}"
        chain += f"[{cur}][{i + 1}:v]overlay={x}:{y}:enable='between(t,{s0:.3f},{s1:.3f})'[{nxt}];"
        cur = nxt
    chain += f"[{cur}]format=yuv420p[vout];"
    # ---- audio layers --------------------------------------------------
    ASSETS = Path(__file__).resolve().parent / "assets"
    audio_in = []           # (label, path)
    def add_audio(path):
        audio_in.append(path)
        return len(ov) + len(audio_in)   # ffmpeg input index (0 = base video)
    layers = []
    # ambience (already gain-adjusted per segment), padded for the end card
    chain += f"[0:a]asetpts=N/SR/TB,apad=pad_dur={END_CARD_SEC}[amb];"
    layers.append("amb")
    # opening sting
    si = add_audio(str(sting))
    chain += f"[{si}:a]adelay=0|0[st];"
    layers.append("st")
    # voiceover
    vo = ep.get("voiceover")
    if vo and Path(ep_dir / vo["file"]).exists():
        vi = add_audio(str(ep_dir / vo["file"]))
        vdelay = int(float(vo.get("start", 0.3)) * 1000)
        vtempo = float(vo.get("tempo", 1.0))
        chain += (f"[{vi}:a]aresample=48000,atempo={vtempo},volume={float(vo.get('gain_db', 0)):.1f}dB,"
                  f"adelay={vdelay}|{vdelay},apad[vo];")
        layers.append("vo")
    # music bed, looped to length, ducked under the voiceover
    mus = ep.get("music", {"file": "music_lofi.wav", "gain_db": -19})
    if mus and mus.get("file"):
        mpath = ep_dir / mus["file"] if (ep_dir / mus["file"]).exists() else ASSETS / mus["file"]
        if mpath.exists():
            mi = add_audio(str(mpath))
            chain += (f"[{mi}:a]aloop=loop=-1:size=2e9,atrim=0:{total + 1:.2f},"
                      f"afade=t=out:st={total - 1.5:.2f}:d=1.5,volume={float(mus.get('gain_db', -22)):.1f}dB[mus0];")
            if "vo" in layers:
                chain += "[vo]asplit=2[vo][vok];[mus0][vok]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=400[mus];"
            else:
                chain += "[mus0]anull[mus];"
            layers.append("mus")
    # auto SFX: whoosh on every cut, pop on every caption, ding when a caption says DING
    # whoosh only on cuts the episode marks as scene changes ("whoosh": true on the segment),
    # or on every cut when ep["whoosh"] == "all"
    cuts = []
    tt = 2.5 if mode == "longform" else 0.0
    whoosh_all = ep.get("whoosh") == "all"
    for sgm in segs:
        if tt > 0.2 and (whoosh_all or sgm.get("whoosh")):
            cuts.append(tt)
        tt += (float(sgm.get("out")) - float(sgm.get("in", 0))) / float(sgm.get("speed", 1.0))
    sfx = []
    if ep.get("sfx", True):
        sfx += [("sfx_whoosh.wav", t, -17) for t in cuts]
        sfx.append(("sfx_whoosh.wav", body_end, -15))                      # into the end card
        for c in captions:
            if c["style"] == "note":
                continue
            custom = c.get("sfx", "auto")
            if custom is None or custom is False:
                continue
            if custom != "auto":
                sfx.append((f"sfx_{custom}.wav", c["start"], -10)); continue
            up = c["text"].upper()
            if "DING" in up or "🔔" in c["text"]:
                sfx.append(("sfx_ding.wav", c["start"], -10))
            elif c["style"] == "price" or "₩" in c["text"] or "$" in c["text"]:
                sfx.append(("sfx_cash.wav", c["start"], -10))
            elif any(k in up for k in ("CASHIER", "SCAN", "PAY", "📱")):
                sfx.append(("sfx_beep.wav", c["start"], -12))
            elif c["style"] == "shout":
                sfx.append(("sfx_thud.wav", c["start"], -8))
            else:
                sfx.append(("sfx_pop.wav", c["start"], -12))
        if score_at is not None:
            sfx.append(("sfx_riser.wav", max(0.0, score_at - 0.9), -14))
            sfx.append(("sfx_chime.wav", score_at, -11))
    for k, (name, at, g) in enumerate(sfx):
        fi = add_audio(str(ASSETS / name))
        d = int(at * 1000)
        chain += f"[{fi}:a]volume={g}dB,adelay={d}|{d}[sfx{k}];"
        layers.append(f"sfx{k}")
    chain += "".join(f"[{l}]" for l in layers) + f"amix=inputs={len(layers)}:duration=first:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=9[aout]"
    for a in audio_in:
        inputs += ["-i", a]
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
