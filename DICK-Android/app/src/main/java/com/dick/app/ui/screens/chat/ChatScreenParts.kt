package com.dick.app

// 从 ChatScreen.kt 拆<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌出：参数即全部输入，不捕获界面状态。

import android.content.Intent
import android.graphics.BitmapFactory
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.rememberDrawerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dick.core.AppConfig
import com.dick.core.AppEnv
import com.dick.core.ChatBridge
import com.dick.core.ChatEngine
import com.dick.core.ChatTree
import com.dick.core.EndingJudge
import com.dick.core.J
import com.dick.core.JsonS
import com.dick.core.Lanes
import com.dick.core.MessageNode
import com.dick.core.MechanicsEngine
import com.dick.core.TimeScale
import com.dick.core.RegexEngine
import com.dick.core.RoleSaves
import com.dick.core.SaveFile
import com.dick.core.SaveSlot
import com.dick.core.SpaceCore
import com.dick.core.StyleGuard
import com.dick.core.TextGuard
import com.dick.core.TreeData
import com.dick.core.TreeStore
import com.dick.core.WorldBook
import com.dick.core.WorldData
import com.dick.core.WorldEntry
import com.dick.core.WorldPacks
import com.dick.core.Workshop
import com.dick.plugins.DicePlugin
import com.dick.plugins.FinancialPlugin
import com.dick.plugins.GalgamePlugin
import com.dick.plugins.JpPlugin
import com.dick.plugins.LifeSpacePlugin
import com.dick.plugins.MathPlugin
import com.dick.plugins.MemoryPlugin
import com.dick.plugins.PluginRegistry
import com.dick.plugins.SearchPlugin
import com.dick.plugins.SwipePlugin
import com.dick.plugins.UiPlugin
import com.dick.plugins.UtauPlugin
import com.dick.plugins.VisionHelper
import java.io.File
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.random.Random

@Composable
internal fun BusyStatusLine(busy: Boolean, theme: ThemeSpec, accent: Color) {
    if (!busy) return
    var secs by remember(busy) { mutableStateOf(0) }
    LaunchedEffect(busy) {
        while (busy) {
            kotlinx.coroutines.delay(1000L)
            secs += 1
        }
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(6.dp)
                .background(accent, CircleShape)
        )
        Spacer(Modifier.width(6.dp))
        Text(
            text = if (secs > 0) "生成中 · ${secs}s" else "生成中",
            fontSize = 12.sp,
            color = theme.muted,
        )
    }
}

internal fun cropSquare(bytes: ByteArray): ByteArray {
    return try {
        val bmp = android.graphics.BitmapFactory.decodeByteArray(bytes, 0, bytes.size) ?: return bytes
        val side = minOf(bmp.width, bmp.height)
        val x = (bmp.width - side) / 2
        val y = (bmp.height - side) / 2
        val sq = android.graphics.Bitmap.createBitmap(bmp, x, y, side, side)
        val out = android.graphics.Bitmap.createScaledBitmap(sq, 256, 256, true)
        val bos = java.io.ByteArrayOutputStream()
        out.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, bos)
        bos.toByteArray()
    } catch (_: Exception) {
        bytes
    }
}

// 文件/时间小工具（纯参数，不读界面状态）

internal fun safeFileToken(name: String): String =
    name.replace('\\', '_').replace('/', '_').replace(':', '_').replace('*', '_')
        .replace('?', '_').replace('<', '_').replace('>', '_').replace('|', '_')

internal fun treeFileForRole(role: String): File {
    val safe = safeFileToken(role)
    return File(File(AppEnv.savesDir(), ".tree").apply { mkdirs() }, "_tree_" + safe + ".json")
}

internal fun stateFileForRole(role: String): File {
    val safe = safeFileToken(role)
    return File(AppEnv.mechStateDir(), "_mech_" + safe + ".json")
}

internal fun utcNowIso(): String {
    val fmt = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", java.util.Locale.US)
    fmt.timeZone = java.util.TimeZone.getTimeZone("UTC")
    return fmt.format(java.util.Date())
}

// 解耦：界面状态当参数传进来的小函数

internal fun syncCardId(selectedRoles: Set<String>): String = if (selectedRoles.isNotEmpty()) selectedRoles.first() else "default"

internal fun applyRegex(text: String, scope: String, selectedRoles: Set<String>, advancedByRole: Map<String, J.Obj>, persona: String): String {
    val roleRules = advancedByRole[selectedRoles.firstOrNull()]?.fields?.get("regex_rules") as? J.Arr
    val roleList = roleRules?.items?.mapNotNull { it as? J.Obj } ?: emptyList()
    val playerRules = try {
        ((JsonS.parse(persona) as? J.Obj)?.fields?.get("advanced") as? J.Obj)?.fields?.get("regex_rules") as? J.Arr
    } catch (_: Exception) {
        null
    }
    val playerList = playerRules?.items?.mapNotNull { it as? J.Obj } ?: emptyList()
    return RegexEngine.apply(text, scope, playerList + roleList, RegexEngine.loadGlobal())
}
