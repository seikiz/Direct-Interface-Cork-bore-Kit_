# -*- coding: utf-8 -*-
"""modules/workshop/transfer.py —— 工坊的**传输与本地文件**半边（块内实现，外部不许 import）

为什么和 client.py 拆开：ARCHITECTURE.md 九.1「单文件目标 ≤400 行」。
这两半的心智负担本来就不一样：
    client.py    连接配置、能力清单、列表/搜索/连通性 —— 都是"读"
    transfer.py  上传/下载/点赞/删除/预览/导出/插件/打开目录 —— 都是"动磁盘或动服务器状态"

`WorkshopClient` 继承这里的 `TransferMixin`，所以**对外仍然是同一个服务对象、同一组方法**
（公开接口没变，属于块内重构，不走接口修订流程）。
宿主端口（host）的清单见 client.py 顶部 —— 两半用的是同一张表。
"""

import os


class TransferMixin(object):
    """传输/本地文件相关的方法；由 WorkshopClient 继承使用（不要单独实例化）。"""

    # ---------------------------------<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌------------------------------- 下载
    def download(self, res_id, rtype, filename):
        """下载在线作品。能力里有 gzip 就走 /gz（省带宽），否则走普通下载。

        两条路都过同一个闸门（串行 + 最小间隔），并把"耗时/字节数/平均吞吐"打出来 ——
        40Mbit 的水管有没有被打满，靠这个看，不靠感觉。
        """
        import time as _t
        try:
            h = self._h()
            kind, _folder, _icon = h._ws_kind(rtype)
            target_dir = h._ws_local_dir(rtype)
            use_gz = h._ws_has_gzip()
            t0 = _t.time()
            with h._ws_xfer_slot():
                if use_gz:
                    r = h._ws_call("GET", h._ws_url("/api/" + kind + "/" + str(res_id) + "/gz"),
                                   timeout=30)
                    if r.status_code >= 400:
                        use_gz = False      # 老服务器没这条 → 退回普通下载
                if not use_gz:
                    r = h._ws_call("GET", h._ws_url("/api/" + kind + "/" + str(res_id)),
                                   timeout=30)
                # requests 会按 Content-Encoding 自动解压；但"只回了压缩体、头被中间层
                # 丢掉"的情况要自己按魔数解 —— 见宿主的 _ws_gz_body。
                payload = h._ws_gz_body(r) if r.status_code < 400 else b""
            if r.status_code >= 400:
                print("[工坊] 下载失败：HTTP %s" % r.status_code)
                return {"ok": False, "err": "下载没成功，稍后再试一次"}
            cost = _t.time() - t0
            fname = (filename or (str(res_id) + ".json")).replace("..", "_")
            if not fname.endswith(".json"):
                fname += ".json"
            dst = os.path.join(target_dir, fname)
            base, ext = os.path.splitext(dst)
            i = 1
            while os.path.exists(dst):
                dst = base + "_" + str(i) + ext
                i += 1
            with open(dst, "wb") as f:
                f.write(payload)
            if cost > 0:
                print("[工坊] 下载完成：%s %d 字节%s，耗时 %.2fs，平均 %.2f MB/s"
                      % (os.path.basename(dst), len(payload),
                         "（gzip 通道）" if use_gz else "", cost,
                         (len(payload) / 1048576.0) / cost))
            if rtype == "角色卡":
                h._reload_roles()
            elif rtype == "世界卡":
                h._reload_worlds()
            # 世界卡包下载到 world_packs/ 后刻意不自动装进 worlds/：装哪几张是用户的选择
            return {"ok": True, "file": os.path.basename(dst), "gzip": bool(use_gz),
                    "bytes": len(payload), "elapsed": round(cost, 3)}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    # ---------------------------------------------------------------- 点赞/删除
    def like(self, res_id, rtype):
        try:
            h = self._h()
            kind, _folder, _icon = h._ws_kind(rtype)
            r = h._ws_call("POST", h._ws_url("/api/" + kind + "/" + str(res_id) + "/like"),
                           timeout=8)
            if r.status_code >= 400:
                print("[工坊] 点赞失败：HTTP %s" % r.status_code)
                return {"ok": False, "err": "点赞没成功，稍后再试一次"}
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def delete(self, res_id, rtype):
        try:
            h = self._h()
            kind, _folder, _icon = h._ws_kind(rtype)
            r = h._ws_call("DELETE", h._ws_url("/api/" + kind + "/" + str(res_id)), timeout=8)
            if r.status_code >= 400:
                return h._ws_http_err(r, "删除")
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    # ---------------------------------------------------------------- 上传
    def upload(self, rtype, name):
        """上传本地作品：**有 gzip 能力就压缩上传**，否则照旧 multipart。

        三件事按顺序发生：
          ① 剔掉本地历史/状态（"每次上传都是新卡"，聊天树绝不外传）；
          ② 有 gzip 能力就 gzip.compress 后 POST /api/<kind>/upload/gz（文件名走 X-Filename）；
          ③ 接口不在（404/405/415/501）→ **自动回退 multipart**，不让用户感知。
        整个传输在闸门里（串行 + 最小间隔），429 按 Retry-After 退避，最多 max_retry 次。
        """
        import gzip as _gz
        import time as _t
        try:
            h = self._h()
            kind, _folder, _icon = h._ws_kind(rtype)
            target_dir = h._ws_local_dir(rtype)
            fname = h._safe_name(name) + ".json"
            path = os.path.join(target_dir, fname)
            if not os.path.isfile(path):
                # 2026-12 文案清理：文件名、目录名、数量都是实现细节，
                # 用户只需要知道下一步做什么。
                print("[工坊] 上传失败：本地找不到 %s" % path)
                return {"ok": False, "err": "找不到这个文件，试试重新选一次"}
            with open(path, "rb") as f:
                raw0 = f.read()      # 先读进内存：换通道重试时文件句柄已到末尾，必须能重发
            raw, gone = h.ws_strip_local_state(raw0)
            use_gz = h._ws_has_gzip()
            body = _gz.compress(raw) if use_gz else raw
            t0 = _t.time()
            r = None
            for attempt in range(max(1, self.max_retry)):
                with h._ws_xfer_slot():
                    if use_gz:
                        # 压缩体走专门接口：body 就是 gzip(JSON)，元数据全靠请求头。
                        # 不设 Content-Encoding 请求头 —— 有专门接口就不必让中间代理去猜。
                        r = h._ws_call(
                            "POST", h._ws_url("/api/" + kind + "/upload/gz"), data=body,
                            headers=dict(h._ws_headers(), **{
                                # 中文卡名必须转 ASCII：requests 按 latin-1 编头，
                                # 直接塞中文会抛 UnicodeEncodeError（真机上必现）。
                                "X-Filename": h.ws_header_name(fname),
                                "Content-Type": "application/json",
                            }),
                            timeout=30)
                        if r.status_code in (404, 405, 415, 501):
                            use_gz = False      # 服务器没有这条接口 → 本轮改走 multipart
                    if not use_gz:
                        r = h._ws_call(
                            "POST", h._ws_url("/api/" + kind + "/upload"),
                            files={"file": (fname, raw, "application/json")},
                            data={"name": name}, timeout=30)
                if r.status_code != 429:
                    break
                wait = h._ws_retry_after(r)
                print("[工坊] 链路限流（429），%.1f 秒后重试（第 %d/%d 次）"
                      % (wait, attempt + 1, max(1, self.max_retry)))
                _t.sleep(wait)
            else:
                # 2026-12 文案清理：界面上不再出现"限流/429"这种词，只说人话。
                # 真正的 429 状态码在上一行的 print 里（开发者日志）。
                return {"ok": False, "err": "现在有点挤，稍等一会儿再试"}
            cost = _t.time() - t0
            if r.status_code >= 400:
                return h._ws_http_err(r, "上传")
            sent = len(body) if use_gz else len(raw)
            if cost > 0:
                print("[工坊] 上传完成：%s，耗时 %.2fs，平均 %.2f MB/s%s"
                      % ("gzip %d→%d 字节（%.0f%%）" % (len(raw), sent,
                                                        100.0 * sent / max(1, len(raw)))
                         if use_gz else "明文 %d 字节" % len(raw),
                         cost, (sent / 1048576.0) / cost,
                         ("，已剔掉 " + "、".join(gone[:3])) if gone else ""))
            return {"ok": True, "message": r.text[:200], "gzip": bool(use_gz),
                    "bytes": sent, "raw_bytes": len(raw), "stripped": gone,
                    "elapsed": round(cost, 3)}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    # ---------------------------------------------------------------- 本地文件
    def preview(self, rtype, filename):
        """读本地卡内容给前端排版（512KB 上限：比任何一张真实卡都大，又不会被巨型文件拖住）"""
        h = self._h()
        target_dir = h._ws_local_dir(rtype)
        filename = os.path.basename((filename or "").replace("..", "_"))
        path = os.path.join(target_dir, filename)
        if not os.path.isfile(path):
            return {"ok": False, "err": "文件不存在"}
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read(512 * 1024)
            return {"ok": True, "preview": text}
        except Exception as e:
            return {"ok": False, "err": str(e)}

    def export(self, rtype, filename):
        """本地文件导出到用户选择的位置"""
        h = self._h()
        target_dir = h._ws_local_dir(rtype)
        filename = os.path.basename((filename or "").replace("..", "_"))
        src = os.path.join(target_dir, filename)
        if not os.path.isfile(src):
            return {"ok": False, "err": "文件不存在"}
        try:
            import webview
            win = webview.windows[0] if getattr(webview, "windows", None) else None
            if win is None:
                return {"ok": False, "err": "窗口未就绪"}
            res = win.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename,
                                         file_types=("JSON (*.json)",))
            if not res:
                return {"ok": False, "err": "cancelled"}
            import shutil
            shutil.copy2(src, res[0])
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def delete_local(self, rtype, filename):
        h = self._h()
        target_dir = h._ws_local_dir(rtype)
        filename = os.path.basename((filename or "").replace("..", "_"))
        path = os.path.join(target_dir, filename)
        if not os.path.isfile(path):
            return {"ok": False, "err": "文件不存在"}
        try:
            os.remove(path)
            if rtype == "角色卡":
                h._reload_roles()
            elif rtype == "世界卡":
                h._reload_worlds()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}

    def open_folder(self, which):
        h = self._h()
        try:
            if which == "roles":
                target = h.save_dir
            elif which == "worlds":
                target = h.world_dir
            elif which == "packs":
                target = h.pack_dir
            elif which == "plugins":
                target = getattr(h.plugin_manager, "plugin_dir", None) or "plugins"
            else:
                target = h.save_dir
            os.startfile(target)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "err": str(e)}

    # ---------------------------------------------------------------- 插件
    def plugins(self):
        """拉取工坊插件列表 + 本地已安装插件名（标记用）"""
        try:
            h = self._h()
            r = h._ws_call("GET", h._ws_url("/api/plugins/list"), timeout=8)
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            listing = r.json()
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}
        local = set()
        for d in getattr(h.plugin_manager, "plugin_dirs", []) or []:
            if os.path.isdir(d):
                for fn in os.listdir(d):
                    if fn.endswith(".py") and not fn.startswith("_"):
                        local.add(fn[:-3])
        return {"ok": True, "plugins": listing, "local": sorted(local)}

    def install_plugin(self, plugin_id):
        """下载插件到 plugins/ 目录并热加载"""
        try:
            h = self._h()
            r = h._ws_call("GET", h._ws_url("/api/plugins/" + str(plugin_id)), timeout=30)
            if r.status_code >= 400:
                return {"ok": False, "err": "HTTP " + str(r.status_code)}
            info = None
            try:
                lr = h._ws_call("GET", h._ws_url("/api/plugins/list"), timeout=8)
                if lr.status_code < 400:
                    info = next((p for p in lr.json() if str(p.get("id")) == str(plugin_id)),
                                None)
            except Exception:
                pass
            fname = (info or {}).get("original_name") or (str(plugin_id) + ".py")
            fname = os.path.basename(str(fname).replace("..", "_"))
            if not fname.endswith(".py"):
                fname += ".py"
            target_dir = getattr(h.plugin_manager, "plugin_dir", None) or "plugins"
            os.makedirs(target_dir, exist_ok=True)
            dst = os.path.join(target_dir, fname)
            with open(dst, "wb") as f:
                f.write(r.content)
            try:
                h.plugin_manager.reload_plugins()
            except Exception as e:
                print(f"[Plugin] 重载失败: {e}")
            return {"ok": True, "name": (info or {}).get("name") or fname, "file": fname}
        except Exception as e:
            return {"ok": False, "err": str(e)[:200]}
