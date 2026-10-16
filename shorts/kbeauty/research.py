#!/usr/bin/env python3
"""Stage 2 - research the products the footage shows, with web search, so captions and VO carry
real information (ingredients, Korean price vs abroad, Olive Young rank, launch date, who it is for).

footage.json -> products.json      usage: research.py work/<id> [--mock] [--max 3]
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import config

PRODUCT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "name": {"type": "string"}, "brand": {"type": "string"}, "name_ko": {"type": "string"},
        "category": {"type": "string"},
        "price_krw": {"type": ["integer", "null"]}, "price_usd_korea": {"type": ["number", "null"]},
        "price_usd_abroad": {"type": ["number", "null"], "description": "typical US/EU retail (Amazon, YesStyle, Olive Young Global)"},
        "size": {"type": "string"},
        "key_ingredients": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                            "properties": {"name": {"type": "string"}, "what_it_does": {"type": "string", "description": "plain English, no medical claims"}},
                            "required": ["name", "what_it_does"]}},
        "hero_facts": {"type": "array", "items": {"type": "string"}, "description": "3-6 concrete, verified facts a foreigner would not know (rank, launch date, sales count, awards, Korean reviews gist)"},
        "good_for": {"type": "array", "items": {"type": "string"}},
        "skip_if": {"type": "array", "items": {"type": "string"}},
        "how_to_use": {"type": "string"},
        "why_viral": {"type": "string"},
        "where_to_buy": {"type": "array", "items": {"type": "string"}},
        "launched": {"type": "string", "description": "launch month/year in Korea or ''"},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "unverified": {"type": "array", "items": {"type": "string"}, "description": "claims seen online that could not be confirmed; never used on screen"},
        "sources": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["name", "brand", "name_ko", "category", "price_krw", "price_usd_korea", "price_usd_abroad", "size",
                 "key_ingredients", "hero_facts", "good_for", "skip_if", "how_to_use", "why_viral", "where_to_buy",
                 "launched", "caveats", "unverified", "sources", "confidence"],
}

RESEARCH_SYSTEM = """You are a K-beauty product researcher for a short-form channel. Search Korean and English sources
(oliveyoung.co.kr, hwahae, glowpick, brand sites, Olive Young Global, Amazon, YesStyle, Reddit r/AsianBeauty, TikTok/YouTube coverage).
Collect only verifiable facts and keep the URL for each. Priorities: (1) current Korean retail price in KRW and the usual price abroad in
USD, (2) the 2-4 key ingredients and what each does in plain language (no medical claims), (3) proof points foreigners don't know:
Olive Young category rank or awards, units sold, launch date in Korea, what Korean reviewers say, (4) who it suits and who should skip it,
(5) why it went viral. Flag anything you could not confirm as unverified. Today is {today}."""

STRUCTURE_SYSTEM = "Convert research notes into the JSON schema exactly. Put every claim you cannot trace to a source into `unverified`."


def research_product(p, footage_hint):
    import llm
    today = dt.date.today().isoformat()
    q = (f"Product: {p['brand']} {p['name']} ({p.get('name_ko') or 'Hangul unknown'}), category {p.get('category')}.\n"
         f"Seen in footage: {footage_hint}\n"
         "Research it as specified and write organized notes with a source URL after each fact.")
    notes, urls = llm.research(RESEARCH_SYSTEM.format(today=today), q)
    data = llm.structured(STRUCTURE_SYSTEM, f"Notes:\n{notes}\n\nKnown source URLs: {json.dumps(urls)}", PRODUCT_SCHEMA,
                          effort="medium")
    data["sources"] = list(dict.fromkeys(data.get("sources", []) + urls))
    if data.get("price_krw") and not data.get("price_usd_korea"):
        data["price_usd_korea"] = round(data["price_krw"] * config.USD_PER_KRW, 2)
    return data


def mock_product(p):
    return {"name": p["name"], "brand": p["brand"], "name_ko": p.get("name_ko", ""), "category": p.get("category", ""),
            "price_krw": 19900, "price_usd_korea": 14.3, "price_usd_abroad": 26.0, "size": "70 pads",
            "key_ingredients": [{"name": "Heartleaf (Houttuynia cordata) 77%", "what_it_does": "calms redness and soothes irritated skin"},
                                {"name": "PHA", "what_it_does": "gentle exfoliation without the sting of AHA"}],
            "hero_facts": ["No. 1 toner pad in Olive Young's 2025 Awards", "Over 10 million pads sold in Korea",
                           "₩19,900 in Korea vs about $26 on Amazon US"],
            "good_for": ["oily or combination skin", "redness-prone skin"], "skip_if": ["very dry skin that needs rich hydration"],
            "how_to_use": "Swipe the textured side over the face after cleansing, pat the rest in.",
            "why_viral": "Korean pharmacists and Olive Young's ranking sticker made it the default 'first toner pad'.",
            "where_to_buy": ["Olive Young Korea", "Olive Young Global", "Amazon US"], "launched": "2023",
            "caveats": ["Patch test if you react to botanical extracts"], "unverified": ["'cures acne' claims seen on TikTok"],
            "sources": ["https://global.oliveyoung.com/"], "confidence": "medium"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--max", type=int, default=3)
    a = ap.parse_args()
    work = Path(a.work)
    footage = json.loads((work / "footage.json").read_text(encoding="utf-8"))
    prods = sorted(footage["detected_products"], key=lambda p: (not p.get("hero"), {"high": 0, "medium": 1, "low": 2}[p["confidence"]]))
    prods = [p for p in prods if p["confidence"] != "low" or p.get("hero")][: a.max]
    mock = a.mock or config.MOCK
    out = {"researched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "products": []}
    for p in prods:
        print(f"researching {p['brand']} {p['name']} ...")
        hint = p.get("evidence", "")
        data = mock_product(p) if mock else research_product(p, hint)
        data["hero"] = bool(p.get("hero"))
        out["products"].append(data)
    (work / "products.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {work / 'products.json'} ({len(out['products'])} products)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
