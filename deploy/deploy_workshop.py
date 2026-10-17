#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""创意工坊服务器一键部署 / 升级 / 回滚（在**服务器上**跑，只用标准库）。

为什么不用 shell 脚本：这个脚本要能在 Windows 上做 --dry-run 验证，也要在
树莓派/NAS/云主机上跑；Python 是 net.py 本来就依赖的东西，比 bash 更好保证
"写出来的和你本地验证过的是同一个东西"。

用法（把本目录整个 scp 上去，然后）：
  sudo python3 deploy_workshop.py --dry-run          # 只看计划，不动任何东西
  sudo python3 deploy_workshop.py                    # 装/升级 + 自检
  sudo python3 deploy_workshop.py --check            # 只自检（不改文件）
  sudo python3 deploy_workshop.py --rollback         # 回到上一份 net.py + 数据

它会做：备份 → 装 net.py → 建 venv(需要时装 flask) → 写 systemd 服务并启动
      → 等 health 就绪 → 跑 selfcheck（含上传/下载/删除闭环）→ 打印下一步。
幂等：重复跑就是升级，不会重复建服务；数据目录只备份不动。
"""
import argparse
import base64
import glob
import json
import os
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE_TPL = """[Unit]
Description=DICK 创意工坊服务器 (net.py)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=__USER__
WorkingDirectory=__APP_DIR__
EnvironmentFile=__ENV_FILE__
Environment=PYTHONIOENCODING=utf-8
Environment=PYTHONUNBUFFERED=1
ExecStart=__PYTHON__ net.py
Restart=always
RestartSec=3
# 只允许写自己的数据目录，别的都只读（net.py <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌只需要 workshop_data 与自身目录）
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=__APP_DIR__
StandardOutput=append:__APP_DIR__/workshop.log
StandardError=append:__APP_DIR__/workshop.log

[Install]
WantedBy=multi-user.target
"""


def say(msg):
    print(msg)


def step(msg):
    print("\n== %s ==" % msg)


def run(cmd, check=False, quiet=True, timeout=600):
    """跑命令；quiet 时把输出都收起来，失败时再打出来。"""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0 and not quiet:
        print((p.stdout or "") + (p.stderr or ""))
    if check and p.returncode != 0:
        raise SystemExit("命令失败：%s\n%s" % (" ".join(cmd), (p.stderr or p.stdout or "")[:400]))
    return p


def have(cmd):
    return shutil.which(cmd) is not None


def port_free(port, host="127.0.0.1"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((host, port)) != 0
    finally:
        s.close()


def http(url, timeout=10, headers=None):
    r = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 0, str(e).encode("utf-8", "replace")


def wait_health(port, host="127.0.0.1", seconds=25):
    url = "http://%s:%d/api/health" % (host, port)
    for _ in range(int(seconds * 2)):
        code, raw = http(url, timeout=2)
        if code == 200:
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}
        time.sleep(0.5)
    return None


def pack_env(path, values):
    """写 env 文件（600）；已存在的键不覆盖（升级时保住原 Key）。"""
    cur = {}
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cur[k.strip()] = v.strip()
    merged = dict(values)
    merged.update({k: v for k, v in cur.items() if v})
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 由 deploy_workshop.py 生成；改完记得 systemctl restart\n")
        for k, v in merged.items():
            f.write("%s=%s\n" % (k, v))
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return merged


def backup(app_dir, tag):
    bdir = os.path.join(app_dir, "backups")
    os.makedirs(bdir, exist_ok=True)
    made = []
    net = os.path.join(app_dir, "net.py")
    if os.path.isfile(net):
        dst = os.path.join(bdir, "net-%s.py" % tag)
        shutil.copy2(net, dst)
        made.append(dst)
    data = os.path.join(app_dir, "workshop_data")
    if os.path.isdir(data):
        dst = os.path.join(bdir, "workshop_data-%s.tar.gz" % tag)
        with tarfile.open(dst, "w:gz") as t:
            t.add(data, arcname="workshop_data")
        made.append(dst)
    # 只留最近 5 组
    for pattern in ("net-*.py", "workshop_data-*.tar.gz"):
        files = sorted(glob.glob(os.path.join(bdir, pattern)), key=os.path.getmtime)
        for old in files[:-5]:
            try:
                os.remove(old)
            except Exception:
                pass
    return made


def pick_python(app_dir, dry):
    """有 venv 用 venv；没有就先试系统 python3 有没有 flask；都不行才建 venv 装 flask。"""
    venv_py = os.path.join(app_dir, ".venv", "bin", "python")
    if os.path.isfile(venv_py):
        return venv_py, "已有 venv"
    sys_py = shutil.which("python3") or shutil.which("python")
    if sys_py and run([sys_py, "-c", "import flask"]).returncode == 0:
        return sys_py, "系统 python3 已装 flask"
    if dry:
        return sys_py or "python3", "将创建 venv 并 pip install flask"
    say("   系统 python 没有 flask，创建 venv 并安装（需要能上网）...")
    os.makedirs(app_dir, exist_ok=True)
    run([sys_py or "python3", "-m", "venv", os.path.join(app_dir, ".venv")], check=True)
    pip = os.path.join(app_dir, ".venv", "bin", "pip")
    run([pip, "install", "--upgrade", "pip"], quiet=True)
    r = run([pip, "install", "flask"], quiet=True, timeout=900)
    if r.returncode != 0:
        raise SystemExit("pip install flask 失败（服务器没网？）。可以先手动装："
                         "apt install python3-flask  或  pip3 install flask，再重跑本脚本")
    return venv_py, "新 venv"


def install_file(src, dst, dry):
    if dry:
        say("   [dry-run] 复制 %s → %s" % (os.path.basename(src), dst))
        return
    shutil.copy2(src, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.environ.get("WORKSHOP_APP_DIR", "/opt/dick-workshop"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("WORKSHOP_PORT", "8080")),
                    help="默认 8080（与线上现状一致：Flask 直接对外）")
    ap.add_argument("--host", default=os.environ.get("WORKSHOP_HOST", "0.0.0.0"),
                    help="默认 0.0.0.0；放到 nginx 后面就传 127.0.0.1")
    ap.add_argument("--key", default="", help="写 Key；不给就沿用 env 里的，没有则随机生成")
    ap.add_argument("--service", default="dick-workshop")
    ap.add_argument("--no-systemd", action="store_true", help="没有 systemd 时用 nohup 起")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="只自检，不改文件")
    ap.add_argument("--rollback", action="store_true")
    a = ap.parse_args()

    app = os.path.abspath(a.dir)
    env_file = os.path.join(app, "workshop.env")
    systemd_dir = "/etc/systemd/system"
    has_systemd = os.path.isdir("/run/systemd/system") and have("systemctl")

    print("=" * 66)
    print("创意工坊部署器   app=%s  port=%d  host=%s" % (app, a.port, a.host))
    print("平台=%s   systemd=%s   dry-run=%s" % (platform.platform(), "有" if has_systemd else "无", a.dry_run))
    print("=" * 66)

    if a.check:
        py, _ = pick_python(app, True)
        r = run([py, os.path.join(HERE, "selfcheck_workshop.py"),
                 "--base", "http://127.0.0.1:%d" % a.port, "--full"], quiet=False)
        return r.returncode

    if a.rollback:
        bdir = os.path.join(app, "backups")
        nets = sorted(glob.glob(os.path.join(bdir, "net-*.py")), key=os.path.getmtime)
        datas = sorted(glob.glob(os.path.join(bdir, "workshop_data-*.tar.gz")), key=os.path.getmtime)
        if not nets:
            print("没有可回滚的备份（%s）" % bdir)
            return 1
        if not a.dry_run:
            shutil.copy2(nets[-1], os.path.join(app, "net.py"))
            if datas:
                with tarfile.open(datas[-1]) as t:
                    t.extractall(app)
            print("已回滚到：%s%s" % (os.path.basename(nets[-1]),
                                    (" ＋ " + os.path.basename(datas[-1])) if datas else ""))
            if has_systemd:
                run(["systemctl", "restart", a.service], quiet=False)
        else:
            print("[dry-run] 会回滚到 %s" % os.path.basename(nets[-1]))
        return 0

    tag = time.strftime("%Y%m%d-%H%M%S")

    step("① 预检")
    net_src = ""
    for cand in (os.path.join(HERE, "net.py"), os.path.join(os.path.dirname(HERE), "net.py")):
        if os.path.isfile(cand):
            net_src = cand
            break
    if not net_src:
        print("✗ 找不到 net.py —— 把它和本脚本放同一个目录（或放它的上一级）再跑")
        return 1
    say("   net.py 就绪：%s（%d KB）" % (net_src, os.path.getsize(net_src) // 1024))
    if not port_free(a.port):
        # 线上那台极可能就是这么跑的：一个裸 python net.py 占着 8080。
        # 直接换文件再启会 bind 失败，所以先把旧工坊进程停掉（只认 net.py，别的一概不动）。
        if a.dry_run:
            say("   [dry-run] 端口 %d 被占：会先停掉旧的 net.py 进程再起" % a.port)
        else:
            pids = run(["pgrep", "-af", "net.py"]).stdout or ""
            olds = [ln for ln in pids.splitlines() if "net.py" in ln and "deploy_workshop" not in ln]
            for ln in olds:
                print("   旧进程：%s" % ln.strip()[:110])
            if olds:
                run(["pkill", "-f", "net.py"], check=False)
                time.sleep(1.5)
                say("   已停掉旧的 net.py 进程")
            if not port_free(a.port):
                print("✗ 端口 %d 还被占着（不是 net.py？）。先手动停掉它："
                      "ss -ltnp 'sport = :%d' 看 PID，或换端口 --port 5000" % (a.port, a.port))
                return 1
    py, why = pick_python(app, a.dry_run)
    say("   Python：%s（%s）" % (py, why))

    step("② 备份（只备份，不动数据）")
    if a.dry_run:
        say("   [dry-run] 会备份 net.py 与 workshop_data → %s/backups/" % app)
    else:
        os.makedirs(app, exist_ok=True)
        for f in backup(app, tag):
            say("   备份 %s（%.1f KB）" % (f, os.path.getsize(f) / 1024.0))

    step("③ 装文件")
    install_file(net_src, os.path.join(app, "net.py"), a.dry_run)
    install_file(os.path.join(HERE, "selfcheck_workshop.py"),
                 os.path.join(app, "selfcheck_workshop.py"), a.dry_run)
    if not a.dry_run:
        os.makedirs(os.path.join(app, "workshop_data"), exist_ok=True)

    step("④ 环境变量")
    want = {
        "WORKSHOP_HOST": a.host,
        "WORKSHOP_PORT": str(a.port),
        "WORKSHOP_API_KEY": a.key or secrets.token_urlsafe(24),
        # 用户可以「直接上传」，不用先找 Key：写操作里只有删除/插件/共享配置要 Key
        "WORKSHOP_OPEN_UPLOAD": "1",
        "WORKSHOP_RATE_PER_HOUR": "60",
        "WORKSHOP_READ_KEY": "0",   # 客户端要能直接浏览下载；想锁死读再改 1
        "WORKSHOP_RELAY": "0",
        "WORKSHOP_UPLOAD_MAX_MB": "64",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "no_proxy": "127.0.0.1,localhost,::1",
    }
    if a.dry_run:
        say("   [dry-run] 会写 %s（已存在则保留原 Key，只补缺）" % env_file)
        vals = want
    else:
        vals = pack_env(env_file, want)
        say("   env：%s（600）" % env_file)
    say("   写鉴权 Key：%s" % vals.get("WORKSHOP_API_KEY"))
    say("   上传/点赞/进度**不需要**这个 Key（OPEN_UPLOAD=1）；只有「删除作品、传插件、"
        "共享模型配置」要它 —— 也就是作者/管理员自己用，普通用户零配置")

    step("⑤ 服务")
    if has_systemd and not a.no_systemd:
        unit = SERVICE_TPL.replace("__USER__", "root" if os.geteuid() == 0 else os.environ.get("USER", "root")) \
            .replace("__APP_DIR__", app).replace("__ENV_FILE__", env_file) \
            .replace("__PYTHON__", py)
        unit_path = os.path.join(systemd_dir, a.service + ".service")
        if a.dry_run:
            say("   [dry-run] 会写 %s 并 systemctl enable --now %s" % (unit_path, a.service))
        else:
            with open(unit_path, "w", encoding="utf-8") as f:
                f.write(unit)
            run(["systemctl", "daemon-reload"], quiet=False)
            run(["systemctl", "enable", a.service], quiet=False)
            run(["systemctl", "restart", a.service], quiet=False)
            say("   systemd 已启动：%s（日志 %s/workshop.log）" % (a.service, app))
    else:
        say("   没有 systemd：用 nohup 起（或你自己用 supervisor/pm2）")
        if not a.dry_run:
            # 只杀"本目录下的 net.py"，别用宽泛的 pkill -f net.py（可能误杀别的服务）
            run(["pkill", "-f", os.path.join(app, "net.py")], check=False)
            log = open(os.path.join(app, "workshop.log"), "ab")
            env = dict(os.environ, **{k: v for k, v in vals.items()})
            subprocess.Popen(["nohup", py, "net.py"], cwd=app, env=env,
                             stdout=log, stderr=log, start_new_session=True)
            say("   已后台启动（pid 见 pgrep -f net.py）")

    step("⑥ 等它起来")
    if a.dry_run:
        say("   [dry-run] 跳过")
        return 0
    h = wait_health(a.port)
    if not h:
        print("✗ 25 秒内 health 没通。看日志：tail -50 %s/workshop.log" % app)
        print("  常见：端口被占 / flask 没装 / env 文件里 WORKSHOP_HOST 填了公网 IP（会 bind 失败）")
        return 1
    say("   health OK：%s" % json.dumps({k: h.get(k) for k in ("status", "auth", "api", "schema")},
                                       ensure_ascii=False))
    types = h.get("types") or []
    say("   支持的类型：%s" % (", ".join(types) if types else "（旧版没有 types）"))

    step("⑦ 自检（含上传→下载→删除闭环）")
    r = subprocess.run([py, os.path.join(app, "selfcheck_workshop.py"),
                        "--base", "http://127.0.0.1:%d" % a.port,
                        "--key", vals.get("WORKSHOP_API_KEY", ""), "--full"])
    if r.returncode != 0:
        print("\n⚠ 自检没过 —— 先把上面 [FAIL] 的几条解决再用（数据已备份，可 --rollback）")
        return r.returncode

    step("⑧ 下一步")
    say("   1) 公网访问：让反代只转发这一个端口（样例 nginx-workshop.conf，改 server_name 后 nginx -t && reload）")
    say("      反代到 127.0.0.1:%d，client_max_body_size ≥ 64m，proxy_request_buffering off" % a.port)
    say("   2) 客户端「线上」页填 Key 才能上传/删除：")
    say("      %s" % vals.get("WORKSHOP_API_KEY"))
    say("   3) 备份：crontab -e 加一行")
    say("      20 4 * * * cd %s && tar czf backups/workshop_data-$(date +\\%%Y%%m%%d).tar.gz workshop_data" % app)
    say("   4) 出问题回滚：sudo python3 deploy_workshop.py --rollback")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
