# bootstrap-node.ps1 — 命令行层级自动准备便携 Node（Linux 式）
# ============================================================
# 不再随程序捆绑 Node（省 98MB）。运行酒馆安装器时，若本机没有可用的
# Node(>=18)，就从 nodejs.org 下载便携版并解压到本目录 node\ 下使用。
# 只把「最终 Node 路径」打到 stdout；进度信息打到 stderr，避免污染结果。
# ============================================================
$ErrorActionPreference = 'Stop'
$dir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$nodeDir = Join-Path $dir 'node'
$nodeExe = Join-Path $nodeDir 'node.exe'

function Write-Phase($m) { [Console]::Error.WriteLine($m) }

function Get-Major([string]$exe) {
  try {
    $raw = (& $exe --version 2>$null | Out-String).Trim()
    if ($raw -notmatch '^v?(\d+)') { return 0 }
    return [int]$Matches[1]
  } catch { return 0 }
}

# 1) 本地已有便携 node 且 >=18 → 直接用
if (Test-Path $nodeExe) {
  if ((Get-Major $nodeExe) -ge 18) { Write-Output $nodeExe; exit 0 }
  Write-Phase '[!] 本地 Node 版本过低，将重建'
}

# 2) 系统 node >=18 → 直接用系统 node
$sys = Get-Command node -ErrorAction SilentlyContinue
if ($sys) {
  if ((Get-Major 'node') -ge 18) { Write-Output 'node'; exit 0 }
  Write-Phase ('[!] 系统 Node 版本过低，改用便携版')
}

# 3) 下载便携 Node（Linux 式：命令行顺手装依赖）
Write-Phase '[*] 未检测到可用 Node，从 nodejs.org 下载便携版 …'
$version = '20.18.1'
try {
  $idx = Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json' -UseBasicParsing -TimeoutSec 30
  $lts = $idx | Where-Object { $_.lts -ne $false } | Select-Object -First 1
  if ($lts) { $version = ($lts.version).TrimStart('v') }
} catch { Write-Phase ('[!] 获取最新版本失败，回退 {0}' -f $version) }

$url  = "https://nodejs.org/dist/v$version/node-v$version-win-x64.zip"
$zip  = Join-Path $dir "node-$version-win64.zip"
$tmp  = Join-Path $dir '_nodetmp'
Write-Phase ('[*] 下载 Node {0} …' -f $version)
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 600
if (-not (Test-Path $zip) -or (Get-Item $zip).Length -lt 1000000) { throw 'Node zip 下载不完整' }

Write-Phase '[*] 解压到 node/ …'
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$inner = Get-ChildItem $tmp -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'node.exe') } | Select-Object -First 1
if (-not $inner) { throw '解压后未找到 node.exe' }
if (Test-Path $nodeDir) { Remove-Item $nodeDir -Recurse -Force }
Move-Item $inner.FullName $nodeDir
Remove-Item $zip -Force -ErrorAction SilentlyContinue
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Phase ('[OK] 便携 Node 就绪：{0}' -f $nodeExe)
Write-Output $nodeExe
