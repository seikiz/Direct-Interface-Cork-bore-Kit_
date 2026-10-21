# -*- coding: utf-8 -*-
"""shell_api_ws —— 从 Kit.py 拆出的 mixin（^api_workshop）。

包含方法：api_workshop_save_conn、api_workshop_detect_proxy、api_workshop_test、api_workshop_list、api_workshop_search、api_workshop_download、api_workshop_like、api_workshop_delete、api_workshop_upload、api_workshop_preview、api_workshop_export、api_workshop_plugins…

为什么是 mixin：`HtmlApp` 是 god-object，150+ 个 `api_*` 门面互相 `self.xxx()`；
mixin 只搬代码位置、不动调用点（MRO 里照样能查到）。"""
from __future__ import annotations

class ApiWsMixin:
    """shell_api_ws"""

    # ---- 工坊面板的 17 个接口：门面（实现全在 mo<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌dules/workshop/client.py）----
    # 接口名/参数/返回形状一个字都没改 —— 前端与历史测试一行不用动。
    def api_workshop_state(self):
        """本地三种作品的文件名 + 连接配置（模块不可用也给空形状，界面不炸）"""
        try:
            return self._workshop_client().state()
        except Exception as e:
            print("[工坊] 模块不可用：%s" % str(e)[:160])
            return {"server_url": "", "active_server": "", "has_key": False, "proxy": "",
                    "local_roles": [], "local_worlds": [], "local_packs": []}


    def api_workshop_save_conn(self, server_url, api_key, proxy=None):
        """存工坊连接信息（api_key 的加密落盘仍在 _ws_save_config 里）"""
        try:
            return self._workshop_client().save_conn(server_url, api_key, proxy)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_detect_proxy(self):
        """自动检测本机代理（系统代理 + 常见代理软件端口）"""
        try:
            return self._workshop_client().detect_proxy()
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_test(self):
        """连通性自检（/api/health + /api/stats）"""
        try:
            return self._workshop_client().test()
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_list(self):
        """在线作品列表（按服务器能力清单决定问哪几种，老服务器不问 packs）"""
        try:
            return self._workshop_client().list_items()
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_search(self, query, rtype):
        try:
            return self._workshop_client().search(query, rtype)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_download(self, res_id, rtype, filename):
        """下载（有 gzip 能力走 /gz，否则普通下载；两条路都在传输闸门里）"""
        try:
            return self._workshop_client().download(res_id, rtype, filename)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_like(self, res_id, rtype):
        try:
            return self._workshop_client().like(res_id, rtype)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_delete(self, res_id, rtype):
        try:
            return self._workshop_client().delete(res_id, rtype)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_upload(self, rtype, name):
        """上传（gzip 优先、404 回退 multipart、429 退避；剔除本地历史在模块里）"""
        try:
            return self._workshop_client().upload(rtype, name)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_preview(self, rtype, filename):
        """读本地卡内容给前端排版（512KB 上限）"""
        try:
            return self._workshop_client().preview(rtype, filename)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_export(self, rtype, filename):
        """导出到用户选择的位置（保存对话框在模块里，走 pywebview）"""
        try:
            return self._workshop_client().export(rtype, filename)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_plugins(self):
        """工坊插件列表 + 本地已装插件名"""
        try:
            return self._workshop_client().plugins()
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_install_plugin(self, plugin_id):
        """下载插件到 plugins/ 并热加载"""
        try:
            return self._workshop_client().install_plugin(plugin_id)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_delete_local(self, rtype, filename):
        try:
            return self._workshop_client().delete_local(rtype, filename)
        except Exception as e:
            return self._ws_module_down(e)


    def api_workshop_open_folder(self, which):
        try:
            return self._workshop_client().open_folder(which)
        except Exception as e:
            return self._ws_module_down(e)

