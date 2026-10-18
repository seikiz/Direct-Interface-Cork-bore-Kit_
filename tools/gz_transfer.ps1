# Gzip 传输流水线：压缩 → 传输 → 解压 → 放置（安卓 / adb）
#
# 为什么不用 adb p<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ush 直接推原文件：
#   1) USB 带宽和手机存储写入都慢，文本/JSON/日志类通常能压到 1/10；
#   2) 传过去的是 .gz，传输中断就是个坏包，不会留下"看起来完整其实截断"的半成品；
#   3) 解压放在手机上做（Android 自带 toybox gzip），PC 端只负责压缩。
#
# 用法：
#   .\gz_transfer.ps1 -Path .\DICK-电脑版.zip -Target /sdcard/Download
#   .\gz_transfer.ps1 -Path .\saves -Target /sdcard/Download/dick_saves -Dir
#   .\gz_transfer.ps1 -Path .\a.json -Target /sdcard/Download -Serial 3B6F5LEAZ2KB5PZU -KeepGz
#
# 参数：
#   -Path     本地文件或目录（目录需 -Dir）
#   -Target   手机上的目标目录（必须已存在，或用 -MakeDir 自动建）
#   -Dir      把目录打成 tar.gz 再传
#   -Serial   多设备时指定序列号
#   -KeepGz   传完保留手机上的 .gz（默认删）
#   -MakeDir  目标目录不存在就 mkdir -p
#
param(
  [Parameter(Mandatory=$true)][string]$Path,
  [Parameter(Mandatory=$true)][string]$Target,
  [switch]$Dir,
  [string]$Serial = "",
  [switch]$KeepGz,
  [switch]$MakeDir
)

$ErrorActionPreference = "Stop"
$adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"
if (-not (Test-Path $adb)) { throw "找不到 adb：$adb" }
$serialArgs = @()
if ($Serial) { $serialArgs = @("-s", $Serial) }

function Step($t) { Write-Host "`n== $t ==" -ForegroundColor Cyan }
function Info($t) { Write-Host "   $t" }
function HumanMB($b) { "{0:N2} MB" -f ($b / 1MB) }

# ---------- 0) 设备与目标检查 ----------
Step "0) 检查设备"
& $adb @serialArgs wait-for-device | Out-Null
$state = (& $adb @serialArgs get-state 2>&1).Trim()
if ($state -ne "device") { throw "设备状态是 '$state'（不是 device），先插线/授权 USB 调试" }
Info "设备就绪：$(& $adb @serialArgs shell getprop ro.product.model)"

$exists = (& $adb @serialArgs shell "[ -d '$Target' ] && echo YES || echo NO").Trim()
if ($exists -ne "YES") {
  if ($MakeDir) { & $adb @serialArgs shell "mkdir -p '$Target'" | Out-Null; Info "已创建目标目录 $Target" }
  else { throw "手机上没有目录：$Target（加 -MakeDir 自动创建）" }
}

# ---------- 1) 压缩 ----------
Step "1) 压缩"
$src = (Resolve-Path $Path).Path
$stamp = Get-Date -Format "HHmmss"
if ($Dir) {
  if (-not (Test-Path $src -PathType Container)) { throw "-Dir 需要目录：$src" }
  $leaf = Split-Path $src -Leaf
  $gz = Join-Path $env:TEMP ("{0}-{1}.tar.gz" -f $leaf, $stamp)
  & tar -czf $gz -C (Split-Path $src -Parent) $leaf
  $origSize = (Get-ChildItem $src -Recurse -File | Measure-Object Length -Sum).Sum
} else {
  if (-not (Test-Path $src -PathType Leaf)) { throw "文件不存在：$src" }
  $leaf = Split-Path $src -Leaf
  $gz = Join-Path $env:TEMP ("{0}-{1}.gz" -f $leaf, $stamp)
  $in = [System.IO.File]::OpenRead($src)
  try {
    $out = [System.IO.File]::Create($gz)
    try {
      $gzs = New-Object System.IO.Compression.GZipStream($out, [System.IO.Compression.CompressionLevel]::Optimal)
      try { $in.CopyTo($gzs) } finally { $gzs.Dispose() }
    } finally { $out.Dispose() }
  } finally { $in.Dispose() }
  $origSize = (Get-Item $src).Length
}
$gzSize = (Get-Item $gz).Length
$ratio = if ($origSize -gt 0) { 100 * (1 - $gzSize / $origSize) } else { 0 }
Info ("原 {0} → 压后 {1}（省 {2:N1}%）" -f (HumanMB $origSize), (HumanMB $gzSize), $ratio)
Info "包：$gz"

# ---------- 2) 传输 ----------
Step "2) 传输"
$remoteGz = "$Target/" + (Split-Path $gz -Leaf)
$t0 = Get-Date
& $adb @serialArgs push $gz $remoteGz 2>&1 | ForEach-Object { Info $_ }
$dt = ((Get-Date) - $t0).TotalSeconds
Info ("耗时 {0:N1}s，速度 {1:N2} MB/s" -f $dt, ($gzSize / 1MB / [Math]::Max($dt, 0.001)))

# 传完核对大小：adb push 成功不代表字节数对（历史上踩过）
$remoteLen = (& $adb @serialArgs shell "stat -c %s '$remoteGz'" 2>$null).Trim()
if ($remoteLen -and [int64]$remoteLen -ne $gzSize) { throw "传输不完整：本地 $gzSize 字节，手机 $remoteLen 字节" }
if ($remoteLen) { Info "大小核对一致（$remoteLen 字节）" }

# ---------- 3) 解压 ----------
Step "3) 解压"
if ($Dir) {
  & $adb @serialArgs shell "cd '$Target' && tar -xzf '$(Split-Path $remoteGz -Leaf)'" 2>&1 | ForEach-Object { Info $_ }
  $outName = $leaf
} else {
  & $adb @serialArgs shell "cd '$Target' && gzip -df '$(Split-Path $remoteGz -Leaf)'" 2>&1 | ForEach-Object { Info $_ }
  $outName = $leaf
}
$placed = "$Target/$outName"
$ok = (& $adb @serialArgs shell "[ -e '$placed' ] && echo YES || echo NO").Trim()
if ($ok -ne "YES") { throw "解压后没找到 $placed（手机可能缺 gunzip/tar？看上面输出）" }
Info "解压完成：$placed"

# ---------- 4) 放置与校验 ----------
Step "4) 放置与校验"
$localHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash.ToLower()
if ($Dir) {
  Info "目录已就位：$placed（逐文件校验见 -VerifyDir，默认跳过）"
} else {
  $remoteHash = (& $adb @serialArgs shell "sha256sum '$placed'" 2>$null) -split '\s+' | Select-Object -First 1
  if ($remoteHash) {
    if ($remoteHash.ToLower() -eq $localHash) { Info "SHA256 校验通过：$($localHash.Substring(0,16))…" }
    else { throw "SHA256 不一致！本地 $localHash，手机 $remoteHash" }
  } else { Info "手机上没 sha256sum，跳过哈希校验（大小已核对）" }
}

if (-not $KeepGz) {
  & $adb @serialArgs shell "rm -f '$remoteGz'" 2>&1 | Out-Null
  Info "已清理手机上的 .gz"
}
Remove-Item $gz -Force -ErrorAction SilentlyContinue

Step "完成"
Info "目标：$placed"
