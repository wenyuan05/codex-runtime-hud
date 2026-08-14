$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python launcher (py) not found.' }
py -3 -m pip install -r requirements-build.txt

$iconDir = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Force -Path $iconDir | Out-Null
py -3 -c "from PIL import Image,ImageDraw; im=Image.new('RGBA',(256,256),(27,27,29,255)); d=ImageDraw.Draw(im); d.rounded_rectangle((12,12,244,244),radius=52,fill=(87,185,126,255)); d.text((74,64),'C',fill='white',stroke_width=2); im.save(r'$iconDir\codex-token-overlay.ico',sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])"
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
