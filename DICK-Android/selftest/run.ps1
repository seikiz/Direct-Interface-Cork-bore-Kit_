# 安卓侧独立测试（不需要 Compose；core 里的 android.graphics 用 android.jar 顶掉）
# 用法：powershell -ExecutionP<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌olicy Bypass -File run.ps1
#
# ① TextGuard：零宽字符防线
# ② MechReset：清空聊天记录 → 机制状态必须回到初始值
# ③ 生活层/空间层对拍：手机端算出来的菜单、时钟、注入、地图必须和电脑端逐字一样
#    （期望值由 python tools/gen_parity.py 冻结在 ParityGoldens.kt 里）
#
# 注：老的 Check.kt「全量自检」已经编不过了 —— core 需要 android.jar，plugins 需要 Compose runtime。
#     这里改成按依赖闭包分三个能跑的测试，别再依赖那个跑不起来的入口。
#
# ⚠ 这个文件**必须带 UTF-8 BOM**：`powershell -File`（Windows PowerShell 5.1）在没有 BOM 时按
#   ANSI/GBK 读脚本，中文注释的字节会成对吃掉行尾换行 → 注释行合并 → 函数定义被注释吞掉
#   → 报一句莫名其妙的「意外的标记 }」。tests/test_ps1_encoding.py 盯着这条。
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$root = Split-Path $here -Parent
$kotlincBat = 'C:\Users\seiki\kotlin-tools\kotlinc\bin\kotlinc.bat'
$kotlinHome = Split-Path (Split-Path $kotlincBat -Parent) -Parent
$core = Join-Path $root 'app\src\main\java\com\dick\core'
$androidJar = 'C:\Users\seiki\AppData\Local\Android\Sdk\platforms\android-35\android.jar'

# java：优先 Android Studio 自带 jbr，缺失退回 kotlin-tools 的 JDK21，再退回 PATH
$java = @(
    'C:\Program Files\Android\Android Studio\jbr\bin\java.exe',
    'C:\Users\seiki\kotlin-tools\jdk21\jdk-21.0.12.1+1\bin\java.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $java) { $java = 'java' }
$env:JAVA_HOME = Split-Path (Split-Path $java -Parent) -Parent

# 输出编码：JDK 18 起 stdout/stderr 跟**控制台代码页**走，`-Dfile.encoding` 管不到它 ——
# 把输出重定向到文件时会变成 GBK，看着像乱码（中文测试结果尤其明显）。显式指定，日志才可读。
$javaEnc = @('-Dfile.encoding=UTF-8', '-Dstdout.encoding=UTF-8', '-Dstderr.encoding=UTF-8')

# 直接调编译器（就是 kotlinc.bat 内部那行 java），不经 cmd：
# classpath 里带 `;` 时，cmd 会把它当批处理参数分隔符 —— 第二个 jar 会被当成源文件
# （报 "source entry is not a Kotlin file"），而 PowerShell 5 和 7 的引号转义规则还不一样，
# 与其跟引号斗，不如不给 cmd 解析的机会。
function Invoke-Kotlinc {
    param([string[]]$KotlincArgs)
    & $java @javaEnc `
        -cp "$kotlinHome\lib\kotlin-preloader.jar" `
        org.jetbrains.kotlin.preloading.Preloader `
        -cp "$kotlinHome\lib\kotlin-compiler.jar" `
        org.jetbrains.kotlin.cli.jvm.K2JVMCompiler @KotlincArgs
}

$result = 0

Write-Host "`n[1/3] TextGuard（零宽字符防线）" -ForegroundColor Cyan
$jar1 = Join-Path $env:TEMP 'textguard_test.jar'
Invoke-Kotlinc @('-classpath', $androidJar, (Join-Path $core 'TextGuard.kt'),
                 (Join-Path $here 'TextGuardTest.kt'), '-include-runtime', '-d', $jar1)
if (-not (Test-Path $jar1)) { Write-Host "TextGuard 编译失败"; exit 1 }
& $java '-Dfile.encoding=UTF-8' -jar $jar1
if ($LASTEXITCODE -ne 0) { $result = 1 }

Write-Host "`n[2/3] 机制状态全量重置（清空聊天记录 → 状态如初）" -ForegroundColor Cyan
$jar2 = Join-Path $env:TEMP 'mech_reset_test.jar'
$coreFiles = @(Get-ChildItem $core -Filter *.kt | ForEach-Object { $_.FullName })
# core 里唯一带第三方依赖的是 Lanes.kt（分道执行，用 kotlinx-coroutines）——
# 全量编 core 就得把它带上，否则整个自检编不过。jar 从 Gradle 缓存里找（离线可用）。
$coroutinesRoot = Join-Path $env:USERPROFILE '.gradle\caches\modules-2\files-2.1\org.jetbrains.kotlinx\kotlinx-coroutines-core-jvm'
$coroutines = Get-ChildItem -Path $coroutinesRoot -Recurse -Filter 'kotlinx-coroutines-core-jvm-*.jar' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
$cp = $androidJar
if ($coroutines) {
    $cp = "$androidJar;$($coroutines.FullName)"
} else {
    Write-Host "  找不到 kotlinx-coroutines-core-jvm-*.jar（Lanes.kt 需要它）—— 先在 DICK-Android 跑一次 gradle 解析依赖" -ForegroundColor Yellow
}
Invoke-Kotlinc (@('-classpath', $cp, (Join-Path $here 'MechResetTest.kt')) + $coreFiles +
                @('-include-runtime', '-d', $jar2))
if (-not (Test-Path $jar2)) { Write-Host "机制重置测试编译失败"; exit 1 }
if ($coroutines) {
    # -jar 的写法协程 jar 不在 classpath 上；万一测试碰到 Lanes 就是 NoClassDefFoundError，所以显式给 classpath
    & $java '-Dfile.encoding=UTF-8' -classpath "$jar2;$($coroutines.FullName)" MechResetTestKt
} else {
    & $java '-Dfile.encoding=UTF-8' -jar $jar2
}
if ($LASTEXITCODE -ne 0) { $result = 1 }

Write-Host "`n[3/3] 生活层/空间层对拍（手机端 vs 电脑端）" -ForegroundColor Cyan
$jar3 = Join-Path $env:TEMP 'dick_parity_test.jar'
$parityCore = @(
    (Join-Path $core 'Json.kt'),
    (Join-Path $core 'Model.kt'),
    (Join-Path $core 'AppEnv.kt'),
    (Join-Path $core 'TableTypes.kt'),
    (Join-Path $core 'Tables.kt'),
    (Join-Path $core 'PyRandom.kt'),
    (Join-Path $core 'Commonsense.kt'),
    (Join-Path $core 'LifeCore.kt')
)
# 空间层还在补 —— 文件在就一起编、一起对拍（不在就只跑生活层，不让整步挂掉）
foreach ($extra in @('SpaceCore.kt')) {
    $p = Join-Path $core $extra
    if (Test-Path $p) { $parityCore += $p }
}
$parityTests = @((Join-Path $here 'ParityGoldens.kt'), (Join-Path $here 'LifeParityTest.kt'))
$spaceTest = Join-Path $here 'SpaceParityTest.kt'
$hasSpace = Test-Path $spaceTest
if ($hasSpace) { $parityTests += $spaceTest }
Remove-Item $jar3 -ErrorAction SilentlyContinue
Invoke-Kotlinc (@('-classpath', $androidJar) + $parityCore + $parityTests +
                @('-include-runtime', '-d', $jar3))
if (-not (Test-Path $jar3)) { Write-Host "对拍测试编译失败"; exit 1 }
& $java '-Dfile.encoding=UTF-8' -classpath $jar3 com.dick.parity.life.LifeParityTestKt
if ($LASTEXITCODE -ne 0) { $result = 1 }
if ($hasSpace) {
    & $java '-Dfile.encoding=UTF-8' -classpath $jar3 com.dick.parity.space.SpaceParityTestKt
    if ($LASTEXITCODE -ne 0) { $result = 1 }
}

if ($result -eq 0) { Write-Host "`n全部通过" -ForegroundColor Green } else { Write-Host "`n有失败项" -ForegroundColor Red }
exit $result
