# -*- coding: utf-8 -*-
"""角色选择弹窗「去 Checkbox」闸门（安卓）。

背景（用户截图 + 原话）
------------------------
角色选择弹窗每行左边有个 Material 的勾选方框，而它右边还有一整张卡片 —— 方框是多余的：
**整张卡片点一下就该选中/取消**。更糟的是那 20 行"重活"（存树 / 存配置 / 清选项 / 重载树 /
重载机制 / 刷新链路）全都塞在 `Checkbox(onCheckedChange = { ck -> … })` 里：UI 事件里混业务，
换一种选中方式（比如现在这样整行可点）就得把这段抄一遍，抄漏一行就是"选完了但引擎没换角色"。

所以这次做两件事，缺一不可：
  ① **删 Checkbox**，整张卡片 `clickable { toggleRole(n) }`，选中态靠
     `2.dp` + `palette.accent` 描边 + 行首 `check_circle`（未选中 `1.dp` + `line`）；
  ② 那 20 行搬成局部函数 `toggleRole(n)`，**行为逐字不变** —— 这条不能靠嘴说：
     本测试把搬家前的 lambda 体原样存成样本，和新函数体逐字符比对（只允许"求反那一行"不同），
     并且把 16 个关键调用的**顺序**也钉住。

`DickCheckRow`（ui/components/Cards.kt）**保留**：设置页还有 6 处在用它；这里只断言
"角色选择这一屏不再引用 `Checkbox(`"。

跑法：python -X utf8 tests/test_android_role_picker.py
"""
import io
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
APP = os.path.join(ROOT, "DICK-Android", "app", "src", "main", "java", "com", "dick", "app")
ROLES = os.path.join(APP, "ui", "screens", "library", "RolesScreen.kt")
CARDS = os.path.join(APP, "ui", "components", "Cards.kt")
SETTINGS = os.path.join(APP, "ui", "screens", "settings", "SettingsScreen.kt")

# 搬家前 `Checkbox(onCheckedChange = { ck -> … })` 里的**原文**（逐字，含缩进无关）。
# 新函数体必须与它逐字符相同，唯一允许的差别是最后那行"求反"的写法（见 TOGGLE_NEW / TOGGLE_OLD）。
ORIGINAL_BODY = u"""saveTree()
        selectedRoles = if (ck) selectedRoles + n else selectedRoles - n
        saveConfig()
        gal.clearChoices()
        scope.launch(Dispatchers.Main) {
            val tf = treeFileFor()
            tree.loadData(if (tf.exists()) {
                try { TreeStore.load(tf).historyTree } catch (_: Exception) { ChatTree().toData() }
            } else ChatTree().toData())
            tree.fixLeaf()
            mech.stateFile = stateFileFor()
            mech.resetConfigTracking()
            mech.reload(mechConfig(), tree, reset = true)
            mech.battleCfg = mechBattleConfig()
            mech.playerCfg = playerBattleConfig()
            mech.initBattle()
            refreshChain()
        }"""
TOGGLE_OLD = u"selectedRoles = if (ck) selectedRoles + n else selectedRoles - n"
TOGGLE_NEW = u"selectedRoles = if (n in selectedRoles) selectedRoles - n else selectedRoles + n"

# 关键调用（顺序即原顺序）：少一个 = 行为被删；顺序变了 = 可能踩到没初始化的东西。
ORDER = [
    "saveTree()",
    "selectedRoles",
    "saveConfig()",
    "gal.clearChoices()",
    "scope.launch(Dispatchers.Main)",
    "val tf = treeFileFor()",
    "tree.loadData(",
    "TreeStore.load(tf)",
    "ChatTree().toData()",
    "tree.fixLeaf()",
    "mech.stateFile = stateFileFor()",
    "mech.resetConfigTracking()",
    "mech.reload(mechConfig(), tree, reset = true)",
    "mech.battleCfg = mechBattleConfig()",
    "mech.playerCfg = playerBattleConfig()",
    "mech.initBattle()",
    "refreshChain()",
]

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
    return cond


def read(p):
    with io.open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def rel(p):
    return os.path.relpath(p, ROOT).replace("\\", "/")


def strip_comments(text):
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    t = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    out = []
    for line in t.split("\n"):
        m = re.search(r"(?<![:\"'`])//", line)
        out.append(line[:m.start()] if m else line)
    return "\n".join(out)


def fn_body(text, name):
    """取 `fun name(...) { … }` 的**函数体**（大括号内），名字可带参数匹配；找不到返回空串。"""
    m = re.search(r"fun\s+%s\s*\(" % re.escape(name), text)
    if not m:
        return u""
    i, depth, p = m.end() - 1, 0, m.end() - 1
    while p < len(text):
        if text[p] == "(":
            depth += 1
        elif text[p] == ")":
            depth -= 1
            if depth == 0:
                break
        p += 1
    k = text.find("{", p)
    if k < 0:
        return u""
    d, q = 1, k + 1
    while q < len(text) and d > 0:
        if text[q] == "{":
            d += 1
        elif text[q] == "}":
            d -= 1
        q += 1
    return text[k + 1:q - 1]


def norm(s):
    """压掉所有空白：比"行为"不比缩进。"""
    return re.sub(r"\s+", "", s)


# ============================================================
#  判定器（反向验证直接喂合成文本）
# ============================================================
def checkbox_problems(code):
    probs = []
    if re.search(r"(?<![A-Za-z_])Checkbox\s*\(", code):
        probs.append(u"还在用 Material Checkbox(")
    if "material3.Checkbox" in code:
        probs.append(u"还 import 着 material3.Checkbox")
    if "onCheckedChange" in code:
        probs.append(u"还留着 onCheckedChange（勾选框的回调）")
    return probs


def click_problems(code):
    probs = []
    if not re.search(r"fun\s+toggleRole\s*\(\s*n\s*:\s*String\s*\)", code):
        probs.append(u"没有 toggleRole(n: String) 这个局部函数")
    if not re.search(r"clickable\s*\{\s*toggleRole\s*\(\s*n\s*\)\s*\}", code):
        probs.append(u"整张卡片没有 clickable { toggleRole(n) }")
    return probs


def selected_state_problems(code):
    probs = []
    if "if (on) 2.dp else 1.dp" not in code:
        probs.append(u"选中态描边粗细不是 2.dp / 1.dp")
    if "if (on) theme.palette.accent else theme.line" not in code:
        probs.append(u"选中态描边颜色没走 palette.accent / line 令牌")
    if not re.search(r'icon\s*=\s*"check_circle"', code):
        probs.append(u"没有 check_circle 选中指示图标")
    if "theme.palette.accent" not in code:
        probs.append(u"没用到强调色令牌")
    return probs


def behavior_problems(code):
    """行为没被删：16 个关键调用都在函数体里、顺序不变，且与搬家前的 lambda 体逐字符一致。"""
    probs = []
    body = fn_body(code, "toggleRole")
    if not body:
        return [u"找不到 toggleRole 的函数体"]
    flat = norm(body)
    last = -1
    for marker in ORDER:
        pos = flat.find(norm(marker))
        if pos < 0:
            probs.append(u"函数体里缺 %s" % marker)
        elif pos < last:
            probs.append(u"调用顺序变了：%s" % marker)
        else:
            last = pos
    if not re.search(r"catch\s*\(\s*_\s*:\s*Exception\s*\)", body):
        probs.append(u"TreeStore.load 的异常吞法变了（原来是 catch (_: Exception)）")
    # 与搬家前逐字符比对：只允许"求反那一行"不同
    want = norm(ORIGINAL_BODY).replace(norm(TOGGLE_OLD), norm(TOGGLE_NEW))
    if flat != want:
        probs.append(u"函数体与搬家前的 lambda 体不一致（行为可能被改了）")
    return probs


def kept_for_others_problems(cards, settings):
    """DickCheckRow 必须留着（设置页在用），只是这一屏不再引用 Checkbox。"""
    probs = []
    if "fun DickCheckRow(" not in cards:
        probs.append(u"Cards.kt 里的 DickCheckRow 被删了（设置页 6 处在用）")
    if cards.count("Checkbox(") < 1:
        probs.append(u"DickCheckRow 里的 Checkbox 也没了（那是设置页的勾选框）")
    if len(re.findall(r"DickCheckRow\(", settings)) < 1:
        probs.append(u"设置页不再用 DickCheckRow（说明可以整块删了，但那是另一件事）")
    return probs


def row_parts_problems(code):
    """行首破甲火苗 + 右侧操作行保持原样（这次只动选中方式，别的都没动）。"""
    probs = []
    for need in ('icon = "local_fire_department"', "avatarTarget", "toggleRoleUnlock",
                 "roleEditName", "saveRole", "exportTarget", "pendingDelete"):
        if need not in code:
            probs.append(u"行里的动作丢了：%s" % need)
    return probs


# ============================================================
#  main
# ============================================================
def main():
    print("=" * 68)
    print(u"角色选择弹窗去 Checkbox（整行可点 / toggleRole 行为逐字不变）")
    print("=" * 68)

    print(u"\n== ① 文件与 Checkbox 清零 ==")
    check(u"RolesScreen.kt 在", os.path.isfile(ROLES), rel(ROLES))
    if not os.path.isfile(ROLES):
        print(u"\n通过 %d / 失败 %d" % (PASS, FAIL))
        return 1
    raw = read(ROLES)
    code = strip_comments(raw)
    p = checkbox_problems(code)
    check(u"角色选择屏里不再有 Checkbox( / onCheckedChange", not p, u"；".join(p[:3]))
    check(u"没有残留的 Checkbox 导入", "androidx.compose.material3.Checkbox" not in raw)
    check(u"文件 %d 行（还是那一屏，没顺手加东西）" % (len(raw.split("\n")) - 1),
          len(raw.split("\n")) - 1 <= 200)

    print(u"\n== ② 整张卡片点一下 = 选中/取消 ==")
    c = click_problems(code)
    check(u"抽出 toggleRole(n) 且整行 clickable 调它", not c, u"；".join(c[:3]))

    print(u"\n== ③ 选中态：令牌描边 + 勾图标（不用 Material 方框） ==")
    s = selected_state_problems(code)
    check(u"2.dp/accent 描边 + check_circle，颜色只走令牌", not s, u"；".join(s[:3]))
    check(u"没有硬编码颜色（Color(0x…)/命名色）",
          not re.search(r"Color\(\s*0x|\bColor\.(White|Black)\b", code))

    print(u"\n== ④ 行为逐字不变（20 行搬到 toggleRole 里，一行不少） ==")
    b = behavior_problems(code)
    check(u"16 个关键调用齐全、顺序与原 lambda 一致", not b, u"；".join(b[:3]))
    body = fn_body(code, "toggleRole")
    check(u"函数体仍覆盖原 20 行（%d 行）" % len(body.strip().split("\n")),
          len(body.strip().split("\n")) >= 18, u"%d 行" % len(body.strip().split("\n")))
    check(u"求反写法与 if(ck) 等价（+ / - 分支配对）",
          norm(TOGGLE_NEW) in norm(body))
    check(u"树重载仍跑在主线程（scope.launch(Dispatchers.Main)）",
          "scope.launch(Dispatchers.Main)" in body)
    print(u"       搬家前：%s" % TOGGLE_OLD)
    print(u"       搬家后：%s" % TOGGLE_NEW)

    print(u"\n== ⑤ 别的地方没被牵连（DickCheckRow 保留） ==")
    cards = read(CARDS)
    settings = read(SETTINGS)
    k = kept_for_others_problems(cards, settings)
    check(u"DickCheckRow 仍在 Cards.kt，且设置页 6 处照旧在用", not k, u"；".join(k[:3]))
    print(u"       设置页 DickCheckRow( 调用 %d 处"
          % len(re.findall(r"DickCheckRow\(", settings)))
    r = row_parts_problems(code)
    check(u"破甲火苗 / 头像 / 编辑 / 档 / 导图 / 删除 这些行内动作一个没少", not r,
          u"；".join(r[:3]))
    check(u"选中高亮只由 `on` 一处算出来（没有第二份布尔副本）",
          "val on = n in selectedRoles" in code)

    print(u"\n== ⑥ 反向验证（把每条弄坏一次，判定器必须红） ==")
    cases = [
        (u"把 Checkbox( 塞回去", code + u"\nCheckbox(checked = false, onCheckedChange = {})\n",
         checkbox_problems, code),
        (u"把 onCheckedChange 塞回去", code + u"\nval x = onCheckedChange\n",
         checkbox_problems, code),
        (u"删掉 clickable { toggleRole(n) }",
         code.replace(".clickable { toggleRole(n) }", ""), click_problems, code),
        (u"删掉 toggleRole 里的 saveConfig()",
         code.replace("        saveConfig()\n        gal.clearChoices()",
                      "        gal.clearChoices()"), behavior_problems, code),
        (u"把主线程改掉（scope.launch()）",
         code.replace("scope.launch(Dispatchers.Main) {", "scope.launch {"),
         behavior_problems, code),
        (u"把求反写错（+ / - 反了）",
         code.replace(TOGGLE_NEW, u"selectedRoles = if (n in selectedRoles) selectedRoles + n else selectedRoles - n"),
         behavior_problems, code),
        (u"选中态改回 line 描边",
         code.replace("if (on) theme.palette.accent else theme.line",
                      "theme.line"), selected_state_problems, code),
        (u"删掉 check_circle 指示",
         code.replace('icon = "check_circle"', 'icon = "circle"'), selected_state_problems, code),
    ]
    for name, bad, judge, before in cases:
        if not check(u"…%s：样本确实变了" % name, bad != before, u"替换没生效（字符串对不上）"):
            continue
        probs = judge(bad)
        check(u"…%s → 红" % name, bool(probs), u"%s" % (probs[:2] or u"居然还是绿的"))

    print("\n" + "=" * 68)
    print(u"通过 %d / 失败 %d" % (PASS, FAIL))
    if not FAIL:
        print("ANDROID_ROLE_PICKER_OK")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
# <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌
