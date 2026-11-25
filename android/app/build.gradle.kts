import javax.inject.Inject
import org.gradle.process.ExecOperations

plugins {
    alias(libs.plugins.android.application)
}

val flowVersionName = providers.gradleProperty("flow.versionName").getOrElse("1.0.0")
// CI sets FLOW_VERSION_CODE (100 + the run number) so every beta from main installs over the one before
val flowVersionCode = (System.getenv("FLOW_VERSION_CODE") ?: providers.gradleProperty("flow.versionCode").getOrElse("1")).toInt()

// Two switches for the app stores (android/README.md 「应用商店」), both off until the filing is done:
//   FLOW_CHANNEL=store (or -Pflow.channel=store): 语流 without its own update check and without REQUEST_INSTALL_PACKAGES,
//     for the stores (they update the app themselves). Unset: the APK from flowlang.cn/download, which updates itself.
//   -Pflow.beian=<APP 备案号>: the number the app hands the page to show (FlowApp privacy.state); empty: nothing shown.
val flowChannel = System.getenv("FLOW_CHANNEL") ?: providers.gradleProperty("flow.channel").getOrElse("direct")
if (flowChannel != "direct" && flowChannel != "store") throw GradleException("FLOW_CHANNEL is direct or store, not $flowChannel")
val flowStore = flowChannel == "store"
val flowBeian = providers.gradleProperty("flow.beian").getOrElse("").trim()
if (flowBeian.contains('"') || flowBeian.contains('\\')) throw GradleException("flow.beian: the number only")

/**
 * The 《用户协议》 and 《隐私和数据》 the first start shows before anything is agreed to (privacy/Consent.kt): the site's two
 * chapters of flow/public/guide/guide.md, rendered by the site's own flow/user_guide.py (tools/legal_docs.py), into the
 * assets as legal/legal.json. Every build, so the app has the words of the site it is built with.
 */
abstract class LegalDocs : DefaultTask() {
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val sources: ConfigurableFileCollection
    @get:Internal abstract val script: RegularFileProperty
    @get:OutputDirectory abstract val outputDir: DirectoryProperty
    @get:Inject abstract val exec: ExecOperations

    @TaskAction
    fun make() {
        exec.exec { commandLine("python3", script.get().asFile.absolutePath, outputDir.get().asFile.absolutePath) }
    }
}

val legalDocs = tasks.register<LegalDocs>("legalDocs") {
    val repo = rootProject.projectDir.parentFile
    script.set(File(repo, "android/tools/legal_docs.py"))
    sources.from(File(repo, "android/tools/legal_docs.py"), File(repo, "flow/user_guide.py"), File(repo, "flow/public/guide/guide.md"))
    outputDir.set(layout.buildDirectory.dir("generated/legal"))
}

androidComponents {
    onVariants { it.sources.assets?.addGeneratedSourceDirectory(legalDocs, LegalDocs::outputDir) }
}

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
        buildConfigField("boolean", "STORE", "$flowStore")
        buildConfigField("String", "BEIAN", "\"$flowBeian\"")
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
            buildConfigField("boolean", "UPDATER", "false")  // 语流内测 comes from CI
            resValue("string", "app_name", "语流内测")
        }
        create("prod") {
            dimension = "site"
            buildConfigField("String", "SITE", "\"https://flowlang.cn\"")
            buildConfigField("boolean", "UPDATER", "${!flowStore}")  // update/Updater.kt: the APK from flowlang.cn only
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
        // the store build: src/prod's REQUEST_INSTALL_PACKAGES and installer receiver are left out
        if (flowStore) getByName("prod") { manifest.srcFile("src/store/AndroidManifest.xml") }
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
