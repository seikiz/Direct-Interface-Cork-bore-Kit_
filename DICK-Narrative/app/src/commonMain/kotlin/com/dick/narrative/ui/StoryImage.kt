package com.dick.narrative.ui

import androidx.compose.foundation.Image
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.layout.ContentScale
import com.dick.narrative.platform.decodeImage
import com.dick.narrative.platform.joinPath
import com.dick.narrative.platform.readBytes

/** 图片缓存：同一路径只<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌解码一次，切换场景不闪。 */
object ImageCache {

    private val cache = HashMap<String, ImageBitmap?>()

    fun get(root: String, rel: String): ImageBitmap? {
        if (rel.isBlank()) return null
        val key = "$root\u0000$rel"
        if (cache.containsKey(key)) return cache[key]
        val bytes = readBytes(joinPath(root, rel)) ?: readBytes(rel)
        val bmp = bytes?.let { decodeImage(it) }
        cache[key] = bmp
        return bmp
    }

    fun clear() = cache.clear()
}

@Composable
fun StoryImage(
    root: String,
    rel: String,
    modifier: Modifier = Modifier,
    scale: ContentScale = ContentScale.Crop,
) {
    val bmp = remember(root, rel) { ImageCache.get(root, rel) }
    if (bmp != null) {
        Image(bitmap = bmp, contentDescription = null, modifier = modifier, contentScale = scale)
    }
}
