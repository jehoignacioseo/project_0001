"""Build voiceover.cues from phrase timestamps plus a placement plan.

phrases.json : [{"s": 0.0, "e": 1.1, "txt": "..."}]  (vo_elevenlabs.py output, or silence-split chunks)
plan.json    : [{"seg": 0, "t": 0.1, "ph": [0, 1]}, ...]  seg index or "end"; ph = phrase indices merged into one cue
Each plan entry becomes one cue {s, e, seg, t, txt}. Cues never overlap on the timeline: when a cue's
wanted position (segment start + t) is earlier than the previous cue's end, it is pushed later by `gap`.
Usage: python3 vo_cues.py ../work/EP02/episode.json ../work/EP02/vo_phrases.json ../work/EP02/vo_plan.json [--source vo_all.wav] [--tempo 1.08]
"""
import argparse, json
from pathlib import Path
from vo_align import seg_starts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode"); ap.add_argument("phrases"); ap.add_argument("plan")
    ap.add_argument("--source", help="set voiceover.source (file next to episode.json)")
    ap.add_argument("--tempo", type=float, help="set voiceover.phrase_tempo")
    ap.add_argument("--gap", type=float, default=0.15, help="minimum silence between cues (timeline seconds)")
    a = ap.parse_args()
    ep_path = Path(a.episode); ep = json.loads(ep_path.read_text())
    phrases = json.loads(Path(a.phrases).read_text()); plan = json.loads(Path(a.plan).read_text())
    vo = ep["voiceover"]
    if a.source: vo["source"] = a.source
    if a.tempo: vo["phrase_tempo"] = a.tempo
    tempo = float(vo.get("phrase_tempo", 1.0))
    starts, body = seg_starts(ep)
    cues, prev_end, pushed = [], 0.0, 0.0
    for item in plan:
        ph = [phrases[i] for i in item["ph"]]
        s, e = ph[0]["s"], ph[-1]["e"]
        txt = " ".join(p["txt"] for p in ph)
        base = body if item["seg"] == "end" else starts[int(item["seg"])]
        want = base + float(item["t"])
        at = max(want, prev_end + a.gap)
        pushed = max(pushed, at - want)
        dur = (e - s) / tempo
        cues.append({"s": round(s, 2), "e": round(e, 2), "seg": item["seg"], "t": round(at - base, 2), "txt": txt})
        flag = f"  (+{at - want:.2f}s late)" if at - want > 0.05 else ""
        print(f"{at:6.2f}s seg{str(item['seg']):>3} {dur:4.2f}s  {txt}{flag}")
        prev_end = at + dur
    vo["cues"] = cues
    ep_path.write_text(json.dumps(ep, ensure_ascii=False, indent=1) + "\n")
    limit = body + 3.0  # render.py END_CARD_SEC: narration past this is cut
    warn = "  ** OVER by %.2fs: shorten or lengthen segments **" % (prev_end - limit) if prev_end > limit else ""
    print(f"{len(cues)} cues, speech ends {prev_end:.2f}s, video ends {limit:.2f}s (body {body:.2f}s + 3.0s end card), max push {pushed:.2f}s{warn}")


if __name__ == "__main__":
    main()
