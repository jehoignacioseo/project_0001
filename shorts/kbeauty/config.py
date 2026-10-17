"""Settings for the K-beauty Shorts automation. Everything is overridable with env vars."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIPELINE = ROOT.parent / "pipeline"              # reuse fonts, SFX, caption/overlay helpers
WORK = Path(os.environ.get("KB_WORK", ROOT.parent / "work" / "kbeauty"))
INBOX = Path(os.environ.get("KB_INBOX", ROOT.parent / "inbox"))
PLAYBOOK = ROOT / "playbook.md"
FONTS = PIPELINE / "fonts"
ASSETS = PIPELINE / "assets"

# Claude
MODEL = os.environ.get("KB_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("KB_EFFORT", "high")
MOCK = os.environ.get("KB_MOCK", "") in ("1", "true", "yes")

# Voice: "edge" (free, no key), "elevenlabs" (ELEVENLABS_API_KEY), "mock" (tone + synthetic timings)
TTS_ENGINE = os.environ.get("KB_TTS", "edge")
TTS_VOICE = os.environ.get("KB_VOICE", "en-US-AvaMultilingualNeural")   # edge voice id
TTS_RATE = os.environ.get("KB_TTS_RATE", "+30%")   # ~1.3x: fast, dense delivery
ELEVEN_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "")
ELEVEN_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")

# Footage speech transcription (Korean/English) with faster-whisper; "" disables
WHISPER_MODEL = os.environ.get("KB_WHISPER", "small")

# Output
W, H, FPS = 1080, 1920, 30
PLATFORMS = ("tiktok", "reels", "shorts")
TARGET_SEC = (25, 45)
LANG = os.environ.get("KB_LANG", "en")
USD_PER_KRW = float(os.environ.get("KB_USD_PER_KRW", "0.00072"))

# Safe zones (fraction of H) where platform UI covers the frame
SAFE_TOP, SAFE_BOTTOM = 0.12, 0.26
