# Insta Content Studio 자동 업데이트
# GitHub에서 최신 코드를 내려받아 프로젝트 폴더에 덮어쓴다.
# data 폴더(설정/게시물)와 node_modules 는 저장소에 없으므로 그대로 보존된다.
param([string]$ProjectDir)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8

if (-not $ProjectDir) { $ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
$ProjectDir = $ProjectDir.Trim().TrimEnd('\', '"')

$zipUrl  = 'https://github.com/jehoignacioseo/project_0001/archive/refs/heads/claude/instagram-auto-content-generator-da6c5j.zip'
$tempDir = Join-Path $env:TEMP ('ics-update-' + [Guid]::NewGuid().ToString('N'))
$zipPath = Join-Path $tempDir 'latest.zip'

try {
  if (-not (Test-Path (Join-Path $ProjectDir 'package.json'))) {
    throw "프로젝트 폴더를 찾지 못했습니다: $ProjectDir"
  }

  Write-Host ''
  Write-Host '  최신 버전을 내려받는 중...' -ForegroundColor Cyan
  New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
  $ProgressPreference = 'SilentlyContinue'
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing

  Write-Host '  압축을 푸는 중...' -ForegroundColor Cyan
  Expand-Archive -Path $zipPath -DestinationPath $tempDir -Force

  $src = Get-ChildItem -Path $tempDir -Directory | Select-Object -First 1
  if (-not $src) { throw '내려받은 파일에서 소스 폴더를 찾지 못했습니다.' }

  Write-Host '  파일을 교체하는 중...' -ForegroundColor Cyan
  # update.bat 은 지금 실행 중이라 건드리지 않는다 (내용이 거의 바뀌지 않음).
  Get-ChildItem -Path $src.FullName -Force |
    Where-Object { $_.Name -ne 'update.bat' } |
    ForEach-Object { Copy-Item -Path $_.FullName -Destination $ProjectDir -Recurse -Force }

  Write-Host '  필요한 패키지를 확인하는 중... (변경이 없으면 금방 끝납니다)' -ForegroundColor Cyan
  Push-Location $ProjectDir
  & npm.cmd install --no-audit --no-fund
  Pop-Location

  Write-Host ''
  Write-Host '  업데이트 완료!' -ForegroundColor Green
  Write-Host '  앱이 켜져 있었다면 검은 창을 닫고, 바탕화면 아이콘으로 다시 실행하세요.'
}
catch {
  Write-Host ''
  Write-Host ('  [!] 업데이트 실패: ' + $_.Exception.Message) -ForegroundColor Red
  Write-Host '      인터넷 연결을 확인하고 다시 시도해 주세요.'
}
finally {
  if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
  Write-Host ''
  Read-Host '  Enter 를 누르면 닫힙니다'
}
