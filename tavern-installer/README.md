# SillyTavern（酒馆）一键安装器

> 与 DICK 分离的独立工具 —— 一键装好酒馆（SillyTavern），不用自己折腾环境。

## 这是什么

DICK 和酒馆（SillyTavern）是同一个沙盒的两种玩法：DICK 轻量成作，酒馆硬核插件生态。**角色卡互通**（DICK 做了双向转换层：酒馆的卡 DICK 直接导入，DICK 导出的卡酒馆直接可用）。

这个安装器帮你一键装好酒馆，不用自己折腾环境。

## 用法

1. **双击 `install.bat`**（或 `node install.js`）
2. 脚本自动：检测 Node → 下载酒馆 → 解压 → 装依赖 → 启动
3. 浏览器打开 `http://localhost:8000` 开始用

## 其他命令

```
node install.js             完整安装
node install.js --skip-deps 跳过依赖安装（已装过时加速）
node install.js --start     直接启动（已装好时）
```

## 环境要求

- **Node.js 18+**（酒馆新版需要；没有会提示安装）
- Windows 10+（自带 tar 解压 zip）

## 安装后

- 数据在 `tavern/data/`（角色卡/世界书/聊天记录都在这里）
- 启动入口：`start.bat` 或进 `tavern` 目录 `npm start`

## 酒馆快速上手（新手必看）

1. 打开 `http://localhost:8000`
2. **配模型**：左下角设置(⚙) → API Connections → 选模型商 → 填 Key（和 DICK 同一个 Key 就行）
3. **导卡**：左侧头像图标（👤 / Edit Characters）→ Import Character → 选 PNG 或 JSON 卡文件
4. **开始聊**：点角色卡片 → 底部输入框说话

**卡互通**：酒馆的角色卡（PNG/v1/v2/v3）拷给 DICK 直接导入；DICK 导出的卡酒馆直接可用——同一张卡两个前端都能用。

> ⚠️ **互通边界**：转换保留角色人设（描述/性格/台词/开场白）与酒馆世界书；DICK 独有的树状记忆、机制卡（好感/状态/战斗）为 DICK 扩展，转酒馆时会剥离（酒馆格式装不下），转回 DICK 后需重新配置。

## 常见问题

**下载失败？** 脚本内置 GitHub + 多源重试，全失败时手动下载酒馆 zip（GitHub → Code → Download ZIP）放到本目录 `tavern.zip` 再运行。

**依赖装不上？** 网络问题时 `node install.js --skip-deps`，然后进 tavern 目录手动 `npm install`。

**端口被占？** 酒馆默认 8000，改 `tavern/config.yaml` 的 port。
