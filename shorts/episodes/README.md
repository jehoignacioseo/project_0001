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
