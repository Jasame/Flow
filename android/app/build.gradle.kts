plugins {
    alias(libs.plugins.android.application)
}

val flowVersionName = providers.gradleProperty("flow.versionName").getOrElse("1.0.0")
// CI sets FLOW_VERSION_CODE (100 + the run number) so every beta from main installs over the one before
val flowVersionCode = (System.getenv("FLOW_VERSION_CODE") ?: providers.gradleProperty("flow.versionCode").getOrElse("1")).toInt()

android {
    namespace = "cn.flowlang.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "cn.flowlang.app"
        minSdk = 26
        targetSdk = 37
        versionCode = flowVersionCode
        versionName = flowVersionName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "FLOW_VERSION", "\"$flowVersionName\"")
        // FlowApp.build: the commit CI built (its first 7), "dev" on a computer — as the desktop app's
        buildConfigField("String", "FLOW_BUILD", "\"${(System.getenv("GITHUB_SHA") ?: "dev").take(7)}\"")
    }

    // Two apps that can sit side by side on one phone (as on iOS):
    //   beta: 「语流内测」 cn.flowlang.app.beta, opens https://flow.jasa.hk
    //   prod: 「语流」     cn.flowlang.app,      opens https://flowlang.cn
    // ("release" cannot be a flavor's name: it is the build type. assembleBetaRelease / assembleProdRelease.)
    flavorDimensions += "site"
    productFlavors {
        create("beta") {
            dimension = "site"
            applicationIdSuffix = ".beta"
            buildConfigField("String", "SITE", "\"https://flow.jasa.hk\"")
            resValue("string", "app_name", "语流内测")
        }
        create("prod") {
            dimension = "site"
            buildConfigField("String", "SITE", "\"https://flowlang.cn\"")
            resValue("string", "app_name", "语流")
        }
    }

    buildTypes {
        debug {
            // the auto-made debug key of this computer; only for the emulator and development
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Unsigned here on purpose: tools/release-apk.sh signs it with the owner's key, whose password stays in
            // the macOS keychain and never passes through Gradle.
        }
    }

    // the FlowApp wrapper the three apps share (docs/native-bridge.md §2): native/flowapp.js goes into the assets as it is
    sourceSets {
        getByName("main") {
            assets.srcDir(rootProject.file("../native"))
        }
    }

    buildFeatures {
        buildConfig = true
        resValues = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    lint {
        // a release build is not blocked by lint on CI; findings are read in build/reports/lint-results
        abortOnError = false
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity)
    implementation(libs.androidx.webkit)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.session)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit)
    testImplementation(libs.json)

    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.espresso.core)
    androidTestImplementation(libs.espresso.web)
    androidTestImplementation(libs.uiautomator)
}
