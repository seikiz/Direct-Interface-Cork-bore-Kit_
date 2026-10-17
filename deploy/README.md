# 创意工坊部署包（net.py 一键装 + 自检 + 回滚）

这个目录里四个东西，**在服务器上**跑一条命令就行：

| 文件 | 作用 |
|---|---|
| `net.py` | 工坊服务端本体（类型注册表 / 能力协商 / 分片上传 / 世界卡包） |
| `deploy_workshop.py` | 一键部署：备份 → 装文件 → 建 env（自动生成写 Key）→ systemd 服务 → 等 health → 自检 → 打印下一步 |
| `selfcheck_workshop.py` | 纯标准库自检（存活/能力/列表/搜索/上传→下载→删除闭环），可单独用 |
| `nginx-workshop.conf` | 反代样例（8080 → 127.0.0.1:5000，含大包与限流） |

## 三步

```bash
# 1) 传上去（任选一种：scp / 面板文件管理器 / git clone 后进 deploy/）
scp -r deploy/* root@<你的服务器>:/opt/dick-workshop/

# 2) 先看计划（不改任何东西）
cd /opt/dick-workshop && sudo python3 deploy_workshop.py --dry-run

# 3) 真装（幂等：重复跑就是升级）
sudo python3 deploy_workshop.py
```

装完它会自己跑一遍自检（含上传/下载/删除），最后打印**写 Key**和下一步。

## 常用

```bash
sudo python3 deploy_workshop.py --check      # 只自检（不动文件）
sudo python3 deploy_workshop.py --rollback   # 回滚上一份 net.py + 数据
sudo python3 deploy_workshop.py --port 8080  # 换端口
sudo python3 deploy_workshop.py --no-systemd # 没有 systemd 的环境（nohup 起）
python3 selfcheck_workshop.py --base http://127.0.0.1:5000 --key <写Key> --full
```

## 它装成什么样

- 目录：`/opt/dick-workshop/`（`net.py`、`workshop.env`(600)、`workshop_data/`、`backups/`、`workshop.log`）
- 服务：`/etc/systemd/system/dick-workshop.service`，`Restart=always`，只允许写自己目录
- 监听：`127.0.0.1:5000`（**别**让 5000 直接对外；用 nginx 反代到 8080）
- 鉴权：自动生成 `WORKSHOP_API_KEY`，并打开 `WORKSHOP_READ_KEY=1`（读也要 Key）。
  如果希望"读公开、只写要 Key"，把 env 里 `WORKSHOP_READ_KEY=1` 改成 `0` 再 restart
- `WORKSHOP_RELAY=0`（内置中转关闭，开着等于开放代理）

## 出问题先看这两处

```bash
tail -50 /opt/dick-workshop/workshop.log
systemctl status dick-workshop -l
```

- **health 25 秒没通**：多半是 `WORKSHOP_HOST` 填了公网 IP（云主机 NAT，bind 会失败）→ 改回 `127.0.0.1` 或 `0.0.0.0`
- **上传 413**：nginx 的 `client_max_body_size` 小于 `WORKSHOP_UPLOAD_MAX_MB`
- **上传 502 空响应**：客户端在本机代理后面。新版客户端默认直连，也可 `set NO_PROXY=<工坊地址>`
- **上传 401**：手机/客户端没填 Key（读公开、写要 Key）
