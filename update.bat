@echo off
chcp 65001 > nul
title Insta Content Studio 업데이트
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" -ProjectDir "%~dp0"
