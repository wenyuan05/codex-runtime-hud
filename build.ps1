$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python launcher (py) not found.' }
py -3 -m pip install -r requirements-build.txt

$iconDir = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
py -3 scripts/make_icon.py --output (Join-Path $iconDir 'codex-token-overlay.ico')
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed with exit code $LASTEXITCODE." }
$distDir = Join-Path $PSScriptRoot 'dist'
$workDir = Join-Path $PSScriptRoot 'build\pyinstaller'
if (Test-Path -LiteralPath $distDir) { Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction Stop }
if (Test-Path -LiteralPath $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction Stop }
py -3 -m PyInstaller --noconfirm --clean --distpath (Join-Path $PSScriptRoot 'dist') --workpath (Join-Path $PSScriptRoot 'build\pyinstaller') CodexTokenOverlay.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

$exe = Join-Path $PSScriptRoot 'dist\CodexTokenOverlay.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'PyInstaller did not produce the EXE.' }
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $PSScriptRoot 'dist\SHA256SUMS.txt') -Encoding utf8 -Value "$hash  CodexTokenOverlay.exe"
Write-Output "Built: $exe"
Write-Output "SHA256: $hash"
