<!-- <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ -->
# codex —— CODEX 视觉小说（GALGAME）块

服务名 `codex`，实现 `service.py:CodexService`。能力搬家来源是仓库根的 `codex_core.py`
（**2030 行**），按 400 行预算拆成 10 个实现文件 + 3 个自检文件，
**格式、校验规则、文案一字未改**。

## 一个 CODEX 包长什么样

```
<包名>/codex.json  +  sprites/ bg/ bgm/ voice/       （导出 zip 就是把这个目录打包）
```

```json
{"codex": "1.0", "name": "我的故事", "author": "", "intro": "简介",
 "scenes": [{"id": "s1", "bg": "bg/教室.png", "bgm": "bgm/主题曲.mp3",
   "lines": [{"speaker": "咲", "sprite": "sprites/咲_立绘.png", "voice": "voice/01.wav",
              "text": "早上好！"},
             {"choice": [{"text": "打招呼", "goto": "s2"}, {"text": "无视", "goto": "s3"}]},
             {"jump": "s4"}, {"end": "结局：日常的一天"}]}]}
```

行类型：`text`（台词）/ `note`（旁白）/ `show`·`hide`·`bg`·`bgm`·`sfx`·`effect`（表现）/
`choice`（分支）/ `jump` / `action`（插件命令）/ `end` / `wait` / `setflag` / `roll`。

## 接口（`kernel.service("codex")` 之后，28 个方法）

| 组 | 方法 |
|---|---|
| 宿主注入 | `bind(host)` —— 认 `codex_dir` / `mark`（水印模块）/ `log` / `progress` |
| 剧本语法 | `classify_file` `parse_script_text` `normalize_script` `sanitize_html` `validate_codex` `step_kind` |
| 条件与推进 | `evaluate_condition` `filter_choices` `cond_pass` `simulate` `run_path` |
| 静态分析 | `analyze_codex`（可达性 / 资源引用 / 死分支） |
| 包与导出 | `make_template` `import_folder` `make_sample_package` `export_zip` `import_zip` |
| 播放器 | `build_standalone_html` `build_standalone_file` `render_standalone` `build_exe_shell` `pyinstaller_cmd` `build_standalone_exe` |
| 路径辅助 | `pack_dir(name)` `list_packages()`（只这两个用 `codex_dir`，别的方法仍按调用方给的路径干活） |

## 文件（每个 ≤400 行，依赖单向）

| 文件 | 行 | 装什么 | 依赖 |
|---|---|---|---|
| `constants.py` | 48 | 格式常量 + 文件名分类（只读查表） | — |
| `scene.py` | 252 | 文本剧本 → codex.json | constants, rules |
| `rules.py` | 251 | 行类型 / 条件 / 选项 / HTML 消毒 / 校验 | — |
| `flow.py` | 308 | 单路径走查 + 全路径模拟 | rules |
| `analyze.py` | 224 | 可达性 / 资源引用 / 死分支 | constants |
| `pack.py` | 312 | 目录布局 + zip + 示例包 + 占位素材 | constants |
| `player_js.py` | 336 | 导出播放器的内联 JS（326 行字符串） | — |
| `player.py` | 202 | 单文件 HTML 渲染（模板 + 注入点 + 水印） | constants, player_js |
| `exe.py` | 155 | 独立 EXE（pywebview 壳 + PyInstaller 命令） | pack, player |
| `service.py` | 187 | 对外接口表（转发 + 注入 mark） | 上面全部 |
| `harness.py` 116 / `cases.py` 361 / `selftest.py` 78 | 自检脚手架（假宿主 / 假水印 / 轻量夹具包）+ 21 个 case + 跑批入口 | service |

## 边界（为什么它搬得走）

1. **自带格式**：目录布局与 zip 结构由 `pack.py` 定义，只认传进来的路径；
   块不读宿主 `config.json`，也不猜"用户数据目录在哪"。
2. **不 import 宿主**：原来 `player.py` 直接 `import dick_mark`（仓库根的水印模块），
   那是块唯一"长在宿主身上"的地方 —— 现在由 `bind(host)` 的 `mark` 注入，没给就跳过。
3. **只依赖 stdlib**：`json` / `os` / `re` / `struct` / `zipfile` / `zlib` / `base64`，
   `requires.pip` 为空。
4. **打包 EXE 不归自检管**：真跑 PyInstaller 要几分钟，自检只验命令构造。

## 自检（闭环，不惊动任何别的块）

```
python -m modules.codex --selftest
→ {"block": "codex", "pass": 21, "fail": 0, "ms": 355, "deps": []}
```

单 case 复现：`python -m modules.codex --selftest --only zip_roundtrip`。
预算说明：占位 PNG 是纯 Python 逐像素画的（一张 420×720 ≈ 126ms、示例包 ≈ 760ms），所以自检只造一个
**轻量夹具包**，示例包布局那个 case 把两个生成器换成桩（生成器本身另有一个 case 直接验字节）。

## 壳层怎么用

仓库根 `codex_core.py` 已经变成**门面**：27 个函数名 + 5 个数据常量一个不少，
主程序 `api_codex_*` 五十处调用点一行都不用改。
`CODEX_FORMAT = "codex/1.0"` 这个"只出现在定义处、没写进包也没校验"的常量留在门面里
（tests/test_compat_surface.py 钉住了这个现状）。
