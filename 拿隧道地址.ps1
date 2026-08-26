# 拿隧道地址.ps1 —— 一键：起创意工坊(net.py) + 临时隧道，并把公网地址打印出来
# 用法：右键"使用 PowerShell 运行"，或在这个目录打开 PowerShell 执行：
#   powershell -ExecutionPolicy Bypass -File .\拿隧道地址.ps1
# 拿到 https://xxx.trycloudflare.com 后，把它填进 Worker 的 UPSTREAM_URL 即可。
$ErrorActionPreference = "Continue"
$dist = Split-Path -Parent $MyInvocation.MyCommand.Path
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$log = Join-Path $dist "_tunnel_log.txt"
$outFile = Join-Path $dist "_tunnel_url.txt"

# 1) 确保工坊服务 net.py 在 5000 端口跑
$netRun = $false
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -match "net\.py") { $netRun = $true; break }
}
if (-not $netRun) {
    Start-Process -FilePath "python" -ArgumentList @("net.py") -WorkingDirectory $dist -WindowStyle Hidden
    Write-Output "已启动 net.py（创意工坊）"
} else {
    Write-Output "net.py 已在运行"
}

# 2) 确保有一条临时隧道指向本机 5000
$tunRun = $false
Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -match "tunnel" -and $_.CommandLine -match "127\.0\.0\.1:5000") { $tunRun = $true; break }
}
if (-not $tunRun) {
    Remove-Item $log,$outFile -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $cf -ArgumentList @("tunnel","--url","http://127.0.0.1:5000","--no-autoupdate") -WindowStyle Hidden -RedirectStandardError $log -RedirectStandardOutput $outFile
    Write-Output "已启动临时隧道，等待地址……"
} else {
    Write-Output "临时隧道已在运行"
}

# 3) 等隧道给出 trycloudflare 地址
$url = ""
Write-Output "正在等待隧道给出公网地址（约 10~20 秒）……"
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $log) {
        $c = Get-Content $log -Raw -ErrorAction SilentlyContinue
        if ($c -match "(https://[a-z0-9\-]+\.trycloudflare\.com)") { $url = $Matches[1]; break }
    }
}

Write-Output ""
if ($url) {
    Write-Output "════════════════════════════════════════"
    Write-Output "  你的临时公网地址："
    Write-Output "  $url"
    Write-Output "════════════════════════════════════════"
    $url | Set-Content -Path (Join-Path $dist "公网地址.txt") -Encoding UTF8
    Write-Output "已同时保存到：$dist\公网地址.txt"
    Write-Output "把上面这个地址填进 Worker 的 UPSTREAM_URL 即可。"
} else {
    Write-Output "⚠️ 还没拿到地址。稍等 20 秒再运行一次；若仍没有，确认："
    Write-Output "  - net.py 是否在 5000 端口跑（python net.py）"
    Write-Output "  - cloudflared 是否装好（C:\Program Files (x86)\cloudflared\cloudflared.exe）"
    Write-Output "  - 日志见：$log"
}
