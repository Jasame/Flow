package cn.flowlang.app

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.provider.CalendarContract
import android.provider.Settings
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.RenderProcessGoneDetail
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebStorage
import android.webkit.WebView
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.SystemBarStyle
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.isVisible
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.webkit.WebResourceErrorCompat
import androidx.webkit.WebSettingsCompat
import androidx.webkit.WebViewClientCompat
import androidx.webkit.WebViewFeature
import cn.flowlang.app.audio.FlowAudio
import cn.flowlang.app.bridge.Bridge
import cn.flowlang.app.net.Http
import cn.flowlang.app.notify.Reminders
import cn.flowlang.app.privacy.Consent
import cn.flowlang.app.privacy.ConsentUi
import cn.flowlang.app.rec.Recorder
import cn.flowlang.app.speech.Speech
import cn.flowlang.app.update.Updater
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import java.io.ByteArrayInputStream
import java.time.Duration
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/**
 * The app: the site in a WebView (so every change to the site is in the app at once), with the native parts behind
 * window.FlowApp (Bridge). Signed in as on the site (the WebView's own cookies, kept on the phone); the back button
 * goes back in the page; other sites open in the phone's browser; the page sits between the status bar, the cutout,
 * the navigation bar and the keyboard, in the page's own colours. On the first start nothing is opened until the learner
 * answers the question about the 《用户协议》 and 《隐私和数据》 (privacy/Consent.kt); 不同意 opens the site in 基本模式.
 */
@OptIn(UnstableApi::class)
class MainActivity : ComponentActivity() {
    companion object {
        /** A path on the site to open ("/#/review" from a reminder). */
        const val EXTRA_PATH = "cn.flowlang.app.PATH"
    }

    private lateinit var root: FrameLayout
    lateinit var web: WebView
        private set
    private lateinit var errorView: View
    private lateinit var basicBar: View
    private lateinit var basicAgree: TextView
    private val bridge by lazy { Bridge(this) }
    private val prefs by lazy { getSharedPreferences("flow-app", MODE_PRIVATE) }
    private val consentUi by lazy { ConsentUi(this) }

    /** The answer to the first start's question on this phone (Consent); read on the WebView's request thread too. */
    @Volatile var privacy = Consent.State.ASK
        private set
    private var opened = false           // the page is loaded: the question has an answer
    private var asking = false           // one of the questions is on screen
    private var waitingPath: Intent? = null  // a reminder tapped while the question was open: its page, once answered
    private var clearHistory = false     // after 撤回同意: 返回 never goes back to the page from before

    // ---------------------------------------------------------------- set-up

    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        bars()
        // the test switch (docs/native-bridge.md §9): `--ez flow.mute true` on a debug or beta build; the UI tests set it themselves
        if (intent?.getBooleanExtra("flow.mute", false) == true && (BuildConfig.DEBUG || BuildConfig.FLAVOR == "beta")) Mute.on = true
        // the update tests: `--es flow.update_url http://127.0.0.1:18765/latest.json` on a debug build, after
        // `adb reverse tcp:18765 tcp:18765` (update/Updater.kt)
        if (BuildConfig.UPDATER && BuildConfig.DEBUG) intent?.getStringExtra("flow.update_url")?.let { Updater.testUrl = it }
        FlowAudio.init(this)
        root = FrameLayout(this)
        root.setBackgroundColor(getColor(R.color.flow_bg))
        web = WebView(this)
        val page = FrameLayout(this)
        page.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        errorView = errorView()
        page.addView(errorView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        errorView.isVisible = false
        basicBar = basicBar()
        basicBar.isVisible = false
        root.addView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(basicBar, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
            addView(page, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        setContentView(root)
        // the page between the bars, the cutout and the keyboard (edge to edge, as Android 15+ draws every app)
        ViewCompat.setOnApplyWindowInsetsListener(root) { v, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
            v.setPadding(bars.left, bars.top, bars.right, maxOf(bars.bottom, ime.bottom))
            WindowInsetsCompat.CONSUMED
        }
        setUpWeb()
        bridge.install(web)
        onBackPressedDispatcher.addCallback(this, back)
        privacy = Consent.state(this)
        if (privacy == Consent.State.ASK) firstQuestion(saved) else open(saved)
    }

    // ---------------------------------------------------------------- the first start's question (privacy/Consent.kt)

    /** The first start, a build with a newer 用户协议 / 隐私和数据, or after 撤回同意: nothing is opened before the answer. */
    private fun firstQuestion(saved: Bundle?, home: Boolean = false) {
        asking = true
        lifecycleScope.launch {
            val yes = try { consentUi.ask() } finally { asking = false }
            if (yes) agreed() else basic()
            open(saved, home)
        }
    }

    /** The page, once there is an answer (同意, or 基本模式). */
    private fun open(saved: Bundle?, home: Boolean = false) {
        opened = true
        showBasicBar()
        Speech.init(this)  // the phone's voice engine, once there is a page to speak for
        val i = waitingPath ?: intent
        waitingPath = null
        if (saved == null || web.restoreState(saved) == null) web.loadUrl(if (home) Site.origin + "/" else startUrl(i))
        // already in front (the question was answered): what waits for an agreement starts now; else onStart does it
        if (privacy == Consent.State.AGREED && lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) whenAgreed()
    }

    private fun agreed() {
        Consent.agree(this)
        privacy = Consent.State.AGREED
        showBasicBar()
    }

    private fun basic() {
        Consent.decline(this)
        privacy = Consent.State.BASIC
        forgetHere()
    }

    /** Only once agreed: the reminders as the site has them, and (语流 from flowlang.cn) a newer version. */
    private fun whenAgreed() {
        Reminders.refreshLater(this)
        if (BuildConfig.UPDATER) Updater.onStart(this)  // at start, then once a day
    }

    /**
     * 基本模式 asks again when a feature needs the agreement ([why]: signing in or up, the microphone, the app's reminders), or
     * when the learner taps 「同意」 on its line (no why). → agreed now. Never asks two questions at once.
     */
    suspend fun consented(why: Int? = null): Boolean {
        if (privacy == Consent.State.AGREED) return true
        if (asking || privacy != Consent.State.BASIC) return false
        asking = true
        val yes = try { consentUi.ask(why?.let { getString(it) }, first = false) } finally { asking = false }
        if (yes) { agreed(); whenAgreed() }
        return yes
    }

    /**
     * 撤回同意 (privacy.withdraw, from the page's 「我的 → 设置」): after its check, this phone forgets the answer and the
     * learner's things here (forgetHere), and the first start's question comes back. The account's own consents stay the
     * site's (「我的 → 账号」). → true once withdrawn (the page that asked is gone by then).
     */
    suspend fun withdraw(): Boolean {
        if (privacy != Consent.State.AGREED || asking) return false
        asking = true
        val yes = try { consentUi.withdrawChosen() } finally { asking = false }
        if (!yes) return false
        FlowAudio.stop()
        if (Recorder.busy) Recorder.cancel()
        Consent.withdraw(this)
        privacy = Consent.State.ASK
        opened = false
        showBasicBar()
        lifecycleScope.launch {
            web.loadUrl("about:blank")
            forgetHere()
            clearHistory = true
            firstQuestion(null, home = true)
        }
        return true
    }

    /** 不同意 or 撤回同意: signed out on this phone, the page's own storage and cache emptied, no reminders, no reading places. */
    private fun forgetHere() {
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
        WebStorage.getInstance().deleteAllData()
        web.clearCache(true)
        Reminders.forget(this)
        getSharedPreferences("flow-progress", MODE_PRIVATE).edit().clear().apply()  // audio/ProgressStore.kt
    }

    private fun dip(v: Int) = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt()

    /** 基本模式's line over the page: what it means, and 「同意」 for everything. */
    private fun basicBar(): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dip(16), dip(4), dip(6), dip(4))
        }
        row.addView(TextView(this).apply { text = getString(R.string.basic_bar); textSize = 13f; setTextColor(getColor(R.color.flow_text)) },
            LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        basicAgree = TextView(this).apply {
            text = getString(R.string.basic_bar_agree)
            textSize = 14f
            setTypeface(typeface, Typeface.BOLD)
            setPadding(dip(14), dip(10), dip(10), dip(10))
            setOnClickListener { lifecycleScope.launch { consented() } }
        }
        row.addView(basicAgree)
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(getColor(R.color.flow_surface))
            addView(row)
            addView(View(this@MainActivity).apply { setBackgroundColor(getColor(R.color.flow_line)) },
                LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, maxOf(1, dip(1) / 2)))
        }
    }

    private fun showBasicBar() {
        basicBar.isVisible = opened && privacy == Consent.State.BASIC
        if (basicBar.isVisible) basicAgree.setTextColor(Accent.color(this))
    }

    /** Transparent bars over the page's own colour; dark icons on the light page, light ones on the dark page. */
    private fun bars() {
        enableEdgeToEdge(SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT), SystemBarStyle.auto(Color.TRANSPARENT, Color.TRANSPARENT))
        if (Build.VERSION.SDK_INT >= 29) window.isNavigationBarContrastEnforced = false
    }

    private fun startUrl(i: Intent?): String =
        i?.getStringExtra(EXTRA_PATH)?.takeIf { it.startsWith("/") && !it.startsWith("//") }?.let { Site.abs(it) } ?: (Site.origin + "/")

    @SuppressLint("SetJavaScriptEnabled")
    private fun setUpWeb() {
        val s = web.settings
        s.javaScriptEnabled = true
        s.domStorageEnabled = true
        s.mediaPlaybackRequiresUserGesture = false  // the next sentence may start by itself (the page unlocks audio in a tap anyway)
        s.allowFileAccess = false
        s.allowContentAccess = false
        s.setSupportMultipleWindows(false)
        s.javaScriptCanOpenWindowsAutomatically = false
        s.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
        s.setGeolocationEnabled(false)
        s.userAgentString = s.userAgentString + " FlowAndroid/" + BuildConfig.FLOW_VERSION
        Site.userAgent = s.userAgentString
        if (WebViewFeature.isFeatureSupported(WebViewFeature.ALGORITHMIC_DARKENING)) WebSettingsCompat.setAlgorithmicDarkeningAllowed(s, false)
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)
        web.setBackgroundColor(getColor(R.color.flow_bg))  // no white flash before the page paints
        web.webViewClient = client
        web.webChromeClient = chrome
        web.setDownloadListener { url, _, _, _, _ -> openOutside(Uri.parse(url)) }  // the guide's PDF: the browser saves it
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
    }

    // ---------------------------------------------------------------- the WebView's callbacks

    private val client = object : WebViewClientCompat() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            val u = request.url
            if (Site.isOwn(u)) {
                if (u.path == "/api/next/vocab/reminder.ics") { reminderLink(u); return true }
                return false
            }
            when (u.scheme) { "http", "https", "mailto", "tel", "sms" -> openOutside(u) }
            return true  // anything else (intent:, file:, …): nothing
        }

        override fun onPageStarted(view: WebView, url: String?, favicon: android.graphics.Bitmap?) { errorView.isVisible = false }

        override fun onPageFinished(view: WebView, url: String?) {
            if (clearHistory && Site.isOwn(url)) { clearHistory = false; view.clearHistory() }
        }

        // 基本模式: signing in or up asks first (Consent.SIGN_IN). The page's form gets a 403 that says why (its `error`),
        // and the question comes up; once agreed, the learner taps again.
        override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
            if (privacy == Consent.State.AGREED || request.method != "POST" || !Site.isOwn(request.url) || !Consent.signIn(request.url.path)) return null
            runOnUiThread { lifecycleScope.launch { consented(R.string.consent_why_signin) } }
            return WebResourceResponse("application/json", "utf-8", 403, "Forbidden", mapOf("Cache-Control" to "no-store"),
                ByteArrayInputStream(Consent.SIGN_IN_ANSWER.toByteArray()))
        }

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceErrorCompat) {
            if (request.isForMainFrame) errorView.isVisible = true
        }

        override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
            // the page's process was ended by the system (memory): start over with a fresh WebView
            (web.parent as? ViewGroup)?.removeView(web)
            web.destroy()
            recreate()
            return true
        }
    }

    private var files: ValueCallback<Array<Uri>>? = null
    private val pickFiles = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { r ->
        val d = r.data
        val uris = when {
            r.resultCode != RESULT_OK || d == null -> null
            d.clipData != null -> Array(d.clipData!!.itemCount) { d.clipData!!.getItemAt(it).uri }
            d.data != null -> arrayOf(d.data!!)
            else -> null
        }
        files?.onReceiveValue(uris)
        files = null
    }

    private val chrome = object : WebChromeClient() {
        // the page's own recorder (getUserMedia), for pages not on the bridge: allowed for this site once the phone allows the app
        override fun onPermissionRequest(request: PermissionRequest) {
            if (!Site.isOwn(request.origin) || !request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) { request.deny(); return }
            lifecycleScope.launch {
                if (consented(R.string.consent_why_mic) && askMic()) request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else request.deny()
            }
        }

        // 反馈's 添加截图
        override fun onShowFileChooser(view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams): Boolean {
            files?.onReceiveValue(null)
            files = callback
            return try {
                val i = params.createIntent()
                if (params.mode == FileChooserParams.MODE_OPEN_MULTIPLE) i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                pickFiles.launch(i); true
            } catch (e: ActivityNotFoundException) { files = null; false }
        }
    }

    // back: a sheet closes first, then the page before, then the app goes to the background (a text keeps playing)
    private val back = object : OnBackPressedCallback(true) {
        override fun handleOnBackPressed() {
            web.evaluateJavascript("(function(){try{return !!(window.FlowApp&&FlowApp._back&&FlowApp._back())}catch(e){return false}})()") { r ->
                if (r == "true") return@evaluateJavascript
                if (web.canGoBack()) web.goBack() else moveTaskToBack(true)
            }
        }
    }

    // ---------------------------------------------------------------- lifecycle

    override fun onStart() {
        super.onStart()
        web.onResume()
        FlowAudio.visible = true
        // opening and coming back: the reminders as the site has them now; 语流: a newer version on flowlang.cn/download
        if (opened && privacy == Consent.State.AGREED) whenAgreed()
    }

    override fun onStop() {
        FlowAudio.visible = false
        if (privacy == Consent.State.AGREED) Reminders.refreshLater(this)  // going to the background too: a day done is taken off
        if (Recorder.busy) Recorder.cut()  // only an app in front may use the microphone
        CookieManager.getInstance().flush()
        web.onPause()
        super.onStop()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(EXTRA_PATH)?.let { if (opened) web.loadUrl(startUrl(intent)) else waitingPath = intent }
    }

    override fun onSaveInstanceState(out: Bundle) {
        super.onSaveInstanceState(out)
        if (opened) web.saveState(out)
    }

    override fun onConfigurationChanged(c: Configuration) {
        super.onConfigurationChanged(c)
        // dark / light switched with the app open: the bars and the space around the page follow at once
        root.setBackgroundColor(getColor(R.color.flow_bg))
        web.setBackgroundColor(getColor(R.color.flow_bg))
        bars()
        (errorView as? LinearLayout)?.let { recolorError(it) }
        // 基本模式's line in the new colours
        (basicBar.parent as? ViewGroup)?.let { p ->
            val k = p.indexOfChild(basicBar)
            p.removeView(basicBar)
            basicBar = basicBar()
            p.addView(basicBar, k, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        showBasicBar()
    }

    override fun onDestroy() {
        // a text may go on playing in the service: it just stops telling this page
        FlowAudio.sink = null
        Recorder.sink = null
        Speech.voicesChanged = null
        if (::web.isInitialized && web.parent != null) { (web.parent as? ViewGroup)?.removeView(web); web.destroy() }
        super.onDestroy()
    }

    // ---------------------------------------------------------------- permissions (asked here, used by the bridge)

    private var waiting: CompletableDeferred<Boolean>? = null
    private val askPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> waiting?.complete(ok); waiting = null }

    private fun granted(p: String) = ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED
    private fun asked(p: String) = prefs.getBoolean("asked:$p", false)

    /**
     * The system dialog, with what the permission is for on top of the page while it is open (purpose). False right away
     * (no dialog shown) means refused for good: then the settings are offered.
     */
    private suspend fun ask(p: String, offTitle: Int, offBody: Int, settings: () -> Unit): Boolean {
        if (granted(p)) return true
        waiting?.complete(false)
        val d = CompletableDeferred<Boolean>()
        waiting = d
        val dialog = !(asked(p) && !shouldShowRequestPermissionRationale(p))  // else refused for good: the phone will not ask
        prefs.edit().putBoolean("asked:$p", true).apply()
        val t0 = SystemClock.elapsedRealtime()
        val note = if (dialog) purpose(p) else null
        askPermission.launch(p)
        val ok = try { d.await() } finally { note?.let { root.removeView(it) } }
        if (!ok && SystemClock.elapsedRealtime() - t0 < 400 && !shouldShowRequestPermissionRationale(p)) offerSettings(offTitle, offBody, settings)
        return ok
    }

    /** 「麦克风权限说明」 / 「通知权限说明」 over the top of the page while the phone asks (工信部 26 号文第 10 条). */
    private fun purpose(p: String): View {
        val (title, body) = if (p == Manifest.permission.RECORD_AUDIO) R.string.mic_purpose_title to R.string.mic_purpose
            else R.string.notify_purpose_title to R.string.notify_purpose
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dip(16), dip(12), dip(16), dip(14))
            background = GradientDrawable().apply {
                cornerRadius = dip(14).toFloat()
                setColor(getColor(R.color.flow_surface))
                setStroke(maxOf(1, dip(1) / 2), getColor(R.color.flow_line))
            }
            elevation = dip(6).toFloat()
        }
        box.addView(TextView(this).apply { text = getString(title); textSize = 15f; setTypeface(typeface, Typeface.BOLD); setTextColor(getColor(R.color.flow_text)) })
        box.addView(TextView(this).apply {
            text = getString(body); textSize = 14f; setLineSpacing(0f, 1.2f); setTextColor(getColor(R.color.flow_text)); setPadding(0, dip(4), 0, 0)
        })
        root.addView(box, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.TOP)
            .apply { setMargins(dip(12), dip(8), dip(12), 0) })
        return box
    }

    fun micPermission(): String = when {
        granted(Manifest.permission.RECORD_AUDIO) -> "granted"
        asked(Manifest.permission.RECORD_AUDIO) && !shouldShowRequestPermissionRationale(Manifest.permission.RECORD_AUDIO) -> "denied"
        else -> "undetermined"
    }

    /** The microphone: once refused, the reason is said before the system asks again. */
    suspend fun askMic(): Boolean {
        val p = Manifest.permission.RECORD_AUDIO
        if (granted(p)) return true
        if (shouldShowRequestPermissionRationale(p) && !explain(R.string.mic_why_title, R.string.mic_why)) return false
        return ask(p, R.string.mic_off_title, R.string.mic_off) { openAppSettings() }
    }

    fun notifyPermission(): String {
        val p = if (Build.VERSION.SDK_INT >= 33) Manifest.permission.POST_NOTIFICATIONS else ""
        return Reminders.permission(this, p.isNotEmpty() && asked(p), p.isNotEmpty() && shouldShowRequestPermissionRationale(p))
    }

    /** 「到点用 App 通知提醒」: the phone's permission (Android 13+), then the app's reminders on, from the server's reminder. */
    suspend fun askNotify(): Boolean {
        if (!notificationsAllowed()) return false
        Reminders.setApp(this, true)
        Reminders.refreshLater(this, force = true)
        return true
    }

    /** The phone's own permission for notifications: asked (Android 13+), or the settings offered when it is off for good. */
    private suspend fun notificationsAllowed(): Boolean {
        if (!Reminders.allowed(this)) {
            if (Build.VERSION.SDK_INT >= 33 && !granted(Manifest.permission.POST_NOTIFICATIONS)) {
                if (!ask(Manifest.permission.POST_NOTIFICATIONS, R.string.notify_off_title, R.string.notify_off) { openNotifySettings() }) return false
            }
            if (!Reminders.allowed(this)) { offerSettings(R.string.notify_off_title, R.string.notify_off) { openNotifySettings() }; return false }
        }
        Reminders.channel(this)
        return true
    }

    fun openNotifySettings() {
        val i = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
        try { startActivity(i) } catch (e: ActivityNotFoundException) { openAppSettings() }
    }

    /**
     * privacy.permissions, for the page's 权限管理 (小米: a page in the app listing what is allowed): what the phone allows
     * now. 'granted', 'undetermined' (the phone will ask when it is first needed) or 'denied' (off: in the phone's settings).
     */
    fun permissions(): org.json.JSONObject {
        val p = Manifest.permission.POST_NOTIFICATIONS
        val notify = when {
            Reminders.allowed(this) -> "granted"
            Build.VERSION.SDK_INT >= 33 && (!asked(p) || shouldShowRequestPermissionRationale(p)) -> "undetermined"
            else -> "denied"
        }
        return org.json.JSONObject().put("mic", micPermission()).put("notify", notify)
    }

    /** privacy.settings: the phone's own page to change one (notifications), or the app's page (the microphone, all). */
    fun openPermissionSettings(what: String) = if (what == "notify") openNotifySettings() else openAppSettings()

    private fun openAppSettings() {
        try { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))) } catch (e: ActivityNotFoundException) { /* none */ }
    }

    private suspend fun explain(title: Int, body: Int): Boolean {
        val d = CompletableDeferred<Boolean>()
        Accent.dialog(this).setTitle(title).setMessage(body)
            .setPositiveButton(R.string.ok) { _, _ -> d.complete(true) }
            .setNegativeButton(R.string.not_now) { _, _ -> d.complete(false) }
            .setOnCancelListener { d.complete(false) }
            .show()
        return d.await()
    }

    private fun offerSettings(title: Int, body: Int, go: () -> Unit) {
        Accent.dialog(this).setTitle(title).setMessage(body)
            .setPositiveButton(R.string.go_settings) { _, _ -> go() }
            .setNegativeButton(R.string.not_now, null)
            .show()
    }

    // ---------------------------------------------------------------- updates (update/Updater.kt)

    // (BuildConfig.UPDATER: never in 语流内测 or in the store build, whose code then has no updater at all)
    private val installSettings = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (BuildConfig.UPDATER) Updater.onInstallSettingsBack(this)
    }

    /** 「安装未知应用」 for 语流, to install the new version it has just downloaded and checked; back in onInstallSettingsBack. */
    fun openInstallSettings() {
        try {
            installSettings.launch(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
        } catch (e: ActivityNotFoundException) {
            if (BuildConfig.UPDATER) Updater.onInstallSettingsBack(this)  // no such screen: the download page is offered instead
        }
    }

    /** flowlang.cn/download in the phone's browser (when installing from here is not possible). */
    fun openDownloadPage() = openOutside(Uri.parse(Updater.DOWNLOAD_PAGE))

    // ---------------------------------------------------------------- links

    private fun openOutside(u: Uri) {
        val i = when (u.scheme) {
            "mailto", "sms" -> Intent(Intent.ACTION_SENDTO, u)
            "tel" -> Intent(Intent.ACTION_DIAL, u)
            else -> Intent(Intent.ACTION_VIEW, u)
        }.addCategory(Intent.CATEGORY_BROWSABLE).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try { startActivity(i) } catch (e: ActivityNotFoundException) { toast(getString(R.string.no_browser)) }
    }

    /**
     * 「加到手机日历」 in the app (docs/native-bridge.md §5): the app's own notifications, or the phone's calendar. The link says
     * what: the daily word review (?hour=), one time (?at=, 这次什么时候复习) or the day's plan (?kind=plan&hour=&minutes=).
     */
    private fun reminderLink(u: Uri) {
        val plan = u.getQueryParameter("kind") == "plan"
        val hour = u.getQueryParameter("hour")?.toIntOrNull()
        val minutes = u.getQueryParameter("minutes")?.toIntOrNull() ?: 10
        val at = u.getQueryParameter("at")?.toDoubleOrNull()
        Accent.dialog(this).setTitle(if (plan) R.string.ics_plan_title else R.string.ics_title).setMessage(R.string.ics_body)
            .setPositiveButton(R.string.ics_app) { _, _ ->
                lifecycleScope.launch {
                    if (consented(R.string.consent_why_notify) && notificationsAllowed()) toast(Reminders.optIn(this@MainActivity, plan, hour, minutes, at))
                }
            }
            .setNeutralButton(R.string.ics_calendar) { _, _ -> lifecycleScope.launch { addToCalendar(u) } }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    /** The server's .ics as a new event in the phone's calendar app (the learner saves it there; no calendar permission). */
    private suspend fun addToCalendar(u: Uri) {
        val text = try { Http.get(u.toString()).takeIf { it.ok }?.body } catch (e: Exception) { null }
        val ev = text?.let { Ics.firstEvent(it) }
        if (ev == null) { toast("日历提醒没拿到，稍后再试"); return }
        val i = Intent(Intent.ACTION_INSERT).setData(CalendarContract.Events.CONTENT_URI)
            .putExtra(CalendarContract.EXTRA_EVENT_BEGIN_TIME, ev.start)
            .putExtra(CalendarContract.EXTRA_EVENT_END_TIME, ev.end)
            .putExtra(CalendarContract.Events.TITLE, ev.title)
            .putExtra(CalendarContract.Events.DESCRIPTION, ev.description)
            .putExtra(CalendarContract.Events.HAS_ALARM, 1)
        ev.rrule?.let { i.putExtra(CalendarContract.Events.RRULE, it) }
        try { startActivity(i) } catch (e: ActivityNotFoundException) { toast(getString(R.string.no_calendar)) }
    }

    private fun toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

    // ---------------------------------------------------------------- the page could not be opened

    private fun errorView(): View {
        val dp = { v: Int -> TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v.toFloat(), resources.displayMetrics).toInt() }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setPadding(dp(32), dp(32), dp(32), dp(32)) }
        box.addView(TextView(this).apply { text = getString(R.string.offline_title); textSize = 20f; gravity = Gravity.CENTER })
        box.addView(TextView(this).apply { text = getString(R.string.offline_body); textSize = 15f; gravity = Gravity.CENTER; setPadding(0, dp(12), 0, dp(20)) })
        box.addView(Button(this).apply { text = getString(R.string.retry); setOnClickListener { errorView.isVisible = false; web.reload() } })
        recolorError(box)
        return box
    }

    private fun recolorError(box: LinearLayout) {
        box.setBackgroundColor(getColor(R.color.flow_bg))
        for (k in 0 until box.childCount) (box.getChildAt(k) as? TextView)?.takeIf { it !is Button }?.setTextColor(getColor(R.color.flow_text))
    }
}

/** The few lines of the server's .ics the calendar needs (vocab_service.ics: DTSTART in UTC, DURATION, RRULE). */
object Ics {
    class Event(val start: Long, val end: Long, val title: String, val description: String, val rrule: String?)

    fun firstEvent(text: String): Event? {
        val lines = ArrayList<String>()
        text.replace("\r\n", "\n").split("\n").forEach { l -> if (l.startsWith(" ") && lines.isNotEmpty()) lines[lines.size - 1] += l.substring(1) else lines += l }
        val ev = lines.dropWhile { it != "BEGIN:VEVENT" }.takeWhile { it != "END:VEVENT" }.takeWhile { it != "BEGIN:VALARM" }
        fun prop(n: String) = ev.firstOrNull { it.startsWith("$n:") || it.startsWith("$n;") }?.substringAfter(':')
        val start = prop("DTSTART")?.let { parse(it) } ?: return null
        val end = prop("DTEND")?.let { parse(it) } ?: prop("DURATION")?.let { start + Duration.parse(it).toMillis() } ?: (start + 10 * 60_000)
        fun unescape(s: String) = s.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
        return Event(start, end, unescape(prop("SUMMARY") ?: "语流"), unescape(prop("DESCRIPTION") ?: ""), prop("RRULE"))
    }

    private fun parse(v: String): Long? = try {
        if (v.endsWith("Z")) LocalDateTime.parse(v.removeSuffix("Z"), DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss")).toInstant(ZoneOffset.UTC).toEpochMilli()
        else LocalDateTime.parse(v, DateTimeFormatter.ofPattern("yyyyMMdd'T'HHmmss")).atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli()
    } catch (e: Exception) { null }
}
