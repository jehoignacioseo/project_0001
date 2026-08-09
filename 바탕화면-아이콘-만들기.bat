@echo off
chcp 65001 > nul
title 바탕화면 아이콘 만들기
cd /d "%~dp0"

echo.
echo   바탕화면에 "Insta Content Studio" 바로가기를 만듭니다...

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make-shortcut.ps1"
