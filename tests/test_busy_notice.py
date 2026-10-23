# -*- coding: utf-8 -*-
"""警报体系：忙 ≠ 错（按重构后的结构钉住约定）。

用户反馈：连点发送，聊天里刷出 8 个「红叉 · 正在处理中，请稍候」——看着像出事了。
根因：忙碌分支走错误通道（on_error），被画成错误气泡、还存进历史树。

现在的分工：
    notices.py   ← 提示分级的唯一真相（BUSY_TEXT / notify_busy / should_show / busy_toast）
    DICK_core.py ← 只 import，不能再出现第二份文案
    Kit.py       ← _on_busy 一行转调；**不许** _append_sys（不写进对话）
    web          ← DICK_TOAST 轻提示；样式在 styles/toast.css（index.html 不许内联 style）
"""
import _websrc  # noqa: E402  读整个前端（index.html + chat-inline-*.js）
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(u"  [OK] %s" % name)
    else:
        FAIL += 1
        print(u"  [FAIL] %s  %s" % (name, detail))


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8").read()


def main():
    print("=" * 62)
    print(u"警报体系：忙是瞬时状态，不是错误")
    print("=" * 62)

    import notices

    print(u"\n== ① 忙：只走 on_busy（不碰错误通道） ==")
    hit = {"busy": 0, "err": 0}
    notices.notify_busy(lambda m: hit.__setitem__("busy", hit["busy"] + 1),
                        lambda m: hit.__setitem__("err", hit["err"] + 1))
    check(u"on_busy 被调用一次", hit["busy"] == 1, str(hit))
    check(u"on_error 一次都没被调用", hit["err"] == 0, str(hit))

    print(u"\n== ② 没给 on_busy → 退回 on_error（向后兼容） ==")
    got = []
    notices.notify_busy(None, lambda m: got.append(m))
    check(u"退回 on_error", got == [notices.BUSY_TEXT], str(got))

    print(u"\n== ③ 去重是纯函数，可单测 ==")
    check(u"刚提示过 → 不再提示", notices.should_show(100.0, 100.5) is False)
    check(u"过了 1.5 秒 → 可以提示", notices.should_show(100.0, 102.0) is True)
    check(u"坏输入 → 放行（不吞提示）", notices.should_show(None, 1.0) is True)

    print(u"\n== ④ 文案唯一来源 ==")
    _core_files = ["DICK_core.py", "core_fetch.py", "core_prompt.py", "core_mech.py",
                   "core_tree.py", "core_context.py", "core_llm.py"]
    core = "\n".join(read(f) for f in _core_files if os.path.isfile(os.path.join(ROOT, f)))
    noti = read("notices.py")
    check(u"文案只出现在 notices.py", noti.count(u"正在处理中，请稍候") == 1,
          str(noti.count(u"正在处理中，请稍候")))
    check(u"核心不再硬编码这段文案", core.count(u"正在处理中，请稍候") == 0,
          str(core.count(u"正在处理中，请稍候")))
    check(u"核心从 notices 导入", "from notices import" in core)
    check(u"忙碌分支统一走 notify_busy（≥4 处）",
          len(re.findall(r"notify_busy\(on_busy, on_error\)", core)) >= 4,
          str(len(re.findall(r"notify_busy\(on_busy, on_error\)", core))))

    print(u"\n== ⑤ 壳层：不写进对话 ==")
    import _shellsrc
    shell = _shellsrc.read()   # 壳层已拆分：Kit.py + shell_*.py
    m = re.search(r"def _on_busy\(self[^)]*\):\n(.*?)\n    def ", shell, re.S)
    check(u"壳层有 _on_busy", bool(m))
    body = m.group(1) if m else ""
    check(u"_on_busy 不调用 _append_sys（不写对话）", "_append_sys" not in body, body[:120])
    check(u"_on_busy 走 notices.busy_toast", "busy_toast" in body, body[:120])
    check(u"两处 fetch 都接了 on_busy", shell.count("on_busy=self._on_busy") >= 2,
          str(shell.count("on_busy=self._on_busy")))
    check(u"去重窗口在 notices 里", "1.5" in noti, "ok" if "1.5" in noti else "缺失")
    check(u"忙提示走输入栏上方（DICK_STATUS），不进对话", "DICK_STATUS" in noti, "没接 DICK_STATUS")
    check(u"忙提示不再弹右下角 toast", "DICK_TOAST" not in noti, "还在用 DICK_TOAST")

    print(u"\n== ⑥ 前端：轻提示出口 + 样式外置 ==")
    web = _websrc.read()
    css = read(os.path.join("web", "styles", "toast.css"))
    check(u"定义 window.DICK_TOAST", "window.DICK_TOAST" in web)
    check(u"有 dickToast 容器", 'id="dickToast"' in web)
    check(u"index.html 不再有内联 <style>", web.lower().count("<style>") == 0,
          u"还有 %d 个" % web.lower().count("<style>"))
    check(u"样式在 styles/toast.css 且只认令牌",
          "var(--surface-2)" in css and "var(--text)" in css and "var(--border)" in css)
    check(u"有 link 引到 toast.css", "styles/toast.css" in web)
    check(u"有 link 引到 composer.css", "styles/composer.css" in web)
    check(u"状态行放在输入栏之前（贴着输入框）",
          0 < web.find(u'id="composerStatus"') < web.find(u'id="inputbar"'),
          "%d vs %d" % (web.find(u'id="composerStatus"'), web.find(u'id="inputbar"')))
    check(u"前端有 DICK_STATUS 出口", "window.DICK_STATUS" in web)
    a = web.find(u"<!-- 轻提示")
    b = web.find(u"</script>", a) if a > 0 else -1
    block = web[a:b] if 0 <= a < b else u""
    check(u"轻提示段切得出来", len(block) > 100, str(len(block)))
    check(u"轻提示段内无 emoji",
          not re.search(u"[\U0001F300-\U0001FAFF\u2705\u274C]", block), block[:60])

    print(u"\n== \u2465 \u624b\u673a\u7aef\uff1a\u72b6\u6001\u884c\u8d34\u8f93\u5165\u6846\uff0c\u4e0d\u8fdb\u5bf9\u8bdd ==")
    _chat_dir = os.path.join("DICK-Android", "app", "src", "main", "java", "com", "dick", "app",
                              "ui", "screens", "chat")
    kt = read(os.path.join(_chat_dir, "ChatScreen.kt"))
    # BusyStatusLine 已拆到 ChatScreenParts.kt —— 同一组断言，把两份拼起来看
    kt += "\n" + read(os.path.join(_chat_dir, "ChatScreenParts.kt"))
    # 输入栏拆到 ChatComposer.kt —— "状态行在输入框之前"是跨文件的顺序断言
    kt += "\n" + read(os.path.join(_chat_dir, "ChatComposer.kt"))
    check(u"\u6709 BusyStatusLine \u7ec4\u5408\u51fd\u6570", "fun BusyStatusLine(" in kt)
    call_at = kt.find("BusyStatusLine(busy = busy")
    field_at = kt.find("OutlinedTextField(")
    check(u"\u72b6\u6001\u884c\u5199\u5728\u8f93\u5165\u6846\u4e4b\u524d",
          0 < call_at < field_at, u"%d vs %d" % (call_at, field_at))
    check(u"\u8ba1\u79d2\u5b9e\u73b0\u5728\uff08delay 1000\uff09", "delay(1000L)" in kt)
    check(u"\u7a7a\u95f2\u65f6\u4e0d\u5360\u4f4d\uff08busy=false \u76f4\u63a5 return\uff09",
          "if (!busy) return" in kt)
    seg = kt[kt.find("fun BusyStatusLine("):][:1200]
    check(u"\u53ea\u7528\u4e3b\u9898\u4ee4\u724c\uff08theme.muted / accent\uff09",
          "theme.muted" in seg and "accent" in seg)
    check(u"\u72b6\u6001\u884c\u91cc\u6ca1\u6709\u5f80\u6d88\u606f\u6811\u5199\uff08addNode\uff09",
          "addNode" not in seg)
    check(u"\u65e0 emoji",
          not re.search(u"[\U0001F300-\U0001FAFF\u2705\u274C]", seg), seg[:60])

    print("\n" + "=" * 62)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("BUSY_NOTICE_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌