# Episode designs (tracked copies of shorts/work/<ep>/)
Raw clips live in shorts/work/<ep>_raw/ (not tracked). To rebuild an episode in a new session:
1. Put the clips in shorts/work/EP02_raw/ (IMG_1853–1876.mov).
2. cp shorts/episodes/EP02/* shorts/work/EP02/
3. cd shorts/pipeline && python3 vo_align.py ../work/EP02/episode.json && python3 render.py ../work/EP02/episode.json --shorts
vo*.mp3 are the Seed Audio takes (Dylan). For the ElevenLabs re-record, replace voiceover.source and re-cue.
EP02 ElevenLabs script: see shorts/episodes/EP02/vo_script_elevenlabs.txt
ElevenLabs re-record (needs ELEVENLABS_API_KEY in the environment):
  cd shorts/pipeline && python3 vo_elevenlabs.py ../episodes/EP02/vo_script_elevenlabs.txt --check   # auth only
  python3 vo_elevenlabs.py ../work/EP02/vo_script_elevenlabs.txt [--voice brian]                    # writes vo_all.mp3/.wav + vo_phrases.json
  then voiceover.source = "vo_all.wav", copy s/e from vo_phrases.json into the cues, vo_align.py, render.py

EP02 ElevenLabs take (Liam, eleven_v4, via the ElevenLabs connector flow): vo_liam_v4.mp3, 60.7s.
vo_words.json = Scribe word timestamps, vo_phrases.json = 45 phrases, vo_plan.json = phrase -> segment placement.
Rebuild cues: cd shorts/pipeline && python3 vo_cues.py ../work/EP02/episode.json ../work/EP02/vo_phrases.json ../work/EP02/vo_plan.json
then vo_align.py and render.py --shorts. episode.json here already carries the resulting cues (source vo_liam_v4.mp3, tempo 1.15).
