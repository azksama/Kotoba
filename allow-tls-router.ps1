$ErrorActionPreference='Stop'
$exe=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'releases\kotoba-tls-router.exe')).Path
$name='Kotoba-Mochi-TLS-8189'
if(Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue){Remove-NetFirewallRule -Name $name}
New-NetFirewallRule -Name $name -DisplayName 'Kotoba + Mochi - TLS partage 8189' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8189 -Program $exe -Profile Any -RemoteAddress Any -ErrorAction Stop | Out-Null
