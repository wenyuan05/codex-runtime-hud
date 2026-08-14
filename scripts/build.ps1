$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python launcher (py) not found.' }
py -3 -m pip install -r (Join-Path $repoRoot 'requirements-build.txt')

$iconDir = Join-Path $repoRoot 'build'
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
py -3 (Join-Path $PSScriptRoot 'make_runtime_icon.py') --output (Join-Path $iconDir 'codex-runtime-hud.ico')
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed with exit code $LASTEXITCODE." }
$distDir = Join-Path $repoRoot 'dist'
$workDir = Join-Path $repoRoot 'build\pyinstaller'
if (Test-Path -LiteralPath $distDir) { Remove-Item -LiteralPath $distDir -Recurse -Force -ErrorAction Stop }
if (Test-Path -LiteralPath $workDir) { Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction Stop }
py -3 -m PyInstaller --noconfirm --clean --distpath $distDir --workpath $workDir (Join-Path $PSScriptRoot '..\packaging\CodexRuntimeHUD.spec')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }

$exe = Join-Path $repoRoot 'dist\CodexRuntimeHUD.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'PyInstaller did not produce the EXE.' }
$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $repoRoot 'dist\SHA256SUMS.txt') -Encoding utf8 -Value "$hash  CodexRuntimeHUD.exe"
Write-Output "Built: $exe"
Write-Output "SHA256: $hash"
