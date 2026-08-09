@echo off
chcp 65001 > nul
title Insta Content Studio 업데이트
cd /d "%~dp0"
set "ICSDIR=%~dp0"
if "%ICSDIR:~-1%"=="\" set "ICSDIR=%ICSDIR:~0,-1%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ICSDIR%\update.ps1" -ProjectDir "%ICSDIR%"
