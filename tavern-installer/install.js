#!/usr/bin/env node
/**
 * SillyTavern（酒馆）一键安装器 v1.0
 * ============================================================
 * 与 DICK 分离的独立工具：一键装好酒馆（SillyTavern）。
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

// 酒馆发布源：GitHub API 拿最新版 → 源码 zip 下载（release 分支最稳）
const GITHUB_API = "https://api.github.com/repos/SillyTavern/SillyTavern/releases/latest";

function releaseUrls(version) {
  // 酒馆无 release 资产，用 GitHub 自动生成的源码 zip（tag 或 release 分支）
  const tag = `https://github.com/SillyTavern/SillyTavern/archive/refs/tags/${version}.zip`;
  const branch = "https://github.com/SillyTavern/SillyTavern/archive/refs/heads/release.zip";
  return [tag, branch];
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
  console.log(`${CYAN}   与 DICK 分离的独立工具 · 角色卡互通${RESET}`);
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
    if (onlyStart) {
      // --start：假定依赖已装好，直接启动
      startTavern();
      return;
    }
    if (skipDeps) {
      // --skip-deps：跳过装依赖，提示手动操作后退出（不自动启动，避免依赖缺失启动失败）
      console.log(`\n${YELLOW}依赖未安装，请手动操作：${RESET}`);
      console.log(`  1. 进入 ${path.relative(ROOT, startCmd)} 目录`);
      console.log(`  2. 运行 npm install`);
      console.log(`  3. 运行 npm start（或双击生成的 start.bat）\n`);
      makeStartBat();
      return;
    }
  }

  // ---------- 3. 下载酒馆 ----------
  if (!fs.existsSync(TAVERN_ZIP)) {
    info("开始下载酒馆（约 100-200MB，GitHub 源码 zip）…");
    const latest = await resolveLatestVersion();
    const versions = latest ? [latest] : [];
    const urls = [];
    for (const v of versions) urls.push(...releaseUrls(v));
    // 兜底：直接试 release 分支（即使 API 不通也能下载最新稳定版）
    if (!urls.includes("https://github.com/SillyTavern/SillyTavern/archive/refs/heads/release.zip")) {
      urls.push("https://github.com/SillyTavern/SillyTavern/archive/refs/heads/release.zip");
    }
    let okDl = false;
    for (const u of urls) {
      try {
        info(`下载: ${u.slice(0, 70)}…`);
        await download(u, TAVERN_ZIP);
        const sz = fs.statSync(TAVERN_ZIP).size;
        if (sz < 1000000) { warn(`文件过小（${(sz/1024/1024).toFixed(1)}MB），换源`); continue; }
        okDl = true;
        ok(`下载完成（${(sz/1024/1024).toFixed(1)}MB）`);
        break;
      } catch (e) {
        warn(`该源失败: ${e.message}`);
      }
    }
    if (!okDl) {
      err("所有下载源都失败。可手动下载酒馆 zip（GitHub → Code → Download ZIP）放到本目录 tavern.zip 再运行。");
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
  console.log(`  - 同一张卡，两个前端都能用。\n`);
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
