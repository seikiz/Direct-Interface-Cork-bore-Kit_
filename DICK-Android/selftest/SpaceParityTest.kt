// 空间层对拍：手机端算出来的地图 / 路费 / <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌可达 / 开门时间 / 位置标签 / 每轮注入，
// 必须和电脑端（`space_core.py`）**逐字**一样。
//
// 为什么值得单独一个测试：空间层是"约束"，不是"装饰" —— 它错了不会报错，只会让角色
// 一会儿在家、一会儿在火车站，或者把"路上 25 分钟"算成 0 分钟。这种漂移没人查得出来，
// 只能靠两端对拍。期望值来路：`tools/gen_parity.py` 在电脑端把 space_core.py 跑一遍，
// 冻成 `selftest/ParityGoldens.kt`；这里拿同样的输入算一遍，差一个字就算失败。
//
// ⚠ ⑦ 组是"第二意见"：那几条路径黄金值也覆盖（world 真的生效 / note_move 的写入路径 /
//   穿帮提醒计数 / describe 排版 / 倍率钩子），但期望值是另外**单独从电脑端算一遍**得来的 ——
//   两边互相印证：黄金值被重生成、而手机端逻辑没跟着改，⑦ 就会亮红。
//   （⑥ 组是纯黄金值对拍：带上 worldJson，跟电脑端同一组输入。）
//
// 用法：powershell -ExecutionPolicy Bypass -File selftest\run.ps1
package com.dick.parity.space

import com.dick.core.AppEnv
import com.dick.core.JsonS
import com.dick.core.MessageNode
import com.dick.core.MoveTag
import com.dick.core.SpaceConfig
import com.dick.core.SpaceCore
import com.dick.parity.Goldens
import java.io.File
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

/** 分钟数一律按浮点容差比（0.4 × 6 这种乘出来的值末尾几位会不一样）。 */
fun near(a: Double, b: Double): Boolean = Math.abs(a - b) < 1e-6

/** 每条用**全新的数据目录**：注入会写状态（穿帮提醒计数），共用一个目录会串味。 */
fun fresh(tag: String) {
    val d = File(System.getProperty("java.io.tmpdir"),
        "dick_space_parity_" + tag + "_" + System.nanoTime())
    d.mkdirs()
    AppEnv.dataRoot = d
    SpaceCore.resetConfigCache()
}

fun nodesOf(roles: List<String>, stamps: List<String>): List<MessageNode> {
    val out = ArrayList<MessageNode>()
    for (i in roles.indices) {
        out.add(MessageNode(role = roles[i], content = "第" + (i + 1) + "句",
            timestamp = stamps.getOrElse(i) { stamps.last() }))
    }
    return out
}

fun mapOf(c: Goldens.MapCase) =
    SpaceCore.mapFor(c.roleJson.ifEmpty { null }, c.worldJson.ifEmpty { null }, null,
        c.era.ifEmpty { null })

fun tagLine(m: MoveTag): String = (if (m.player) "ploc" else "loc") + "|" + m.place + "|" + m.by

fun putState(role: String, json: String, cfg: SpaceConfig) {
    val f = SpaceCore.statePath(role, cfg)
    f.parentFile?.mkdirs()
    f.writeText(json, Charsets.UTF_8)
}

fun placeEq(g: Triple<String, Double, Boolean>, w: Triple<String, Double, Boolean>): Boolean =
    g.first == w.first && near(g.second, w.second) && g.third == w.third

// ⑦ 组用的输入（与电脑端探针逐字一致）
const val CFG_JSON =
    "{\"enabled\": true, \"max_chars\": 240, \"show_reachable\": true, \"reachable_limit\": 4, " +
            "\"default_transport\": \"走路\", \"warn_when_impossible\": true, \"state_dir\": \"space\"}"
const val CAMPUS_WORLD =
    "{\"name\": \"校园日常\", \"description\": \"六月，栀子花开\", \"params\": {\"space\": " +
            "\"{\\\"places\\\": [{\\\"name\\\": \\\"教学楼\\\", \\\"minutes\\\": 6}, " +
            "{\\\"name\\\": \\\"食堂\\\", \\\"minutes\\\": 8, \\\"open\\\": [6, 20]}, " +
            "{\\\"name\\\": \\\"图书馆\\\", \\\"minutes\\\": 10, \\\"open\\\": [8, 22]}, " +
            "{\\\"name\\\": \\\"便利店\\\", \\\"minutes\\\": 5, \\\"open\\\": [22, 2]}], " +
            "\\\"home\\\": \\\"宿舍\\\", \\\"rooms\\\": [\\\"卧室\\\", \\\"阳台\\\"], " +
            "\\\"transport\\\": {\\\"走路\\\": 1.0, \\\"骑车\\\": 0.4}, " +
            "\\\"links\\\": {\\\"教学楼|图书馆\\\": 3}}\"}}"
const val BASE_ISO = "2026-05-04T12:00:00"

fun main() {
    println("== 空间层对拍（手机端 vs 电脑端） ==")

    // ---------------------------------------------------------------- ① 地图
    println("\n-- ① 地图（年代默认 + 世界卡覆盖 + 角色卡叠加） --")
    for (c in Goldens.mapCases) {
        val mp = mapOf(c)
        ck(mp.home == c.home, "[" + c.label + "] home 得到 " + mp.home + " 期望 " + c.home)
        if (c.era.isNotEmpty()) {
            ck(mp.era == c.era, "[" + c.label + "] era 得到 " + mp.era + " 期望 " + c.era)
        }
        val gotPlaces = mp.places.entries.sortedBy { it.key }
            .map { Triple(it.key, it.value.minutes, it.value.room) }
        if (gotPlaces.size != c.places.size) {
            ck(false, "[" + c.label + "] 地点个数 得到 " + gotPlaces.size + " 期望 " + c.places.size)
        } else {
            for (i in gotPlaces.indices) {
                ck(placeEq(gotPlaces[i], c.places[i]),
                    "[" + c.label + "] 地点 得到 " + gotPlaces[i] + " 期望 " + c.places[i])
            }
        }
        ck(mp.rooms == c.rooms, "[" + c.label + "] rooms 得到 " + mp.rooms + " 期望 " + c.rooms)

        val trGot = SpaceCore.transportOptions(mp)
        val trWant = c.transport.sortedWith(compareBy({ it.second }, { it.first }))
        var trOk = trGot.size == trWant.size
        if (trOk) {
            for (i in trGot.indices) {
                if (trGot[i].first != trWant[i].first || !near(trGot[i].second, trWant[i].second)) trOk = false
            }
        }
        ck(trOk, "[" + c.label + "] transport 得到 " + trGot + " 期望 " + trWant)

        val lkGot = mp.links.entries.sortedBy { it.key }.map { it.key to it.value }
        val lkWant = c.links.sortedBy { it.first }
        var lkOk = lkGot.size == lkWant.size
        if (lkOk) {
            for (i in lkGot.indices) {
                if (lkGot[i].first != lkWant[i].first || !near(lkGot[i].second, lkWant[i].second)) lkOk = false
            }
        }
        ck(lkOk, "[" + c.label + "] links 得到 " + lkGot + " 期望 " + lkWant)
    }
    println("  共 " + Goldens.mapCases.size + " 张地图（含明清 / 仙侠 / 末世 / 世界卡自带 / 角色卡叠加）")

    // ---------------------------------------------------------------- ② 路费
    println("\n-- ② 两地路费（轮辐估算 + links 覆盖） --")
    for (c in Goldens.travelCases) {
        val mp = SpaceCore.mapFor(null, c.worldJson.ifEmpty { null }, null, c.era.ifEmpty { null })
        val got = SpaceCore.travelMinutes(mp, c.a, c.b, c.by.ifEmpty { null })
        ck(near(got, c.expect), "[" + c.label + "] 得到 " + got + " 期望 " + c.expect)
    }
    println("  共 " + Goldens.travelCases.size + " 条")

    // ---------------------------------------------------------------- ③ 可达
    println("\n-- ③ 这段时间够去哪（升序，默认不列屋里） --")
    for (c in Goldens.reachCases) {
        val mp = SpaceCore.mapFor(null, c.worldJson.ifEmpty { null }, null, c.era.ifEmpty { null })
        val got = SpaceCore.reachable(mp, c.from, c.minutes, c.limit, c.by.ifEmpty { null }, c.includeRooms)
        var same = got.size == c.expect.size
        if (same) {
            for (i in got.indices) {
                if (got[i].first != c.expect[i].first || !near(got[i].second, c.expect[i].second)) same = false
            }
        }
        if (same) {
            ck(true, c.label)
        } else {
            ck(false, "[" + c.label + "] 可达列表不一致")
            println("    手机端: " + got)
            println("    电脑端: " + c.expect)
        }
    }
    println("  共 " + Goldens.reachCases.size + " 组（含「不限条数」limit=0）")

    // ---------------------------------------------------------------- ④ 开门
    println("\n-- ④ 开门时间（含跨天营业） --")
    for (c in Goldens.openCases) {
        val mp = SpaceCore.mapFor(null, c.worldJson.ifEmpty { null }, null, c.era.ifEmpty { null })
        val (gotOk, gotWhy) = SpaceCore.openNow(mp.places[c.place],
            LocalDateTime.of(2026, 5, 4, c.hour, c.minute))
        ck(gotOk == c.ok && gotWhy == c.why,
            "[" + c.label + "] 得到 (" + gotOk + ", " + gotWhy + ") 期望 (" + c.ok + ", " + c.why + ")")
    }
    println("  共 " + Goldens.openCases.size + " 组")

    // ---------------------------------------------------------------- ⑤ 位置标签
    println("\n-- ⑤ 位置标签（[loc:地名|交通] / [ploc:地名]） --")
    for (c in Goldens.tagCases) {
        val got = SpaceCore.parseMove(c.text).map { tagLine(it) }
        if (got == c.moves) {
            ck(true, c.label)
        } else {
            ck(false, "[" + c.label + "] 标签解析不一致")
            println("    手机端: " + got)
            println("    电脑端: " + c.moves)
        }
        ck(SpaceCore.stripMoveTags(c.text) == c.stripped,
            "[" + c.label + "] 剥离后 得到 " + SpaceCore.stripMoveTags(c.text) + " 期望 " + c.stripped)
    }
    println("  共 " + Goldens.tagCases.size + " 条（含 [位置:]/[地点:]/[LOC:]/斜线路径/空串）")

    // ---------------------------------------------------------------- ⑥ 注入
    println("\n-- ⑥ 每轮注入的【空间】（逐字比对，带世界卡） --")
    for (c in Goldens.spaceInjectCases) {
        fresh("inj")
        val cfg = SpaceCore.parseConfig(c.cfgJson)
        if (c.stateJson.isNotEmpty()) putState(c.roleName, c.stateJson, cfg)
        val got = SpaceCore.injectionText(roleJson = null, worldJson = c.worldJson.ifEmpty { null },
            scale = c.scale, cfg = cfg,
            now = LocalDateTime.parse(c.nowIso), name = c.roleName, chain = nodesOf(c.roles, c.stamps))
        if (got == c.expect) {
            ck(true, c.label)
        } else {
            ck(false, "[" + c.label + "] 注入文本不一致")
            show(got, c.expect)
        }
    }
    println("  共 " + Goldens.spaceInjectCases.size + " 组注入")

    // ---------------------------------------------------------------- ⑦ 补充
    // 第二意见：这几条路径 ⑥ 组也有黄金值，但下面的期望值是**另外单独从电脑端算一遍**得来的；
    // note_move 的写入路径（穿帮记录怎么落盘）黄金值完全没覆盖，只有这里盯着。
    println("\n-- ⑦ 第二意见（也是电脑端算的，但没冻进黄金值） --")

    val cfg = SpaceCore.parseConfig(CFG_JSON)

    // (a) world 生效：校园卡 home=宿舍、rooms=[卧室,阳台]（与 ⑥ 组「在家（该报屋里）」同一条输入）。
    fresh("x_rooms")
    putState("阿绫", "{\"place\": \"宿舍\", \"since\": \"2026-05-04T10:50:00\", \"by\": \"走路\", " +
            "\"scale\": 1.0}", cfg)
    var got7 = SpaceCore.injectionText(worldJson = CAMPUS_WORLD, scale = 1.0, cfg = cfg,
        now = LocalDateTime.parse(BASE_ISO), name = "阿绫",
        chain = nodesOf(listOf("user"), listOf(BASE_ISO)))
    var want7 = "【空间】阿绫 现在：宿舍（70 分钟前到，走路）\n屋里：卧室、阳台（都在 1 分钟内）\n" +
            SpaceCore.GUIDE
    if (got7 == want7) ck(true, "world 生效：屋里有卧室/阳台") else {
        ck(false, "world 生效：屋里那句不对")
        show(got7, want7)
    }

    // (b) world 生效：校园卡里 便利店(5) + 教学楼(6) = 11 分钟（与 ⑥ 组「玩家也在地图上」同一条输入；
    //     不传 world 的话会是 6 分钟 —— 这正是当初那条黄金值盲区的样子）。
    fresh("x_player")
    putState("阿绫", "{\"place\": \"教学楼\", \"since\": \"2026-05-04T11:30:00\", \"by\": \"走路\", " +
            "\"player_place\": \"便利店\", \"player_since\": \"2026-05-04T11:48:00\"}", cfg)
    got7 = SpaceCore.injectionText(worldJson = CAMPUS_WORLD, scale = 1.0, cfg = cfg,
        now = LocalDateTime.parse(BASE_ISO), name = "阿绫",
        chain = nodesOf(listOf("user"), listOf(BASE_ISO)))
    want7 = "【空间】阿绫 现在：教学楼（30 分钟前到，走路）\n你在便利店，到这儿要 11 分钟\n" +
            SpaceCore.GUIDE
    if (got7 == want7) ck(true, "world 生效：玩家到这儿 11 分钟") else {
        ck(false, "world 生效：玩家路费不对")
        show(got7, want7)
    }

    // (c) 照抄的电脑端怪癖：轮辐捷径比的是字面量"家"，不是 map.home。
    //     校园卡 home=宿舍、地图上没有"家"，travel(教学楼→家) 仍走 `b == 家` 那一支 → travel[教学楼] = 6。
    val campus = SpaceCore.mapFor(null, CAMPUS_WORLD, null, null)
    ck(near(SpaceCore.travelMinutes(campus, "教学楼", "家", null), 6.0),
        "照抄的怪癖：travel(教学楼→家) 得到 " + SpaceCore.travelMinutes(campus, "教学楼", "家", null) + " 期望 6.0")

    // (d) note_move 的写入路径（黄金值完全没覆盖）：时间不够也照样记下位置，并留下穿帮记录。
    fresh("x_move")
    putState("阿绫", "{\"place\": \"家\", \"since\": \"2026-05-04T11:30:00\", \"by\": \"走路\", " +
            "\"scale\": 1.0}", cfg)
    val mpDefault = SpaceCore.mapFor(null, null, cfg, null)
    val (st1, v1) = SpaceCore.noteMove("阿绫", "火车站", by = "", scale = 1.0,
        now = LocalDateTime.parse(BASE_ISO), mp = mpDefault, cfg = cfg)
    ck(!v1.ok && near(v1.need, 40.0) && v1.have != null && near(v1.have!!, 30.0) && v1.from == "家",
        "note_move 判定 得到 " + v1 + " 期望 (ok=false, need=40, have=30, from=家)")
    ck(v1.why == "从家到火车站要 40 分钟，这段时间只过了 30 分钟", "note_move 说明 得到 " + v1.why)
    ck(st1.place == "火车站" && st1.prev == "家" && st1.since == BASE_ISO &&
            st1.by == "走路" && near(st1.scale, 1.0),
        "note_move 状态 得到 " + st1)
    ck(st1.violation?.from == "家" && st1.violation?.to == "火车站" &&
            near(st1.violation?.need ?: -1.0, 40.0) && near(st1.violation?.have ?: -1.0, 30.0) &&
            st1.violation?.at == BASE_ISO && st1.violation?.warned == 0,
        "note_move 穿帮记录 得到 " + st1.violation)

    // 状态文件的字段名/数字写法要和电脑端同一份（两端能互读）。
    val raw = SpaceCore.loadStateRaw("阿绫", cfg)
    ck(raw.fields.keys.toSet() == setOf("place", "since", "by", "scale", "prev", "violation"),
        "状态文件字段 得到 " + raw.fields.keys)
    val js = JsonS.stringify(raw, pretty = false)
    ck(js.contains("\"place\":\"火车站\"") && js.contains("\"prev\":\"家\"") &&
            js.contains("\"since\":\"2026-05-04T12:00:00\"") &&
            js.contains("\"at\":\"2026-05-04T12:00:00\""),
        "状态文件取值 得到 " + js)
    ck(js.contains("\"need\":40.0") && js.contains("\"have\":30.0") && js.contains("\"scale\":1.0"),
        "状态文件里的整数浮点带 .0（与电脑端 json.dump 一致）得到 " + js)

    // (e) 穿帮提醒最多念两次：第一、二次念，第三次不念；计数落盘。
    val chain1 = nodesOf(listOf("user"), listOf(BASE_ISO))
    val warnLine = "⚠ 上一轮她 30 分钟前还在家，现在写到火车站：" +
            "从家到火车站要 40 分钟，这段时间只过了 30 分钟 —— " +
            "要么补一句路上/交通方式，要么把她拉回原处。"
    val head = "【空间】阿绫 现在：火车站（0 分钟前到，走路）\n"
    val t1 = SpaceCore.injectionText(scale = 1.0, cfg = cfg, now = LocalDateTime.parse(BASE_ISO),
        name = "阿绫", chain = chain1)
    ck(t1 == head + warnLine + "\n" + SpaceCore.GUIDE, "第一次穿帮提醒")
    if (t1 != head + warnLine + "\n" + SpaceCore.GUIDE) show(t1, head + warnLine + "\n" + SpaceCore.GUIDE)
    val t2 = SpaceCore.injectionText(scale = 1.0, cfg = cfg, now = LocalDateTime.parse(BASE_ISO),
        name = "阿绫", chain = chain1)
    ck(t2 == head + warnLine + "\n" + SpaceCore.GUIDE, "第二次穿帮提醒")
    val t3 = SpaceCore.injectionText(scale = 1.0, cfg = cfg, now = LocalDateTime.parse(BASE_ISO),
        name = "阿绫", chain = chain1)
    ck(t3 == head + SpaceCore.GUIDE, "第三次不再念")
    if (t3 != head + SpaceCore.GUIDE) show(t3, head + SpaceCore.GUIDE)
    ck(SpaceCore.loadState("阿绫", cfg).violation?.warned == 2, "念过两次后落盘 warned=2")

    // (f) note_move：时间够 → 位置照记，穿帮记录清掉；`家/厨房` 落到屋里的"厨房"。
    fresh("x_ok")
    putState("阿绫", "{\"place\": \"家\", \"since\": \"2026-05-04T11:55:00\", \"by\": \"走路\", " +
            "\"scale\": 1.0, \"violation\": {\"from\": \"家\", \"to\": \"火车站\", \"need\": 40.0, " +
            "\"have\": 1.0, \"at\": \"2026-05-04T12:00:00\", \"why\": \"来不及\", \"warned\": 1}}", cfg)
    val (st2, v2) = SpaceCore.noteMove("阿绫", "家/厨房", by = "", scale = 1.0,
        now = LocalDateTime.parse(BASE_ISO), mp = SpaceCore.mapFor(null, null, cfg, null), cfg = cfg)
    ck(v2.ok && near(v2.need, 0.5) && v2.have != null && near(v2.have!!, 5.0) && v2.from == "家" && v2.why.isEmpty(),
        "note_move 时间够 得到 " + v2 + " 期望 (ok=true, need=0.5, have=5, from=家)")
    ck(st2.place == "厨房" && st2.prev == "家" && st2.violation == null && st2.offmap.isEmpty(),
        "note_move 清除穿帮 + 屋里路径 得到 " + st2)

    // (g) "哪都去不了"（⑥ 组没覆盖这条分支）
    fresh("x_none")
    putState("阿绫", "{\"place\": \"医院\", \"since\": \"2026-05-04T11:55:00\", \"by\": \"走路\"}", cfg)
    got7 = SpaceCore.injectionText(scale = 1.0, cfg = cfg, now = LocalDateTime.parse(BASE_ISO),
        name = "阿绫", chain = nodesOf(listOf("user"), listOf("2026-05-04T11:59:00")))
    want7 = "【空间】阿绫 现在：医院（5 分钟前到，走路）\n这1分钟哪儿都去不了（最近的也要 20 分钟）\n" +
            SpaceCore.GUIDE
    if (got7 == want7) ck(true, "预算不够：哪儿都去不了") else {
        ck(false, "预算不够那句不对")
        show(got7, want7)
    }

    // (h) /在哪 的完整状态（黄金值没覆盖 describe）
    fresh("x_describe")
    putState("阿绫", "{\"place\": \"学校\", \"since\": \"2026-05-04T11:55:00\", \"by\": \"骑车\"}", cfg)
    got7 = SpaceCore.describe(scale = 1.0, cfg = cfg, now = LocalDateTime.parse(BASE_ISO), name = "阿绫")
    want7 = listOf(
        "空间层：开",
        "阿绫 现在：学校（5 分钟前到，骑车）",
        "地图（25 个地点，下面是从「学校」出发的耗时）：",
        "  家         25 分钟",
        "  卧室        26 分钟",
        "  客厅        26 分钟",
        "  厨房        26 分钟",
        "  卫生间       26 分钟",
        "  阳台        26 分钟",
        "  书房        26 分钟",
        "  玄关        26 分钟",
        "  楼下        27 分钟",
        "  小区门口      28 分钟",
        "  便利店       31 分钟",
        "  公交站       33 分钟",
        "  菜市场       35 分钟",
        "  超市        37 分钟",
        "  公园        40 分钟",
        "  餐厅        40 分钟",
        "  咖啡馆       43 分钟",
        "  医院        45 分钟",
        "  朋友家       50 分钟",
        "  电影院       55 分钟",
        "  公司        60 分钟",
        "  火车站       65 分钟",
        "  邻近城市     205 分钟",
        "  远方（省外）   625 分钟",
        "改法：/在哪 <地点> ｜ /在哪 <地点>|骑车 ｜ /在哪 我=<地点> ｜ /空间 关 ｜ /空间 交通 打车",
    ).joinToString("\n")
    if (got7 == want7) ck(true, "describe 排版") else {
        ck(false, "describe 排版不一致")
        show(got7, want7)
    }

    // (i) 倍率：显式非法值 → 1.0；null → 走 scaleProvider（接 UI 时设成 TimeScale.current）。
    SpaceCore.scaleProvider = { 720.0 }
    ck(near(SpaceCore.scaleOf(null), 720.0), "scaleOf(null) 应走 scaleProvider")
    SpaceCore.scaleProvider = { 1.0 }
    ck(near(SpaceCore.scaleOf(null), 1.0) && near(SpaceCore.scaleOf(0.0), 1.0) &&
            near(SpaceCore.scaleOf(-3.0), 1.0) && near(SpaceCore.scaleOf(3600.0), 3600.0),
        "显式倍率：非法 → 1.0，合法 → 原值")

    println("\n通过 " + ok + " / 失败 " + bad)
    if (bad > 0) {
        println("SPACE_PARITY_FAILED")
        kotlin.system.exitProcess(1)
    }
    println("SPACE_PARITY_OK")
}
