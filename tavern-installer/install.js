#!/usr/bin/env node
/**
 * SillyTavern（酒馆）一键安装器 v1.0
 * ============================================================
 * 与 DICK 分离的独立工具：帮用户一键装好酒馆（互吹落地）。
 *
 * 功能：
 *   1. 检测 Node.js / npm（酒馆新版需要 Node 18+）
 *   2. 镜像下载酒馆（GitHub 直连不通时自动走镜像）
 *   3. 解压到 tavern/ 目录
 *   4. 安装依赖（npm install）
 *   5. 启动酒馆 + 提示卡互通（DICK 与酒馆角色卡通用）
 *
 * 用法：
 *   node install.js             完整安装
 *   node install.js --skip-deps 跳过依赖安装（已装过时加速）
 *   node install.js --start     直接启动（已装好时）
 * ============================================================
 */
"use strict";

const { execSync, spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");
const zlib = require("zlib");

const ROOT = __dirname;
const TAVERN_DIR = path.join(ROOT, "tavern");
const TAVERN_ZIP = path.join(ROOT, "tavern.zip");

// 酒馆发布源：先用 GitHub API 拿最新版资产名，失败则回退已知版本 + 镜像
const GITHUB_API = "https://api.github.com/repos/SillyTavern/SillyTavern/releases/latest";
const FALLBACK_VERSIONS = [
  "1.12.12", "1.12.11", "1.12.10", "1.12.9", "1.12.8", "1.12.7",
  "1.12.6", "1.12.5", "1.12.4", "1.12.3", "1.12.2", "1.12.1", "1.12.0",
];

function releaseUrls(version) {
  const base = `https://github.com/SillyTavern/SillyTavern/releases/download/${version}/SillyTavern-${version}.zip`;
  return [
    base,
    `https://ghfast.top/${base}`,
    `https://ghproxy.net/${base}`,
    `https://gh-proxy.com/${base}`,
  ];
}

async function resolveLatestVersion() {
  return new Promise((resolve) => {
    const req = https.get(GITHUB_API, { headers: { "User-Agent": "DICK-tavern-installer" } }, (res) => {
      if (res.statusCode !== 200) { res.resume(); resolve(null); return; }
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          const tag = JSON.parse(body).tag_name || "";
          if (tag && /^\d/.test(tag)) resolve(tag);
          else resolve(null);
        } catch { resolve(null); }
      });
    });
    req.on("error", () => resolve(null));
    req.setTimeout(15000, () => req.destroy(new Error("timeout")));
  });
}

const GREEN = "\x1b[32m", YELLOW = "\x1b[33m", CYAN = "\x1b[36m", RED = "\x1b[31m", RESET = "\x1b[0m";
const ok = (m) => console.log(`${GREEN}✔${RESET} ${m}`);
const info = (m) => console.log(`${CYAN}ℹ${RESET} ${m}`);
const warn = (m) => console.log(`${YELLOW}⚠${RESET} ${m}`);
const err = (m) => console.log(`${RED}✖${RESET} ${m}`);

function sh(cmd, opts = {}) {
  return execSync(cmd, { stdio: "inherit", shell: true, ...opts });
}

function nodeVersion() {
  try {
    const v = execSync("node --version", { encoding: "utf8" }).trim();
    const major = parseInt(v.replace(/^v/, "").split(".")[0], 10);
    return { v, major };
  } catch {
    return null;
  }
}

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith("https") ? https : http;
    const req = lib.get(url, { headers: { "User-Agent": "DICK-tavern-installer" } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        info(`重定向 → ${res.headers.location}`);
        download(res.headers.location, dest).then(resolve, reject);
        return;
      }
      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }
      const f = fs.createWriteStream(dest);
      res.pipe(f);
      f.on("finish", () => f.close(resolve));
      f.on("error", reject);
    });
    req.on("error", reject);
    req.setTimeout(120000, () => req.destroy(new Error("下载超时")));
  });
}

function unzip(zipPath, destDir) {
  // 用系统 tar 解压 zip（Windows 10+ 自带，跨平台最稳）
  fs.mkdirSync(destDir, { recursive: true });
  sh(`tar -xf "${zipPath}" -C "${destDir}"`);
}

function hasDirWithPackageJson(dir) {
  try {
    return fs.readdirSync(dir).some((d) => fs.existsSync(path.join(dir, d, "package.json")));
  } catch {
    return false;
  }
}

async function main() {
  const args = process.argv.slice(2);
  const onlyStart = args.includes("--start");
  const skipDeps = args.includes("--skip-deps");

  console.log(`\n${CYAN}═══════════════════════════════════════${RESET}`);
  console.log(`${CYAN}   SillyTavern（酒馆）一键安装器 v1.0${RESET}`);
  console.log(`${CYAN}   与 DICK 分离的独立工具 · 卡互通友军${RESET}`);
  console.log(`${CYAN}═══════════════════════════════════════${RESET}\n`);

  // ---------- 1. Node 检测 ----------
  const node = nodeVersion();
  if (!node) {
    err("未检测到 Node.js。酒馆新版需要 Node 18+。");
    err("请先安装 Node.js：https://nodejs.org/ 或 `winget install OpenJS.NodeJS`");
    process.exit(1);
  }
  ok(`Node.js ${node.v}（需要 18+，${node.major >= 18 ? "满足" : "不满足！"}` + (node.major >= 18 ? "）" : "，请升级）"));
  if (node.major < 18) process.exit(1);

  // ---------- 2. 已安装 → 直接启动 ----------
  const tavernEntry = path.join(TAVERN_DIR, hasDirWithPackageJson(TAVERN_DIR) ? "" : "");
  const startCmd = findStartCmd();
  if (startCmd) {
    ok(`检测到酒馆已装于 ${TAVERN_DIR}`);
    if (onlyStart || skipDeps) {
      info("启动酒馆…（默认端口 8000，浏览器打开 http://localhost:8000）");
      console.log(`\n${YELLOW}启动方式（任选其一）：${RESET}`);
      console.log(`  1. 运行 start.bat（已生成）`);
      console.log(`  2. 进入 tavern 目录执行: npm start`);
      console.log(`  3. 双击 tavern\\Start.bat\n`);
      startTavern();
      return;
    }
  }

  // ---------- 3. 下载酒馆 ----------
  if (!fs.existsSync(TAVERN_ZIP)) {
    info("开始下载酒馆（约 100MB，GitHub 不通自动切镜像）…");
    // 先试 GitHub API 拿最新版本号
    const latest = await resolveLatestVersion();
    let versions = latest ? [latest, ...FALLBACK_VERSIONS.filter(v => v !== latest)] : FALLBACK_VERSIONS;
    let okDl = false;
    for (const ver of versions) {
      for (const u of releaseUrls(ver)) {
        try {
          info(`下载源: ${u.slice(0, 80)}…`);
          await download(u, TAVERN_ZIP);
          okDl = true;
          ok(`下载完成（版本 ${ver}）`);
          break;
        } catch (e) {
          // 静默试下一个源
        }
      }
      if (okDl) break;
    }
    if (!okDl) {
      err("所有下载源都失败。请检查网络，或手动下载酒馆 zip 放到本目录 tavern.zip");
      process.exit(1);
    }
  } else {
    ok("已存在 tavern.zip，跳过下载");
  }

  // ---------- 4. 解压 ----------
  info("解压到 tavern/ …");
  try {
    unzip(TAVERN_ZIP, TAVERN_DIR);
    ok("解压完成");
  } catch (e) {
    err("解压失败: " + e.message);
    process.exit(1);
  }

  // ---------- 5. 装依赖 ----------
  if (!skipDeps) {
    const pkgDir = findPkgDir();
    if (!pkgDir) {
      warn("未找到 package.json（解压结构异常），跳过依赖安装");
    } else {
      info(`在 ${path.relative(ROOT, pkgDir) || "tavern"} 安装依赖（npm install，约 1-3 分钟）…`);
      try {
        sh(`cd "${pkgDir}" && npm install --no-audit --no-fund`, { cwd: pkgDir });
        ok("依赖安装完成");
      } catch (e) {
        warn("依赖安装可能不完整（网络问题），可重试 `node install.js --skip-deps` 后进 tavern 目录 npm install");
      }
    }
  }

  // ---------- 6. 生成启动入口 + 提示 ----------
  makeStartBat();
  ok("安装完成！");
  console.log(`\n${GREEN}════════ 酒馆已就绪 ════════${RESET}`);
  console.log(`  启动：双击 ${YELLOW}start.bat${RESET}，浏览器打开 ${YELLOW}http://localhost:8000${RESET}`);
  console.log(`  数据：${YELLOW}tavern/data${RESET}（角色卡/世界书都在这里）\n`);
  console.log(`${CYAN}🤝 与 DICK 卡互通：${RESET}`);
  console.log(`  - 酒馆的角色卡（PNG 嵌卡 / v1/v2/v3 JSON）DICK 直接导入`);
  console.log(`  - DICK 导出的卡是干净的酒馆 v2 格式，酒馆直接可用`);
  console.log(`  - 同一张卡，两个前端都能玩——我们是一个阵营。\n`);
  startTavern();
}

function findPkgDir() {
  // tavern/SillyTavern-*/package.json 或 tavern/package.json
  try {
    const entries = fs.readdirSync(TAVERN_DIR);
    for (const d of entries) {
      const p = path.join(TAVERN_DIR, d, "package.json");
      if (fs.existsSync(p)) return path.join(TAVERN_DIR, d);
    }
    if (fs.existsSync(path.join(TAVERN_DIR, "package.json"))) return TAVERN_DIR;
  } catch {}
  return null;
}

function findStartCmd() {
  const pkgDir = findPkgDir();
  return pkgDir;
}

function startTavern() {
  const pkgDir = findPkgDir();
  if (!pkgDir) {
    warn("未找到酒馆入口，请手动进 tavern 目录 npm start");
    return;
  }
  info(`启动酒馆（${path.relative(ROOT, pkgDir)}）…`);
  try {
    const child = spawn("cmd", ["/c", "npm start"], { cwd: pkgDir, detached: true, stdio: "ignore" });
    child.unref();
    console.log(`\n${GREEN}酒馆已在后台启动：http://localhost:8000${RESET}`);
    console.log(`${YELLOW}第一次启动请设置 API Key（设置 → API 连接）。\n${RESET}`);
  } catch (e) {
    warn("自动启动失败，请手动进 tavern 目录 npm start");
  }
}

function makeStartBat() {
  const pkgDir = findPkgDir();
  const startDir = pkgDir ? path.relative(ROOT, pkgDir).replace(/\//g, "\\") : "tavern";
  const bat = `@echo off
cd /d "%~dp0${startDir}"
echo Starting SillyTavern...
echo Open http://localhost:8000 in your browser
npm start
pause
`;
  fs.writeFileSync(path.join(ROOT, "start.bat"), bat, { encoding: "utf8" });
  ok("已生成 start.bat 启动入口");
}

main().catch((e) => {
  err("安装失败: " + e.message);
  process.exit(1);
});
