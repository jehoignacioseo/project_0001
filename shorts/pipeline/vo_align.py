"""Place voiceover phrases on the cut timeline.

episode.json -> voiceover.cues = [{s, e, seg, t}]: take vo source seconds [s, e),
speed it up by phrase_tempo, and start it at (segment `seg` start + t). seg may be
"end" for the end card. Writes voiceover.file (wav) next to episode.json.
Usage: python3 vo_align.py ../work/S1-01/episode.json
"""
import json, sys
from pathlib import Path
from common import run

def seg_starts(ep):
    t, starts = 0.0, []
    for s in ep["segments"]:
        starts.append(t)
        t += (float(s["out"]) - float(s["in"])) / float(s.get("speed", 1.0))
    return starts, t

def main(path):
    ep_path = Path(path).resolve(); ep_dir = ep_path.parent
    ep = json.loads(ep_path.read_text())
    vo = ep["voiceover"]; cues = vo["cues"]; tempo = float(vo.get("phrase_tempo", 1.0))
    starts, body = seg_starts(ep)
    src = ep_dir / vo["source"]; out = ep_dir / vo["file"]
    chain, labels = "", []
    for i, c in enumerate(cues):
        base = body if c["seg"] == "end" else starts[int(c["seg"])]
        at = int(round((base + float(c["t"])) * 1000))
        dur = (c["e"] - c["s"]) / tempo
        chain += (f"[0:a]atrim={c['s']}:{c['e']},asetpts=PTS-STARTPTS,atempo={tempo},"
                  f"afade=t=in:d=0.02,afade=t=out:st={max(dur-0.03,0):.3f}:d=0.03,"
                  f"adelay={at}|{at}[p{i}];")
        labels.append(f"[p{i}]")
        print(f"{base + c['t']:6.2f}s  {dur:4.2f}s  {c.get('txt','')}")
    chain += "".join(labels) + f"amix=inputs={len(cues)}:normalize=0:dropout_transition=0,apad=whole_dur={body + 3.5:.2f}[vo]"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-filter_complex", chain, "-map", "[vo]",
         "-ar", "48000", "-ac", "2", str(out)])
    print("wrote", out)

if __name__ == "__main__":
    main(sys.argv[1])
