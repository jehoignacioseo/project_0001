@echo off
chcp 65001 > nul
title 바탕화면 아이콘 만들기
cd /d "%~dp0"

echo.
echo   바탕화면에 "Insta Content Studio" 바로가기를 만듭니다...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$lnk = $ws.CreateShortcut((Join-Path $desktop 'Insta Content Studio.lnk'));" ^
  "$lnk.TargetPath = (Join-Path '%~dp0' 'start.bat');" ^
  "$lnk.WorkingDirectory = '%~dp0';" ^
  "$lnk.IconLocation = 'shell32.dll,220';" ^
  "$lnk.Description = '인스타그램 콘텐츠 자동 생성 앱';" ^
  "$lnk.Save()"

if errorlevel 1 (
  echo   [!] 바로가기 생성에 실패했습니다.
) else (
  echo   완료! 바탕화면의 "Insta Content Studio" 아이콘을 더블클릭하면 실행됩니다.
)

echo.
pause
