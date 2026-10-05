$ErrorActionPreference = 'Stop'
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    return
} catch { }
$ollamaCommand = Get-Command ollama -ErrorAction SilentlyContinue
$ollamaExe = if ($ollamaCommand) { $ollamaCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe' }
if (-not (Test-Path -LiteralPath $ollamaExe)) { throw 'Ollama is missing. Run setup-ollama.ps1 first.' }
$logDirectory = Join-Path $PSScriptRoot 'logs'
$null = New-Item -ItemType Directory -Path $logDirectory -Force
# Only this server process inherits these values; no user/system environment edits.
$settings = @{ OLLAMA_HOST = '127.0.0.1:11434'; OLLAMA_NUM_PARALLEL = '1'; OLLAMA_MAX_LOADED_MODELS = '1' }
$previous = @{}
try {
    foreach ($key in $settings.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
        [Environment]::SetEnvironmentVariable($key, $settings[$key], 'Process')
    }
    $server = Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDirectory 'ollama-out.log') -RedirectStandardError (Join-Path $logDirectory 'ollama-error.log')
} finally {
    foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, $previous[$key], 'Process') }
}
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
        return
    } catch { Start-Sleep -Seconds 1 }
}
throw 'Ollama did not start. See logs\ollama-error.log.'
