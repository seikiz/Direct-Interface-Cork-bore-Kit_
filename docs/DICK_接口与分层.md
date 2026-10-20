# DICK · 接口与分层（含线程模型）

> 只讲**现在的 DICK**。图是 ASCII，可直接照抄白板。
> 重点放在线程：这个项目"线程多"不是缺点，但**每一根线程都必须说得清归属**。

---

## 一、分层（三层 + 一层进程外）

```
┌──────────────────────────────────────────────────────────────────────┐
│  壳层 shells（装配 + 画界面，不实现业务）                             │
│    Direct-Interface Cork-bore Kit.py   HtmlApp（154 个 api_* 门面）   │
│    web/ 13 屏 · net.py（工坊服务器） · Android（Compose） · 播放器     │
└──────────────────────────▲──────────────────────┬────────────────────┘
                           │ service("id")        │ 事件 bus
┌──────────────────────────┴──────────────────────▼────────────────────┐
│  模块层 modules/<id>/（每个块一个目录，唯一入口 module.py:register）  │
│    backup  workshop  image_gen  voice  codex  couple                   │
│    四件套：manifest.json / block.json / module.py / README.md          │
└──────────────────────────▲──────────────────────┬────────────────────┘
                           │ 只许 import kernel    │ register / bind(host)
┌──────────────────────────┴──────────────────────▼────────────────────┐
│  内核 kernel/（不认识任何业务）                                       │
│    registry（服务）  bus（事件）  loader（manifest 装配）              │
│    manifest（五校验） config / paths / log / version                   │
└──────────────────────────────────────────────────────────────────────┘
      ▲ 进程外：adb / PyInstaller / 工坊服务器 net.py（独立进程）
```

三条铁律（画图时标出来）：
1. `kernel ← modules ← shells` 单向；
2. 模块之间**不许互相 import**，只能经 `registry.service()` / `bus.emit()`；
3. 壳层只做装配，业务不许写在 `api_*` 里。

---

## 二、接口清单

### 内核（`kernel/`）

| 接口 | 签名 | 契约 |
|---|---|---|
| `boot` | `boot(base_dir=None, modules_dir=None, log=None, load=True, echo=True)` | 单块失败不拦启动；返回 kernel |
| `registry.register` | `register(name, obj, owner=…)` | 重名拒绝；可按 owner 一次性回滚 |
| `kernel.service` | `service(name)` | **模块间唯一通信方式** |
| `bus.on / emit / emit_async` | `on(topic, handler)` / `emit(topic, **payload)` | 坏订阅者不传染；异步可注入执行器 |
| `loader.discover / load` | `discover()` / `load(module_id, retry=False)` | 按 manifest 装配；块内文件对外无名可 import |

### 模块契约（`modules/<id>/`）

| 文件 | 内容 | 校验 |
|---|---|---|
| `manifest.json` | `id / version(四段) / provides{services,routes,ui_screens,commands} / requires / lazy` | 多余字段拒；少注册=吹牛、多注册=偷给 → 回滚 |
| `block.json` | `files` 白名单 / `selftest` / `interface.methods` / 预算 | 清单外文件 → 红 |
| `module.py` | `def register(kernel)` | 唯一入口 |
| `README.md` | 职责 + 接口 + 为什么这么切 | 缺 → 红 |

### 七个块

| 块 | service | 一句话 |
|---|---|---|
| `kernel` | — | 内核自身 |
| `backup` | `backup` | 加密备份（crypto 由宿主注入） |
| `workshop` | `workshop` | 工坊客户端（列表/上传/下载/点赞/进度） |
| `image_gen` | `image_gen` | 四后端生图 |
| `voice` | `voice` | utau / hanasu 合成 |
| `codex` | `codex` | 编年史（9 个实现文件） |
| `couple` | `couple` | 耦合包 + 分次设定 + 模式互斥 |

---

## 三、线程模型（这是重点）

### 3.1 线程清单（按"谁创建、干什么、活多久"）

| # | 线程 / 执行体 | 创建位置 | 干什么 | 生命周期 |
|---|---|---|---|---|
| 1 | **主线程** | 解释器 | 事件循环 + 控制台 + 收尾 | 全程 |
| 2 | **pywebview GUI 线程** | pywebview 内部 | 窗口与 JS↔Python 桥（`api_*` 在这里被调用） | 全程 |
| 3 | `_detect_ollama` | `Kit.py:787` | 启动探测本地模型 | 一次性 |
| 4 | `_ws_pull_api` | `Kit.py:806` | 工坊拉取 API 配置 | 一次性 |
| 5 | `_vision_then_send` | `Kit.py:1805` | 图片识别后再发送 | 每张图一次 |
| 6 | `_ws_save_upload` | `Kit.py:4210` | 上传存档到工坊 | 每次上传 |
| 7 | `_ws_push_api_sync` | `Kit.py:4275` | 推送 API 配置 | 每次同步 |
| 8 | `_codex_exe_worker` | `Kit.py:5339` | 打包播放器 EXE | 每次导出 |
| 9 | `_codex_player_worker` | `Kit.py:5502` | 生成播放器资源 | 每次导出 |
| 10 | `_codex_release_worker` | `Kit.py:5918` | 发布编年史 | 每次发布 |
| 11 | `threading.Timer(0.5)` | `Kit.py:6988` | 延迟执行一次 UI 回调 | 0.5 秒 |
| 12 | `_gen_rolling_summary` | `DICK_core.py:725` | 后台压缩滚动摘要 | 每次裁剪历史 |
| 13 | `_fetch_response`（多个入口） | `DICK_core.py:1015/2315/2320/2336/2396/2415` | **主对话请求**（流式/非流式、重试） | 每轮对话 |
| 14 | `_fetch_auto_turn` | `DICK_core.py:2890` | 群聊自动接话 | 每轮自动 |
| 15 | `jobs.py` 任务线程 | `jobs.py` | 长任务跑批（带锁与状态机） | 任务期间 |
| 16 | 插件线程 | `plugins/jp_tts_plugin.py`、`financial_plugin.py` | TTS 播放 / 行情轮询 | 插件加载期间 |
| 17 | **waitress 工作线程 × N**（默认 `cpu×4`，线上 8） | `net.py:1434` | 工坊 HTTP 请求 | 服务器运行期间 |
| 18 | 工坊后台同步/进度写入 | `net.py`（`_index_lock`、`_RATE_LOCK` 保护） | 索引与限流 | 服务器运行期间 |

> 统计口径：全仓 `threading.Thread(` **37 处**、`Lock/RLock` **22 处**、`daemon=True` **38 处**、
> `subprocess.Popen/run` **57 处**（含构建/测试脚本），**没有** ThreadPoolExecutor。

### 3.2 锁的归属（谁保护什么）

| 锁 | 位置 | 保护什么 | 不保护什么 |
|---|---|---|---|
| `_proc_lock` | `DICK_core.py:532` | `is_processing` 的"检查+置位"原子化（防同一角色并发两轮） | 不保护 tree，也不保护网络请求本身 |
| `_summary_lock` | `DICK_core.py:519` | 滚动摘要的生成 | 不保护消息内容 |
| `self._lock` | `Kit.py:759`（`HtmlApp`） | 壳层共享状态（如最近一次状态快照） | 不保护 core 内部 |
| 模块级 `lock` | `Kit.py:640` | 某个一次性初始化 | — |
| `_index_lock` | `net.py:140` | `index.json` 读改写 | 不保护作品文件 |
| `_RATE_LOCK` | `net.py:277` | 限流计数 | — |
| `jobs` 的 `_lock` | `jobs.py:68/164` | 任务表 / 状态机 | 不保护任务内部数据 |

### 3.3 线程之间的数据怎么走（画这张最重要）

```
 JS 前端  ──api_*()──▶  pywebview 桥线程（#2）
                              │ 只做参数校验 + 转调
                              ▼
                   HtmlApp 门面（api_*）
                     │ ├─ service("workshop") ──▶ modules/workshop（同步，可能起 #6/#7）
                     │ ├─ service("backup")   ──▶ modules/backup
                     │ └─ self.core.xxx()     ──▶ DICK_core
                     ▼
                 DICK_core
                     ├─ _proc_lock（#13 单轮互斥）
                     ├─ 起线程 #12/#13/#14 去跑模型请求（不阻塞 UI 线程）
                     └─ 结果经回调回 JS（回调必须在桥线程/主线程执行）
```

**三条纪律**（画在图旁）：
1. **UI 线程绝不阻塞**：一切网络/打包/压缩都另起线程（#3–#14 全是这个理由）；
2. **共享可变状态必须有一把锁**，或者干脆只由单一线程写（`_proc_lock` 就是这个思路）；
3. **回调线程**：模型流式回调最终要回到 JS，别在 worker 线程里直接摸 UI。

### 3.4 已知的线程风险（诚实清单）

| 风险 | 现状 | 处置 |
|---|---|---|
| `_fetch_response` 有 6 个启动点 | 都靠 `_proc_lock` 互斥，但入口分散 | 已在计划：合并成"请求队列"（单一线程消费） |
| 插件线程不受内核管 | 插件自己 `Thread` + `daemon=True` | 建议插件走 `bus.emit_async`（内核统一执行器） |
| `net.py` 限流/索引两把锁是进程内的 | 多进程（waitress 单进程多线程，OK） | 若将来上 gunicorn 多 worker，必须换 Redis/文件锁 |
| 打包/导出线程（#8–#10）无并发上限 | 连点两次会起两个 PyInstaller | 建议加"同名任务去重" |
| `subprocess` 57 处 | 大部分在构建/测试 | 运行期只有 codex 打包与 ffmpeg 类调用，需要超时与 kill |

---

## 四、复用/筛选六问（DICK 版）

1. **在哪一层？** kernel / module / shell / tool —— 答不出就别写。
2. **依赖谁？** 模块只能依赖 kernel；依赖宿主就写 `bind(host)`。
3. **能整块搬走吗？** 只带 `kernel/` 拷走还能 `--selftest` 通过（搬家测试）= 可复用。
4. **接口签名变了吗？** 变了走修订记录 + 签名快照（`tools/block_interfaces.json`）。
5. **是不是一处真相？** 文案/图标/令牌/卡片字段/词表，只有一份。
6. **线程谁负责？** 新起线程必须写清：谁创建、跑多久、共享什么、用哪把锁。

---

## 五、一句话总结

**DICK 现在的形状**：内核薄（registry/bus/loader/manifest），模块厚（7 块，各自自带契约与自检），
壳层只装配（api_* 全是门面），线程多但**每根都有明确归属与锁**。
判据不是"代码多少行"，而是**改一处要碰几个文件、能不能单独验证、能不能整块搬走**。
