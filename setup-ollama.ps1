$ErrorActionPreference = 'Stop'
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaExe = if ($ollamaCommand) { $ollamaCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe' }
if (-not (Test-Path -LiteralPath $ollamaExe)) {
    & winget install --id Ollama.Ollama --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'Ollama installation failed.' }
    $ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
}
& (Join-Path $PSScriptRoot 'start-ollama.ps1')
& python -X utf8 (Join-Path $PSScriptRoot 'setup_model.py')
if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
& $ollamaExe create 'ja-en-game:12b' -f (Join-Path $PSScriptRoot 'Modelfile')
if ($LASTEXITCODE -ne 0) { throw 'Model configuration failed.' }
& $ollamaExe list
Write-Host 'Ready. Use: .\translate.ps1 .\your-game.json --dry-run'
