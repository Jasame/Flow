package cn.flowlang.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Color
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
import android.webkit.WebSettings
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
import cn.flowlang.app.rec.Recorder
import cn.flowlang.app.speech.Speech
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

/**
 * The app: the site in a WebView (so every change to the site is in the app at once), with the native parts behind
 * window.FlowApp (Bridge). Signed in as on the site (the WebView's own cookies, kept on the phone); the back button
 * goes back in the page; other sites open in the phone's browser; the page sits between the status bar, the cutout,
 * the navigation bar and the keyboard, in the page's own colours.
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
    private val bridge by lazy { Bridge(this) }
    private val prefs by lazy { getSharedPreferences("flow-app", MODE_PRIVATE) }

    // ---------------------------------------------------------------- set-up

    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        bars()
        // the test switch (docs/native-bridge.md §9): `--ez flow.mute true` on a debug or beta build; the UI tests set it themselves
        if (intent?.getBooleanExtra("flow.mute", false) == true && (BuildConfig.DEBUG || BuildConfig.FLAVOR == "beta")) Mute.on = true
        FlowAudio.init(this)
        Speech.init(this)
        root = FrameLayout(this)
        root.setBackgroundColor(getColor(R.color.flow_bg))
        web = WebView(this)
        root.addView(web, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        errorView = errorView()
        root.addView(errorView, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        errorView.isVisible = false
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
        if (saved == null || web.restoreState(saved) == null) web.loadUrl(startUrl(intent))
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

        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceErrorCompat) {
            if (request.isForMainFrame) errorView.isVisible = true
        }

        override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
            // the page's process was ended by the system (memory): start over with a fresh WebView
            root.removeView(web)
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
            lifecycleScope.launch { if (askMic()) request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else request.deny() }
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
        Reminders.refreshLater(this)  // opening and coming back: the reminders as the site has them now
    }

    override fun onStop() {
        FlowAudio.visible = false
        Reminders.refreshLater(this)  // going to the background too: a day done is taken off
        if (Recorder.busy) Recorder.cut()  // only an app in front may use the microphone
        CookieManager.getInstance().flush()
        web.onPause()
        super.onStop()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        intent.getStringExtra(EXTRA_PATH)?.let { web.loadUrl(startUrl(intent)) }
    }

    override fun onSaveInstanceState(out: Bundle) {
        super.onSaveInstanceState(out)
        web.saveState(out)
    }

    override fun onConfigurationChanged(c: Configuration) {
        super.onConfigurationChanged(c)
        // dark / light switched with the app open: the bars and the space around the page follow at once
        root.setBackgroundColor(getColor(R.color.flow_bg))
        web.setBackgroundColor(getColor(R.color.flow_bg))
        bars()
        (errorView as? LinearLayout)?.let { recolorError(it) }
    }

    override fun onDestroy() {
        // a text may go on playing in the service: it just stops telling this page
        FlowAudio.sink = null
        Recorder.sink = null
        Speech.voicesChanged = null
        if (::web.isInitialized && web.parent != null) { root.removeView(web); web.destroy() }
        super.onDestroy()
    }

    // ---------------------------------------------------------------- permissions (asked here, used by the bridge)

    private var waiting: CompletableDeferred<Boolean>? = null
    private val askPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) { ok -> waiting?.complete(ok); waiting = null }

    private fun granted(p: String) = ContextCompat.checkSelfPermission(this, p) == PackageManager.PERMISSION_GRANTED
    private fun asked(p: String) = prefs.getBoolean("asked:$p", false)

    /** The system dialog; false right away (no dialog shown) means refused for good: then the settings are offered. */
    private suspend fun ask(p: String, offTitle: Int, offBody: Int, settings: () -> Unit): Boolean {
        if (granted(p)) return true
        waiting?.complete(false)
        val d = CompletableDeferred<Boolean>()
        waiting = d
        prefs.edit().putBoolean("asked:$p", true).apply()
        val t0 = SystemClock.elapsedRealtime()
        askPermission.launch(p)
        val ok = d.await()
        if (!ok && SystemClock.elapsedRealtime() - t0 < 400 && !shouldShowRequestPermissionRationale(p)) offerSettings(offTitle, offBody, settings)
        return ok
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

    private fun openAppSettings() {
        try { startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName"))) } catch (e: ActivityNotFoundException) { /* none */ }
    }

    private suspend fun explain(title: Int, body: Int): Boolean {
        val d = CompletableDeferred<Boolean>()
        AlertDialog.Builder(this).setTitle(title).setMessage(body)
            .setPositiveButton(R.string.ok) { _, _ -> d.complete(true) }
            .setNegativeButton(R.string.not_now) { _, _ -> d.complete(false) }
            .setOnCancelListener { d.complete(false) }
            .show()
        return d.await()
    }

    private fun offerSettings(title: Int, body: Int, go: () -> Unit) {
        AlertDialog.Builder(this).setTitle(title).setMessage(body)
            .setPositiveButton(R.string.go_settings) { _, _ -> go() }
            .setNegativeButton(R.string.not_now, null)
            .show()
    }

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
        AlertDialog.Builder(this).setTitle(if (plan) R.string.ics_plan_title else R.string.ics_title).setMessage(R.string.ics_body)
            .setPositiveButton(R.string.ics_app) { _, _ ->
                lifecycleScope.launch { if (notificationsAllowed()) toast(Reminders.optIn(this@MainActivity, plan, hour, minutes, at)) }
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
