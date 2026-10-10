import org.jetbrains.compose.desktop.application.dsl.TargetFormat
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("com.android.application")
    id("org.jetbrains.compose")
    id("org.jetbrains.kotlin.plugin.compose")
}

kotlin {
    androidTarget {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
    }
    jvm("desktop") {
        compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
    }

    sourceSets {
        val commonMain by getting {
            dependencies {
                implementation(compose.runtime)
                implementation(compose.foundation)
                implementation(compose.material3)
                implementation(compose.ui)
                implementation(compose.components.resources)
                implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
            }
        }
        val commonTest by getting {
            dependencies { implementation(kotlin("test")) }
        }
        val androidMain by getting {
            dependencies {
                implementation("androidx.activity:activity-compose:1.9.3")
            }
        }
        val desktopMain by getting {
            dependencies { implementation(compose.desktop.currentOs) }
        }
    }
}

android {
    namespace = "com.dick.narrative"
    compileSdk = 35
    defaultConfig {
        applicationId = "com.dick.narrative"
        minSdk = 26
        targetSdk = 35
        // 版号唯一真相 = 仓库根目录 version.json（与电脑端/安卓端同一份）。
        // 播放器发的是同一个产品的一部分，版号跟着走，别在这里写死。
        val vJson = rootProject.file("../../version.json").readText()
        fun vStr(k: String) = Regex("\"" + k + "\"\\s*:\\s*\"([^\"]+)\"").find(vJson)!!.groupValues[1]
        fun vInt(k: String) = Regex("\"" + k + "\"\\s*:\\s*(\\d+)").find(vJson)!!.groupValues[1].toInt()
        versionCode = vInt("code")
        versionName = vStr("version")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

compose.desktop {
    application {
        mainClass = "com.dick.narrative.MainKt"
        nativeDistributions {
            // AppImage = 免安装的绿色版：一个文件夹，里面有 DI<seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌CK-Narrative.exe 和自带的 Java 运行时。
            // 想要「安装程序」（TargetFormat.Exe / Msi）需要先装 WiX Toolset v3。
            targetFormats(TargetFormat.AppImage)
            packageName = "DICK-Narrative"
            packageVersion = "1.0.0"
            description = "DICK 叙事引擎 · 原生播放器"
            vendor = "DICK"
            windows {
                menu = true
                shortcut = true
                // 生成的 exe 图标（有 icon.ico 时才生效，没有就用默认）
                iconFile.set(project.file("icon.ico").takeIf { it.exists() })
            }
        }
    }
}
