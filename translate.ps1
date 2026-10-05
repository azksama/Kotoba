# Pass all options straight to Python, including --dry-run and JSON pointer globs.
$ErrorActionPreference = 'Stop'
if ($args -notcontains '--dry-run' -and $args -notcontains '--help' -and $args -notcontains '-h') {
    & (Join-Path $PSScriptRoot 'start-ollama.ps1')
}
& python -X utf8 (Join-Path $PSScriptRoot 'translate_json.py') @args
exit $LASTEXITCODE
