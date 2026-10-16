#!/usr/bin/env python3
"""Stage 4 - AI voice. One audio file per narration line with word-level timestamps, so captions can be
karaoke-synced to the voice.

engines: edge (Microsoft neural voices, free, word boundaries), elevenlabs (ELEVENLABS_API_KEY, timestamps API),
         mock (silence + evenly spaced timings, for offline tests)
episode.json -> vo/line_NN.mp3 + vo/lines.json      usage: tts.py work/<id> [--engine edge|elevenlabs|mock] [--voice id]
"""
import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from common import ensure_dir, ffprobe, run  # noqa: E402

import config  # noqa: E402

WORD_RE = re.compile(r"[A-Za-z0-9₩$%'’.,\-]+|[가-힯]+")


def _norm_words(text):
    return [w for w in text.replace("—", " ").split() if w.strip()]


def edge_line(text, voice, rate, out):
    import edge_tts

    async def go():
        com = edge_tts.Communicate(text, voice, rate=rate)
        words = []
        with open(out, "wb") as f:
            async for ch in com.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] == "WordBoundary":
                    words.append({"w": ch["text"], "s": ch["offset"] / 1e7, "e": (ch["offset"] + ch["duration"]) / 1e7})
        return words
    return asyncio.run(go())


def eleven_line(text, voice, out):
    import requests
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key or not voice:
        sys.exit("ELEVENLABS_API_KEY / ELEVENLABS_VOICE_ID missing")
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
                      headers={"xi-api-key": key}, json={"text": text, "model_id": config.ELEVEN_MODEL,
                                                         "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35}},
                      timeout=120)
    r.raise_for_status()
    j = r.json()
    import base64
    Path(out).write_bytes(base64.b64decode(j["audio_base64"]))
    al = j["alignment"]
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, s0 = [], "", None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": s0, "e": e}); cur, s0 = "", None
            continue
        if s0 is None:
            s0 = s
        cur += ch
        last_e = e
    if cur:
        words.append({"w": cur, "s": s0, "e": last_e})
    return words


def mock_line(text, out):
    words = _norm_words(text)
    dur = max(0.8, len(words) / 2.7 + 0.25)
    run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", f"{dur:.2f}", "-i", "sine=frequency=330:sample_rate=48000",
         "-af", "volume=0.08,atempo=1.0", "-c:a", "libmp3lame", "-q:a", "4", str(out)])
    step = (dur - 0.25) / max(1, len(words))
    return [{"w": w, "s": round(i * step, 3), "e": round((i + 1) * step - 0.02, 3)} for i, w in enumerate(words)]


def whisper_words(path):
    """Word timestamps from the rendered voice itself (used when the engine gives none)."""
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(config.WHISPER_MODEL or "base", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(path), word_timestamps=True, language="en" if config.LANG == "en" else None)
        return [{"w": w.word.strip(), "s": float(w.start), "e": float(w.end)} for s in segs for w in s.words]
    except Exception as e:
        print(f"  whisper alignment unavailable: {e}", file=sys.stderr)
        return []


def _even_words(text, dur):
    script = _norm_words(text)
    step = max(dur - 0.15, 0.3) / max(1, len(script))
    return [{"w": w, "s": round(i * step, 3), "e": round((i + 1) * step - 0.02, 3)} for i, w in enumerate(script)]


def _align_words(words, text, audio=None):
    """Make sure timing words line up with the script words (engines may split punctuation).
    No timings at all -> transcribe the voice with faster-whisper; still nothing -> even spacing."""
    script = _norm_words(text)
    if not words and audio is not None:
        words = whisper_words(audio)
        if not words:
            return _even_words(text, ffprobe_audio(audio))
    if len(words) == len(script):
        return [{"w": sw, "s": tw["s"], "e": tw["e"]} for sw, tw in zip(script, words)]
    if not words:
        return []
    # fallback: distribute script words over the spoken span
    s0, e1 = words[0]["s"], words[-1]["e"]
    step = (e1 - s0) / max(1, len(script))
    return [{"w": w, "s": round(s0 + i * step, 3), "e": round(s0 + (i + 1) * step - 0.02, 3)} for i, w in enumerate(script)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work")
    ap.add_argument("--engine", default=None)
    ap.add_argument("--voice", default=None)
    ap.add_argument("--rate", default=config.TTS_RATE)
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    engine = "mock" if (a.mock or config.MOCK) else (a.engine or config.TTS_ENGINE)
    voice = a.voice or (config.ELEVEN_VOICE if engine == "elevenlabs" else config.TTS_VOICE)
    work = Path(a.work)
    ep = json.loads((work / "episode.json").read_text(encoding="utf-8"))
    vo_dir = ensure_dir(work / "vo")
    lines = []
    for i, seg in enumerate(ep["segments"]):
        text = (seg.get("vo") or "").strip()
        if not text and i == len(ep["segments"]) - 1:
            text = (ep.get("cta", {}).get("vo") or "").strip()
        if not text:
            continue
        out = vo_dir / f"line_{i:02d}.mp3"
        if engine == "edge":
            words = edge_line(text, voice, a.rate, out)
        elif engine == "elevenlabs":
            words = eleven_line(text, voice, out)
        else:
            words = mock_line(text, out)
        words = _align_words(words, text, out)
        dur = ffprobe_audio(out)
        lines.append({"seg": i, "text": text, "file": str(out.relative_to(work)), "duration": round(dur, 3), "words": words})
        print(f"  seg {i}: {dur:.2f}s  {text[:60]}")
    meta = {"engine": engine, "voice": voice, "rate": a.rate, "lines": lines}
    (vo_dir / "lines.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {vo_dir / 'lines.json'} ({len(lines)} lines, engine={engine})")
    return 0


def ffprobe_audio(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.strip() or 0)


if __name__ == "__main__":
    sys.exit(main())
