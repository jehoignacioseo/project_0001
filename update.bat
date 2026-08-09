@echo off
chcp 65001 > nul
title Insta Content Studio 업데이트
cd /d "%~dp0"

echo.
echo   ==========================================
echo      Insta Content Studio 업데이트
echo   ==========================================
echo.

if not exist "package.json" (
  echo   [!] 이 파일은 프로젝트 폴더 안에 있어야 합니다.
  echo       package.json 파일이 보이는 폴더에 넣고 다시 실행해 주세요.
  goto :done
)

set "ZIPURL=https://github.com/jehoignacioseo/project_0001/archive/refs/heads/claude/instagram-auto-content-generator-da6c5j.zip"
set "TMPZIP=%TEMP%\ics-latest.zip"
set "TMPDIR=%TEMP%\ics-latest"
set "SRCDIR=%TMPDIR%\project_0001-claude-instagram-auto-content-generator-da6c5j"

echo   [1/4] 최신 버전을 내려받는 중...
if exist "%TMPZIP%" del /q "%TMPZIP%"
curl -L -s -o "%TMPZIP%" "%ZIPURL%"
if not exist "%TMPZIP%" (
  echo   [!] 다운로드에 실패했습니다. 인터넷 연결을 확인해 주세요.
  goto :done
)

echo   [2/4] 압축을 푸는 중...
if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
mkdir "%TMPDIR%"
tar -xf "%TMPZIP%" -C "%TMPDIR%"
if not exist "%SRCDIR%\package.json" (
  echo   [!] 압축 풀기에 실패했습니다.
  goto :done
)

echo   [3/4] 파일을 교체하는 중...
REM update.bat 은 지금 실행 중이라 교체 대상에서 제외한다.
if exist "%SRCDIR%\update.bat" del /q "%SRCDIR%\update.bat"
xcopy "%SRCDIR%\*" "%~dp0" /E /Y /Q /I > nul
if errorlevel 1 (
  echo   [!] 파일 교체에 실패했습니다.
  goto :done
)

echo   [4/4] 필요한 패키지를 확인하는 중...
call npm install --no-audit --no-fund
if errorlevel 1 (
  echo   [!] 패키지 설치에 실패했습니다.
  goto :done
)

echo.
echo   업데이트 완료!
echo   앱이 켜져 있었다면 검은 창을 닫고, 바탕화면 아이콘으로 다시 실행하세요.

:done
if exist "%TMPZIP%" del /q "%TMPZIP%"
if exist "%TMPDIR%" rmdir /s /q "%TMPDIR%"
echo.
pause
