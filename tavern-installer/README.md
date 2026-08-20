# SillyTavern（酒馆）一键安装器

> 与 DICK 分离的独立工具 —— 帮你想玩酒馆时一键装好它（互吹落地：不是嘴上推荐，是直接帮你装）。

## 这是什么

DICK 和酒馆（SillyTavern）是同一个沙盒的两种玩法：DICK 轻量成作，酒馆硬核插件生态。**角色卡互通**（酒馆的卡 DICK 直接导入，DICK 导出的卡酒馆直接可用）。

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
- **卡互通**：酒馆的角色卡（PNG/v1/v2/v3）拷给 DICK 直接导入；DICK 导出的卡酒馆直接用

## 常见问题

**下载失败？** 脚本内置 GitHub + 镜像多源，全失败时手动下载酒馆 zip 放到本目录 `tavern.zip` 再运行。

**依赖装不上？** 网络问题时 `node install.js --skip-deps`，然后进 tavern 目录手动 `npm install`。

**端口被占？** 酒馆默认 8000，改 `tavern/config.yaml` 的 port。
