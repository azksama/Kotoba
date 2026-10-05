# Run in an administrator PowerShell. Restricts access to local/private VPN ranges.
$ErrorActionPreference='Stop'
$binary=Join-Path $PSScriptRoot 'releases\kotoba-companion.exe'
if(-not(Test-Path -LiteralPath $binary)){$binary=Join-Path $PSScriptRoot 'target\debug\kotoba-companion.exe'}
$binary=(Resolve-Path -LiteralPath $binary).Path
$name='Kotoba-PC-HTTPS'
$existing=Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue
if($existing){$existing | Remove-NetFirewallRule}
New-NetFirewallRule -Name $name -DisplayName 'Kotoba PC - HTTPS local et VPN' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 48736 -Program $binary -Profile Any -RemoteAddress 'LocalSubnet','192.168.0.0/16','10.0.0.0/8','172.16.0.0/12' -ErrorAction Stop | Out-Null
Write-Host 'Acces HTTPS autorise depuis le reseau local et les reseaux VPN prives.'
