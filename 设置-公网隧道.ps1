# 设置-公网隧道.ps1 —— 一次性：创建 Cloudflare「命名隧道」，得到一个稳定公网地址
# ==============================<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌==============================
# 用途：让创意工坊（net.py, 端口 5000）在公网上有一个【稳定】地址
#   https://<隧道ID>.cfargotunnel.com
# 这个地址不会像 trycloudflare 临时隧道那样每次重启都变。
#
# 前提：
#   - 本机已装 cloudflared（C:\Program Files (x86)\cloudflared\cloudflared.exe）
#   - 有 Cloudflare 账号（首次会打开浏览器授权）
#
# 只需跑一次。之后让 tunnel_keepalive.ps1 常驻即可。
# ============================================================
$ErrorActionPreference = "Stop"
$dist = Split-Path -Parent $MyInvocation.MyCommand.Path
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$configPath = Join-Path $dist "tunnel-config.yml"
$TUNNEL_NAME = "dick-workshop"

function Say($m) { Write-Host "[DICK 公网隧道] $m" }

if (-not (Test-Path $cf)) {
    Write-Host "[ERR] 未找到 cloudflared：$cf"
    Write-Host "      请到 https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ 下载并安装。"
    exit 1
}

Say "Step 1/3  登录 Cloudflare（会打开浏览器，授权后本窗口继续）..."
& $cf tunnel login
if ($LASTEXITCODE -ne 0) { Say "登录失败/取消"; exit 1 }

Say "Step 2/3  创建命名隧道（若已存在会用旧的）..."
$out = (& $cf tunnel create $TUNNEL_NAME 2>&1 | Out-String)
$uuid = ""
if ($out -match "([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})") {
    $uuid = $Matches[1]
}
if (-not $uuid) {
    # 退回：从 ~/.cloudflared 里找最近生成的那个 <uuid>.json
    $cfdir = Join-Path $env:USERPROFILE ".cloudflared"
    if (Test-Path $cfdir) {
        $f = Get-ChildItem $cfdir -Filter "*.json" -ErrorAction SilentlyContinue |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($f) { $uuid = $f.BaseName }
    }
}
if (-not $uuid) {
    Say "未能获取隧道 ID，创建输出如下："
    Write-Host $out
    exit 1
}
Say ("隧道 ID = " + $uuid)

# 写 cloudflared 配置（把 5000 端口映射到 <uuid>.cfargotunnel.com）
$cred = Join-Path $env:USERPROFILE ".cloudflared\$uuid.json"
$yml = @"
tunnel: $uuid
credentials-file: ${cred}
ingress:
  - hostname: ${uuid}.cfargotunnel.com
    service: http://127.0.0.1:5000
  - service: http_status:404
"@
[System.IO.File]::WriteAllText($configPath, $yml, (New-Object System.Text.UTF8Encoding($false)))
Say ("已写入配置：$configPath")

# 稳定公网地址
$url = "https://${uuid}.cfargotunnel.com"
Say "稳定公网地址（把下面这行填到各端『工坊地址/服务器地址』）："
Write-Host ("    " + $url)

Say "Step 3/3  启动隧道并保持后台..."
Start-Process -FilePath $cf -ArgumentList @("tunnel","run",$TUNNEL_NAME,"--config",$configPath) -WindowStyle Hidden
Say "隧道已启动（后台）。详情可查看 tunnel_keepalive.ps1 日志。"
Say ("提醒：把上面的 " + $url + " 填到 DICK 各端『工坊地址』即可走公网（手机上填到 🔑 API 配置/工坊地址）。")
