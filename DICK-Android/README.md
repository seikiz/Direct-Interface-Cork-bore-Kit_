# DICK-Android — 手机版（APK）

Python 桌面版的功能移植到 Android。核心层（JSON/对话树/引擎）零第三方依赖，
已在桌面 kotlinc 环境编译并全部自检通过；插件层（骰子/记忆/滑动/搜索/财报/翻译）
纯 Kotlin，同样可离线测试。

## 功能清单（v1.0）

- 流式聊天（气泡 UI、打字中实时显示）
- 侧滑抽屉：☰ → 其它项目 → 设置/角色/世界/分享
- 底部传图：🖼️ 选图后发送，气泡内显示图片
- 传图补丁：图片先走 OVH 免费视觉链（免 Key，5 模型轮换，每模型 2 次/分钟/IP）转成中文描述，再喂给纯文本 DeepSeek 思考
- 角色卡：内置 3 个示例，可新建；多选 = 群聊，[角色名]: 前缀自动归属，@角色名 指定发言
- 群聊自动接话（设置里开关）
- 提示词预设 7 个（默认/跑团主持人/小说叙事/单推/角色单推/公文/财报）
- 世界卡（平行世界多选，内置 2 个示例）
- 玩家角色卡（设置里填写，以你的角色身份发言）
- 上下文预算（4K~128K 自动裁剪）
- 记忆链 /memory（保存与回溯）
- 多候选 /swipe
- 骰子 /r 2d6、/d20、/dice
- 联网搜索 /搜索 与 深搜 /深搜（自动跟进抓正文）
- 财报助手 /财报 爬取|标题|入库|检索|定时 + 通用爬取 /爬取 <网址>（10 官方源深爬 + 政策库自动引用）
- 日文翻译 /jp /zh
- 系统 TTS 朗读 AI 回复（日文自动切日语语音引擎，需手机装有对应语音包）
- 聊天记录一键分享（系统分享面板）

## PC 版专属（APK 暂不含）

VOICEVOX 可爱声线、Word/Excel 排版导出、创意工坊服务器、PNG 酒馆卡导入。

## 构建（在装有 Android Studio 的本机）

1. 打开本目录（Android Studio 会自动装缺失的 SDK 组件并同步依赖——仓库已配阿里云镜像）
2. 命令行方式：

    cd DICK-Android
    powershell -ExecutionPolicy Bypass -File ..\DICK-Kotlin\install-gradle.ps1   # 若 Gradle 未装
    gradle assembleDebug

3. 产物：app/build/outputs/apk/debug/app-debug.apk
   安装：adb install app-debug.apk 或直接把 apk 传到手机点击安装（需允许未知来源）

4. 装好后：设置里填 DeepSeek API Key → 选角色 → 开聊。

## 核心逻辑离线自检（无需 Android SDK）

    kotlinc -include-runtime -d check.jar app/src/main/java/com/dick/core/*.kt app/src/main/java/com/dick/plugins/*.kt app/src/main/java/com/dick/tools/*.kt
    java -Dfile.encoding=UTF-8 -jar check.jar --selftest

> 上面的 `check.jar` 那条命令**已经跑不起来**了：core 需要 android.jar，plugins 需要 Compose runtime。
> 能用的是 `selftest\run.ps1`（按依赖闭包分两个测试）：
>
>     powershell -ExecutionPolicy Bypass -File selftest\run.ps1
>
> `core` 现在有一个带第三方依赖的文件 —— `Lanes.kt`（分道执行，用 kotlinx-coroutines），
> 脚本会自动从 Gradle 缓存里取 `kotlinx-coroutines-core-jvm-*.jar` 加进 classpath。

## 分道执行（Lanes.kt）

手机端原来到处是 `scope.launch(Dispatchers.IO) { …; launch(Main) { 更新界面 } }`：
并发不受控、顺序没保证、出问题也看不出"现在在跑什么"；更要紧的是**保序类的重活压在主线**上 ——
每落一条回复就要在主线程上序列化整棵树并写盘、写机制状态 JSON、跑插件钩子。

现在按电脑端 `jobs.py` 的同一套想法分道（`core/Lanes.kt`）：

| 线 | 并行度 | 跑什么 |
| --- | --- | --- |
| `io` | 1 | 存档落盘、机制状态落盘、角色卡导入/导出、工坊导出 |
| `vision` | 1 | 图片理解（免费视觉链自己有速率限制） |
| `plugin` | 1 | 插件钩子（同一插件要先看到前一条回复）—— 记忆链的落盘也在这条线上 |
| `net` | 4 | 工坊同步、搜索、下载、局域网探测（请求彼此独立） |

约定：**同线保序、跨线并行**；`Lanes.status()` 能看到每线在跑什么、完成/失败多少次；
单条任务抛异常只记账，不会拖垮这条线。`App.kt` 与插件里的裸 `Thread { }` 已经清零。
线只留真在用的四条 —— 声明了没人用的空线比缺一条更糟（读代码的人会以为它在跑东西）。

`tests/test_android_lanes.py` 用结构断言盯着这些约定：重活不许回主线程、每条线都得有人用
（空线是负债）、裸 `Thread { }` 只许出现在下面那两处被说明的文件里。它是**文本层面的**结构检查 ——
证明"谁跑在哪条线上"，不证明运行时真的不卡（那个得在真机上量）。

几个刻意留在原地的，都写在代码注释里存档：

- **流式剥标签留在主线程**：`mech.stripTags()` 会写 mech 的 `state`（`apply=false` 时也可能新建
  `status` 字段），多个线程同时碰就是数据竞争 —— 快不是这里的第一优先级。
- **TTS 留在主线程**：系统 TTS 的调用本身要在主线程发起。
- **`ChatEngine` 的流式工作线程**：要能 `interrupt` 停掉，也不能长期占住一条线的名额。
- **`TrpgServer` 的 accept / handle 循环**：常驻服务端循环，不是"干完就完"的任务。

"先在主线程取快照，再把写盘丢给 io 线"是这里的固定写法（`saveTree()`、`persistMechAsync()`）：
序列化必须趁数据没被改完，写盘才可以慢慢来。

## 目录结构

    app/src/main/java/com/dick/
      core/       Json / Model / ChatTree / ChatEngine(HttpURLConnection) / AppEnv / Lanes(分道执行)
      plugins/    Plugin 接口 + 注册表 + 6 个内置插件（含 WebFetch 抓取工具）
      app/        MainActivity + Compose 主界面（设置/角色/世界/分享/TTS）
                  CardIo.kt 角色卡进出的"重活"（读 URI / 解析 PNG 嵌卡 / 写角色卡+世界卡），跑在 io 线上
      tools/      Check.kt 自检（含 Python 存档兼容）
    selftest/     不依赖 Compose 的独立测试（TextGuard / 机制状态重置），run.ps1 一键跑
