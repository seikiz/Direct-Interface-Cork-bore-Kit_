// 生活层对拍：手机端算出来的菜单/时钟<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌/注入，必须和电脑端**逐字**一样。
//
// 为什么值得单独一个测试：菜单是确定性抽样（种子 = 角色｜世界第几天｜哪一餐），
// 这条设计的承诺是"重启、回档、电脑端和手机端算出来都一样"。真漂了不会报错，
// 只会"她今天吃的东西变了" —— 那种问题没人查得出来，只能靠对拍。
//
// 期望值来路：`tools/gen_parity.py` 在电脑端把 life_core.py 跑一遍冻成
// `selftest/ParityGoldens.kt`。这里拿同样的输入算一遍，差一个字就算失败。
//
// 用法：powershell -ExecutionPolicy Bypass -File selftest\run.ps1
package com.dick.parity.life

import com.dick.core.LifeCore
import com.dick.core.LifeTables
import com.dick.core.Commonsense
import com.dick.core.MessageNode
import com.dick.parity.Goldens
import java.time.LocalDateTime

var ok = 0
var bad = 0

fun ck(cond: Boolean, msg: String) {
    if (cond) {
        ok++
    } else {
        bad++
        println("  [FAIL] $msg")
    }
}

fun show(got: String, want: String) {
    println("    手机端: " + got.replace("\n", "\\n"))
    println("    电脑端: " + want.replace("\n", "\\n"))
}

fun nodesOf(roles: List<String>, stamps: List<String>): List<MessageNode> {
    val out = ArrayList<MessageNode>()
    for (i in roles.indices) {
        out.add(MessageNode(role = roles[i], content = "第" + (i + 1) + "句",
            timestamp = stamps.getOrElse(i) { stamps.last() }))
    }
    return out
}

fun menuLines(c: Goldens.MenuCase): List<String> {
    val cfg = LifeCore.parseConfig(c.cfgJson)
    val profile = LifeCore.profileFor(c.roleJson, cfg, c.worldJson)
    val labels = LifeTables.MEAL_LABELS.toMap()
    val meals = c.meals.map { it to (labels[it] ?: it) }
    return LifeCore.dayMenu(profile, c.lifeDay, meals).map {
        it.meal + "|" + it.staple + "|" + it.dishes.joinToString(",") + "|" + it.drink + "|" +
                it.methods.joinToString(",")
    }
}

fun main() {
    println("== 生活层对拍（手机端 vs 电脑端） ==")

    println("\n-- ① 认年代（世界卡/角色卡 → 生活层 / 常识库） --")
    for (c in Goldens.eraCases) {
        ck(LifeCore.detectEra(c.worldJson) == c.lifeEra,
            "[" + c.label + "] 生活层年代 得到 " + LifeCore.detectEra(c.worldJson) + " 期望 " + c.lifeEra)
        ck(Commonsense.detectEra(c.worldJson, c.roleJson) == c.csEra,
            "[" + c.label + "] 常识库年代 得到 " + Commonsense.detectEra(c.worldJson, c.roleJson) +
                    " 期望 " + c.csEra)
        ck(Commonsense.detectKind(c.worldJson, c.roleJson) == c.csKind,
            "[" + c.label + "] 设定类型 得到 " + Commonsense.detectKind(c.worldJson, c.roleJson) +
                    " 期望 " + c.csKind)
    }
    println("  共 " + Goldens.eraCases.size + " 组年代判定")

    println("\n-- ② 一日三餐的确定性抽样（同一个角色同一天必须同一份菜单） --")
    for (c in Goldens.menuCases) {
        val got = menuLines(c)
        if (got == c.dishes) {
            ck(true, c.label)
        } else {
            ck(false, "[" + c.label + "] 菜单不一致")
            for (i in 0 until maxOf(got.size, c.dishes.size)) {
                val g = got.getOrNull(i) ?: "(少一餐)"
                val w = c.dishes.getOrNull(i) ?: "(多一餐)"
                if (g != w) show(g, w)
            }
        }
    }
    println("  共 " + Goldens.menuCases.size + " 组菜单（含 720× 与史前这种极端年代）")

    println("\n-- ③ 每轮注入的【生活·那边】（逐字比对） --")
    for (c in Goldens.lifeInjectCases) {
        val cfg = LifeCore.parseConfig(c.cfgJson)
        val got = LifeCore.injectionText(nodesOf(c.roles, c.stamps), c.scale, c.roleJson,
            c.worldJson, cfg, LocalDateTime.parse(c.nowIso))
        if (got == c.expect) {
            ck(true, c.label)
        } else {
            ck(false, "[" + c.label + "] 注入文本不一致")
            show(got, c.expect)
        }
    }
    println("  共 " + Goldens.lifeInjectCases.size + " 组注入")

    println("\n-- ④ /生活 面板（同一个命令两端同一个样子） --")
    for (c in Goldens.lifeDescribeCases) {
        val cfg = LifeCore.parseConfig(c.cfgJson)
        val got = LifeCore.describe(nodesOf(c.roles, c.stamps), c.scale, c.roleJson,
            c.worldJson, cfg, LocalDateTime.parse(c.nowIso))
        if (got == c.expect) {
            ck(true, c.label)
        } else {
            ck(false, "[" + c.label + "] /生活 面板不一致")
            show(got, c.expect)
        }
    }
    println("  共 " + Goldens.lifeDescribeCases.size + " 组面板")

    println("\n通过 " + ok + " / 失败 " + bad)
    if (bad > 0) {
        println("LIFE_PARITY_FAILED")
        kotlin.system.exitProcess(1)
    }
    println("LIFE_PARITY_OK")
}
