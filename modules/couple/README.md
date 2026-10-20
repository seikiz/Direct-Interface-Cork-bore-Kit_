# 耦合卡块（couple）

**一句话**：把「主卡 + 世界 + 机制 + 设定表」当成一个**不可拆的整体**，并做**分次设定**。

## 为什么
客户原话：「提示词少了不够有深度，提示词多了没有活人感」。
解法不是调一个参数，而是三件事一起：
- **耦合包**保证"该在的一定在"（缺一件就报错，不是警告）；
- **分次设定**保证每轮只吃够用的量（核心常驻 + 次要轮换）；
- **模式互斥**保证不会和单推/群聊混着用。

## 接口
```
service "couple"
  .validate(pack)                     校验耦合包
  .can_enable(mode, active)           能不能开这个模式（互斥判定）
  .build(pack, turn, recent_text, used_recently, budget_chars)
                                      返回 {text, picked, skipped, chars, budget, core}
```

## 规则（写死在 selector，不在调用点）
1. `tier=core` **永远常驻**，不会被预算裁掉；
2. `tier=secondary` 按「话题相关 × 权重」排序，刚用过的**硬性排到后面**；
3. 预算默认 `rules.budget_chars`（缺省 1200），可覆盖；
4. 同输入 → 同输出（确定性，便于复盘）。

## 互斥
`single / group / coupled` 同一互斥组：开耦合必须先把单推、群聊关掉。
`can_enable()` 是唯一真相，UI 不许自己判断。

## 自检
```
python -m modules.couple --selftest
→ {"block": "couple", "pass": 4, "fail": 0, "ms": 1, "deps": []}
```
