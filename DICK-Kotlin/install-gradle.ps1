$ErrorActionPreference = "Stop"
$ver = "8.10.2"
$tools = Join-Path $env:USERPROFILE "kotlin-tools"
New-Item -ItemType Directory -Force -Path $tools | Out-Null

# ---------- JDK（Android Studio 自带 JBR，免安装） ----------
$jbr = "C:\Program Files\Android\Android Studio\jbr"
if (Test-Path (Join-Path $jbr "bin\java.exe")) {
    setx JAVA_HOME $jbr | Out-Null
    $p0 = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($p0 -notlike "*Android Studio\jbr\bin*") {
        setx PATH ($p0.TrimEnd(";") + ";" + (Join-Path $jbr "bin")) | Out-Null
    }
    Write-Host "JAVA_HOME -> $jbr"
} else {
    Write-Host "WARN: Android Studio JBR not found at $jbr"
}

# ---------- Gradle ----------
$gradleHome = Join-Path $tools ("gradle-" + $ver)
$zip = Join-Path $tools ("gradle-" + $ver + "-bin.zip")

if (-not (Test-Path (Join-Path $gradleHome "bin\gradle.bat"))) {
    if (-not (Test-Path $zip)) {
        $urls = @(
            "https://mirrors.cloud.tencent.com/gradle/gradle-$ver-bin.zip",
            "https://mirrors.huaweicloud.com/gradle/gradle-$ver-bin.zip",
            "https://services.gradle.org/distributions/gradle-$ver-bin.zip"
        )
        $ok = $false
        foreach ($u in $urls) {
            Write-Host "Trying: $u"
            try {
                Invoke-WebRequest -Uri $u -OutFile $zip -UseBasicParsing -TimeoutSec 300
                if ((Get-Item $zip).Length -gt 10MB) { $ok = $true; break }
            } catch {
                Write-Host ("Failed: " + $_.Exception.Message)
            }
        }
        if (-not $ok) { throw "All download sources failed. Check your network." }
    }
    Write-Host "Extracting..."
    Expand-Archive -Path $zip -DestinationPath $tools -Force
} else {
    Write-Host "Gradle already installed, skipping."
}

$bin = Join-Path $gradleHome "bin"
$p = [Environment]::GetEnvironmentVariable("Path", "User")
if ($p -notlike ("*" + $bin + "*")) {
    setx PATH ($p.TrimEnd(";") + ";" + $bin) | Out-Null
    Write-Host "Added to user PATH: $bin"
} else {
    Write-Host "PATH already contains Gradle"
}

Write-Host ""
Write-Host "Done! Open a NEW terminal and verify:"
Write-Host "  gradle --version"
Write-Host "Then build:"
Write-Host "  cd " + (Split-Path -Parent $MyInvocation.MyCommand.Path)
Write-Host "  gradle assembleDebug"
