<!-- <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌ -->
# image_gen —— 生图块（四个后端 · 预设可覆盖 · 支持 seed）

服务名 `image_gen`，实现 `service.py:ImageGenService`。能力搬家来源是仓库根的
`image_gen.py`（489 行），**协议与文案一字未改**，只是从"宿主的一个库"变成"能整目录搬走的块"。

## 接口（`kernel.service("image_gen")` 之后）

| 组 | 方法 |
|---|---|
| 宿主注入 | `bind(host)` —— 认 `time` / `proxy` / `log` / `progress` 四个属性，都可缺省 |
| 一键生图 | `generate(prompt, preset, size, api_key, base_url, model, negative_prompt, extra, seed, presets, backend, timeout)` → `(ok, 数据, 消息)` |
| 后端识别 | `backend_of` / `resolve_backend` / `needs_key` / `split_size` / `mime_of` |
| 预设读写 | `presets_path` / `load_presets` / `save_presets` / `user_presets_json` / `list_presets` |

`generate` 的第二个返回值：`{"b64"|"url", "mime", "preset", "seed"}`（前端直接展示 / 存聊天）。

## 四个后端（按 `base_url` 自动识别，设置里也能手选）

| 后端 | 端点 | 要不要 Key |
|---|---|---|
| `openai` | `POST {base}/images/generations` | 要（硅基流动 / 智谱 / 任意兼容中转） |
| `pollinations` | `GET {base}/prompt/<提示词>` | 不要（免费，有 402/429 限流，自带一次退避） |
| `sdwebui` | `POST {base}/sdapi/v1/txt2img` | 不要（本地 A1111 / Forge / SD.Next） |
| `comfyui` | `POST {base}/prompt` + 轮询 `/history` + `/view` | 不要（本地 ComfyUI，默认 8188） |

## 边界（为什么它搬得走）

1. **不读宿主配置**：`api_key` / `base_url` / `model` / `backend` 全由调用方按次传进来。
2. **不猜宿主路径**：预设文件路径由调用方给（`load_presets(base_dir)`）。
3. **只依赖 stdlib**：`urllib` / `json` / `base64` / `uuid`，`requires.pip` 为空。
4. **网络收在一个 `Net` 里**：自检塞假传输（`FakeNet`），所以四条协议不开一条 socket。

## 文件（每个 ≤400 行）

| 文件 | 行 | 装什么 |
|---|---|---|
| `module.py` | 32 | 唯一入口 `register(kernel)` |
| `service.py` | 129 | `ImageGenService`：宿主注入 + 上面那张接口表 |
| `backends.py` | 377 | `Net` + 四个后端的协议实现 + 分发 |
| `presets.py` | 174 | 内置 6 套预设 + 用户覆盖的读写（不认识的键不丢） |
| `harness.py` | 132 | 自检脚手架：假传输 / 假宿主 / 断言小工具（一条 socket 都不开） |
| `cases.py` | 369 | 19 个 case：四条协议的两头 + 坏输入 |
| `selftest.py` | 79 | `--selftest` 入口：跑 case、算耗时、打一行 JSON |

## 自检（闭环，不惊动任何别的块）

```
python -m modules.image_gen --selftest
→ {"block": "image_gen", "pass": 19, "fail": 0, "ms": 5, "deps": []}
```

单 case 复现：`python -m modules.image_gen --selftest --only comfyui`。

## 壳层怎么用

仓库根 `image_gen.py` 已经变成**门面**（转调本块，同名函数一个不少），主程序的
`api_gen_image` / `api_gen_presets` / `api_save_image_gen` / `api_get_image_presets_file` /
`api_save_image_presets_file` 一行都不用改，行为与搬家前完全一致。
