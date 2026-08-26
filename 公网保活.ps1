# ============================================================
#  公网保活.ps1 - 让创意工坊(net.py:5000) + cloudflared 隧道常驻
#  并把最新公网地址自动写进 workshop_config.json（应用跟随最新 URL）
#  计划任务：开机时 + 每 5 分钟。首次请先运行 设置-公网隧道.ps1 拿稳定地址，
#  或本脚本先起临时隧道（URL 会随重启更新）。
# ============================================================
$ErrorActionPreference = "Continue"
$dist = Split-Path -Parent $MyInvocation.MyCommand.Path
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$logFile = Join-Path $dist "_tunnel_err.txt"
$outFile = Join-Path $dist "_tunnel_out.txt"
$cfgFile = Join-Path $dist "workshop_config.json"

# 1) 创意工坊服务 net.py 常驻（端口 5000）
$netRunning = $false
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -match "net\.py") { $netRunning = $true; break }
}
if (-not $netRunning) {
    if (Test-Path (Join-Path $dist "net.py")) {
        Start-Process -FilePath "python" -ArgumentList @("net.py") -WorkingDirectory $dist -WindowStyle Hidden
        Write-Output "NET_STARTED"
    }
} else { Write-Output "NET_RUNNING" }

# 2) cloudflared 隧道常驻（指向本机 5000）
$tunRunning = $false
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -match "tunnel" -and $_.CommandLine -match "127\.0\.0\.1:5000") { $tunRunning = $true; break }
}
if (-not $tunRunning) {
    if (Test-Path $cf) {
        Start-Process -FilePath $cf -ArgumentList @("tunnel","--url","http://127.0.0.1:5000","--no-autoupdate") -WindowStyle Hidden -RedirectStandardError $logFile -RedirectStandardOutput $outFile
        Write-Output "TUNNEL_STARTED"
    }
} else { Write-Output "TUNNEL_RUNNING" }

# 3) 从日志提取当前公网 URL，写入配置（应用跟随最新地址）
if (Test-Path $logFile) {
    $c = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    if ($c -match "(https://[a-z0-9\-]+\.trycloudflare\.com)") {
        $url = $Matches[1]
        $cfg = @{}
        if (Test-Path $cfgFile) {
            try { $cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json -AsHashtable } catch { $cfg = @{} }
        }
        $old = [string]$cfg["server_url"]
        if ($old -ne $url) {
            $cfg["server_url"] = $url
            if (-not $cfg.ContainsKey("api_key")) { $cfg["api_key"] = "" }
            if (-not $cfg.ContainsKey("proxy")) { $cfg["proxy"] = "" }
            $cfg | ConvertTo-Json -Depth 5 | Set-Content -Path $cfgFile -Encoding UTF8
            Write-Output ("URL_UPDATED=" + $url)
        } else { Write-Output "URL_UNCHANGED" }
    } else { Write-Output "NO_URL_YET" }
}
