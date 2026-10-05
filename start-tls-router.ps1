$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$config=Get-Content -LiteralPath (Join-Path $root '.kotoba\network.json') -Raw | ConvertFrom-Json
if($config.publicHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$'){throw 'Nom DNS invalide.'}
$route=Get-NetRoute -AddressFamily IPv4 -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
$lan=(Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 | Where-Object IPAddress -NotLike '169.254.*' | Select-Object -First 1).IPAddress
if(-not $lan){throw 'Adresse LAN introuvable.'}
$exe=Join-Path $root 'releases\kotoba-tls-router.exe'
$existing=Get-NetTCPConnection -LocalPort 8189 -LocalAddress $lan -State Listen -ErrorAction SilentlyContinue
if($existing){
    foreach($listener in $existing){if((Get-Process -Id $listener.OwningProcess).Path -ne $exe){throw 'Le port 8189 LAN est deja utilise par un autre programme.'}}
    Write-Host "Repartiteur TLS deja actif sur ${lan}:8189";return
}
$log=Join-Path $root 'logs';$null=New-Item -ItemType Directory -Path $log -Force
Start-Process -FilePath $exe -WorkingDirectory $root -ArgumentList @('--bind',"${lan}:8189",'--kotoba-name',$config.publicHost) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $log 'tls-router.log') -RedirectStandardError (Join-Path $log 'tls-router-error.log') | Out-Null
for($i=0;$i -lt 15;$i++){
    if(Get-NetTCPConnection -LocalPort 8189 -LocalAddress $lan -State Listen -ErrorAction SilentlyContinue){Write-Host "Repartiteur TLS actif sur ${lan}:8189";return}
    Start-Sleep -Seconds 1
}
throw 'Le repartiteur TLS ne demarre pas. Voir logs\tls-router-error.log.'
