# kernel/ —— 微内核（装模块 / 给服务 / 发事件）

**判断标准只有一份：[`ARCHITECTURE.md`](../ARCHITECTURE.md)。** 本文件只讲"怎么用、怎么加、怎么被拦"，
不重复也不改写任何铁律；冲突时以 ARCHITECTURE.md 为准（改它要按第八节的流程走）。

## 五个组成部分（各自一句话）

| 文件 | 职责 |
|---|---|
| `registry.py` | 服务注册/查找，模块之间**只能**经它通信（重名拒绝、可按 owner 一次性摘干净） |
| `bus.py` | 事件总线：同步 `emit` + 可注入执行器的异步投递，坏订阅者不传染 |
| `loader.py` | 按 manifest 发现并加载模块；单个模块失败只记日志，内核照常启动 |
| `manifest.py` | 清单数据类与校验（id/version/provides/requires/lazy 五条硬规则） |
| `config.py` `paths.py` `log.py` `version.py` | 从现有实现抽的最小件（路径/配置/日志/四段号），**不另起炉灶** |

## 模块契约

`modules/<id>/manifest.json`（四张表可缺省，但写了就要对得上）：

```json
{"id": "backup", "version": "1.0.0.0",
 "provides": {"services": ["backup"], "routes": ["api_export_backup_encrypted"],
              "ui_screens": ["bk"], "commands": []},
 "requires": {"services": [], "modules": []}, "lazy": true}
```

`modules/<id>/module.py` —— **唯一入口**：

```python
def register(kernel):                      # 由加载器调用一次
    kernel.registry.register("backup", BackupService(log=kernel.log), owner="backup")
```

- `lazy: true` = 启动不装，第一次 `kernel.service("backup")` 才装（省启动时间，失败也只影响这一块）。
- `provides.services` 与 `register` 期间真实注册的服务**必须完全一致**：少注册=吹牛、多注册=偷给，
  两种情况加载器都会回滚并判该模块失败（`loader.py::_reconcile`）。
- 模块之间协作只有两条路：`registry` 拿服务、`bus` 发事件。**没有第三条。**
- 模块对象是**进程级单例**（同一目录被多个内核加载只 import 一次）：状态一律挂在服务实例上，不许用模块级可变全局。

## 四条铁律的执法者（不靠自觉）

| 铁律（详见 ARCHITECTURE.md 三） | 谁在拦 |
|---|---|
| 单向依赖 `kernel ← modules ← shells` | `tools/audit_kernel_boundaries.py`（`kernel-*` / `module-*`） |
| 一个模块只有一个入口 | 同上（`module-entry`）+ 加载器的合成包名让内部文件**没有稳定名字可 import** |
| 可降级（模块炸了内核照起） | `tests/test_kernel.py` 第②节 + 加载器本身 |
| manifest 必须说真话 | `loader._reconcile` + `tests/test_kernel.py` 第③节 |
| 反修正主义（白名单只许缩短、行数上限只许下调、不许 `# noqa`/条件 import） | 同上工具（`whitelist-*` / `limit` / `bypass-*`）+ 基线 `tools/kernel_boundaries_baseline.json` |

跑一次：`python tools/audit_kernel_boundaries.py`（`--baseline` 比对，恶化即非 0）。

## 新增一个模块（5 步）

1. **想清楚它属于哪一层**：只影响一个屏的展示 → 放壳层，别建模块（ARCHITECTURE.md 第四节）。
2. `mkdir modules/<id>`，写 `manifest.json`（id=目录名、version 四段、provides.services 只写真会注册的）与 `block.json`（文件白名单/接口签名/自检命令）。
3. 写 `module.py` 的 `register(kernel)`，在**它里面**注册服务；内部实现拆成同目录其它文件（相对 import）。
4. 要别人的能力就 `kernel.service("对方")`；要联动就 `kernel.bus.emit("自己的名字.事件", …)`；**不许** `import modules.<对方>`。
5. 壳层接线 `self._kernel_service("<id>")`（记得 `bind(host)`），给块补 `--selftest`，再跑 `python tools/accept.py` 只看最后一行。

## 为什么不能跨模块 import（具体反例）

```python
# modules/workshop/client.py —— 错误示范
from modules.backup.service import BackupService     # × 编译期焊死
```
坏在哪：① `backup` 改名/拆文件 → `workshop` 直接 `ImportError`，连"没装 backup"都表达不出来；② 两个模块从此只能一起发布、一起测；③ 循环 import 迟早出现。正确写法：

```python
svc = kernel.service("backup")        # 拿不到就抛 ServiceNotFound → 走降级分支
kernel.bus.on("backup.done", on_done) # 只关心"发生了"，不关心谁实现
```

## 已知欠债（不是例外，是排期）

| 位置 | 为什么绕不开 | 清理方式 | 到期 |
|---|---|---|---|
| `modules/workshop/client.py` 仍通过宿主端口调 `_ws_call` 这族传输函数 | 本批只迁 17 个接口的编排；传输层还和壳层的树存档/API 同步共用 | 第二批把 `_ws_*` 搬进模块，端口缩到 `{dirs, config, log}` | 下一批 |
| `DICK_core.py` 与 UI 仍有隐式双向引用（`self.core.*` 散布在壳层） | 那是对话主干，改动面最大；先立契约再搬 | 以 `chat` 模块承接 `ChatCore`，壳层只经 `kernel.service("chat")` | 第三批 |

白名单目前只有 1 条（`crypto_core`，理由写在工具的 `SHARED_LEAF_LIBS` 里），基线 `tools/kernel_boundaries_baseline.json` 钉死了条数：**只会变少，不会变多**。
