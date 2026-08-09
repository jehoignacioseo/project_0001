# 바탕화면에 "Insta Content Studio" 바로가기를 만든다.
$ErrorActionPreference = 'Stop'

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$target     = Join-Path $projectDir 'start.bat'
$desktop    = [Environment]::GetFolderPath('Desktop')
$linkPath   = Join-Path $desktop 'Insta Content Studio.lnk'

if (-not (Test-Path $target)) {
  Write-Host ''
  Write-Host '  [!] start.bat 을 찾을 수 없습니다.' -ForegroundColor Red
  Write-Host '      start.bat 과 이 파일이 같은 폴더에 있어야 합니다.'
  Write-Host ''
  Read-Host '  Enter 를 누르면 닫힙니다'
  exit 1
}

$shell    = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath       = $target
$shortcut.WorkingDirectory = $projectDir
$shortcut.IconLocation     = 'shell32.dll,220'
$shortcut.Description      = '인스타그램 콘텐츠 자동 생성 앱'
$shortcut.Save()

Write-Host ''
Write-Host '  완료!' -ForegroundColor Green
Write-Host '  바탕화면의 "Insta Content Studio" 아이콘을 더블클릭하면 앱이 실행됩니다.'
Write-Host ''
Read-Host '  Enter 를 누르면 닫힙니다'
