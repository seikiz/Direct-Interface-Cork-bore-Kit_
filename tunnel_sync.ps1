# ============================================================
#  tunnel_sync.ps1 - 创意工坊隧道地址自动同步
#  监控 cloudflared 隧道日志 → 检测到新 trycloudflare URL →
#  更新 Worker 环境变量 → 重新部署（保持固定地址永远可用）
#  用法：计划任务每 5 分钟跑一次，或手动执行
# ============================================================
$ErrorActionPreference = "Continue"

$dist = "C:\Users\seiki\Desktop\dist"
$logFile = Join-Path $dist "_tunnel_err.txt"
$toml = Join-Path $dist "_wf\wrangler.toml"
$workerDir = Join-Path $dist "_wf"
$stateFile = Join-Path $dist "_tunnel_sync_state.txt"

# 1) 从隧道日志提取当前 trycloudflare URL
$currentUrl = ""
if (Test-Path $logFile) {
    $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    if ($content -match "(https://[a-z0-9\-]+\.trycloudflare\.com)") {
        $currentUrl = $Matches[1]
    }
}
if (-not $currentUrl) {
    Write-Output "NO_URL_IN_LOG"
    exit 0
}

# 2) 读取当前 toml 里的 UPSTREAM_URL
$tomlContent = Get-Content $toml -Raw -ErrorAction SilentlyContinue
$oldUrl = ""
if ($tomlContent -match 'UPSTREAM_URL = "([^"]+)"') {
    $oldUrl = $Matches[1]
}

Write-Output ("CURRENT=" + $currentUrl)
Write-Output ("OLD=" + $oldUrl)

if ($currentUrl -eq $oldUrl) {
    Write-Output "NO_CHANGE"
    exit 0
}

# 3) 更新 wrangler.toml
$newToml = $tomlContent -replace 'UPSTREAM_URL = "[^"]*"', ('UPSTREAM_URL = "' + $currentUrl + '"')
Set-Content -Path $toml -Value $newToml -Encoding UTF8
Write-Output ("TOML_UPDATED=" + $currentUrl)

# 4) 重新部署 Worker
Push-Location $workerDir
try {
    $deploy = wrangler deploy 2>&1 | Out-String
    if ($deploy -match "Deployed") {
        Write-Output "WORKER_DEPLOYED"
        $currentUrl | Set-Content -Path $stateFile -Encoding UTF8
    } else {
        $snip = $deploy
        if ($snip.Length -gt 300) { $snip = $snip.Substring(0, 300) }
        Write-Output ("DEPLOY_FAIL: " + $snip)
    }
} catch {
    Write-Output ("DEPLOY_ERROR: " + $_.Exception.Message)
} finally {
    Pop-Location
}
