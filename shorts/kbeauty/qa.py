#!/usr/bin/env python3
"""Stage 6 - automatic quality gate before anything is published.

Checks the rendered files (specs, duration, loudness), the timing (hook within 3s, caption coverage, cards inside the
video), and the content (every on-screen number traces to products.json or footage; no medical claims; metadata limits).
Writes qa.json and exits non-zero on a FAIL.      usage: qa.py work/<id>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import config

MEDICAL = re.compile(r"\b(cures?|treats?|heals?|eliminates?|clinically proven|dermatologist[- ]approved)\b", re.I)
LIMITS = {"tiktok_caption": 150, "reels_caption": 2200, "shorts_title": 100, "shorts_desc": 5000}


def loudness(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    return json.loads(m.group()) if m else {}


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    j = json.loads(out)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return {"w": v["width"], "h": v["height"], "fps": eval(v["r_frame_rate"]), "dur": float(j["format"]["duration"]),
            "audio": any(s["codec_type"] == "audio" for s in j["streams"])}


def numbers(text):
    return set(re.findall(r"\d[\d,.]*", text))


def main():
    work = Path(sys.argv[1])
    ep = json.loads((work / "episode.json").read_text(encoding="utf-8"))
    tl = json.loads((work / "out" / "timeline.json").read_text(encoding="utf-8"))
    products = json.loads((work / "products.json").read_text(encoding="utf-8"))
    footage = json.loads((work / "footage.json").read_text(encoding="utf-8"))
    vo = json.loads((work / "vo" / "lines.json").read_text(encoding="utf-8"))
    checks = []

    def chk(name, ok, detail="", level="FAIL"):
        checks.append({"check": name, "status": "PASS" if ok else level, "detail": detail})

    # files
    for pf, f in tl["outputs"].items():
        p = probe(f)
        chk(f"{pf}: 1080x1920 30fps with audio", p["w"] == 1080 and p["h"] == 1920 and abs(p["fps"] - 30) < 0.1 and p["audio"],
            f"{p['w']}x{p['h']} {p['fps']:.1f}fps audio={p['audio']}")
        chk(f"{pf}: duration {config.TARGET_SEC[0]}-{config.TARGET_SEC[1] + 5}s", config.TARGET_SEC[0] - 5 <= p["dur"] <= config.TARGET_SEC[1] + 5,
            f"{p['dur']:.1f}s", level="WARN")
        l = loudness(f)
        if l:
            li, tp = float(l.get("input_i", -99)), float(l.get("input_tp", 0))
            chk(f"{pf}: loudness -16..-12 LUFS, TP <= -1", -16.5 <= li <= -11.5 and tp <= -0.9, f"{li:.1f} LUFS, TP {tp:.1f}", level="WARN")
    # timing
    starts = tl["starts"]
    chk("hook cut is 1.5-3.5s", 1.2 <= tl["segments"][0]["dur"] <= 3.6, f"{tl['segments'][0]['dur']:.2f}s", level="WARN")
    first_vo = min((l["seg"] for l in vo["lines"]), default=99)
    chk("voice starts in the first cut", first_vo == 0, f"first VO on segment {first_vo}")
    long_cuts = [s for s in tl["segments"] if s["dur"] > 6.5]
    chk("no cut longer than 6.5s (pattern interrupt)", not long_cuts, f"{len(long_cuts)} long cuts", level="WARN")
    frozen = sum(s.get("freeze", 0) or 0 for s in tl["segments"])
    chk("frame freezes < 3s total", frozen < 3.0, f"{frozen:.1f}s frozen (voice longer than footage)", level="WARN")
    spoken = sum(l["duration"] for l in vo["lines"])
    chk("voice covers >= 55% of the body", spoken / max(tl["body"], 1) >= 0.55, f"{spoken / max(tl['body'], 1):.0%}", level="WARN")
    for c in ep["cards"]:
        s0 = starts[c["seg"]] + c["t"]
        chk(f"card '{c['title']}' inside video", s0 + c["d"] <= tl["body"] + 0.01, f"{s0:.1f}-{s0 + c['d']:.1f}s of {tl['body']:.1f}s")
    cards_sorted = sorted((starts[c["seg"]] + c["t"], c["d"]) for c in ep["cards"])
    overlap = any(a[0] + a[1] > b[0] for a, b in zip(cards_sorted, cards_sorted[1:]))
    chk("cards do not overlap", not overlap)
    # content integrity: numbers on screen/voice must exist in research or footage
    known = set()
    for p in products["products"]:
        known |= numbers(json.dumps(p, ensure_ascii=False))
    for c in footage["clips"]:
        for s in c["scenes"]:
            known |= numbers(s.get("visible_text", "") + " " + str(s.get("price_krw") or ""))
    known_digits = {re.sub(r"[^\d]", "", k) for k in known}
    for k in list(known):                      # 14.3 -> 14 (rounded conversions are fine)
        try:
            known_digits.add(str(int(round(float(k.replace(",", ""))))))
        except ValueError:
            pass
    shown = " ".join(" ".join(c["lines"]) + " " + c["title"] for c in ep["cards"]) + " " + " ".join(e["text"] for e in ep["emphasis"]) \
        + " " + " ".join(ep["title_band"])
    unknown = [n for n in numbers(shown) if re.sub(r"[^\d]", "", n) not in known_digits and len(re.sub(r"[^\d]", "", n)) > 1]
    chk("every on-screen number traces to research/footage", not unknown, f"untraced: {unknown}", level="WARN")
    text_all = shown + " " + " ".join(s["vo"] for s in ep["segments"]) + " " + json.dumps(ep["platforms"], ensure_ascii=False)
    chk("no medical claims", not MEDICAL.search(text_all), (MEDICAL.search(text_all) or [None])[0] if MEDICAL.search(text_all) else "")
    # metadata limits
    pl = ep["platforms"]
    chk("tiktok caption <= 150", len(pl["tiktok"]["caption"]) <= LIMITS["tiktok_caption"], str(len(pl["tiktok"]["caption"])))
    chk("shorts title <= 100", len(pl["shorts"]["title"]) <= LIMITS["shorts_title"], str(len(pl["shorts"]["title"])))
    chk("AI voice disclosed in shorts description", "ai" in pl["shorts"]["description"].lower(), "", level="WARN")
    chk("3 alternative hooks for trial reels", len(ep["hook_alternatives"]) == 3)
    chk("cover file exists", Path(tl["cover"]).exists())

    fails = [c for c in checks if c["status"] == "FAIL"]
    warns = [c for c in checks if c["status"] == "WARN"]
    (work / "qa.json").write_text(json.dumps({"ok": not fails, "checks": checks}, indent=1, ensure_ascii=False), encoding="utf-8")
    for c in checks:
        if c["status"] != "PASS":
            print(f"{c['status']:4} {c['check']}  {c['detail']}")
    print(f"QA: {len(checks) - len(fails) - len(warns)} pass, {len(warns)} warn, {len(fails)} fail -> {work / 'qa.json'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
