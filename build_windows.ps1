param(
    [string]$Python = "",
    [string]$OutputRoot = "",
    [switch]$SkipTests
)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
if (-not $Python) { $Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe" }
if (-not $OutputRoot) { $OutputRoot = Join-Path $ProjectRoot "release\2.0.0" }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
if (-not (Test-Path -LiteralPath $Python)) { throw "Crie .venv com Python 3.12 e instale requirements-lock.txt usando uv pip install." }
& $Python -c "import sys; assert sys.version_info[:2] == (3, 12), 'Use Python 3.12'"
if ($LASTEXITCODE -ne 0) { throw "Python incompatível." }
if (-not $SkipTests) {
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Testes falharam." }
}
& $Python -m PyInstaller --clean --noconfirm --distpath $OutputRoot --workpath (Join-Path $ProjectRoot "build\v2") SunriseCast.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou." }
$Bundle = Join-Path $OutputRoot "SunriseCast"
$Executable = Join-Path $Bundle "SunriseCast.exe"
if (-not (Test-Path -LiteralPath $Executable)) { throw "Executável ausente." }
$Forbidden = Get-ChildItem -LiteralPath $Bundle -Force -Recurse | Where-Object {
    $_.Name -in @(".env", ".spotify_cache", "podcasts.json", "settings.json", "state.json", "app.log")
}
if ($Forbidden) { throw "O pacote contém arquivos pessoais." }
Copy-Item -LiteralPath (Join-Path $ProjectRoot "update_installation.ps1") -Destination $OutputRoot
Copy-Item -LiteralPath (Join-Path $ProjectRoot "UPDATE_GUIDE.md") -Destination $OutputRoot
Copy-Item -LiteralPath (Join-Path $ProjectRoot "requirements-lock.txt") -Destination $OutputRoot
Write-Host "Build concluído: $Executable"
