#!/usr/bin/env python3
"""Stage 5 - assemble the video: cuts fitted to the voice, animated push-ins, image/review inserts,
fixed top title bar, karaoke captions, info cards, emphasis words, SFX, ducked music, loudness,
and one end card per platform.

episode.json + vo/lines.json -> out/<id>_{tiktok,reels,shorts}.mp4, out/<id>_cover.jpg, out/meta_<platform>.json
usage: render.py work/<id> [--platforms tiktok,reels,shorts] [--fast]

Segment types (episode.segments[].type): footage (default) | image (src = URL or file, dur) | review (review{}, dur).
"""
import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from caption_png import render_caption  # noqa: E402
from common import ensure_dir, ffprobe, run  # noqa: E402
from overlays import end_card  # noqa: E402
import audio_assets  # noqa: E402

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("pipeline_render", Path(__file__).resolve().parent.parent / "pipeline" / "render.py")
_pr = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_pr)
HDR_TO_SDR, _vf_fit = _pr.HDR_TO_SDR, _pr._vf_fit

import cards  # noqa: E402
import config  # noqa: E402
import kcaptions  # noqa: E402

W, H, FPS = config.W, config.H, config.FPS
END_SEC = 2.2
VO_LEAD = 0.15          # voice starts this long after the cut
VO_TAIL = 0.30          # cut outlives the voice by this much
BAR_H = 280             # fixed top title bar height when episode.title_bar is set
FOLLOW = {"tiktok": "Follow for more Seoul finds", "reels": "Follow · save this for your trip", "shorts": "Subscribe for the next find"}


# ----------------------------------------------------------------------------- timeline
def fit_segments(ep, lines, clips):
    """Make every cut long enough for its narration. Footage: extend `out` inside the clip when possible,
    otherwise freeze the last frame. Inserts: stretch `dur`. Returns (segments, starts, body_duration)."""
    by_seg = {l["seg"]: l for l in lines}
    t, starts = 0.0, []
    for i, s in enumerate(ep["segments"]):
        kind = s.get("type", "footage")
        need_vo = by_seg[i]["duration"] + VO_LEAD + VO_TAIL if i in by_seg else 0.0
        if kind == "footage":
            speed = float(s.get("speed", 1.0))
            cut = (s["out"] - s["in"]) / speed
            need = max(cut, need_vo)
            if need > cut:
                room = clips[s["src"]]["duration"] - s["out"]
                extend = min(room, (need - cut) * speed)
                s["out"] = round(s["out"] + max(0.0, extend), 3)
                cut = (s["out"] - s["in"]) / speed
                s["freeze"] = round(max(0.0, need - cut), 3)
            s["dur"] = round(cut + s.get("freeze", 0.0), 3)
        else:
            s["dur"] = round(max(float(s.get("dur") or 2.5), need_vo), 3)
        starts.append(t)
        t += s["dur"]
    return ep["segments"], starts, t


def _zoom_expr(z0, z1, dur):
    """crop expressions for a continuous push-in/out from z0 to z1 over `dur` seconds."""
    if abs(z1 - z0) < 1e-3:
        return f"crop=w='iw/{z0:.4f}':h='ih/{z0:.4f}':x='(iw-ow)/2':y='(ih-oh)/2'"
    z = f"({z0:.4f}+({z1 - z0:.4f})*min(t/{max(dur, 0.1):.3f}\\,1))"
    return f"crop=w='iw/{z}':h='ih/{z}':x='(iw-ow)/2':y='(ih-oh)/2'"


def _common_out(cmd, out, dur):
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-t", f"{dur:.3f}", str(out)]
    run(cmd)
    return out


def normalize(seg, idx, tmp, raw_dir, info, top):
    """One footage cut -> W x H clip (video window W x (H-top) padded under the title bar)."""
    VH = H - top
    src = raw_dir / seg["src"]
    speed = float(seg.get("speed", 1.0))
    out = tmp / f"seg{idx:02d}.mp4"
    z0 = float(seg.get("zoom", 1.0)); z1 = float(seg.get("zoom_to", z0))
    vf = (HDR_TO_SDR + "," if info.get("hdr") else "format=yuv420p,") + _vf_fit(
        info["portrait"], W, VH, True, float(seg.get("crop_x", 0.5)), float(seg.get("crop_y", 0.5)),
        1.0, seg.get("fit", "crop"), seg.get("pan"), (seg["out"] - seg["in"]) / speed)
    if speed != 1.0:
        vf += f",setpts=PTS/{speed}"
    vf += "," + _zoom_expr(z0, z1, seg["dur"]) + f",scale={W}:{VH}:flags=lanczos,setsar=1"
    if seg.get("freeze"):
        vf += f",tpad=stop_mode=clone:stop_duration={seg['freeze']:.3f}"
    if top:
        vf += f",pad={W}:{H}:0:{top}:black"
    af = (f"atempo={min(max(speed, 0.5), 2.0)}" if speed != 1.0 else "anull") + f",volume={float(seg.get('amb_gain_db', -14)):.1f}dB"
    if seg.get("freeze"):
        af += f",apad=pad_dur={seg['freeze']:.3f}"
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{seg['in']:.3f}", "-to", f"{seg['out']:.3f}", "-i", str(src)]
    if not info["has_audio"]:
        cmd += ["-f", "lavfi", "-t", f"{seg['dur']:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    cmd += ["-filter_complex", f"[0:v]{vf}[v];[{0 if info['has_audio'] else 1}:a]{af},aresample=48000[a]",
            "-map", "[v]", "-map", "[a]"]
    return _common_out(cmd, out, seg["dur"])


def fetch_image(src, tmp):
    """URL or local path -> local file (cached by URL hash)."""
    if not str(src).startswith(("http://", "https://")):
        return Path(src)
    p = tmp / f"img_{hashlib.md5(src.encode()).hexdigest()[:10]}{Path(src.split('?')[0]).suffix or '.jpg'}"
    if not p.exists():
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0 (kbeauty-shorts)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            p.write_bytes(r.read())
    return p


def still_clip(img_path, idx, tmp, dur, top, z0=1.0, z1=1.1, label=None, fade=True):
    """Image -> W x H clip with a slow Ken Burns push, optional source label, silent audio."""
    VH = H - top
    out = tmp / f"seg{idx:02d}.mp4"
    vf = (f"scale={W}:{VH}:force_original_aspect_ratio=increase,crop={W}:{VH},format=yuv420p,fps={FPS},"
          + _zoom_expr(z0, z1, dur) + f",scale={W}:{VH}:flags=lanczos,setsar=1")
    if fade:
        vf += ",fade=t=in:st=0:d=0.18"
    inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(img_path)]
    chain = f"[0:v]{vf}[v0];"
    cur = "v0"
    if label:
        png, lw, lh = cards.label_pill(str(tmp / f"label{idx:02d}.png"), label)
        inputs += ["-i", png]
        chain += f"[{cur}][1:v]overlay=40:{VH - lh - 40}[v1];"
        cur = "v1"
    if top:
        chain += f"[{cur}]pad={W}:{H}:0:{top}:black[vout];"
    else:
        chain += f"[{cur}]null[vout];"
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo",
           "-filter_complex", chain.rstrip(";"), "-map", "[vout]", "-map", f"{2 if label else 1}:a"]
    return _common_out(cmd, out, dur)


def concat(parts, out):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in parts))
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out


# ----------------------------------------------------------------------------- render
def render(work, platforms, fast=False):
    work = Path(work)
    ep = json.loads((work / "episode.json").read_text(encoding="utf-8"))
    vo = json.loads((work / "vo" / "lines.json").read_text(encoding="utf-8"))
    footage = json.loads((work / "footage.json").read_text(encoding="utf-8"))
    clips = {c["file"]: c for c in footage["clips"]}
    raw_dir = Path(json.loads((work / "run.json").read_text())["raw"]) if (work / "run.json").exists() else work / "raw"
    out_dir = ensure_dir(work / "out")
    tmp = ensure_dir(work / "tmp")
    lines = vo["lines"]
    bar = ep.get("title_bar")
    top = int(bar.get("height", BAR_H)) if bar else 0
    VH = H - top

    segs, starts, body = fit_segments(ep, lines, clips)
    parts = []
    for i, s in enumerate(segs):
        kind = s.get("type", "footage")
        if kind == "footage":
            parts.append(normalize(s, i, tmp, raw_dir, clips[s["src"]], top))
        elif kind == "image":
            img = fetch_image(s["src"], tmp)
            parts.append(still_clip(img, i, tmp, s["dur"], top, float(s.get("zoom", 1.0)), float(s.get("zoom_to", 1.12)), s.get("label") or None))
        elif kind == "review":
            png = cards.review_card(str(tmp / f"review{i:02d}.jpg"), s["review"], W, VH)
            parts.append(still_clip(png, i, tmp, s["dur"], top, 1.0, 1.04, None))
        else:
            raise ValueError(f"unknown segment type {kind}")
    base = concat(parts, tmp / "body.mp4")
    total = body + END_SEC

    # ---- karaoke captions (absolute times) -------------------------------------------------
    timed = []
    for l in lines:
        t0 = starts[l["seg"]] + VO_LEAD
        timed.append({"words": [{"w": w["w"], "s": t0 + w["s"], "e": t0 + w["e"]} for w in l["words"]]})
    ass = kcaptions.write_ass(timed, tmp / "captions.ass", baseline_y=top + int(VH * 0.66))

    # ---- PNG overlays: (png, x, y, start, end) ---------------------------------------------
    ov, sfx = [], []
    hook_end = min(starts[1] if len(starts) > 1 else 3.0, 3.2)
    tb, tb_h = cards.title_band(str(tmp / "title.png"), ep["title_band"])
    ov.append((tb, "0", str(top + (16 if top else int(H * config.SAFE_TOP) + 20)), 0.0, max(hook_end, 2.6)))
    card_y = top + int(VH * 0.30)
    for i, c in enumerate(ep.get("cards", [])):
        png, ch = cards.info_card(str(tmp / f"card{i:02d}.png"), c["type"], c["title"], c["lines"])
        s0 = starts[c["seg"]] + float(c["t"])
        s1 = min(s0 + float(c["d"]), body)
        ov.append((png, "(W-w)/2", str(card_y), s0, s1))
        if c["type"] == "price":
            sfx.append(("sfx_riser.wav", max(0.0, s0 - 0.9), -15)); sfx.append(("sfx_cash.wav", s0, -11))
        else:
            sfx.append(("sfx_pop.wav", s0, -11))
    for i, e in enumerate(ep.get("emphasis", [])):
        png, cw, chh, cy = render_caption(str(tmp / f"emph{i:02d}.png"), e["text"], e["style"], W, H, True)
        s0 = starts[e["seg"]] + float(e["t"])
        ov.append((png, "(W-w)/2", str(top + int(VH * 0.55) - chh // 2), s0, s0 + float(e["d"])))
        sfx.append(("sfx_thud.wav" if e["style"] == "shout" else "sfx_cash.wav" if e["style"] == "price" else "sfx_pop.wav", s0, -9))
    cta_png, cw, chh = cards.cta_card(str(tmp / "cta.png"), ep["cta"]["on_screen"])
    cta_start = starts[-1] + 0.2
    ov.append((cta_png, "(W-w)/2", str(top + int(VH * (1 - config.SAFE_BOTTOM)) - chh - 10), cta_start, body))
    for s, t in zip(segs, starts):
        if s.get("whoosh") and t > 0.2:
            sfx.append(("sfx_whoosh.wav", t, -17))
        if s.get("type") in ("image", "review") and t > 0.2:
            sfx.append(("sfx_click.wav", t, -14))
    sfx.append(("sfx_whoosh.wav", body, -15))
    sfx.append(("sfx_pop.wav", 0.02, -12))
    bar_png = cards.top_bar(str(tmp / "bar.png"), [tuple(x) for x in bar["lines"]], W, top) if bar else None
    if bar_png:
        ov.append((bar_png, "0", "0", 0.0, total))

    # ---- video chain ----------------------------------------------------------------------
    inputs = ["-i", str(base)]
    chain = f"[0:v]setpts=N/FRAME_RATE/TB,tpad=stop_mode=clone:stop_duration={END_SEC}[v0];"
    cur = "v0"
    for i, (png, x, y, s0, s1) in enumerate(ov):
        inputs += ["-i", png]
        chain += f"[{cur}][{i + 1}:v]overlay={x}:{y}:enable='between(t,{s0:.3f},{s1:.3f})'[v{i + 1}];"
        cur = f"v{i + 1}"
    chain += f"[{cur}]ass='{_ffesc(ass)}':fontsdir='{_ffesc(config.FONTS)}',format=yuv420p[vbody]"
    mix = mix_audio(base, work, lines, starts, sfx, ep, total, tmp)
    master = tmp / "master_noend.mp4"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-i", str(mix), "-filter_complex", chain, "-map", "[vbody]", "-map", f"{len(ov) + 1}:a",
         "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "veryfast" if fast else "medium", "-crf", "19", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", str(master)])

    # ---- per-platform end card + metadata ------------------------------------------------------
    outputs = {}
    for pf in platforms:
        ec = end_card(str(tmp / f"end_{pf}.png"), None, ep["cta"]["on_screen"], W, H, 1.0, subscribe=FOLLOW[pf])
        out = out_dir / f"{ep['id']}_{pf}.mp4"
        fc = f"[0:v][1:v]overlay=0:0:enable='gte(t,{body:.3f})'[v1];"
        ins = ["-i", str(master), "-i", ec]
        if bar_png:
            ins += ["-i", bar_png]; fc += "[v1][2:v]overlay=0:0[v2];[v2]format=yuv420p[v]"
        else:
            fc += "[v1]format=yuv420p[v]"
        run(["ffmpeg", "-y", "-v", "error", *ins, "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
             "-c:v", "libx264", "-preset", "veryfast" if fast else "medium", "-crf", "19", "-r", str(FPS),
             "-c:a", "copy", "-movflags", "+faststart", str(out)])
        meta = dict(ep["platforms"][pf])
        meta.update({"file": str(out), "duration": round(total, 2), "pinned_comment": ep["pinned_comment"],
                     "hook_alternatives": ep["hook_alternatives"], "ai_voice": True, "lang": ep.get("lang", "en")})
        (out_dir / f"meta_{pf}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
        outputs[pf] = str(out)
        print(f"{pf}: {out} ({total:.1f}s)")
    hook_frame = tmp / "hook_frame.jpg"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "0.6", "-i", str(base), "-frames:v", "1", "-q:v", "2", str(hook_frame)])
    cards.cover(str(out_dir / f"{ep['id']}_cover.jpg"), str(hook_frame), ep["cover_text"])
    timeline = {"starts": starts, "body": body, "total": total, "segments": segs, "outputs": outputs,
                "cover": str(out_dir / f"{ep['id']}_cover.jpg"), "title_bar": bool(bar)}
    (out_dir / "timeline.json").write_text(json.dumps(timeline, indent=1, ensure_ascii=False), encoding="utf-8")
    return timeline


def mix_audio(base, work, lines, starts, sfx, ep, total, tmp):
    """Mix ambience + voice + ducked music + SFX, then two-pass EBU R128 loudness (-14 LUFS, -2 dBTP)
    with a true-peak limiter as a safety net. Returns the final wav."""
    inputs = ["-i", str(base)]
    layers = []

    def add(path):
        inputs.extend(["-i", str(path)]); return len(inputs) // 2 - 1
    chain = f"[0:a]asetpts=N/SR/TB,apad=pad_dur={END_SEC}[amb];"; layers.append("amb")
    for k, l in enumerate(lines):
        ai = add(work / l["file"]); d = int((starts[l["seg"]] + VO_LEAD) * 1000)
        chain += f"[{ai}:a]aresample=48000,adelay={d}|{d},apad[vo{k}];"
    if lines:
        chain += "".join(f"[vo{k}]" for k in range(len(lines))) + f"amix=inputs={len(lines)}:normalize=0,asplit=2[vo][vok];"
        layers.append("vo")
    mus = ep.get("music") or {}
    mname = mus.get("file", "music_pop.wav")
    mpath = Path(mname) if Path(mname).is_absolute() else (work / mname if (work / mname).exists() else audio_assets.ensure(mname))
    if mpath.exists():
        mi = add(mpath)
        chain += (f"[{mi}:a]aloop=loop=-1:size=2e9,atrim=0:{total + 1:.2f},afade=t=in:st=0:d=0.6,"
                  f"afade=t=out:st={total - 1.6:.2f}:d=1.6,volume={float(mus.get('gain_db', ep.get('music_gain_db', -17))):.1f}dB[mus0];")
        # duck under the voice but keep it audible: ratio 4, slow release so it swells back between lines
        chain += ("[mus0][vok]sidechaincompress=threshold=0.03:ratio=4:attack=25:release=420:makeup=1[mus];" if lines else "[mus0]anull[mus];")
        layers.append("mus")
    for k, (name, at, g) in enumerate(sfx):
        fi = add(config.ASSETS / name); d = int(at * 1000)
        chain += f"[{fi}:a]volume={g}dB,adelay={d}|{d}[sfx{k}];"; layers.append(f"sfx{k}")
    chain += "".join(f"[{l}]" for l in layers) + f"amix=inputs={len(layers)}:duration=first:normalize=0[mix]"
    raw = tmp / "mix_raw.wav"
    run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", chain, "-map", "[mix]", "-t", f"{total:.3f}",
         "-ar", "48000", "-ac", "2", str(raw)])
    import re as _re
    res = run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", "loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json", "-f", "null", "-"], quiet=False)
    m = _re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, _re.S)
    meas = json.loads(m.group()) if m else {}
    ln = "loudnorm=I=-14:TP=-2:LRA=9"
    if meas and meas.get("input_i") not in (None, "-inf"):
        ln += (f":measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:measured_LRA={meas['input_lra']}"
               f":measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true")
    out = tmp / "mix.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af",
         f"{ln},aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,alimiter=limit=0.79:attack=5:release=50:level=false",
         "-ar", "48000", "-ac", "2", str(out)])
    return out


def _ffesc(p):
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--platforms", default=",".join(config.PLATFORMS))
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    render(a.work, [p for p in a.platforms.split(",") if p], a.fast)
    return 0


if __name__ == "__main__":
    sys.exit(main())
