# -*- coding: utf-8 -*-
"""把 CI 失败脚本名写到 GitHub Issue（公开可读，不需要 admin 权限）。

为什么不用注解/日志：
  · `::error file=` 注解被 GitHub 丢弃（文件不在本次改动里）；
  · job 级 `::error::` 也没出现在 annotations；
  · job 日志要仓库 admin 权限（API 403）；
  · commit status 那条路实测没写进去（多半是 token 的 statuses 权限）。
Issue 是**公开可读**的，API 一条 GET 就能拿到内容，而且天然带历史。

用法（CI 里）：
    GH_TOKEN=xxx python tools/ci_report.py --file /tmp/dick_failed.txt --sha <sha>
本地试运行（没有 token）：只会打印将要写什么，不发请求。
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
TITLE = "[自动] CI 失败报告"


def req(method, url, token, data=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    r = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "dick-ci-report",
    })
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"raw": e.read().decode("utf-8", "replace")[:400]}
    except Exception as e:                      # noqa: BLE001
        return 0, {"raw": str(e)[:200]}


def main():
    args = sys.argv[1:]
    path = ""
    sha = os.environ.get("GITHUB_SHA", "")
    for i, a in enumerate(args):
        if a == "--file" and i + 1 < len(args):
            path = args[i + 1]
        elif a == "--sha" and i + 1 < len(args):
            sha = args[i + 1]

    names = ""
    if path and os.path.isfile(path):
        names = open(path, encoding="utf-8", errors="replace").read().strip()
    if not names:
        print("没有失败脚本，跳过上报")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = "https://github.com/%s/actions/runs/%s" % (repo, os.environ["GITHUB_RUN_ID"])

    text = "失败脚本：\n\n```\n%s\n```\n\n提交：`%s`\n运行：%s\n\n平台：%s" % (
        names.strip(), sha[:12], run_url or "(本地)", sys.platform)

    if not token or not repo:
        print("[dry-run] 未配置 token/repo，将写入的内容：\n" + text)
        return 0

    # 找一个已有的报<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌告 issue
    q = urllib.parse.quote('repo:%s in:title "%s" state:open' % (repo, TITLE))
    code, data = req("GET", API + "/search/issues?q=" + q, token)
    num = 0
    if code == 200 and data.get("items"):
        num = data["items"][0]["number"]

    if num:
        code, data = req("POST", "%s/repos/%s/issues/%d/comments" % (API, repo, num),
                         token, {"body": text})
        print("评论 issue #%d -> HTTP %d" % (num, code))
    else:
        code, data = req("POST", "%s/repos/%s/issues" % (API, repo),
                         token, {"title": TITLE, "body": text})
        print("创建 issue -> HTTP %d %s" % (code, str(data)[:200]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
