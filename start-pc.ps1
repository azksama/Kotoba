param([string]$Address, [switch]$ShowPairing)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
$networkFile=Join-Path $PSScriptRoot '.kotoba\network.json'
$network=if(Test-Path -LiteralPath $networkFile){Get-Content -LiteralPath $networkFile -Raw | ConvertFrom-Json}else{$null}
if(-not $Address -and $network){$Address=$network.publicHost}
if(-not $Address){
    $route=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
    $Address=(Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress
}
if(-not $Address){throw 'Adresse LAN introuvable. Utilisez -Address 192.168.x.x.'}
$data=Join-Path $PSScriptRoot '.kotoba'
$null=New-Item -ItemType Directory -Path $data -Force
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
& icacls $data /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
if($LASTEXITCODE -ne 0){throw 'Impossible de proteger les fichiers de connexion.'}
& (Join-Path $PSScriptRoot 'start-ollama.ps1')
$binary=Join-Path $PSScriptRoot 'releases\kotoba-companion.exe'
if(-not(Test-Path -LiteralPath $binary)){$binary=Join-Path $PSScriptRoot 'target\debug\kotoba-companion.exe'}
if(-not(Test-Path -LiteralPath $binary)){throw 'Compilez le compagnon avec cargo build -p kotoba-companion.'}
$existing=Get-NetTCPConnection -LocalPort 48736 -State Listen -ErrorAction SilentlyContinue
if(-not $existing){
    $log=Join-Path $PSScriptRoot 'logs';$null=New-Item -ItemType Directory -Path $log -Force
    $serverArgs=@('--host',$Address)
    if($network){$serverArgs+=@('--bind','127.0.0.1:48736','--advertise-port',[string]$network.publicPort)}
    Start-Process -FilePath $binary -WorkingDirectory $PSScriptRoot -ArgumentList $serverArgs -WindowStyle Hidden -RedirectStandardOutput (Join-Path $log 'companion.log') -RedirectStandardError (Join-Path $log 'companion-error.log') | Out-Null
    for($i=0;$i -lt 30;$i++){if(Get-NetTCPConnection -LocalPort 48736 -State Listen -ErrorAction SilentlyContinue){break};Start-Sleep -Seconds 1}
}
if(-not(Get-NetTCPConnection -LocalPort 48736 -State Listen -ErrorAction SilentlyContinue)){throw 'Le compagnon ne demarre pas. Consultez logs\companion-error.log.'}
$displayPort=if($network){$network.publicPort}else{48736}
Write-Host "Kotoba PC : https://${Address}:$displayPort"
if($network){& (Join-Path $PSScriptRoot 'start-tls-router.ps1')}
Write-Host 'Connexion privee : .kotoba\pairing.txt (a importer dans Android).'
if($ShowPairing){Start-Process notepad.exe -ArgumentList ('"'+(Join-Path $data 'pairing.txt')+'"')}
