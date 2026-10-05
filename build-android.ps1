param([ValidateSet('aarch64','x86_64')][string]$Target='aarch64',[switch]$Debug)
$ErrorActionPreference='Stop'
$root=$PSScriptRoot
$env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
$env:ANDROID_HOME=Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$env:NDK_HOME=(Get-ChildItem (Join-Path $env:ANDROID_HOME 'ndk') -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
$abi=if($Target -eq 'aarch64'){'arm64-v8a'}else{'x86_64'}
$flavor=if($Target -eq 'aarch64'){'Arm64'}else{'X86_64'}
$mode=if($Debug){'Debug'}else{'Release'}
$profile=$mode.ToLowerInvariant()
Push-Location (Join-Path $root 'mobile')
try{
    $arguments=@('run','tauri','android','build','--','--apk','--target',$Target)
    if($Debug){$arguments+='--debug'}
    & npm.cmd @arguments 2>&1 | Tee-Object -Variable log | ForEach-Object { Write-Host $_ }
    if($LASTEXITCODE -ne 0){
        if(($log -join "`n") -notmatch 'Creation symbolic link is not allowed'){throw 'Compilation Rust Android echouee.'}
        $jni=Join-Path $root "mobile\src-tauri\gen\android\app\src\main\jniLibs\$abi"
        $null=New-Item -ItemType Directory -Path $jni -Force
        Copy-Item -LiteralPath (Join-Path $root "target\$Target-linux-android\$profile\libkotoba_mobile.so") -Destination (Join-Path $jni 'libkotoba_mobile.so') -Force
        Push-Location 'src-tauri\gen\android'
        try{& .\gradlew.bat ":app:assemble${flavor}${mode}" -x ":app:rustBuild${flavor}${mode}" --console=plain
            if($LASTEXITCODE -ne 0){throw 'Assemblage APK echoue.'}
        }finally{Pop-Location}
    }
    $releases=Join-Path $root 'releases';$null=New-Item -ItemType Directory -Path $releases -Force
    $apkFlavor=$flavor.ToLowerInvariant()
    $inputApk=Join-Path $root "mobile\src-tauri\gen\android\app\build\outputs\apk\$apkFlavor\$profile\app-$apkFlavor-$profile$(if(-not $Debug){'-unsigned'}).apk"
    if(-not(Test-Path -LiteralPath $inputApk)){throw "APK introuvable: $inputApk"}
    $version=(Get-Content (Join-Path $root "mobile/src-tauri/tauri.conf.json") -Raw | ConvertFrom-Json).version
    $output=Join-Path $releases "Kotoba-$version-android-$Target$(if($Debug){'-debug'}).apk"
    if($Debug){Copy-Item -LiteralPath $inputApk -Destination $output -Force}
    else{
        $signing=Join-Path $root '.android-signing';$null=New-Item -ItemType Directory -Path $signing -Force
        $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        & icacls $signing /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
        $key=Join-Path $signing 'release.jks';$password=Join-Path $signing 'password.txt'
        if((Test-Path $key) -xor (Test-Path $password)){throw 'Signature incomplete : restaurer cle et mot de passe ensemble.'}
        if(-not(Test-Path $key)){
            $bytes=New-Object byte[] 32;[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
            [IO.File]::WriteAllText($password,[Convert]::ToBase64String($bytes))
            $env:KOTOBA_SIGN_PASSWORD=[IO.File]::ReadAllText($password)
            & "$env:JAVA_HOME\bin\keytool.exe" -genkeypair -keystore $key -storepass:env KOTOBA_SIGN_PASSWORD -keypass:env KOTOBA_SIGN_PASSWORD -alias kotoba -keyalg RSA -keysize 3072 -validity 10000 -dname 'CN=Kotoba, O=AZK, C=FR' -noprompt
            if($LASTEXITCODE -ne 0){throw 'Creation de cle echouee.'}
        }
        $env:KOTOBA_SIGN_PASSWORD=[IO.File]::ReadAllText($password)
        $tools=(Get-ChildItem "$env:ANDROID_HOME\build-tools" -Directory | Sort-Object Name -Descending | Select-Object -First 1).FullName
        & "$tools\apksigner.bat" sign --ks $key --ks-key-alias kotoba --ks-pass env:KOTOBA_SIGN_PASSWORD --key-pass env:KOTOBA_SIGN_PASSWORD --out $output $inputApk
        if($LASTEXITCODE -ne 0){throw 'Signature echouee.'}
        & "$tools\apksigner.bat" verify --verbose $output
        if($LASTEXITCODE -ne 0){throw 'Verification de signature echouee.'}
        & "$tools\zipalign.exe" -c -P 16 -v 4 $output | Select-Object -Last 1
        if($LASTEXITCODE -ne 0){throw 'Alignement APK invalide.'}
    }
    Get-FileHash -LiteralPath $output -Algorithm SHA256
}finally{Remove-Item Env:KOTOBA_SIGN_PASSWORD -ErrorAction SilentlyContinue;Pop-Location}
