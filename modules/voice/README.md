<!-- <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ -->
# voice —— 语音块（UTAU 唱歌 / HANASU-VOICEVOX 说话）

服务名 `voice`，实现 `service.py:VoiceService`。能力搬家来源是仓库根的 `voice_engine.py`
（260 行），**音色参数、语气规则、错误文案一字未改**。

## 接口（`kernel.service("voice")` 之后）

| 方法 | 干什么 |
|---|---|
| `bind(host)` | 宿主注入：`base_dir` / `utau_python` / `voicebank` / `utau_speak` / `synth` / `synth_ready` / `voicevox_url` / `log` |
| `synthesize(text, cache_dir, pitch_mode="auto", engine=None)` | **输入是文本、输出是 wav 路径**；缓存目录由调用方给 |
| `pick(engine)` | `auto` = HANASU 就绪就用它，否则回落 UTAU；返回 `(实例, 名字)` |
| `is_ready(engine)` | `(能不能用, 引擎名)` |
| `detect_conflicts()` | 日语系统 / 文件系统编码 / 控制台编码 / VOICEVOX 就绪的体检表 |
| `engines()` | `["utau", "hanasu"]` |

## 两个引擎

| 引擎 | 怎么合成 | 依赖 |
|---|---|---|
| `utau` | 进程内（宿主注入的 `synth`）优先；没有再回落 `utau_env` 子进程跑 `utau_speak.py` | 声库目录 + 二者之一 |
| `hanasu` | VOICEVOX 本地 HTTP：`/audio_query` → 语气微调 → `/synthesis`（默认 `:50021`） | 本地 VOICEVOX |

语气模式：`auto`（按文本判 happy/sad/angry/question/flat）/ `flat` / 其余同名值。
`auto` 只影响语速与语调，不改文本。

## 边界（为什么它搬得走）

1. **不猜目录**：解释器、声库、合成脚本三样路径全部 `bind(host)` 注入；
   缺了就抛出带人话的 `VoiceEngineError`（"未找到声库：…" / "UTAU 环境缺失：…"）。
2. **不 import 第三方引擎**：进程内合成（`putao`）由宿主以 `synth` 回调注入；
   `synth_ready()` 决定"进程内到底行不行"，块本身只依赖 stdlib。
3. **传输可替换**：HANASU 的 HTTP 收在 `opener(method, url, data, headers, timeout)`，
   自检塞替身就能把三段请求跑通，不开一条 socket。
4. **声卡独占**：`synthesize` 自带一把锁，并发调用会排队 —— 搬家前这条串行是靠壳层
   `jobs` 的 `voice` 线（并发 1）保证的，块自己搬走以后必须自带这条约束。

## 文件（每个 ≤400 行）

| 文件 | 行 | 装什么 |
|---|---|---|
| `module.py` | 35 | 唯一入口 `register(kernel)` |
| `engines.py` | 221 | `VoiceEngineError` / `analyze_tone` / `UtauEngine` / `HanasuEngine` |
| `service.py` | 189 | `VoiceService`：宿主注入、挑引擎、独占锁、环境体检 |
| `harness.py` | 146 | 自检脚手架：假宿主 / 假 HANASU / 假 UTAU（不连网、不起 VOICEVOX） |
| `cases.py` | 307 | 16 个 case：两条合成路线 + 5 条坏输入 + 并发独占 |
| `selftest.py` | 79 | `--selftest` 入口：跑 case、算耗时、打一行 JSON |

## 自检（闭环，不惊动任何别的块）

```
python -m modules.voice --selftest
→ {"block": "voice", "pass": 16, "fail": 0, "ms": 150, "deps": []}
```

单 case 复现：`python -m modules.voice --selftest --only hanasu_protocol`。
自检里唯一起子进程的那条（`utau_subprocess`）只跑本地 python 写一个 wav，不连网、不占端口。

## 壳层怎么用

仓库根 `voice_engine.py` 已经变成**门面**：`VoiceEngine` / `UtauEngine` / `HanasuEngine` /
`VoiceEngineError` / `detect_jp_conflicts` / `_analyze_tone` 一个都不少，签名与搬家前一致。
宿主侧的三条加固（`_safe_stdout`、`putao` 内嵌合成、`utau_speak.py` 路径）留在门面里，
块里不出现任何"只有在 DICK 里才成立"的分支。
