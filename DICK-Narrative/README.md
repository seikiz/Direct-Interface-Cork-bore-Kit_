# DICK 叙事引擎 · 原生播放器

同一个故事，同一套引擎，两端渲染：**桌面 EXE** 和 **安卓 APK**。
不是网页套壳，是真正的原生窗口程序（Compose Multiplatform / Kotlin）。

- 引擎与界面完全分离：`engine/` 是纯 Kotlin，不引用任何 UI，可以单独测试。
- 故事格式与 DICK 的 GAL制作器一致（`scenes[]` + `lines[]` + `roles[]`），
  所以制作器里做出来的东西，这里**不用转换**就能直接跑。

---

## 一、目录结构

```
DICK-Narrative/
├── app/src/
│   ├── commonMain/kotlin/com/dick/narrative/
│   │   ├── engine/          引擎（纯 Kotlin，无 UI）
│   │   │   ├── Spec.kt        规格模型 + JSON 解析（旧 GAL 格式也能读）
│   │   │   ├── Condition.kt   条件求值（aff / status / flags / all / any）
│   │   │   ├── Engine.kt      线-点-分支 状态机 + 存档快照
│   │   │   └── Demo.kt        内置示例故事（没有故事包时也能开）
│   │   ├── platform/        平台层（expect）
│   │   │   └── Platform.kt    文件 / 图片 / 音频 / 全屏
│   │   └── ui/              播放器界面（Compose）
│   │       ├── Player.kt      画面 + 对话框 + 分支 + 菜单 / 回想 / 设置 / 存读档 / CG
│   │       ├── Frame.kt       引擎 → 界面的不可变快照
│   │       ├── SaveStore.kt   存档 / 读档 / 设置落盘
│   │       ├── StoryImage.kt  图片缓存
│   │       └── Theme.kt       哥特暗色
│   ├── desktopMain/         桌面实现（java.io / skiko / javax.sound）+ main()
│   ├── androidMain/         安卓实现（BitmapFactory / MediaPlayer）+ Activity
│   └── commonTest/          引擎测试（9 项）
└── story/story.json         示例故事包
```

---

## 二、故事格式（引擎与渲染器之间唯一的契约）

```jsonc
{
  "name": "故事名",           // 标题界面显示
  "intro": "一句话简介",
  "roles": [                  // 角色是独立实体
    { "name": "薇拉", "sprite": "sprites/vera.png", "voice": "voice/vera_01.ogg" }
  ],
  "scenes": [                 // 一条线 = 一个场景
    {
      "id": "s1",             // 分支跳转用的名字，必须唯一
      "title": "序章 · 门厅",  // 右上角显示
      "key": true,            // 关键线（制作器里用来「只看关键」）
      "images": ["cg/a.png"], // 这条线里固定显示的剧照
      "next": "s2",           // 走完这条线去哪
      "lines": [ /* 点 */ ]
    }
  ]
}
```

### 点（`lines[]` 里的每一项）

| kind | 作用 | 主要字段 |
|---|---|---|
| `say` | 角色台词 | `speaker`（角色名）、`text` |
| `note` | 旁白 | `note` |
| `bg` | 换背景 | `bg` |
| `bgm` | 换背景音乐 | `bgm` |
| `sfx` | 音效 | `sfx` |
| `effect` | 特效 | `effect`：`shake`/`flash`（含「震」「闪」也行） |
| `show` / `hide` | 立绘出现 / 消失 | `sprite` |
| `wait` | 停顿 | `ms` |
| `setflag` | 设置标记 | `flag: {"k":"名字","v":true}` |
| `choice` | 分支 | `choice: [{"text":"选项","goto":"s2","if":{...}}]` |
| `jump` | 跳转 | `goto` |
| `end` | 结局 | `end`（结局标题） |
| `action` | 留给宿主程序的动作 | `action` |

任何一个点都可以额外带：

- `if` —— 条件不成立就跳过这个点（`choice` 的选项则是「不显示这个选项」）。
- `voice` —— 这一句的语音（不写就用角色的默认语音）。
- `duration` / `effect` 等表现字段，按需。

### 条件写法（与 DICK 机制卡一致）

```jsonc
{"aff": ">=85"}                       // 好感度，支持 >= > <= < != =
{"status": {"心情": "开心"}}           // 状态字段精确匹配
{"flags": ["见过面", "!已经死了"]}      // 存在 / 必须不存在（! 前缀）
{"all": [c1, c2]}                     // 全部成立
{"any": [c1, c2]}                     // 任一成立
{} 或 不写                             // 恒真
```

---

## 三、怎么跑

前置：本机需要 **JDK 17+**，Android 打包还需要 Android SDK（`local.properties` 里的 `sdk.dir`）。

```powershell
cd C:\Users\seiki\Desktop\dist\DICK-Narrative

# 引擎测试（9 项，不依赖界面）
& C:\Users\seiki\kotlin-tools\gradle-8.10.2\bin\gradle.bat :app:desktopTest

# 桌面直接运行（开发用）
& C:\Users\seiki\kotlin-tools\gradle-8.10.2\bin\gradle.bat :app:run

# 桌面打包成免安装的 EXE
& C:\Users\seiki\kotlin-tools\gradle-8.10.2\bin\gradle.bat :app:packageAppImage

# 安卓 APK
& C:\Users\seiki\kotlin-tools\gradle-8.10.2\bin\gradle.bat :app:assembleDebug
```

也可以直接用一键脚本（推荐，坑都埋好了）：

```powershell
cd C:\Users\seiki\Desktop\dist\DICK-Narrative
powershell -ExecutionPolicy Bypass -File build.ps1          # 测试 + EXE + APK 全做
powershell -ExecutionPolicy Bypass -File build.ps1 -Run     # 只想先看看长什么样
```

产物位置：

- EXE：`app/build/compose/binaries/main/app/DICK-Narrative/DICK-Narrative.exe`
  —— **整个 `DICK-Narrative` 文件夹要一起拷走**才能运行（里面带了 Java 运行时，约 127 MB）
- APK：`app/build/outputs/apk/debug/app-debug.apk`（约 9 MB）

### 打包 EXE 的两个坑（已解决，换机器时可能再遇到）

1. Windows 上 Compose 打包会去 GitHub 下 WiX，国内常常连不上（会卡很久然后失败）。
   免安装的 `AppImage` 其实用不到 WiX —— 把环境变量 **`WIX_PATH` 指向任意一个存在的目录**即可跳过下载。
   `build.ps1` 已自动设好。
2. **打包需要 `jpackage`**，而 Android Studio 自带的 JBR 里没有。本项目用的是另外下的 JDK 21
   （`C:\Users\seiki\kotlin-tools\jdk21\jdk-21.0.12.1+1`），`build.ps1` 会自动指过去。
   只有「安装程序」格式（`TargetFormat.Exe` / `Msi`）才真的需要 WiX Toolset v3。

### 故事放哪儿

程序按这个顺序找故事：

1. 环境变量 `DICK_STORY_DIR`
2. 程序（exe）同级目录下的 `story/` 或 `data/`
3. 当前工作目录

都没有就播内置示例《钟楼之下》，保证程序永远打得开。
存档在 `%USERPROFILE%\.dick-narrative\saves\`（安卓在应用私有目录）。

---

## 四、已经能用的 / 还没做的

**能用**：背景、立绘、剧照、台词 + 旁白、打字机（速度可调）、分支选项（带条件）、
标记与条件、跳转与多结局、震屏 / 闪白、BGM / 语音 / 音效（音量可调）、
存读档（自动 + 8 个手动槽，槽位显示时间 / 所在线 / 台词文字预览）、回想、设置、
CG 鉴赏（列出故事里出现过的剧照）、标题界面、全屏（桌面端可用）。

**还没做**（按优先级）：

1. 存档槽只有**文字**预览，还没有画面缩略图。
2. 桌面端 BGM 目前只解 **WAV**；mp3/ogg 需要再加一个解码库（安卓端已全支持）。
3. 立绘只有一个位置（居中），没有左中右 / 缩放 / 淡入淡出。
4. 没有自动播放、快进已读、字号设置。
5. 全屏在安卓端是空实现（交给系统栏策略）。
6. 没有 Live2D。
7. 安卓端还没做「选故事包」的界面，故事要先拷进应用私有目录或打包进 assets。

---

## 五、和 GAL制作器 的关系（这段是重点）

**GAL制作器 里做的东西，导出来就能直接用这个播放器跑，不需要任何转换。**
制作器顶部工具条上有一个 `🎬 播放器` 按钮：

```
GAL制作器（DICK 网页端 · 线-点-分支 节点图）
        │
        │  点「🎬 播放器」→  先自动存盘 → 选个目录（默认桌面）
        ▼
  <你选的目录>/<包名>/
      DICK-Narrative.exe        ← 原生播放器（自带 Java 运行时）
      app/  runtime/            ← 播放器本体，别删
      story/
          codex.json            ← 你的剧本，原样搬过去
          sprites/ bg/ bgm/ voice/   ← 素材
      玩这个.txt
```

**整个文件夹一起拷走就能给别人玩**（约 127 MB，因为带了运行环境）。
双击 `DICK-Narrative.exe` 即可，不需要装 Python、不需要装 Java、不是网页套壳。

打开「🎬 播放器」前，播放器必须已经构建过一次：

```powershell
cd C:\Users\seiki\Desktop\dist\DICK-Narrative
powershell -ExecutionPolicy Bypass -File build.ps1 -Exe
```

没构建的话，点按钮会直接提示你先去构建（不会静默失败）。

**导出的目录里为什么是 `codex.json` 而不是 `story.json`？**
两个名字播放器都认，`codex.json` 在前。制作器本来写的就是 `codex.json`，所以原样搬过去，
这样同一个包同时还能被 DICK 主程序和网页播放器读，不用维护两份。

### 兼容性上踩过的坑（都修了）

制作器实际写出来的格式比想象中「松」，播放器一开始对不上，改了三处：

| 制作器实际写法 | 一开始的问题 | 现在 |
|---|---|---|
| `bg` / `bgm` 挂在**线**上（`scenes[i].bg`） | 解析器只认点级 bg/bgm，线级被丢掉 → 进场景不切背景 | 线级 bg/bgm 在进入这条线时生效 |
| 一行可以挂**多张**立绘 `sprites: [{file:...}]` | 只读单数 `sprite` | 单数/列表都吃，列表优先 |
| 示例包和老剧本**不写 `kind`** | 靠字段猜类型 | 保留字段推断，并和 `codex_step_kind` 的顺序对齐 |

另外播放器目录会自己带一份示例故事，导出时会**先清掉** `story/` 再放你的，
否则两个故事会打架（这个坑真踩到过：导出的 exe 显示的是示例故事名）。

---

## 五、三端关系

```
       GAL制作器（DICK 网页端 · 线-点-分支 编辑器）
                     │  产出 codex.json + 素材
                     ▼
              ┌──────────────┐
              │  叙事引擎     │  一份规格，多端渲染
              └──────────────┘
                 │        │        │
        DICK 主程序内嵌   本播放器   独立 HTML
        （聊天里直接玩）  EXE/APK    （导出选项之一）
                            ▲
                            │  🎬 播放器 按钮
                    GAL制作器 直接导出 ┘
```

## 六、相关测试

```powershell
# 引擎（Kotlin，12 项）
cd DICK-Narrative
& C:\Users\seiki\kotlin-tools\gradle-8.10.2\bin\gradle.bat :app:desktopTest

# 导出链路（Python，23 项，不需要真播放器）
cd ..
python tests/test_codex_player_export.py

# 真·端到端（手动，会拷 127MB 并弹窗口）
python tests/manual_player_e2e.py 我的故事
```

