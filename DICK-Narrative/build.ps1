# DICK 叙事引擎 · 一键构建
#
# 用法（在 DICK-Na<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌rrative 目录下）：
#   powershell -ExecutionPolicy Bypass -File build.ps1            # 测试 + 打包 EXE + 打包 APK
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Test      # 只跑引擎测试
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Run       # 直接运行桌面版
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Exe       # 只打包 EXE
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Apk       # 只打包 APK
#   powershell -ExecutionPolicy Bypass -File build.ps1 -Clean     # 先清 build 再全做

param(
    [switch]$Test,
    [switch]$Run,
    [switch]$Exe,
    [switch]$Apk,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'

$Gradle = 'C:\Users\seiki\kotlin-tools\gradle-8.10.2\bin\gradle.bat'
# 打包 EXE 需要 jpackage —— Android Studio 自带的 JBR 里没有，所以单独下了一个 JDK 21
$Jdk21  = 'C:\Users\seiki\kotlin-tools\jdk21\jdk-21.0.12.1+1'
# Windows 打包时 Compose 会去 GitHub 下 WiX（国内常常连不上）。
# 设置 WIX_PATH 指向一个已存在的目录即可跳过下载；绿色版 AppImage 用不到 WiX。
$WixDir = 'C:\Users\seiki\kotlin-tools\wix'

$Root = $PSScriptRoot

if (-not (Test-Path $Gradle)) { throw "找不到 gradle：$Gradle" }

$JvmHome = $null
if (Test-Path (Join-Path $Jdk21 'bin\jpackage.exe')) {
    $JvmHome = $Jdk21
} else {
    Write-Host "！找不到带 jpackage 的 JDK：$Jdk21" -ForegroundColor Yellow
    Write-Host "  打包 EXE 会失败；测试和 APK 不受影响。" -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $WixDir | Out-Null
$env:WIX_PATH = $WixDir

# 没指定就全做
if (-not ($Test -or $Run -or $Exe -or $Apk)) { $Test = $true; $Exe = $true; $Apk = $true }

function Invoke-Gradle {
    param([string[]]$Tasks, [string]$JavaHome)
    $gargs = @()
    if ($JavaHome) { $gargs += "-Dorg.gradle.java.home=$JavaHome" }
    $gargs += $Tasks
    $gargs += '--console=plain'
    Write-Host "> gradle $($Tasks -join ' ')" -ForegroundColor Cyan
    & $Gradle @gargs
    if ($LASTEXITCODE -ne 0) { throw "gradle failed (exit $LASTEXITCODE)" }
}

Push-Location $Root
try {
    if ($Clean) {
        Write-Host '> 清理 build 目录' -ForegroundColor Cyan
        Remove-Item -Recurse -Force (Join-Path $Root 'app\build') -ErrorAction SilentlyContinue
    }

    if ($Test) { Invoke-Gradle @(':app:desktopTest') }

    if ($Run) {
        Write-Host '> 启动桌面版（关掉窗口即结束）' -ForegroundColor Cyan
        Invoke-Gradle @(':app:run')
    }

    if ($Exe) { Invoke-Gradle @(':app:packageAppImage') $JvmHome }

    if ($Apk) { Invoke-Gradle @(':app:assembleDebug') }

    Write-Host ''
    Write-Host '================ 产物 ================' -ForegroundColor Green

    $exeDir = Join-Path $Root 'app\build\compose\binaries\main\app\DICK-Narrative'
    if ($Exe -and (Test-Path $exeDir)) {
        # 把示例故事放到 exe 旁边，开箱能玩
        $storySrc = Join-Path $Root 'story'
        if (Test-Path $storySrc) { Copy-Item $storySrc -Destination $exeDir -Recurse -Force }
        $size = [math]::Round(((Get-ChildItem $exeDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
        Write-Host "桌面版：$exeDir  （$size MB）" -ForegroundColor Green
        Write-Host "        双击里面的 DICK-Narrative.exe 即可运行（整个文件夹一起拷走就能用）" -ForegroundColor Green
    }

    $apkDir = Join-Path $Root 'app\build\outputs\apk\debug'
    if ($Apk -and (Test-Path $apkDir)) {
        $apkFile = Get-ChildItem $apkDir -Filter '*.apk' | Select-Object -First 1
        if ($apkFile) {
            $mb = [math]::Round($apkFile.Length / 1MB, 2)
            Write-Host "安卓版：$($apkFile.FullName)  （$mb MB）" -ForegroundColor Green
        }
    }
    Write-Host '======================================' -ForegroundColor Green
}
finally {
    Pop-Location
}
