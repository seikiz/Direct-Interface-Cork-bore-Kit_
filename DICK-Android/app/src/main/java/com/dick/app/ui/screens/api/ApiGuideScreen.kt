package com.dick.app

import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * 📖 API 教程（安卓侧）
 *
 * 和网页端 `web/screens/api_guide.html` + `web/js/screens/api_guide.js` **同一份内容**：
 * 同一批 `lang/strings.json` 键（guide_* / apiWiz* / apiGuideTitle），同一张服务商事实表。
 * 两边都不许自己写死一句用户看得见的文案 —— 漏翻就是漏翻，切到日文立刻能看出来。
 *
 * 数据为什么写死在代码里而不是读 json：服务商事实（注册地址 / Base URL / 模型名）本身
 * 就是**语言无关**的常量，塞进三语文案表只会得到三条一模一样的串；所以它们还是走
 * `lang/strings.json`（`guide_pN_url/base/model` 三语同串，校验器允许"无汉字的同串"），
 * 由本文件按行 order 引用 —— 引用的都是**字面量键**，`tools/gen_i18n.py` 扫得到。
 *
 * 硬边界（见 web/UI_ARCHITECTURE.md 的「安卓侧」）：
 *   · 只吃参数/只读主题令牌，不读 ChatViewModel 的业务字段；
 *   · 颜色只来自 `LocalDickPalette`，本文件不出现任何 Color(0x…)；
 *   · 文案一律走 I18n.t(key, 中文原串)（键在 lang/strings.json 里）。
 */
data class ApiGuideProvider(
    val name: String,
    val url: String,
    val base: String,
    val model: String,
    val buy: String,
    val where: String,
)

/** 教程里的 6 家服务商（顺序 = 网页端指南里的顺序，两端必须一致）。 */
fun apiGuideProviders(): List<ApiGuideProvider> = listOf(
    ApiGuideProvider(
        I18n.t("guide_p1_name", "DeepSeek 官方"),
        I18n.t("guide_p1_url", "https://platform.deepseek.com/"),
        I18n.t("guide_p1_base", "https://api.deepseek.com"),
        I18n.t("guide_p1_model", "deepseek-flash"),
        I18n.t("guide_p1_buy", "要充值（按量计费）。新账号通常没有赠额，先充一点再试。"),
        I18n.t("guide_p1_where", "控制台 → API keys → 创建，形如 sk-…"),
    ),
    ApiGuideProvider(
        I18n.t("guide_p2_name", "智谱 GLM"),
        I18n.t("guide_p2_url", "https://open.bigmodel.cn/"),
        I18n.t("guide_p2_base", "https://open.bigmodel.cn/api/paas/v4"),
        I18n.t("guide_p2_model", "glm-4.6"),
        I18n.t("guide_p2_buy", "要充值（含体验额度，用完后按量计费）。"),
        I18n.t("guide_p2_where", "控制台 → API Keys（个人中心）→ 复制。"),
    ),
    ApiGuideProvider(
        I18n.t("guide_p3_name", "硅基流动 SiliconFlow"),
        I18n.t("guide_p3_url", "https://cloud.siliconflow.cn/"),
        I18n.t("guide_p3_base", "https://api.siliconflow.cn/v1"),
        I18n.t("guide_p3_model", "deepseek-ai/DeepSeek-V3"),
        I18n.t("guide_p3_buy", "注册送一点额度，之后要充值。"),
        I18n.t("guide_p3_where", "控制台 → API 密钥 → 新建。"),
    ),
    ApiGuideProvider(
        I18n.t("guide_p4_name", "OpenRouter"),
        I18n.t("guide_p4_url", "https://openrouter.ai/"),
        I18n.t("guide_p4_base", "https://openrouter.ai/api/v1"),
        I18n.t("guide_p4_model", "openrouter/auto"),
        I18n.t("guide_p4_buy", "部分模型免费，付费模型要充值。"),
        I18n.t("guide_p4_where", "右上头像 → Keys → Create Key。"),
    ),
    ApiGuideProvider(
        I18n.t("guide_p5_name", "Pollinations（免 Key）"),
        I18n.t("guide_p5_url", "https://pollinations.ai/"),
        I18n.t("guide_p5_base", "https://text.pollinations.ai/openai"),
        I18n.t("guide_p5_model", "openai"),
        I18n.t("guide_p5_buy", "免费，不用充值（高峰期限流）。"),
        I18n.t("guide_p5_where", "不需要 Key，留空即可。"),
    ),
    ApiGuideProvider(
        I18n.t("guide_p6_name", "本地 Ollama / LM Studio"),
        I18n.t("guide_p6_url", "https://ollama.com/"),
        I18n.t("guide_p6_base", "http://127.0.0.1:11434/v1"),
        I18n.t("guide_p6_model", "qwen2.5:7b"),
        I18n.t("guide_p6_buy", "完全免费，只吃自己电脑的算力。"),
        I18n.t("guide_p6_where", "不需要 Key；先在本机启动 Ollama（或 LM Studio 开 OpenAI 兼容端口）。"),
    ),
)

@Composable
private fun SecTitle(s: String) {
    val pal = LocalDickPalette.current
    Text(s, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = pal.text,
        modifier = Modifier.padding(top = 10.dp, bottom = 4.dp))
}

@Composable
private fun Body(s: String) {
    val pal = LocalDickPalette.current
    Text(s, fontSize = 12.sp, color = pal.textSub, modifier = Modifier.padding(bottom = 2.dp))
}

@Composable
private fun KV(k: String, v: String) {
    val pal = LocalDickPalette.current
    Row(Modifier.fillMaxWidth().padding(vertical = 1.dp)) {
        Text(k + "：", fontSize = 11.sp, color = pal.textSub)
        Text(v, fontSize = 11.sp, color = pal.text)
    }
}

/** 教程面板本体（只读，挂在 OverlayHost 里）。 */
@Composable
fun ApiGuideDialog(vm: ChatViewModel) {
    if (!vm.showApiGuide.value) {
        return
    }
    val pal = LocalDickPalette.current
    val uri = LocalUriHandler.current
    DickDialog(
        onDismissRequest = { vm.showApiGuide.value = false },
        title = { IconText(I18n.t("apiGuideTitle", "API 教程")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                // ① 怎<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌么选模型
                SecTitle(I18n.t("guidePickTitle", "怎么选模型"))
                Body(I18n.t("guidePickChat", "日常聊天 / 角色扮演 → deepseek-flash（推荐，默认）"))
                Body(I18n.t("guidePickReason", "长文推理 / 复杂代码 / Agent 任务 → deepseek-v4-pro（可选，按量更贵，别当默认；性价比一般，只在 flash 顶不住时再换）"))
                Body(I18n.t("guidePickFree", "完全不想花钱 → 免费链（Pollinations / 免 Key 模型）"))

                // ② 服务商清单
                SecTitle(I18n.t("apiGuideTitle", "API 教程"))
                apiGuideProviders().forEach { p ->
                    Text(p.name, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                        color = pal.text, modifier = Modifier.padding(top = 6.dp))
                    KV(I18n.t("guideLabelUrl", "注册地址"), p.url)
                    KV(I18n.t("guideLabelBuy", "要不要充值"), p.buy)
                    KV(I18n.t("apiWizWhere", "去哪里拿 Key"), p.where)
                    KV(I18n.t("st_base_url", "Base URL"), p.base)
                    KV(I18n.t("st_model", "模型"), p.model)
                    DickActionButton(
                        label = p.url,
                        variant = DickButtonVariant.Plain,
                        fontSize = 11.sp,
                        onClick = { try { uri.openUri(p.url) } catch (_: Exception) {} },
                    )
                }

                // ③ 三步配置
                SecTitle(I18n.t("apiWizTitle", "三步配置 API"))
                Body(I18n.t("guideStep1", "拿 Key：按上表去对应官网注册，把 Key 复制下来。"))
                // 句子中间的 emoji 一律去掉（用户口径：图标走 Material Symbols 字体，
                // 句子中间塞彩色 emoji 会露成旧版观感）。引用按钮直接说名字。
                Body(I18n.t("guideStep2", "粘贴：设置 →「API 配置」→ 选模型商 → 把 Key 粘进输入框，Base URL 会自动填好。"))
                Body(I18n.t("guideStep3", "点「测试并保存」：真实请求一次 /models，通了才写进 config.json；不通会告诉你下一步。"))

                // ④ 常见错误对照表
                SecTitle(I18n.t("guideErrTitle", "常见错误对照表"))
                listOf(
                    I18n.t("guideErr1S", "401 / invalid api key：Key 不对") to I18n.t("guideErr1F", "回设置整条重贴一遍（前后别带空格），确认没把 Base URL 粘进 Key 框。"),
                    I18n.t("guideErr2S", "余额不足 / insufficient balance") to I18n.t("guideErr2F", "去官网充值；只想先试试就先切免费链。"),
                    I18n.t("guideErr3S", "模型名不对 / model not found") to I18n.t("guideErr3F", "照上表「模型名示例」原样填（大小写和斜杠都要一致）；带 org/ 前缀的别漏。"),
                    I18n.t("guideErr4S", "超时 / 连接被重置（被墙）") to I18n.t("guideErr4F", "填代理（如 http://127.0.0.1:7890）再测；或换 Pollinations / 本地 Ollama。"),
                    I18n.t("guideErr5S", "429 / rate limit：限流") to I18n.t("guideErr5F", "等几十秒再试；换了服务商仍 429 就是额度用完了（免费链最常见）。"),
                ).forEach { (s, f) ->
                    Text(s, fontSize = 12.sp, color = pal.danger)
                    Body(f)
                }

                // ⑤ 免费链 / 省钱 / 官方搜索 / 免责
                SecTitle(I18n.t("guideFreeTitle", "免费链：不填 Key 也能聊"))
                Body(I18n.t("guideFreeBody", "Pollinations 与免 Key 模型链不需要任何 Key，装上就能说话；代价是高峰期慢、质量不如付费模型，敏感内容也更容易被拒。想稳定就配一个 Key。"))
                SecTitle(I18n.t("guideTipTitle", "省钱小贴士"))
                Body(I18n.t("guideTipBody", "DeepSeek 自 2026-08-13 起是峰谷定价：闲时价格是高峰时段的一半。批量跑、睡前挂着跑长任务更划算。"))
                SecTitle(I18n.t("guideSearchTitle", "想用官方搜索"))
                Body(I18n.t("guideSearchBody", "DeepSeek 在 2026-10-17 开放了自研搜索 API（文档见 /zh-cn/guides/search）。插件里的「联网搜索 / 深搜」可以把它当后端之一，填同一个 Key 即可；原来的免 Key 搜索照旧保留，不填也能用。"))
                Spacer(Modifier.height(8.dp))
                Body(I18n.t("guideFooter", "模型名与价格会变，以官方控制台与更新日志为准：https://api-docs.deepseek.com/zh-cn/updates/"))
            }
        },
        confirmButton = {
            DickActionButton(label = I18n.t("btn_cancel", "关闭"),
                variant = DickButtonVariant.Plain,
                onClick = { vm.showApiGuide.value = false })
        },
    )
}
