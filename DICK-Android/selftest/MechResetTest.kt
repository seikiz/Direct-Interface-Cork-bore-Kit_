// 机制状态全量重置回归：清空<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌聊天记录后必须「状态如初」
//
// 为什么单独一个文件：Check.kt 那套全量自检要 Android SDK（core 用了 android.graphics）
// 和 Compose runtime（plugins）才编得过，已经跑不起来了；而这条契约必须随时能验 ——
// 它守的是真实出现过的 bug：手机端清空历史后，好感 100/精力 90/淫乱度 84/告白「已触发」全都还在。
//
// 用法：powershell -ExecutionPolicy Bypass -File selftest\run.ps1
import com.dick.core.ChatTree
import com.dick.core.J
import com.dick.core.MechanicsEngine
import java.io.File

var ok = 0
var bad = 0

fun ck(cond: Boolean, msg: String) {
    if (cond) { ok++; println("  [OK] $msg") } else { bad++; println("  [FAIL] $msg") }
}

fun main() {
    println("== 机制状态全量重置（清空聊天记录 → 状态如初） ==")

    // 机制卡配置：好感上限 100、初始 20；两个 int 状态字段
    val cfg = J.Obj()
    val aff = J.Obj()
    aff.fields["enabled"] = J.Bool(true)
    aff.fields["initial"] = J.Num(20.0)
    aff.fields["min"] = J.Num(0.0)
    aff.fields["max"] = J.Num(100.0)
    cfg.fields["affection"] = aff
    val stCfg = J.Obj()
    stCfg.fields["enabled"] = J.Bool(true)
    stCfg.fields["fields"] = J.Arr(mutableListOf(
        J.Obj().also { it.fields["key"] = J.Str("精力"); it.fields["type"] = J.Str("int"); it.fields["initial"] = J.Num(100.0) },
        J.Obj().also { it.fields["key"] = J.Str("淫乱度"); it.fields["type"] = J.Str("int"); it.fields["initial"] = J.Num(0.0) },
    ))
    cfg.fields["status"] = stCfg

    val dir = File(System.getProperty("java.io.tmpdir"), "dick_mech_reset_" + System.nanoTime())
    dir.mkdirs()
    val tree = ChatTree()
    val mech = MechanicsEngine()
    mech.stateFile = File(dir, "_mech_test.json")

    mech.reload(cfg, tree, reset = true, forceInitial = true)
    ck(mech.state?.fields?.get("affection")?.int() == 20, "初始态：好感 = 配置 initial（20）")
    ck(mech.getIntStatus("精力") == 100, "初始态：精力 = 100")

    // 聊一阵之后的状态（复刻截图里的数值），并落盘到 mech_state/
    mech.state!!.fields["affection"] = J.Num(100.0)
    (mech.state!!.fields["status"] as J.Obj).fields["精力"] = J.Num(90.0)
    (mech.state!!.fields["flags"] as J.Obj).fields["告白"] = J.Bool(true)
    mech.persistState()
    ck(mech.stateFile!!.exists(), "状态已落盘（mech_state）")

    // 关键：只传 reset=true 是不够的 —— 外层状态文件比树快照优先，旧值会被原样读回来。
    // 这条断言把这个坑钉在测试里：谁要是把 forceInitial 去掉，这里就会红。
    mech.reload(cfg, tree, reset = true)
    ck(mech.state?.fields?.get("affection")?.int() == 100, "（记录这个坑）reset=true 会读回旧状态 100")

    // 清空历史用的调用：forceInitial=true 才是真正的全量重置
    mech.reload(cfg, tree, reset = true, forceInitial = true)
    ck(mech.state?.fields?.get("affection")?.int() == 20, "forceInitial：好感回到 20")
    ck(mech.getIntStatus("精力") == 100, "forceInitial：精力回到 100")
    ck(mech.getIntStatus("淫乱度") == 0, "forceInitial：淫乱度回到 0")
    ck((mech.state!!.fields["flags"] as J.Obj).fields.isEmpty(), "forceInitial：flags 清空（告白不再「已触发」）")

    dir.deleteRecursively()

    println()
    println("机制重置测试：" + ok + " 通过 / " + bad + " 失败")
    if (bad > 0) kotlin.system.exitProcess(1)
}
