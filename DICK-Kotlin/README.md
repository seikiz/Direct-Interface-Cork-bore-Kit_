# DICK-Kotlin — Direct-Interface Cork-bore Kit（Kotlin 版）

Python 版（CustomTkinter）的架构转运目标。**数据格式与 Python 版完全兼容**：
同一份 saves/worlds/personas/prompt_presets/config.json/policy_db.json 两边通用。

## 技术栈

- Kotlin 2.1 + Compose Desktop 1.8（仅 UI 层）
- **核心层零依赖**：手写 JSON 解析/序列化（Json.kt，精确对齐 Python json 输出：整数原样、原始 UTF-8、2 空格缩进）
- kotlinx-coroutines（UI 异步）
- JDK 内置 HttpClient（OpenAI 兼容流式 API）
- JDK 17+（Android Studio 自带 JBR 即可）

## 验证状态（2026-08 已实测）

- 核心层已用 kotlinc 2.1.10 编译通过，17 项自检全绿（JSON 转义/整数保留/snake_case/树操作）
- 真实 Python 版存档 saves/咲.json 已通过互通验证（15 节点完整解析、链重建正确）
- Kotlin 编译器已安装：C:\Users\seiki\kotlin-tools\kotlinc（已加入用户 PATH，任意终端可用 kotlinc）
- UI 层（Compose）需本机 Gradle 构建（沙箱网络无法拉取 Maven 依赖）

## 构建与运行（本机）

1. 用 Android Studio / IntelliJ IDEA 打开本目录，等 Gradle 同步（首次会下载依赖）
2. 或在命令行（需本机已装 Gradle 8+）：

    gradle wrapper --gradle-version 8.10.2
    gradlew run

3. 兼容性自检（读 Python 版存档并打印统计）：

    gradle run --args="saves/咲.json"

   或指定数据根目录共用 Python 版全部数据（把 saves/worlds/personas 等当成本机目录）：

    gradle run -Ddick.home="C:/Users/seiki/Desktop/dist" --args="saves/咲.json"

4. 核心层自检（无需 Gradle，纯离线）：

    kotlinc -include-runtime -d check.jar src/main/kotlin/com/dick/core/*.kt src/main/kotlin/com/dick/plugins/*.kt src/main/kotlin/com/dick/tools/*.kt
    java -Dfile.encoding=UTF-8 -jar check.jar --selftest
    java -Dfile.encoding=UTF-8 -jar check.jar C:/path/to/saves/咲.json

## 目录结构

    src/main/kotlin/com/dick/
      core/    领域层（纯 Kotlin，无 UI 依赖）
        Model.kt        MessageNode / ChatTree / 世界卡 / 角色卡 / 预设 / 配置
        TreeStore.kt    存档读写（与 Python history_tree 格式一致）
        AppPaths.kt     便携路径（dick.home / exe 目录）
        Config.kt       config.json 读写
        ChatEngine.kt   流式聊天引擎（DeepSeek 等 OpenAI 兼容服务）
      plugins/ 插件接口（对应 Python 版 on_load/on_command/on_message_send/on_message_received）
      ui/      Compose Desktop 界面
    src/test/kotlin/com/dick/core/  单元测试（树操作 / JSON 兼容性）

## 路线图

- P1（本次）：骨架 + 领域层 + 流式引擎 + 最小聊天窗口 + Python 存档兼容自检 ✓
- P2：完整聊天 UI（气泡/头像/群聊 @/多候选/预算滚动摘要/预设/世界卡/记忆链）
- P3：插件体系（19 个内置插件 Kotlin 化：骰子/记忆/滑动/日文/TTS/世界书/搜索/财报/办公…）
- P4：VOICEVOX TTS、创意工坊客户端、jpackage 便携打包（exe 旁数据目录同 Python 版）

## P1 已知边界（后续阶段补齐）

- 无插件动态加载、无角色卡 UI（system_prompt 暂用内置默认值）
- 无上下文预算/滚动摘要/世界书注入/群聊轮转（数据模型已预留 metadata）
- 流式回调在 IO 线程触发，UI 侧用 scope.launch(Dispatchers.Main) 收口（见 ui/Main.kt）
