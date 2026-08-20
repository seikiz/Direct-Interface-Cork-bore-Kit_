package com.dick.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.Button
import androidx.compose.material.MaterialTheme
import androidx.compose.material.OutlinedTextField
import androidx.compose.material.Surface
import androidx.compose.material.Text
import androidx.compose.material.darkColors
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import com.dick.core.AppPaths
import com.dick.core.ChatEngine
import com.dick.core.ChatTree
import com.dick.core.ConfigStore
import com.dick.core.SaveFile
import com.dick.core.TreeStore
import com.dick.core.Usage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.io.File

const val DEFAULT_SYSTEM_PROMPT = "你是一个友好的 AI 助手，用中文回答。"

@Composable
fun App() {
    val engine = remember { ChatEngine() }
    val configStore = remember { ConfigStore() }
    val tree = remember { ChatTree() }
    val messages = remember { mutableStateListOf<Pair<String, String>>() } // (角色, 内容)
    var apiKey by remember { mutableStateOf("") }
    var input by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var streaming by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    LaunchedEffect(Unit) {
        configStore.load()
        apiKey = configStore.data.apiKey
        engine.apiKey = apiKey
        engine.model = configStore.data.model
    }

    fun saveChat() {
        val file = File(AppPaths.savesDir(), "kotlin_chat.json")
        TreeStore.save(
            file,
            SaveFile(name = "Kotlin 测试", systemPrompt = DEFAULT_SYSTEM_PROMPT, historyTree = tree.toData()),
        )
    }

    fun send() {
        val text = input.trim()
        if (text.isEmpty() || busy) return
        busy = true
        input = ""
        streaming = ""
        messages.add("你" to text)
        val parentId = tree.addNode("user", text)
        val chain = tree.getCurrentChainNodes()
        engine.send(
            chain = chain,
            systemPrompt = DEFAULT_SYSTEM_PROMPT,
            onStream = { full ->
                scope.launch(Dispatchers.Main) { streaming = full }
            },
            onResponse = { reply, usage: Usage? ->
                scope.launch(Dispatchers.Main) {
                    tree.addNode("assistant", reply, parentId)
                    messages.add("AI" to reply)
                    streaming = ""
                    busy = false
                    saveChat()
                }
            },
            onError = { err ->
                scope.launch(Dispatchers.Main) {
                    messages.add("系统" to "❌ " + err)
                    streaming = ""
                    busy = false
                }
            },
        )
    }

    MaterialTheme(colors = darkColors()) {
        Column(Modifier.fillMaxSize().padding(12.dp).background(Color(0xFF0F1115))) {
            Row {
                OutlinedTextField(
                    value = apiKey,
                    onValueChange = { apiKey = it },
                    label = { Text("API Key") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                Spacer(Modifier.width(8.dp))
                Button(onClick = {
                    engine.apiKey = apiKey.trim()
                    configStore.data = configStore.data.copy(apiKey = apiKey.trim())
                    configStore.save()
                }) { Text("保存 Key") }
            }
            Spacer(Modifier.height(8.dp))
            LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
                items(messages) { (role, content) -> Bubble(role, content) }
                if (busy && streaming.isNotEmpty()) {
                    item { Bubble("AI", streaming + "…") }
                }
            }
            Spacer(Modifier.height(8.dp))
            Row {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    label = { Text("输入消息…") },
                    modifier = Modifier.weight(1f),
                    singleLine = false,
                    maxLines = 4,
                )
                Spacer(Modifier.width(8.dp))
                Button(onClick = ::send, enabled = !busy) { Text("发送") }
            }
        }
    }
}

@Composable
fun Bubble(role: String, content: String) {
    val nameColor = if (role == "你") Color(0xFF4ADE80) else Color(0xFF60A5FA)
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(role, color = nameColor, fontWeight = FontWeight.Bold, fontSize = 12.sp)
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = Color(0xFF1A1E26),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(content, Modifier.padding(8.dp), color = Color(0xFFE5E7EB))
        }
    }
}

fun main(args: Array<String>) {
    // 自检 / Python 存档兼容检查：gradle run --args="--selftest" 或 --args="saves/咲.json"
    if (args.isNotEmpty() && (args[0] == "--selftest" || args[0].endsWith(".json"))) {
        com.dick.tools.Check.main(args)
        return
    }
    application {
        Window(onCloseRequest = ::exitApplication, title = "Direct-Interface Cork-bore Kit (Kotlin)") {
            App()
        }
    }
}
