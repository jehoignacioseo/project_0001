"""Record an episode voiceover with ElevenLabs and emit phrase timestamps for re-cueing.

Reads a script file whose first line is a config line, e.g.
  Voice: Liam (TX3LPaxmHKxFdv7VOQHJ) or Brian (nPczCjzI2devNBz1zQrb); model eleven_v3; stability 0.4, similarity 0.75, style 0.3, speed 1.05
followed by the narration paragraphs. Writes next to the script (or --out):
  vo_all.mp3        the take
  vo_all.wav        48 kHz stereo copy (what episode.json voiceover.source points at)
  vo_phrases.json   [{s, e, txt}] per sentence, from ElevenLabs character alignment
Then set voiceover.source = "vo_all.wav" in episode.json, copy s/e into the cues, and run vo_align.py.

Auth: ELEVENLABS_API_KEY if set; otherwise the request is sent without a key and relies on the
session's proxy to inject one (cloud sessions). `--check` only verifies auth and exits.
Usage: python3 vo_elevenlabs.py ../episodes/EP02/vo_script_elevenlabs.txt [--voice brian] [--check]
"""
import argparse, base64, json, os, re, sys
from pathlib import Path

import requests

from common import run

API = "https://api.elevenlabs.io/v1"
VOICES = {"liam": "TX3LPaxmHKxFdv7VOQHJ", "brian": "nPczCjzI2devNBz1zQrb"}
V3_STABILITY = (0.0, 0.5, 1.0)  # eleven_v3 only accepts Creative / Natural / Robust


def headers():
    h = {"Accept": "application/json"}
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        h["xi-api-key"] = key
    return h


def parse_script(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    cfg_line = lines[0] if lines and lines[0].lower().startswith("voice:") else ""
    body = "\n".join(lines[1:] if cfg_line else lines).strip()
    cfg = {"voice_id": VOICES["liam"], "model": "eleven_v3",
           "stability": 0.5, "similarity": 0.75, "style": 0.3, "speed": 1.0}
    m = re.search(r"\(([A-Za-z0-9]{15,})\)", cfg_line)
    if m:
        cfg["voice_id"] = m.group(1)
    m = re.search(r"model\s+([\w.-]+)", cfg_line)
    if m:
        cfg["model"] = m.group(1)
    for key in ("stability", "similarity", "style", "speed"):
        m = re.search(rf"{key}\s+([0-9.]+)", cfg_line)
        if m:
            cfg[key] = float(m.group(1))
    return cfg, body


def check_auth():
    r = requests.get(f"{API}/user", headers=headers(), timeout=30)
    if r.status_code == 200:
        u = r.json()
        sub = u.get("subscription", {})
        print(f"auth ok: tier={sub.get('tier')} chars={sub.get('character_count')}/{sub.get('character_limit')}")
        return True
    detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
    print(f"auth FAILED ({r.status_code}): {detail}", file=sys.stderr)
    if r.status_code == 401:
        print("-> no ElevenLabs key reached the API. Set ELEVENLABS_API_KEY in the environment "
              "(cloud: environment settings -> Network secrets / env vars) and start a new session.",
              file=sys.stderr)
    return False


def phrases_from_alignment(al):
    """Split character alignment into sentences; returns [{s, e, txt}]."""
    chars, starts, ends = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    out, buf, s0 = [], [], None
    text = "".join(chars)
    for i, ch in enumerate(chars):
        if s0 is None and not ch.isspace():
            s0 = starts[i]
        buf.append(ch)
        end_of_sentence = ch in ".?!" and (i + 1 == len(chars) or chars[i + 1].isspace()) and not text[max(0, i - 2):i + 1] == "..."
        if ch == "\n" or end_of_sentence:
            txt = "".join(buf).strip()
            if txt:
                out.append({"s": round(s0, 2), "e": round(ends[i], 2), "txt": txt})
            buf, s0 = [], None
    txt = "".join(buf).strip()
    if txt:
        out.append({"s": round(s0, 2), "e": round(ends[-1], 2), "txt": txt})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--voice", help="liam | brian | <voice_id>")
    ap.add_argument("--model")
    ap.add_argument("--stability", type=float)
    ap.add_argument("--speed", type=float)
    ap.add_argument("--out", help="output directory (default: next to the script)")
    ap.add_argument("--name", default="vo_all", help="output basename (default vo_all)")
    ap.add_argument("--check", action="store_true", help="only verify the API connection")
    a = ap.parse_args()

    if not check_auth():
        sys.exit(2)
    if a.check:
        return

    cfg, text = parse_script(a.script)
    if a.voice:
        cfg["voice_id"] = VOICES.get(a.voice.lower(), a.voice)
    if a.model:
        cfg["model"] = a.model
    if a.stability is not None:
        cfg["stability"] = a.stability
    if a.speed is not None:
        cfg["speed"] = a.speed
    if cfg["model"].startswith("eleven_v3") and cfg["stability"] not in V3_STABILITY:
        snapped = min(V3_STABILITY, key=lambda v: abs(v - cfg["stability"]))
        print(f"note: {cfg['model']} only accepts stability {V3_STABILITY}; using {snapped} instead of {cfg['stability']}")
        cfg["stability"] = snapped

    out_dir = Path(a.out) if a.out else Path(a.script).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    body = {
        "text": text,
        "model_id": cfg["model"],
        "voice_settings": {
            "stability": cfg["stability"],
            "similarity_boost": cfg["similarity"],
            "style": cfg["style"],
            "speed": cfg["speed"],
            "use_speaker_boost": True,
        },
    }
    print(f"voice={cfg['voice_id']} model={cfg['model']} settings={body['voice_settings']} chars={len(text)}")
    r = requests.post(f"{API}/text-to-speech/{cfg['voice_id']}/with-timestamps",
                      params={"output_format": "mp3_44100_128"}, headers={**headers(), "Content-Type": "application/json"},
                      json=body, timeout=300)
    if r.status_code != 200:
        print(f"TTS failed ({r.status_code}): {r.text[:1500]}", file=sys.stderr)
        sys.exit(1)
    res = r.json()
    mp3 = out_dir / f"{a.name}.mp3"
    wav = out_dir / f"{a.name}.wav"
    mp3.write_bytes(base64.b64decode(res["audio_base64"]))
    run(["ffmpeg", "-y", "-v", "error", "-i", str(mp3), "-ar", "48000", "-ac", "2", str(wav)])
    phrases = phrases_from_alignment(res["alignment"])
    (out_dir / f"{a.name.replace('vo_all', 'vo')}_phrases.json").write_text(json.dumps(phrases, ensure_ascii=False, indent=1), encoding="utf-8")
    for p in phrases:
        print(f"{p['s']:6.2f} - {p['e']:6.2f}  {p['txt']}")
    print(f"wrote {mp3}, {wav} ({phrases[-1]['e'] if phrases else 0:.1f}s), {len(phrases)} phrases")


if __name__ == "__main__":
    main()
