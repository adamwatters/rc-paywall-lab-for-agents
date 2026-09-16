import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// The ONE line to keep in sync with the RevenueCat SDK version your app ships
// (`python3 lab.py detect-sdk <app> --apply` sets it). Artifacts come from Maven Central.
val revenueCatVersion = "10.8.0"

android {
    namespace = "dev.paywalllab.harness"
    compileSdk = 36
    defaultConfig {
        applicationId = "dev.paywalllab.harness"
        minSdk = 24
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }
    buildFeatures { compose = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
kotlin { compilerOptions { jvmTarget.set(JvmTarget.JVM_17) } }

dependencies {
    implementation("com.revenuecat.purchases:purchases:$revenueCatVersion")
    implementation("com.revenuecat.purchases:purchases-ui:$revenueCatVersion")
    implementation(platform("androidx.compose:compose-bom:2024.09.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.5.1")
}
