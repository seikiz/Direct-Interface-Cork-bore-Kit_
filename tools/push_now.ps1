# 一次性推送脚本：网络一好就能跑（不要手打一长串 git 参数）
#
# 用法（PowerShe<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ll，在仓库根目录）：
#     pwsh -File tools\push_now.ps1
#
# 它会按顺序试三种通道，任一成功就停：
#   ① SSH over 443（ssh.github.com）——需要 ~/.ssh/id_ed25519 已加到 GitHub
#   ② HTTPS（HTTP/1.1 + 大 postBuffer）
#   ③ 分批评 HTTPS（把一个包拆成多个小请求，绕过某些 DPI 对长连接的上传重置）
#
# 环境变量：
#   $env:PROXY = "http://127.0.0.1:7890"   # 有代理就设上，脚本会用它跑 ②

$ErrorActionPreference = "Continue"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
if ($env:PROXY) { $env:HTTP_PROXY = $env:PROXY; $env:HTTPS_PROXY = $env:PROXY }

$repo = "https://github.com/seikiz/Direct-Interface-Cork-bore-Kit_.git"
$sshRepo = "ssh://git@ssh.github.com:443/seikiz/Direct-Interface-Cork-bore-Kit_.git"

function Pending { (git rev-list --count origin/main..HEAD) }
function Synced { (git rev-parse origin/main) -eq (git rev-parse HEAD) }

Write-Host ("待推提交：" + (Pending) + " 个") -ForegroundColor Cyan
if (Synced) { Write-Host "已经是同步状态，无需推送" -ForegroundColor Green; exit 0 }

# ---------------------------------------------------------------- ① SSH 443
Write-Host "`n[1/3] 试 SSH over 443 ..." -ForegroundColor Yellow
git ls-remote $sshRepo *> $null
if ($LASTEXITCODE -eq 0) {
    git push $sshRepo "HEAD:refs/heads/main"
    if (Synced) { Write-Host "SSH 推送成功" -ForegroundColor Green; exit 0 }
    Write-Host "SSH 通了但推送失败，继续试 HTTPS" -ForegroundColor Yellow
} else {
    Write-Host "SSH 未授权（公钥没加到 GitHub），跳过" -ForegroundColor DarkYellow
}

# ---------------------------------------------------------------- ② HTTPS 整包
Write-Host "`n[2/3] 试 HTTPS 整包推送 ..." -ForegroundColor Yellow
git -c http.version=HTTP/1.1 -c http.postBuffer=104857600 push origin main
if (Synced) { Write-Host "HTTPS 推送成功" -ForegroundColor Green; exit 0 }

# ---------------------------------------------------------------- ③ 分批评
Write-Host "`n[3/3] 分批推送（每个提交一次请求）..." -ForegroundColor Yellow
$shas = git rev-list --reverse origin/main..HEAD
foreach ($sha in $shas) {
    $ok = $false
    for ($try = 1; $try -le 3; $try++) {
        git -c http.version=HTTP/1.1 -c http.postBuffer=10485760 push origin "${sha}:refs/heads/main" *> $null
        if ((git rev-parse origin/main) -eq $sha) { $ok = $true; break }
        Start-Sleep -Seconds 2
    }
    Write-Host ("  " + $sha.Substring(0, 7) + " -> " + $(if ($ok) { "OK" } else { "失败" }))
    if (-not $ok) { break }
}

Write-Host ""
if (Synced) {
    Write-Host "推送完成：origin/main = $(git rev-parse --short HEAD)" -ForegroundColor Green
    Write-Host "CI 会在 push 后自动跑（.github/workflows/test.yml）" -ForegroundColor Green
    exit 0
}
Write-Host "三种通道都不通。可选：" -ForegroundColor Red
Write-Host "  · 开代理后： `$env:PROXY='http://127.0.0.1:7890'; pwsh -File tools\push_now.ps1"
Write-Host "  · 把 ~/.ssh/id_ed25519.pub 加到 GitHub，再跑本脚本"
Write-Host "  · 或把 DICK-发布\dick-pending.bundle 拷到能联网的机器："
Write-Host "      git clone DICK-发布\dick-pending.bundle dick; cd dick; git push origin main"
exit 1
