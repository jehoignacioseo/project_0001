#!/usr/bin/env python3
"""Stage 1 - understand the raw footage without a human.

raw folder -> work/<id>/clips.json + frames/*.jpg + footage.json
  * ffprobe every clip, detect scene cuts, grab one keyframe per scene
  * sharpness/exposure heuristics per keyframe
  * faster-whisper transcript of anything said in the footage (Korean or English)
  * Claude vision: what is on screen (product, brand, visible text, price tag, store, shot type),
    which moments are usable, and which products need research

usage: analyze.py <raw_folder> --out work/<id> [--note "user's one-line note"] [--mock]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from common import ensure_dir, ffprobe, run  # noqa: E402

import config  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".3gp"}
MAX_FRAMES_PER_CLIP = 10
SCENE_THRESH = 0.32
MIN_SCENE = 1.2

SHOT_TYPES = ["product_closeup", "texture_or_swatch", "hand_apply", "face", "shelf", "price_tag", "ranking_sticker",
              "sold_out_sign", "store_interior", "store_exterior", "packaging_text", "unboxing", "other"]

FOOTAGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "clips": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "file": {"type": "string"},
                "summary": {"type": "string", "description": "one sentence: what this clip shows"},
                "scenes": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "index": {"type": "integer"},
                        "shot_type": {"type": "string", "enum": SHOT_TYPES},
                        "description": {"type": "string"},
                        "visible_text": {"type": "string", "description": "exact text readable on screen (Korean kept as is), '' if none"},
                        "products": {"type": "array", "items": {"type": "string"}, "description": "product names visible, brand + product"},
                        "price_krw": {"type": ["integer", "null"], "description": "price if a tag is readable"},
                        "usable": {"type": "boolean", "description": "sharp and steady enough to use"},
                        "hook_potential": {"type": "integer", "minimum": 0, "maximum": 10},
                        "why_hook": {"type": "string"},
                    },
                    "required": ["index", "shot_type", "description", "visible_text", "products", "price_krw", "usable", "hook_potential", "why_hook"],
                }},
            },
            "required": ["file", "summary", "scenes"],
        }},
        "detected_products": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "name": {"type": "string"}, "brand": {"type": "string"},
                "name_ko": {"type": "string", "description": "Hangul name if visible or known, else ''"},
                "category": {"type": "string"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "evidence": {"type": "string"},
                "hero": {"type": "boolean", "description": "true for the 1-2 products the video should be about"},
            },
            "required": ["name", "brand", "name_ko", "category", "confidence", "evidence", "hero"],
        }},
        "store": {"type": ["string", "null"], "description": "store name and location if identifiable"},
        "footage_angle": {"type": "string", "description": "what story this footage can honestly tell in one sentence"},
        "missing": {"type": "array", "items": {"type": "string"}, "description": "shots the editor wishes existed (fed back to the filmer)"},
    },
    "required": ["clips", "detected_products", "store", "footage_angle", "missing"],
}

SYSTEM = """You are the footage analyst for a K-beauty short-form channel aimed at non-Korean viewers.
You receive keyframes from raw phone footage shot in Korea (stores like Olive Young, Daiso, Musinsa, pharmacies, or at home) plus any
speech transcribed from the clips and the filmer's one-line note. Identify exactly what is on screen: product names (brand + product,
read the packaging text), Hangul text, price tags (₩), ranking/sold-out stickers, textures, application shots. Be literal about visible
text; never invent a product name you cannot read or recognise with confidence. Judge each scene for usability (sharp, steady, well
lit) and hook potential (would the first 1-2 seconds of this stop a scroll?). Decide which 1-2 products are the hero of this footage."""


def scene_cuts(path, dur):
    """Scene-change timestamps via ffmpeg's scene score."""
    res = run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", f"select='gt(scene,{SCENE_THRESH})',showinfo",
               "-an", "-f", "null", "-"], quiet=False)
    cuts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", res.stderr)]
    out, last = [0.0], 0.0
    for c in cuts:
        if c - last >= MIN_SCENE:
            out.append(c); last = c
    # long static clips: split every 4s so the editor still sees the whole clip
    bounds = out + [dur]
    final = [0.0]
    for a, b in zip(bounds, bounds[1:]):
        t = a
        while b - t > 6.0:
            t += 4.0
            final.append(t)
        if b < dur:
            final.append(b)
    return sorted(set(final))


def keyframe(path, t, out):
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
         "-vf", "scale=540:-2", "-q:v", "4", str(out)])
    return out


def frame_quality(jpg):
    im = np.asarray(Image.open(jpg).convert("L"), dtype=np.float32)
    lap = (np.abs(im[1:-1, 1:-1] * 4 - im[:-2, 1:-1] - im[2:, 1:-1] - im[1:-1, :-2] - im[1:-1, 2:])).var()
    return {"sharpness": round(float(lap), 1), "brightness": round(float(im.mean()), 1)}


def transcribe(path, info):
    if not info["has_audio"] or not config.WHISPER_MODEL:
        return ""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        segs, meta = model.transcribe(str(path), vad_filter=True)
        text = " ".join(s.text.strip() for s in segs)
        return f"[{meta.language}] {text}" if text.strip() else ""
    except Exception as e:  # model download or codec failures must not stop the pipeline
        print(f"  transcription skipped: {e}", file=sys.stderr)
        return ""


def probe_all(raw, out):
    frames_dir = ensure_dir(out / "frames")
    clips = []
    for p in sorted(Path(raw).iterdir()):
        if p.suffix.lower() not in VIDEO_EXT:
            continue
        info = ffprobe(p)
        dur = info["duration"]
        bounds = scene_cuts(p, dur)
        if len(bounds) - 1 > MAX_FRAMES_PER_CLIP:          # keep the longest scenes
            pairs = sorted(zip(bounds, bounds[1:] + [dur]), key=lambda ab: ab[0] - ab[1])[:MAX_FRAMES_PER_CLIP]
            bounds = sorted(a for a, _ in pairs)
        scenes = []
        for i, a in enumerate(bounds):
            b = bounds[i + 1] if i + 1 < len(bounds) else dur
            if b - a < 0.4:
                continue
            jpg = keyframe(p, a + (b - a) / 2, frames_dir / f"{p.stem}_s{len(scenes):02d}.jpg")
            scenes.append({"index": len(scenes), "start": round(a, 2), "end": round(b, 2), "frame": str(jpg.relative_to(out)),
                           **frame_quality(jpg)})
        info.update({"file": p.name, "scenes": scenes, "speech": transcribe(p, info)})
        clips.append(info)
        print(f"{p.name}: {dur:.1f}s {info['width']}x{info['height']} scenes={len(scenes)} speech={'yes' if info['speech'] else 'no'}")
    return clips


def analyze_with_claude(clips, out, note):
    import llm
    blocks, images = [], []
    for c in clips:
        blocks.append({"type": "text", "text": f"### clip {c['file']} ({c['duration']:.1f}s, {'portrait' if c['portrait'] else 'landscape'})"
                       + (f"\nspeech: {c['speech']}" if c["speech"] else "")})
        for s in c["scenes"]:
            blocks.append({"type": "text", "text": f"scene {s['index']} {s['start']}-{s['end']}s sharpness={s['sharpness']} brightness={s['brightness']}"})
            blocks.append(llm._image_block(out / s["frame"]))
    blocks.append({"type": "text", "text": f"Filmer's note: {note or '(none)'}\n\nAnalyse every scene of every clip. "
                   "Return scene indices exactly as given."})
    return llm.structured(SYSTEM, blocks, FOOTAGE_SCHEMA, max_tokens=24000)


def mock_analysis(clips, note):
    """Deterministic stand-in for Claude so the pipeline can be tested offline."""
    kinds = ["shelf", "product_closeup", "price_tag", "texture_or_swatch", "hand_apply", "ranking_sticker"]
    res = {"clips": [], "detected_products": [], "store": "Olive Young Myeongdong (mock)",
           "footage_angle": "Mock: a toner pad that is #1 at Olive Young, with price tag and texture shots.",
           "missing": ["a shot of the empty shelf"]}
    for ci, c in enumerate(clips):
        scenes = []
        for s in c["scenes"]:
            k = kinds[(ci + s["index"]) % len(kinds)]
            scenes.append({"index": s["index"], "shot_type": k, "description": f"mock {k} shot",
                           "visible_text": "₩19,900" if k == "price_tag" else ("올리브영 1위" if k == "ranking_sticker" else ""),
                           "products": ["Anua Heartleaf 77% Toner Pad"], "price_krw": 19900 if k == "price_tag" else None,
                           "usable": s["sharpness"] > 5, "hook_potential": 8 if k in ("ranking_sticker", "price_tag") else 5,
                           "why_hook": "proof element" if k in ("ranking_sticker", "price_tag") else "plain"})
        res["clips"].append({"file": c["file"], "summary": f"mock clip {ci + 1}", "scenes": scenes})
    res["detected_products"] = [{"name": "Heartleaf 77% Toner Pad", "brand": "Anua", "name_ko": "아누아 어성초 77 토너패드",
                                 "category": "toner pad", "confidence": "high", "evidence": "mock", "hero": True}]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--out", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    out = ensure_dir(a.out)
    clips = probe_all(a.raw, out)
    if not clips:
        sys.exit(f"no video files in {a.raw}")
    (out / "clips.json").write_text(json.dumps(clips, indent=2, ensure_ascii=False), encoding="utf-8")
    analysis = mock_analysis(clips, a.note) if (a.mock or config.MOCK) else analyze_with_claude(clips, out, a.note)
    # merge timing back into the analysis so later stages have one file to read
    by_file = {c["file"]: c for c in clips}
    for ac in analysis["clips"]:
        src = by_file.get(ac["file"])
        if not src:
            continue
        for s in ac["scenes"]:
            if s["index"] < len(src["scenes"]):
                s.update({k: src["scenes"][s["index"]][k] for k in ("start", "end", "frame", "sharpness")})
        ac.update({k: src[k] for k in ("duration", "width", "height", "portrait", "has_audio", "hdr", "speech")})
    analysis["user_note"] = a.note
    (out / "footage.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    heroes = [p for p in analysis["detected_products"] if p.get("hero")]
    print(f"wrote {out / 'footage.json'}: {len(analysis['detected_products'])} products, hero={[p['name'] for p in heroes]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
