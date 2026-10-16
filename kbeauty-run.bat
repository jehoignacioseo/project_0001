@echo off
chcp 65001 >nul
REM K-beauty Shorts automation (Windows). Drag a folder of clips onto this file, or run it to watch the inbox.
REM First run: install Python 3.10+ and ffmpeg (winget install Gyan.FFmpeg), then: pip install -r shorts\kbeauty\requirements.txt
REM Set ANTHROPIC_API_KEY (and optional YT_* / IG_* / TIKTOK_* / ELEVENLABS_*) as user environment variables.
cd /d "%~dp0shorts\kbeauty"
if "%~1"=="" (
  python watch.py --inbox "%~dp0shorts\inbox"
) else (
  python run.py "%~1" %2 %3 %4 %5 %6
)
pause
