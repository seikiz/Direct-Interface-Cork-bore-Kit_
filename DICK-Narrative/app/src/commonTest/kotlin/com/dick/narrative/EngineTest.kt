package com.dick.narrative

import com.dick.narrative.engine.Cond
import com.dick.narrative.engine.DemoStory
import com.dick.narrative.engine.NarrativeEngine
import com.dick.narrative.engine.NarrState
import com.dick.narrative.engine.SpecParser
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/*
 * 引擎测试：不依赖 UI、不依赖文件系统，所以桌面和手机跑的是同一份逻辑。
 * 运行：gradle.bat :app:desktopTest
 */
class EngineTest {

    @Test
    fun spec_parses() {
        val spec = DemoStory.spec
        assertEquals("钟楼之下", spec.name)
        assertEquals(2, spec.roles.size)
        assertEquals(4, spec.lines.size)
        assertEquals("s1", spec.startId)
        assertEquals("薇拉", spec.role("薇拉")?.name)
    }

    @Test
    fun legacy_json_still_parses() {
        val text = """
        {
          "name": "旧格式",
          "roles": [{"name":"甲"}],
          "scenes": [
            {"id":"a","title":"A","lines":[
              {"speaker":"甲","text":"你好"},
              {"choice":[{"text":"走","goto":"b"}]}
            ]}
          ]
        }
        """.trimIndent()
        val spec = SpecParser.parse(text)
        assertEquals("旧格式", spec.name)
        assertEquals(1, spec.lines.size)
        assertEquals("say", spec.lines[0].steps[0].kind)
        assertEquals("choice", spec.lines[0].steps[1].kind)
    }

    @Test
    fun walks_to_choice() {
        val e = NarrativeEngine(DemoStory.spec)
        e.start()

        assertEquals("s1", e.lineId)
        assertEquals("bg/hall.png", e.bg)
        assertEquals("bgm/theme.ogg", e.bgm)
        assertEquals("雨敲在彩窗上，门厅里只有一座停摆的钟。", e.note)

        e.advance()
        assertEquals("管家", e.speaker)
        assertTrue(e.text.startsWith("小姐"))

        e.advance()
        assertEquals("薇拉", e.speaker)

        e.advance()
        assertEquals(3, e.choices.size)
        assertEquals("行礼，报上姓名", e.choices[0].text)
        assertEquals(2, e.backlog.size)
    }

    @Test
    fun condition_hides_option() {
        val e = NarrativeEngine(DemoStory.spec)
        e.start()
        e.state.affection = 10
        e.advance(); e.advance(); e.advance()
        assertEquals(2, e.choices.size)
    }

    @Test
    fun branch_sets_flag_and_reaches_end() {
        val e = NarrativeEngine(DemoStory.spec)
        e.start()
        e.advance(); e.advance(); e.advance()
        e.choose(0)

        assertEquals("s2", e.lineId)
        assertEquals("薇拉", e.speaker)

        e.advance()
        assertEquals("灯芯爆了一下。", e.note)
        assertTrue(e.state.flags["met"] == true)

        e.advance()
        assertEquals("s4", e.lineId)

        e.advance()
        assertTrue(e.ended)
        assertEquals("钟楼之下 · 完", e.endTitle)
    }

    @Test
    fun flag_condition_shows_extra_note() {
        val e = NarrativeEngine(DemoStory.spec)
        e.start()
        e.advance(); e.advance(); e.advance()
        e.choose(2)                      // 「那座钟」分支 → 设置 clock 标记
        assertEquals("s3", e.lineId)

        e.advance(); e.advance()          // 走到 s4
        assertEquals("s4", e.lineId)

        e.advance()
        assertEquals("（他曾经问过那座钟。）", e.note)
    }

    @Test
    fun save_and_restore_keeps_position() {
        val e = NarrativeEngine(DemoStory.spec)
        e.start()
        e.advance(); e.advance()

        val snap = e.snapshot()
        val loaded = NarrativeEngine(DemoStory.spec)
        loaded.restore(snap)

        assertEquals(e.lineId, loaded.lineId)
        assertEquals(e.speaker, loaded.speaker)
        assertEquals(e.text, loaded.text)
        assertEquals(e.state.affection, loaded.state.affection)

        loaded.advance()
        assertEquals(3, loaded.choices.size)
    }

    @Test
    fun save_at_choice_frame_restores_choices() {
        val e = NarrativeEngine(DemoStory.spec)
        e.start()
        e.advance(); e.advance(); e.advance()
        assertTrue(e.choices.isNotEmpty())

        val loaded = NarrativeEngine(DemoStory.spec)
        loaded.restore(e.snapshot())
        assertEquals(3, loaded.choices.size)
        assertEquals("行礼，报上姓名", loaded.choices[0].text)

        loaded.choose(1)
        assertEquals("s2", loaded.lineId)
    }

    // ---------- 和 GAL制作器 实际产出的格<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌式对齐（这是真正要对接的契约） ----------

    /** 制作器把 bg/bgm 挂在「线」上，立绘可以是一行多张，选项带 if */
    private val makerJson = """
    {
      "codex": 1,
      "name": "制作器产物",
      "author": "",
      "intro": "对接测试",
      "roles": [{ "name": "薇拉", "sprite": "sprites/vera.png", "voice": "" }],
      "scenes": [
        {
          "id": "s1",
          "title": "第一线",
          "bg": "bg/hall.png",
          "bgm": "bgm/a.mp3",
          "next": "s2",
          "lines": [
            { "kind": "say", "speaker": "薇拉", "text": "一",
              "sprites": [{ "file": "sprites/vera.png" }] },
            { "kind": "choice", "choice": [
                { "text": "走", "goto": "s2" },
                { "text": "留", "if": { "aff": ">=90" } }
            ] }
          ]
        },
        {
          "id": "s2",
          "title": "第二线",
          "bg": "bg/parlor.png",
          "bgm": "bgm/b.mp3",
          "lines": [{ "kind": "end", "end": "完" }]
        }
      ]
    }
    """.trimIndent()

    @Test
    fun maker_format_parses() {
        val spec = SpecParser.parse(makerJson)
        assertEquals("制作器产物", spec.name)
        assertEquals(2, spec.lines.size)

        val s1 = spec.line("s1")!!
        assertEquals("第一线", s1.title)
        assertEquals("bg/hall.png", s1.bg)          // 线级背景
        assertEquals("bgm/a.mp3", s1.bgm)           // 线级音乐
        assertEquals("s2", s1.next)
        assertEquals(listOf("sprites/vera.png"), s1.steps[0].sprites)
        assertEquals(2, s1.steps[1].choices.size)
        assertEquals("s2", s1.steps[1].choices[0].goto)
    }

    @Test
    fun maker_format_plays() {
        val e = NarrativeEngine(SpecParser.parse(makerJson))
        e.start()
        assertEquals("bg/hall.png", e.bg)           // 进线就切背景
        assertEquals("bgm/a.mp3", e.bgm)            // 进线就换音乐
        assertEquals("薇拉", e.speaker)
        assertEquals("一", e.text)
        assertEquals(1, e.sprites.size)
        assertEquals("sprites/vera.png", e.sprites[0].file)

        e.advance()
        assertEquals(1, e.choices.size)             // aff=50，>=90 那个选项被藏掉
        assertEquals("走", e.choices[0].text)

        e.choose(0)
        assertEquals("s2", e.lineId)
        assertEquals("bg/parlor.png", e.bg)         // 换线换背景
        assertEquals("bgm/b.mp3", e.bgm)
        assertTrue(e.ended)
        assertEquals("完", e.endTitle)
    }

    @Test
    fun scene_level_bgm_survives_step_level_bg() {
        // 线级 bgm + 点级 bg 同时存在时，两个都要生效。
        // bg 这类「不阻塞」的点在 start() 里就执行完了，所以最终看到的是点级背景、
        // 而线级音乐不会被步骤清掉。
        val json = """
        {"name":"x","scenes":[{"id":"s1","bg":"bg/a.png","bgm":"bgm/a.mp3",
         "lines":[{"kind":"bg","bg":"bg/b.png"},{"kind":"say","speaker":"甲","text":"嗨"}]}]}
        """.trimIndent()
        val e = NarrativeEngine(SpecParser.parse(json))
        e.start()
        assertEquals("bg/b.png", e.bg)              // 点级背景覆盖线级背景
        assertEquals("bgm/a.mp3", e.bgm)            // 线级音乐还在
        assertEquals("嗨", e.text)
        assertEquals("甲", e.speaker)
    }

    @Test
    fun condition_semantics() {        val st = NarrState(affection = 80)
        st.status["心情"] = "开心"
        st.flags["met"] = true
        st.flags["gone"] = false

        assertTrue(Cond.eval(st, null))
        assertTrue(Cond.eval(st, SpecParser.parseCondition("""{"aff":">=80"}""")))
        assertFalse(Cond.eval(st, SpecParser.parseCondition("""{"aff":">=85"}""")))
        assertTrue(Cond.eval(st, SpecParser.parseCondition("""{"aff":"<90"}""")))
        assertTrue(Cond.eval(st, SpecParser.parseCondition("""{"aff":80}""")))
        assertTrue(Cond.eval(st, SpecParser.parseCondition("""{"status":{"心情":"开心"}}""")))
        assertFalse(Cond.eval(st, SpecParser.parseCondition("""{"status":{"心情":"生气"}}""")))
        assertTrue(Cond.eval(st, SpecParser.parseCondition("""{"flags":["met","!gone"]}""")))
        assertFalse(Cond.eval(st, SpecParser.parseCondition("""{"flags":["gone"]}""")))
        assertTrue(Cond.eval(st, SpecParser.parseCondition("""{"any":[{"aff":">=99"},{"flags":["met"]}]}""")))
        assertFalse(Cond.eval(st, SpecParser.parseCondition("""{"all":[{"aff":">=10"},{"flags":["gone"]}]}""")))
        assertTrue(Cond.eval(st, SpecParser.parseCondition("")))          // 空条件恒真
    }
}
