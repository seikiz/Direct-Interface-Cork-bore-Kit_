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

## 目录结构

    app/src/main/java/com/dick/
      core/       Json / Model / ChatTree / ChatEngine(HttpURLConnection) / AppEnv
      plugins/    Plugin 接口 + 注册表 + 6 个内置插件（含 WebFetch 抓取工具）
      app/        MainActivity + Compose 主界面（设置/角色/世界/分享/TTS）
      tools/      Check.kt 自检（含 Python 存档兼容）
