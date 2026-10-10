import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// 版号的唯一真相是仓库根目录的 version.json（电脑端读同一份，见 app_version.py）。
// 这里在配置阶段把它读出来：versionCode 也用四段号算（1.0.0.1 → 1000001），
// 免得"改了三端里的一处"这种老毛病。别在下面写死字符串。
val versionJson: String = rootProject.file("../version.json").readText()
fun verStr(key: String): String =
    Regex("\"" + key + "\"\\s*:\\s*\"([^\"]+)\"").find(versionJson)!!.groupValues[1]
fun verInt(key: String): Int =
    Regex("\"" + key + "\"\\s*:\\s*(\\d+)").find(versionJson)!!.groupValues[1].toInt()
val dickVersionName: String = verStr("version")
val dickVersionCode: Int = verInt("code")

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.dick.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.dick.app"
        minSdk = 26
        targetSdk = 35
        versionCode = dickVersionCode
        versionName = dickVersionName
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.1")
}
// <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌