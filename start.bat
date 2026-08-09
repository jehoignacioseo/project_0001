@echo off
chcp 65001 > nul
title Insta Content Studio
cd /d "%~dp0"

echo.
echo   ==========================================
echo      Insta Content Studio
echo   ==========================================
echo.

where node >nul 2>nul
if errorlevel 1 (
  echo   [!] Node.js 가 설치되어 있지 않습니다.
  echo       https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행해 주세요.
  echo.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo   처음 실행이라 필요한 파일을 설치합니다. 1~2분 걸립니다...
  echo.
  call npm install
  if errorlevel 1 (
    echo.
    echo   [!] 설치에 실패했습니다. 인터넷 연결을 확인해 주세요.
    pause
    exit /b 1
  )
  echo.
)

echo   앱을 켜는 중입니다. 잠시 후 브라우저가 자동으로 열립니다.
echo.
echo   이 창을 닫으면 앱이 종료됩니다.
echo.

start "" /b cmd /c "timeout /t 8 /nobreak > nul & start http://localhost:3000"

call npm run dev

echo.
echo   앱이 종료되었습니다.
pause
