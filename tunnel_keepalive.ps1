# ============================================================
#  tunnel_keepalive.ps1 - 创意工坊隧道保活 + 地址同步
#  1. 检查 cloudflared 隧道进程，没跑就启动（输出到日志）
#  2. 调用 tunnel_sync.ps1 同步 Worker 固定地址
#  计划任务：开机时 + 每 5 分钟
# ============================================================
$ErrorActionPreference = "Continue"
$dist = "C:\Users\seiki\Desktop\dist"
$logFile = Join-Path $dist "_tunnel_err.txt"
$outFile = Join-Path $dist "_tunnel_out.txt"

$tunnelRunning = $false
$procs = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    if ($p.CommandLine -match "tunnel.*url http://127.0.0.1:5000") {
        $tunnelRunning = $true
        break
    }
}

if (-not $tunnelRunning) {
    Write-Output "TUNNEL_NOT_RUNNING - starting..."
    Start-Process -FilePath "C:\Program Files (x86)\cloudflared\cloudflared.exe" -ArgumentList "tunnel","--url","http://127.0.0.1:5000","--no-autoupdate" -WindowStyle Hidden -RedirectStandardOutput $outFile -RedirectStandardError $logFile
    $found = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $logFile) {
            $c = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
            if ($c -match "https://[a-z0-9\-]+\.trycloudflare\.com") {
                $found = $true
                break
            }
        }
    }
    if ($found) { Write-Output "TUNNEL_STARTED" } else { Write-Output "TUNNEL_START_WAIT" }
} else {
    Write-Output "TUNNEL_RUNNING"
}

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dist "tunnel_sync.ps1")
