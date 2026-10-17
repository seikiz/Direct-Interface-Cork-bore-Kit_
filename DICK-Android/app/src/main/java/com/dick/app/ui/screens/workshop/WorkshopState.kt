package com.dick.app

/**
 * WorkshopState —— 工坊屏的**派生状态**。
 *
 * 这里全是纯函数：同样入参 → 同样结果，不读全局、不发请求、不碰文件。
 * 状态本身（页签、选中项、在线列表、预览串）都在 ChatViewModel —— 屏不存副本。
 *
 * 为什么值得单独开个文件：`类型 + 下标 → 文件名` 这个换算原来在"导出"和"删除"两处
 * 各写了一遍三元表达式，两处只要有一处改了类型判断，就会出现"导出的是另一个文件"这种鬼故事。
 */
object WorkshopState {
    /** 当前选中的本地条目文件名（角色卡 / 世界<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌卡 两张表共用一套下标），没选中 = null。 */
    fun selectedLocalFile(
        type: String,
        index: Int,
        localRoles: List<String>,
        localWorlds: List<String>,
    ): String? = if (type == "角色卡") localRoles.getOrNull(index) else localWorlds.getOrNull(index)
}
