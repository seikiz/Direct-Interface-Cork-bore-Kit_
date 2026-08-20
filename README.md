# Direct-Interface Cork-bore Kit（DICK）

> 本地 AI 角色扮演聊天平台 · 树状记忆 · 机制养成 · 战斗系统 · CODEX 成作引擎
> 电脑（Python/pywebview） + 手机（Kotlin/Compose）双端原生 · 免费 · 数据归你

---

## 这是什么

**DICK**（全称 Direct-Interface Cork-bore Kit）是一个本地运行的 AI 角色扮演聊天平台，和 SillyTavern（酒馆）是同一个沙盒的两种玩法：

- **DICK**：轻量、开箱即用、傻瓜友好，一键把角色卡打包成独立 GALGAME
- **酒馆（SillyTavern）**：硬核、插件生态深不见底、折腾友好

两者角色卡互通——酒馆的卡 DICK 直接导入，DICK 导出的卡酒馆直接用（仓库里自带酒馆安装器 `tavern-installer/`，想用酒馆一键装好）。

## 核心特性

### 聊天
- 树状记忆：主线平铺、分支收纳，随时回溯任意节点
- 多候选回复（滑条）、重生成、编辑消息
- 群聊自动接话（每个角色物理隔离，绝不串戏）
- 世界卡 / 世界书 / 平行世界穿越

### 玩法
- 机制卡：好感度（百分比制）/ 状态 / 事件触发
- 战斗系统：公式白名单、招式、buff、玩家同规格
- GAL 选项：AI 生成选项分支 + 隐藏 ROLL（坍缩/天选/暴击/稀有）
- UTAU 语音：`[ja]` 日文配音（电脑完整版 / 手机系统 TTS）

### 成作（CODEX，仅电脑）
- 傻瓜化导入素材（立绘/背景/音乐/配音）→ 剧本 JSON → 全屏播放器
- 一键打包：独立 EXE / HTML / .codex（可分发、可卖）
- AI 起草剧本、一键配音、系统权限（文件关联/调用程序/全屏）

### 其他
- 正则管道、去 AI 味、预设、插件系统（Python 后端，`.py` 即用）
- 财报助手、联网搜索、股票分析、日文翻译、骰子
- 双端数据互通（同一角色卡两边都能用）

## 快速开始

### 电脑
1. 下载 release 的 `DICK-Setup.exe`（安装包）或 `DICK.zip`（便携版）
2. 双击运行 → 设置里填 API Key（DeepSeek/其他模型商）
3. 左侧选角色 → 开始聊天

### 手机
- 安装 `app-debug.apk` → 设置 API Key → 开聊

## 想玩酒馆？

仓库里 `tavern-installer/` 是一键安装器：
```
cd tavern-installer
node install.js     # 或双击 install.bat
```
装完酒馆，你的卡两边都能用。

## 开发

```bash
# 电脑
python html_app.py          # 源码运行
python -m PyInstaller DICK_HTML.spec --noconfirm   # 打包 EXE
python build_installer.py   # 生成安装包

# 测试
python tests/test_*.py      # 逐个运行（240+ 项）

# 手机（Android）
cd DICK-Android
gradle :app:assembleDebug
```

## 文档

- `说明书.md` — 完整使用说明
- `PLUGIN_DEV.md` — 插件编写标准
- `状态变量说明.md` — 机制/战斗/好感度变量速查

## 许可

MIT —— 自由使用、修改、分发。数据与作品归你自己。
