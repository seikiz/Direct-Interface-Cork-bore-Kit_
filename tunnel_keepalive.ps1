# ============================================================
#  tunnel_keepalive.ps1 - 创意工坊「命名隧道」保活（稳定公网地址）
#  只用 cloudflared tunnel run 保持本命名隧道在跑；URL 是稳定的
#  https://<隧道ID>.cfargotunnel.com，不会像 trycloudflare 那样变，
#  因此无需抓取地址/重部署 Worker。
#  计划任务：开机时 + 每 5 分钟。首次请先运行 设置-公网隧道.ps1。
# ============================================================
$ErrorActionPreference = "Continue"
$dist = Split-Path -Parent $MyInvocation.MyCommand.Path
$configPath = Join-Path $dist "tunnel-config.yml"
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$TUNNEL_NAME = "dick-workshop"

# 是否有本命名隧道的进程在跑
$running = $false
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -match "tunnel\s+run" -and $_.CommandLine -match [regex]::Escape($TUNNEL_NAME)) {
        $running = $true
        break
    }
}

if ($running) {
    Write-Output "TUNNEL_RUNNING"
    exit 0
}

if (-not (Test-Path $configPath)) {
    Write-Output "NO_CONFIG - 请先运行 设置-公网隧道.ps1"
    exit 0
}

Write-Output "TUNNEL_NOT_RUNNING - starting..."
Start-Process -FilePath $cf -ArgumentList @("tunnel", "run", $TUNNEL_NAME, "--config", $configPath) -WindowStyle Hidden
Write-Output "TUNNEL_STARTED"
