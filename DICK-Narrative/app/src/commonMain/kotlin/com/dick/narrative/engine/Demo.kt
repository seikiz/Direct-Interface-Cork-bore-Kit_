package com.dick.narrative.engine

/**
 * 内置示例故事：没有故事包时也能把播放器跑起来，同时当作引擎的功能自检。
 * 覆盖：背景 / 立绘 / 旁白 / 台词 / 设置标记 / 带条件的选项 / 跳转 / 结局。
 */
object DemoStory {

    val spec: NarrativeSpec = NarrativeSpec(
        name = "钟楼之下",
        intro = "内置示例。把 story.json 放到程序目录下的 story 文件夹里就会读你的故事。",
        roles = listOf(
            NarrRole(name = "薇拉", sprite = "sprites/vera.png"),
            NarrRole(name = "管家", sprite = "sprites/butler.png"),
        ),
        lines = listOf(
            Line(
                id = "s1",
                title = "序章 · 门厅",
                key = true,
                steps = listOf(
                    Step(kind = "bg", bg = "bg/hall.png"),
                    Step(kind = "bgm", bgm = "bgm/theme.ogg"),
                    Step(kind = "note", note = "雨敲在彩窗上，门厅里只有一座停摆的钟。"),
                    Step(kind = "say", role = "管家", text = "小姐，客人到了。"),
                    Step(kind = "say", role = "薇拉", text = "……让他进来吧。这里已经很久没有活人的脚步声了。"),
                    Step(
                        kind = "choice",
                        choices = listOf(
                            ChoiceOption(text = "行礼，报上姓名", goto = "s2"),
                            ChoiceOption(text = "沉默地站着", goto = "s2"),
                            ChoiceOption(
                                text = "「这座钟，是停在哪一年？」",
                                goto = "s3",
                                condition = cond("""{"aff": ">=50"}"""),
                            ),
                        ),
                    ),
                ),
            ),
            Line(
                id = "s2",
                title = "第一章 · 会客室",
                next = "s4",
                steps = listOf(
                    Step(kind = "bg", bg = "bg/parlor.png"),
                    Step(kind = "say", role = "薇拉", text = "坐吧。你想问的事，我未必答得上来。"),
                    Step(kind = "setflag", flagKey = "met", flagValue = true),
                    Step(kind = "effect", effect = "flash"),
                    Step(kind = "note", note = "灯芯爆了一下。"),
                ),
            ),
            Line(
                id = "s3",
                title = "第一章 · 那座钟",
                next = "s4",
                steps = listOf(
                    Step(kind = "say", role = "薇拉", text = "……一九〇三年。你倒是第一个问这个的。"),
                    Step(kind = "setflag", flagKey = "clock", flagValue = true),
                    Step(kind = "say", role = "薇拉", text = "跟我来。", effect = "shake"),
                ),
            ),
            Line(
                id = "s4",
                title = "终章 · 钟楼",
                steps = listOf(
                    Step(kind = "bg", bg = "bg/tower.png"),
                    Step(
                        kind = "say",
                        role = "薇拉",
                        text = "钟摆一动，时间就会往前走。你确定要替它上发条？",
                        condition = null,
                    ),
                    Step(
                        kind = "note",
                        note = "（他曾经问过那座钟。）",
                        condition = cond("""{"flags": ["clock"]}"""),
                    ),
                    Step(kind = "end", endTitle = "钟楼之下 · 完"),
                ),
            ),
        ),
    )
}

private fun cond(text: String) = SpecParser.parseCondition(text)
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌