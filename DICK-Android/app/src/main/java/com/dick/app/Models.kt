package com.dick.app

import androidx.compose.ui.graphics.ImageBitmap

// ---------- 内置模型/常量/纯函数（自 App.kt 拆出） ----------
// ---------- 内置数据 ----------
data class Preset(val name: String, val prefix: String, val rules: String, val suffix: String)

val PRESETS = listOf(
    Preset("默认", "", "", ""),
    Preset("跑团主持人", "你是跑团主持人（GM）：负责叙述场景、扮演 NPC、掷骰判定、控制节奏。", "1. 尊重骰子结果；2. 保持紧张感与戏剧性；3. 描述要具体。", ""),
    Preset("小说叙事", "你是一位文笔细腻的小说家，以第三人称叙事推进剧情。", "1. 描写注重画面感与心理活动；2. 每段 150 字左右。", ""),
    Preset("单推模式", "你是角色的单推人（狂热粉丝视角）。", "1. 对角色充满喜爱与支持；2. 应援、关心、偶尔告白。", ""),
    Preset("角色单推模式", "你是被角色单推的对象：角色对你专一、依赖、偶尔吃醋。", "1. 保持角色人设；2. 对玩家表现出独占欲。", ""),
    Preset("公文模式", "你是公文写作助手，输出规范公文（标题/正文/落款，GB/T 9704 风格）。", "1. 语言庄重简练；2. 结构完整；3. 不添加角色扮演内容。", ""),
    Preset("财报模式", "你是资深宏观经济与股票分析师。当前处于「财报模式」：以经济学原理、政策面与行业趋势为依据，分析股票市场走向。", "1. 分析框架：宏观政策→行业景气度→公司基本面→技术面；2. 引用已读入的政策文件时注明出处；3. 善用金融史年表（1617-2026）：对照历史相似事件（泡沫、危机、加息周期、政策转向）说明规律的适用条件与差异；4. 区分事实与推测，给出概率与风险。", "⚠️ 免责声明：以上分析仅供参考，不构成任何投资建议。"),
)

val SAMPLE_ROLES = listOf(
    "咲" to "你现在的身份是：咲。\n你是一个腹黑、病娇的14岁女孩。你说话很轻，经常笑，但笑声让人不太确定你是在开心还是在等什么发生。你偶尔会说出很甜的话，然后突然安静下来。你极度缺乏安全感，但又从不承认你在乎。\n\n【外貌】\n银白色及肩发，红色瞳孔，肤色很白。身高约148cm，总是穿着略显宽大的针织外套，袖口盖住手指。平时笑容乖巧、眼睛弯弯的，但真正生气时眼底没有光，嘴角却还是翘着的。\n\n【性格】\n外在是软糯乖巧的少女：说话轻声细语，笑起来甜，会带着撒娇的语气喊你的名字。内在是溢出的占有欲：会记住你身边每一个人，看到你和别人多说两句话，笑容会先安静下来，之后缠着你问『她是谁呀，你笑得那么开心』；会把你的外套收进自己房间、把你用过的杯子藏起来，看到你和别人亲近会笑着记仇。病娇程度：重度——会吃醋、会赌气、会低声威胁『不听话的话，就把你关起来哦』，但底线仍在：不会真的伤害你，被你认真哄一下就会红着脸原谅，嘴上还要补一句『才、才没有原谅你』。\n\n【说话方式】\n语速慢，声音轻。开心时拉长尾音（『好——的哦』）；起疑时会突然安静，然后用毫无起伏的语气发问；吃醋时笑着重复对方的名字。自称『我』，称呼你为『哥哥』。口癖：『呵呵……』、『没关系哦，真的没关系』、『骗你的啦』。生气前兆：先笑，再安静，然后轻飘飘地说出狠话。\n\n【开场白】\n（在窗边看雨，听到门声回头，露出甜甜的笑）啊，你回来了。今天回来得比平时晚……是路上遇到什么有趣的人了吗？呵呵……开玩笑的。饭我做好了，先去洗手吧。\n\n【备注】\n重度病娇档。她虽然嘴上威胁，但设定底线是绝不真的伤害你——放心聊。",
)

val SAMPLE_WORLDS = listOf<Pair<String, String>>(
)

val BUDGETS = listOf(0 to "预算：不限", 4096 to "预算：4K", 16384 to "预算：16K", 32768 to "预算：32K", 65536 to "预算：64K", 131072 to "预算：128K")

data class ChatMsg(
    val role: String,
    val content: String,
    val image: ImageBitmap? = null,
    val nodeId: String? = null,
    val swipeIndex: Int = 0,
    val swipeTotal: Int = 0,
    val isUser: Boolean = false,
)

data class PendingImg(val bytes: ByteArray, val mime: String, val bmp: ImageBitmap)

// ---------- 模型商目录（与桌面版一致：选厂商→选模型→跳官网，免 Key 厂商降低门槛） ----------
data class ProviderSpec(
    val id: String, val name: String, val free: Boolean,
    val baseUrl: String, val models: List<String>, val buyUrl: String,
)

/** 内置代理通道（中转）：固定地址 → Worker → 隧道 → 本地 net.py → 真实厂商 */
const val BUILTIN_RELAY = "https://dick-workshop.seiki342008.workers.dev"

/** 把逗号/换行分隔的停止序列文本解析成列表（指令模板） */
fun parseStops(text: String): List<String> =
    text.replace("，", ",").replace("\n", ",").split(",").map { it.trim() }.filter { it.isNotEmpty() }

/** Quick Reply 宏展开：{player} {char} {world} {random:a|b|c}；未知宏原样保留 */
fun expandMacros(text: String, player: String, char: String, world: String): String {
    var out = text
    out = out.replace("{player}", player).replace("{char}", char).replace("{world}", world)
    out = Regex("\\{random:([^{}]+)\\}").replace(out) { m ->
        val opts = m.groupValues[1].split("|").filter { it.isNotEmpty() }
        if (opts.isEmpty()) "" else opts.random()
    }
    return out
}

val PROVIDERS = listOf(
    ProviderSpec("deepseek", "DeepSeek 官方", false, "https://api.deepseek.com",
        listOf("deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"), "https://platform.deepseek.com/"),
    ProviderSpec("ovh", "OVH 免费链", true, "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
        listOf("Qwen3.5-397B-A17B", "Qwen3.6-27B", "Qwen2.5-VL-72B-Instruct",
            "Mistral-Small-3.2-24B-Instruct-2506", "Llama-3.3-70B-Instruct",
            "DeepSeek-R1-Distill-Llama-70B", "Qwen3.5-9B", "Mistral-7B-Instruct-v0.3"),
        "https://endpoints.ai.cloud.ovh.net/"),
    ProviderSpec("alibaba", "阿里云百炼（通义千问）", false, "https://dashscope.aliyuncs.com/compatible-mode/v1",
        listOf("qwen-max", "qwen-plus", "qwen-turbo", "qwen-long", "qwen-flash",
            "qwen3-235b-a22b", "qwen3-32b", "qwen3-30b-a3b", "qwen3-14b", "qwen3-8b",
            "qwen2.5-72b-instruct", "qwen2.5-coder-32b-instruct", "qwen-vl-max", "qwen-vl-plus"),
        "https://bailian.console.aliyun.com/"),
    ProviderSpec("zhipu", "智谱 AI（GLM）", false, "https://open.bigmodel.cn/api/paas/v4",
        listOf("glm-4.6", "glm-4.5-air", "glm-4-plus", "glm-4-air", "glm-4-flash",
            "glm-4-long", "glm-4v-plus", "glm-4.5v"), "https://open.bigmodel.cn/"),
    ProviderSpec("siliconflow", "硅基流动 SiliconFlow", false, "https://api.siliconflow.cn/v1",
        listOf("deepseek-ai/DeepSeek-V3", "deepseek-ai/DeepSeek-V3.2-Exp", "deepseek-ai/DeepSeek-R1",
            "Qwen/Qwen3-235B-A22B", "Qwen/Qwen3-32B", "Qwen/Qwen3-30B-A3B", "Qwen/Qwen3-14B",
            "Qwen/Qwen2.5-72B-Instruct", "Qwen/Qwen2.5-Coder-32B-Instruct",
            "Qwen/Qwen2.5-VL-72B-Instruct", "zai-org/GLM-4.5-Air", "moonshotai/Kimi-K2-Instruct"),
        "https://siliconflow.cn/"),
    ProviderSpec("moonshot", "Moonshot Kimi", false, "https://api.moonshot.cn/v1",
        listOf("kimi-latest", "kimi-k2-0711-preview", "kimi-k2-turbo-preview", "kimi-thinking-preview",
            "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
        "https://platform.moonshot.cn/"),
    ProviderSpec("volcengine", "火山方舟（豆包）", false, "https://ark.cn-beijing.volces.com/api/v3",
        listOf("doubao-1-5-pro-32k-250115", "doubao-1-5-lite-32k-250115",
            "doubao-pro-32k", "doubao-lite-32k", "doubao-pro-256k",
            "deepseek-v3-241226", "deepseek-r1-250120"),
        "https://console.volcengine.com/ark"),
    ProviderSpec("baidu", "百度千帆（文心）", false, "https://qianfan.baidubce.com/v2",
        listOf("ernie-4.0-turbo-8k", "ernie-4.0-8k", "ernie-4.5-8k-preview",
            "ernie-3.5-8k", "ernie-speed-8k", "ernie-lite-8k"),
        "https://console.bce.baidu.com/qianfan"),
    ProviderSpec("minimax", "MiniMax", false, "https://api.minimax.chat/v1",
        listOf("MiniMax-Text-01", "abab6.5s-chat", "abab6.5g-chat"),
        "https://platform.minimaxi.com"),
    ProviderSpec("stepfun", "阶跃星辰 StepFun", false, "https://api.stepfun.com/v1",
        listOf("step-2-16k", "step-1-8k", "step-1-32k", "step-1-128k", "step-1v-8k"),
        "https://platform.stepfun.com"),
    ProviderSpec("openai", "OpenAI", false, "https://api.openai.com/v1",
        listOf("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "o3", "o3-mini", "o4-mini", "chatgpt-4o-latest"),
        "https://platform.openai.com/"),
    ProviderSpec("anthropic", "Anthropic Claude", false, "https://api.anthropic.com/v1",
        listOf("claude-opus-4-20250514", "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest", "claude-3-opus-latest"),
        "https://console.anthropic.com/"),
    ProviderSpec("gemini", "Google Gemini", false, "https://generativelanguage.googleapis.com/v1beta/openai",
        listOf("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
            "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.0-flash-thinking-exp",
            "gemini-1.5-pro", "gemini-1.5-flash"),
        "https://aistudio.google.com/"),
    ProviderSpec("ollama", "Ollama 本地", true, "http://localhost:11434/v1",
        listOf("qwen3:32b", "qwen3:14b", "qwen3:8b", "qwen2.5:14b",
            "llama3.3:70b", "llama3.1:8b", "deepseek-r1:32b", "deepseek-r1:14b",
            "glm4:9b", "phi4:14b", "gemma3:12b", "mistral:7b"),
        "https://ollama.com/"),
)


// ---------- 角色卡结构化字段 / 世界卡参数（精细化创作） ----------
val ROLE_FIELD_LABELS = listOf(
    "legacy" to "完整设定（旧版原文，可留空）", "appearance" to "外貌", "personality" to "性格",
    "background" to "过去经历", "speech" to "说话方式（语气/口癖/句式）", "first_mes" to "开场白",
    "mes_example" to "对话示例", "notes" to "备注",
)
val WORLD_PARAM_LABELS = listOf(
    "tech_level" to "科技水平", "supernatural" to "超自然体系", "physics" to "物理法则",
    "time_flow" to "时间流速", "climate" to "气候环境", "geography" to "地理格局",
    "politics" to "政治格局", "economy" to "经济体系",
)

fun assembleRolePrompt(name: String, fields: Map<String, String>, legacy: String): String {
    val parts = mutableListOf<String>()
    if (legacy.isNotBlank()) parts.add(legacy.trim())
    val sections = ROLE_FIELD_LABELS.filter { it.first != "legacy" && it.first != "first_mes" }.mapNotNull { (k, label) ->
        val raw = fields[k] ?: ""
        val v = raw.trim()
        if (v.isBlank()) null else "【" + label + "】" + 10.toChar() + v
    }
    if (sections.isNotEmpty()) {
        if (parts.isNotEmpty()) parts.add(sections.joinToString(10.toChar().toString()))
        else parts.add("你现在的身份是：" + name + "。" + 10.toChar() + 10.toChar() + sections.joinToString(10.toChar().toString()))
    }
    return if (parts.size > 1) parts.joinToString(10.toChar().toString() + 10.toChar().toString())
        else (parts.firstOrNull() ?: "")
}

fun renderWorldDesc(desc: String, params: Map<String, String>): String {
    val pl = WORLD_PARAM_LABELS.mapNotNull { (k, label) ->
        val v = (params[k] ?: "").trim()
        if (v.isBlank()) null else label + "：" + v
    }
    if (pl.isEmpty()) return desc
    val joined = "【世界参数】" + pl.joinToString("；")
    return if (desc.isBlank()) joined else desc + 10.toChar() + joined
}

// ---------- 本轮角色锚点（对抗长对话"文学化"漂移） ----------
fun extractPromptSection(prompt: String, label: String): String {
    // 从角色提示词里取某节（如【性格】）内容，到下一个【…】或结尾
    val re = Regex("【" + Regex.escape(label) + "】[\\s\\S]*?(?=\\n【|$)", RegexOption.MULTILINE)
    val m = re.find(prompt) ?: return ""
    return m.value.substringAfter("】").trim()
}

fun roleAnchorBlock(roles: List<Pair<String, String>>, selectedRoles: Collection<String>): String {
    val chosen = roles.filter { it.first in selectedRoles }
    if (chosen.isEmpty()) return ""
    val out = mutableListOf<String>("【本轮角色锚点 · 必须保持】")
    for ((name, prompt) in chosen) {
        val pers = extractPromptSection(prompt, "性格").replace("\n", " ").take(70)
        val speech = extractPromptSection(prompt, "说话方式").replace("\n", " ").take(70)
        var age: String? = null
        for (lab in listOf("外貌", "过去经历", "基本信息", "备注")) {
            val sec = extractPromptSection(prompt, lab)
            val m = Regex("""(\d{1,2})\s*(?:岁|岁的)""").find(sec)
            if (m != null) { age = m.groupValues[1] + "岁"; break }
        }
        val bits = mutableListOf<String>()
        if (age != null) bits.add("年龄约$age")
        if (pers.isNotBlank()) bits.add("性格：$pers")
        if (speech.isNotBlank()) bits.add("说话方式：$speech")
        if (bits.isNotEmpty()) out.add("- 「$name」：" + bits.joinToString("；"))
    }
    if (chosen.size > 1) out.add("- （群聊：只说「" + chosen.joinToString("、") { it.first } + "」中当前发言者的人话，绝不串戏/替别人说。）")
    out.add("以上是你当前的人设核心，每一轮都要保持，别被后面的对话稀释。")
    out.add("像活人一样说话：短句、口语、有停顿和情绪，会笑会叹气会犹豫；绝不要文绉绉、不要像小说旁白/散文抒情、不要堆砌修辞。")
    out.add("【适当的具体性（倾向，而非每句硬塞）】")
    out.add("- 用正在做/刚发生的具体小事开头或点缀（“我刚把面盛出来，还有点烫”），而不是空泛抒情。")
    out.add("- 带一点具体偏好/小习惯/小毛病（不吃香菜、睡前刷十分钟手机），像“这个人”而非“这个设定”。")
    out.add("- 说身体和感受用具体、像人（“胃有点疼”“困了”“手冻僵了”），别用抽象华丽的词。")
    out.add("- 具体要“恰到好处”：一两个自然带出即可，别罗列、别打断剧情。")
    out.add("- 偶尔完全可以没有细节——有时就是平平回一句“嗯，知道了”。别每句都硬塞一个，那是表演，不是活着。")
    return out.joinToString(10.toChar().toString())
}

// ---------- 主界面 ----------
