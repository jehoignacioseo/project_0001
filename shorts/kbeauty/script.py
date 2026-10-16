#!/usr/bin/env python3
"""Stage 3 - the AI editor writes the episode: format choice, hook, cut list, VO lines per cut,
info cards, verdict, CTA, platform captions, cover text and alternative hooks.

footage.json + products.json + playbook.md -> episode.json      usage: script.py work/<id> [--mock] [--lang en]
"""
import argparse
import json
import re
import sys
from pathlib import Path

import config

EPISODE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "format": {"type": "string", "description": "one of the playbook formats"},
        "hook_type": {"type": "string"},
        "title_band": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2,
                       "description": "2 short lines shown during the hook (<= 22 chars each, caps for the key word)"},
        "hook_alternatives": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        "segments": {"type": "array", "minItems": 4, "maxItems": 14, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "src": {"type": "string", "description": "clip file name"},
                "in": {"type": "number"}, "out": {"type": "number"},
                "speed": {"type": "number", "minimum": 0.5, "maximum": 2.0},
                "zoom": {"type": "number", "minimum": 1.0, "maximum": 1.6, "description": "punch-in on closeups"},
                "crop_x": {"type": "number", "minimum": 0, "maximum": 1}, "crop_y": {"type": "number", "minimum": 0, "maximum": 1},
                "whoosh": {"type": "boolean", "description": "true when this cut is a scene change"},
                "amb_gain_db": {"type": "number", "description": "natural sound level under the VO: -14 default, -6 for texture ASMR shots"},
                "vo": {"type": "string", "description": "the narration spoken over this cut; '' for pure ASMR cuts. 6-18 words."},
                "purpose": {"type": "string", "enum": ["hook", "context", "fact", "texture", "proof", "verdict", "cta"]},
            },
            "required": ["src", "in", "out", "speed", "zoom", "crop_x", "crop_y", "whoosh", "amb_gain_db", "vo", "purpose"],
        }},
        "cards": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "type": {"type": "string", "enum": ["price", "product", "fact", "ingredients", "verdict"]},
                "seg": {"type": "integer"}, "t": {"type": "number", "description": "seconds after the segment starts"},
                "d": {"type": "number", "description": "seconds on screen (2-4)"},
                "title": {"type": "string"}, "lines": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
            },
            "required": ["type", "seg", "t", "d", "title", "lines"],
        }},
        "emphasis": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"seg": {"type": "integer"}, "t": {"type": "number"}, "d": {"type": "number"},
                           "text": {"type": "string", "description": "1-3 words, e.g. 'SOLD OUT' or '₩19,900'"},
                           "style": {"type": "string", "enum": ["shout", "price", "pop"]}},
            "required": ["seg", "t", "d", "text", "style"],
        }},
        "verdict": {"type": "string"},
        "cta": {"type": "object", "additionalProperties": False,
                "properties": {"on_screen": {"type": "string"}, "vo": {"type": "string"}}, "required": ["on_screen", "vo"]},
        "music_gain_db": {"type": "number"},
        "platforms": {"type": "object", "additionalProperties": False, "properties": {
            "tiktok": {"type": "object", "additionalProperties": False, "properties": {"caption": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}}}, "required": ["caption", "hashtags"]},
            "reels": {"type": "object", "additionalProperties": False, "properties": {"caption": {"type": "string"}, "hashtags": {"type": "array", "items": {"type": "string"}}}, "required": ["caption", "hashtags"]},
            "shorts": {"type": "object", "additionalProperties": False, "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "description", "tags"]},
        }, "required": ["tiktok", "reels", "shorts"]},
        "cover_text": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 2},
        "pinned_comment": {"type": "string", "description": "first comment with where-to-buy + price, posted by the channel"},
        "facts_used": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                       "properties": {"claim": {"type": "string"}, "source": {"type": "string"}}, "required": ["claim", "source"]}},
        "editor_notes": {"type": "string", "description": "why this format/hook was chosen given the footage; what to film next time"},
    },
    "required": ["id", "format", "hook_type", "title_band", "hook_alternatives", "segments", "cards", "emphasis", "verdict", "cta",
                 "music_gain_db", "platforms", "cover_text", "pinned_comment", "facts_used", "editor_notes"],
}

SYSTEM_TMPL = """You are the editor-in-chief and scriptwriter of a K-beauty short-form channel for non-Korean viewers.
You turn analysed phone footage plus researched product facts into one complete episode: TikTok / Reels / Shorts, 25-45 seconds,
vertical. You pick the cuts (clip file + in/out seconds), write the narration line for each cut, place information cards, and write the
platform metadata. You never invent facts: every number, ingredient, rank, date or price must appear in products.json or be visible in
the footage (footage.json visible_text / price_krw). Speak in {lang}.

Follow the playbook below strictly; it encodes what the platforms reward right now.

<playbook>
{playbook}
</playbook>

Cutting rules:
- Only use scenes marked usable. The first segment must be the scene with the highest hook_potential that fits the hook, 1.5-3.0s long.
- A cut lasts 2-4.5s unless it is a texture/ASMR hold (<= 5s). The narration for a cut must fit it: ~2.6 words per second at 1.08x.
  If a line is longer than its cut, make the cut longer (within the scene's start/end) or split the line across two cuts.
- Vary shot types across consecutive cuts (closeup -> shelf -> price -> texture). Use zoom 1.15-1.3 on closeups for a punch-in.
- Landscape clips: choose crop_x to keep the product centered.
- Cards: 1 price card when a price is known, 1 product card (brand + name + Hangul + size), 1 ingredients card (2-3 items), optional
  fact card. Cards show 2.5-3.5s and must not overlap each other. Emphasis words only at reveals (price, sold out, #1).
- End: verdict cut (who it is for / skip if) then a CTA cut with one specific ask. Total 25-45s of segments.
- Metadata: TikTok caption <=150 chars with a question; Reels caption starts with the hook; Shorts title <=60 chars; description lists
  prices and facts and ends with "Voice: AI narration". Hashtags without '#'. Pinned comment: where to buy + Korean price + abroad price.
- id: a short slug from the hero product and today, e.g. anua-toner-pad-1016."""


def _footage_brief(footage):
    lines = [f"Store: {footage.get('store')}", f"Angle: {footage.get('footage_angle')}", f"Filmer note: {footage.get('user_note', '')}"]
    for c in footage["clips"]:
        lines.append(f"\nclip {c['file']} dur={c.get('duration', 0):.1f}s {'portrait' if c.get('portrait') else 'landscape'}"
                     + (f" speech={c['speech']}" if c.get("speech") else ""))
        for s in c["scenes"]:
            if "start" not in s:
                continue
            lines.append(f"  scene {s['index']} {s['start']}-{s['end']}s {s['shot_type']} usable={s['usable']} hook={s['hook_potential']}: "
                         f"{s['description']}" + (f" | text: {s['visible_text']}" if s["visible_text"] else "")
                         + (f" | ₩{s['price_krw']:,}" if s.get("price_krw") else ""))
    return "\n".join(lines)


def write_with_claude(footage, products, lang):
    import llm
    system = SYSTEM_TMPL.format(lang=lang, playbook=config.PLAYBOOK.read_text(encoding="utf-8"))
    user = (f"<footage>\n{_footage_brief(footage)}\n</footage>\n\n<products>\n{json.dumps(products, ensure_ascii=False, indent=1)}\n</products>\n\n"
            "Write the episode JSON.")
    return llm.structured(system, user, EPISODE_SCHEMA, max_tokens=20000)


def mock_episode(footage, products):
    usable = [(c, s) for c in footage["clips"] for s in c["scenes"] if s.get("usable") and "start" in s]
    usable.sort(key=lambda cs: -cs[1]["hook_potential"])
    p = products["products"][0]
    vo = ["This toner pad sold out three times. Here is why.",
          "It is number one in Korea's biggest beauty store, and it costs nineteen thousand won here.",
          "Seventy-seven percent heartleaf, which calms redness, plus a gentle exfoliant.",
          "", "Swipe once after cleansing, then pat the rest in.",
          "Great if your skin is oily or red. Skip it if you are very dry.",
          "Save this for your Seoul trip, and comment your skin type."]
    purposes = ["hook", "proof", "fact", "texture", "fact", "verdict", "cta"]
    segs = []
    for i, (c, s) in enumerate((usable * 3)[:7]):
        d = min(3.6, s["end"] - s["start"])
        segs.append({"src": c["file"], "in": s["start"], "out": round(s["start"] + d, 2), "speed": 1.0,
                     "zoom": 1.2 if s["shot_type"] == "product_closeup" else 1.0, "crop_x": 0.5, "crop_y": 0.5,
                     "whoosh": i in (1, 3, 5), "amb_gain_db": -6 if purposes[i] == "texture" else -14,
                     "vo": vo[i], "purpose": purposes[i]})
    return {"id": "mock-anua-pad", "format": "retail proof", "hook_type": "proof",
            "title_band": ["SOLD OUT 3 TIMES", "at Olive Young"], "hook_alternatives": ["₩19,900 here, $26 in the US", "Koreans' #1 toner pad", "Stop buying toner pads until you see this"],
            "segments": segs,
            "cards": [{"type": "price", "seg": 1, "t": 0.4, "d": 3.0, "title": "KOREA PRICE", "lines": ["₩19,900 ≈ $14", "Amazon US: $26"]},
                      {"type": "product", "seg": 2, "t": 0.3, "d": 3.0, "title": "Anua", "lines": ["Heartleaf 77% Toner Pad", "아누아 어성초 77 토너패드", "70 pads"]},
                      {"type": "ingredients", "seg": 4, "t": 0.3, "d": 3.0, "title": "KEY INGREDIENTS", "lines": ["Heartleaf 77% · calms redness", "PHA · gentle exfoliation"]},
                      {"type": "verdict", "seg": 5, "t": 0.3, "d": 3.0, "title": "VERDICT", "lines": ["✅ oily / redness-prone", "❌ very dry skin"]}],
            "emphasis": [{"seg": 1, "t": 0.1, "d": 1.4, "text": "#1", "style": "shout"}],
            "verdict": "Great for oily or redness-prone skin; skip if very dry.",
            "cta": {"on_screen": "Comment your skin type 👇", "vo": vo[-1]}, "music_gain_db": -21,
            "platforms": {"tiktok": {"caption": "Koreans' #1 toner pad, ₩19,900 here. What's your skin type?", "hashtags": ["kbeauty", "oliveyoung", "koreanskincare", "anua", "tonerpad"]},
                          "reels": {"caption": "Sold out 3 times at Olive Young. Save this for your Seoul trip.", "hashtags": ["kbeauty", "koreanskincare", "oliveyoung", "anua", "seoul", "skincareroutine"]},
                          "shorts": {"title": "Korea's #1 toner pad costs $14 here (not $26)", "description": "Anua Heartleaf 77% Toner Pad at Olive Young.\n₩19,900 (~$14) in Korea vs ~$26 on Amazon US.\nHeartleaf 77% calms redness; PHA exfoliates gently.\nVoice: AI narration\n#Shorts #kbeauty", "tags": ["kbeauty", "anua", "olive young", "toner pad"]}},
            "cover_text": ["SOLD OUT", "3 TIMES"], "pinned_comment": "Anua Heartleaf 77% Toner Pad · ₩19,900 (~$14) at Olive Young Korea · ~$26 on Amazon US / Olive Young Global",
            "facts_used": [{"claim": "₩19,900", "source": "footage price tag"}, {"claim": "Olive Young #1", "source": "mock"}],
            "editor_notes": "mock episode"}


def validate(ep, footage):
    """Clamp cut times into real scene ranges and drop references to unknown clips."""
    clips = {c["file"]: c for c in footage["clips"]}
    good = []
    for s in ep["segments"]:
        c = clips.get(s["src"])
        if not c:
            print(f"  dropping segment: unknown clip {s['src']}", file=sys.stderr)
            continue
        dur = float(c.get("duration", 0))
        s["in"] = max(0.0, min(float(s["in"]), max(0.0, dur - 0.5)))
        s["out"] = max(s["in"] + 0.8, min(float(s["out"]), dur))
        good.append(s)
    if len(good) < 3:
        raise SystemExit("episode has fewer than 3 valid segments")
    ep["segments"] = good
    n = len(good)
    ep["cards"] = [c for c in ep["cards"] if 0 <= c["seg"] < n]
    ep["emphasis"] = [e for e in ep["emphasis"] if 0 <= e["seg"] < n]
    ep["id"] = re.sub(r"[^a-z0-9-]+", "-", ep["id"].lower()).strip("-") or "episode"
    return ep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--lang", default=config.LANG)
    a = ap.parse_args()
    work = Path(a.work)
    footage = json.loads((work / "footage.json").read_text(encoding="utf-8"))
    products = json.loads((work / "products.json").read_text(encoding="utf-8"))
    ep = mock_episode(footage, products) if (a.mock or config.MOCK) else write_with_claude(footage, products, a.lang)
    ep = validate(ep, footage)
    ep["lang"] = a.lang
    (work / "episode.json").write_text(json.dumps(ep, indent=2, ensure_ascii=False), encoding="utf-8")
    body = sum((s["out"] - s["in"]) / s["speed"] for s in ep["segments"])
    print(f"wrote {work / 'episode.json'}: {ep['id']} format={ep['format']} {len(ep['segments'])} cuts ~{body:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
