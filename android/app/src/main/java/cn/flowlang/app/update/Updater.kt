package cn.flowlang.app.update

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageInfo
import android.content.pm.PackageInstaller
import android.content.pm.PackageManager
import android.content.pm.Signature
import android.os.Build
import android.util.Log
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.core.content.pm.PackageInfoCompat
import androidx.lifecycle.lifecycleScope
import cn.flowlang.app.Accent
import cn.flowlang.app.BuildConfig
import cn.flowlang.app.MainActivity
import cn.flowlang.app.R
import cn.flowlang.app.Site
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.lang.ref.WeakReference
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.time.LocalDate
import java.util.Locale
import kotlin.coroutines.coroutineContext

/**
 * New versions of 语流 (the APK from flowlang.cn/download, not a store). When the app starts, and the first time each
 * day it comes back to the front, it reads latest.json; a newer version is offered with what changed (「下载」 /
 * 「稍后」, and 「稍后」 keeps that version quiet for the rest of the day). 「下载」 fetches the APK into the app's cache and
 * checks its size and SHA-256 against latest.json, and that it is this app, newer, signed with the same key. Then the
 * phone's own installer takes it, and it always asks the learner to confirm: an app installed from an APK cannot update
 * itself without that tap. Installing needs 「安装未知应用」 for 语流; it is asked, with the reason, only at that point.
 * Only the 语流 app (prod) looks; 语流内测 comes from CI. Nothing is sent but the request for latest.json and the APK.
 */
object Updater {
    private const val TAG = "FlowUpdate"
    private const val OFFICIAL = "https://flowlang.cn/download/latest.json"
    const val DOWNLOAD_PAGE = "https://flowlang.cn/download/"
    private const val ACTION_STATUS = "cn.flowlang.app.UPDATE_STATUS"
    private const val MAX_JSON = 64 * 1024
    private const val MAX_APK = 200L * 1024 * 1024

    /** Debug builds only (the update tests): where latest.json is read from, e.g. http://127.0.0.1:18765/latest.json
     *  with `adb reverse tcp:18765 tcp:18765` (the debug network config lets plain http to 127.0.0.1 through). */
    var testUrl: String? = null

    private val source get() = testUrl ?: OFFICIAL
    private val enabled get() = BuildConfig.FLAVOR == "prod" && (!BuildConfig.DEBUG || testUrl != null)

    private var checkedThisRun = false
    private var busy = false                  // a check, an offer or an install is under way: no second one
    private var activity: WeakReference<MainActivity>? = null
    private var waitingFile: File? = null     // checked, waiting for 「安装未知应用」
    private var waitingInfo: UpdateInfo? = null
    @Volatile private var session = -1

    private fun prefs(c: Context) = c.getSharedPreferences("flow-update", Context.MODE_PRIVATE)
    private fun today() = LocalDate.now().toString()

    // ---------------------------------------------------------------- looking

    /** MainActivity.onStart: when the app starts, then the first time each day it comes back to the front. */
    fun onStart(a: MainActivity) {
        activity = WeakReference(a)
        if (!enabled || busy) return
        val p = prefs(a)
        val day = today()
        if (!UpdateGate.shouldCheck(checkedThisRun, p.getString("checked", null), day)) return
        checkedThisRun = true
        busy = true
        a.lifecycleScope.launch {
            var offered = false
            try {
                val info = withContext(Dispatchers.IO) { fetchInfo() } ?: return@launch
                p.edit().putString("checked", day).apply()  // a failed check is tried again the next time
                if (!info.newerThan(myCode(a), BuildConfig.FLOW_VERSION)) return@launch
                if (UpdateGate.quiet(info.version, day, p.getString("quiet.version", null), p.getString("quiet.day", null))) return@launch
                if (a.isFinishing || a.isDestroyed) return@launch
                offer(a, info)
                offered = true
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.i(TAG, "no update information (${e.javaClass.simpleName})")
            } finally {
                if (!offered) busy = false
            }
        }
    }

    private fun offer(a: MainActivity, info: UpdateInfo) {
        val text = buildString {
            if (info.notes.isNotEmpty()) append(info.notes).append("\n\n")
            append(a.getString(R.string.update_how, mb(info.size)))
        }
        var chosen = false
        Accent.dialog(a)
            .setTitle(a.getString(R.string.update_title, info.version))
            .setMessage(text)
            .setPositiveButton(R.string.update_download) { _, _ -> chosen = true; download(a, info) }
            .setNegativeButton(R.string.update_later) { _, _ -> chosen = true; quiet(a, info) }
            .setOnDismissListener { if (!chosen) quiet(a, info) }  // back button: as 「稍后」
            .show()
    }

    /** 「稍后」, or given up on: not this version again today (a newer one still shows). */
    private fun quiet(c: Context, info: UpdateInfo) {
        prefs(c).edit().putString("quiet.version", info.version).putString("quiet.day", today()).apply()
        busy = false
    }

    // ---------------------------------------------------------------- downloading and checking

    private enum class Problem { MISMATCH, NET }
    private class Got(val file: File?, val problem: Problem?)

    private fun download(a: MainActivity, info: UpdateInfo) {
        val pad = (20 * a.resources.displayMetrics.density).toInt()
        val label = TextView(a).apply { text = a.getString(R.string.update_downloading, 0) }
        val bar = ProgressBar(a, null, android.R.attr.progressBarStyleHorizontal).apply {
            max = 100
            progressTintList = android.content.res.ColorStateList.valueOf(Accent.color(a))
        }
        val box = LinearLayout(a).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad / 2, pad, 0)
            addView(label)
            addView(bar)
        }
        var job: Job? = null
        val dlg = Accent.dialog(a)
            .setTitle(a.getString(R.string.update_title, info.version))
            .setView(box)
            .setNegativeButton(R.string.cancel) { _, _ -> job?.cancel(); quiet(a, info) }
            .setCancelable(false)
            .show()
        job = a.lifecycleScope.launch {
            val got = try {
                withContext(Dispatchers.IO) {
                    fetchApk(a, info) { pct -> a.runOnUiThread { bar.progress = pct; label.text = a.getString(R.string.update_downloading, pct) } }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "download failed (${e.javaClass.simpleName})")
                Got(null, Problem.NET)
            }
            if (dlg.isShowing) dlg.dismiss()
            val f = got.file
            when {
                f != null -> {
                    val wrong = withContext(Dispatchers.IO) { checkApk(a, f) }
                    if (wrong == null) ready(a, info, f) else { f.delete(); refuse(a, info, wrong) }
                }
                got.problem == Problem.MISMATCH -> retry(a, info, R.string.update_bad_title, R.string.update_bad)
                else -> retry(a, info, R.string.update_net_title, R.string.update_net)
            }
        }
    }

    /** Into the app's cache, checked as it comes: no more than latest.json's size, then that size and SHA-256 exactly. */
    private suspend fun fetchApk(c: Context, info: UpdateInfo, progress: (Int) -> Unit): Got {
        val dir = File(c.cacheDir, "update").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
        val f = File(dir, "flow-update.apk")
        val conn = open(info.url)
        try {
            if (conn.responseCode != 200) return Got(null, Problem.NET)
            val md = MessageDigest.getInstance("SHA-256")
            var n = 0L
            var shown = -1
            conn.inputStream.use { input ->
                f.outputStream().use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        coroutineContext.ensureActive()
                        val r = input.read(buf)
                        if (r < 0) break
                        n += r
                        if (n > info.size || n > MAX_APK) { f.delete(); return Got(null, Problem.MISMATCH) }
                        md.update(buf, 0, r)
                        out.write(buf, 0, r)
                        val pct = (n * 100 / info.size).toInt()
                        if (pct != shown) { shown = pct; progress(pct) }
                    }
                }
            }
            if (n != info.size || hex(md.digest()) != info.sha256) { f.delete(); return Got(null, Problem.MISMATCH) }
            return Got(f, null)
        } catch (e: IOException) {
            f.delete()
            return Got(null, Problem.NET)
        } finally {
            conn.disconnect()
        }
    }

    /** Null when [f] is this app, newer than the one installed and signed with the same key; else what is wrong. */
    private fun checkApk(c: Context, f: File): Int? {
        val pm = c.packageManager
        @Suppress("DEPRECATION")
        val flags = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        val apk = archive(pm, f.path, flags) ?: return R.string.update_wrong_unreadable
        if (apk.packageName != c.packageName) return R.string.update_wrong_package
        val mine = installed(pm, c.packageName, flags)
        if (PackageInfoCompat.getLongVersionCode(apk) <= PackageInfoCompat.getLongVersionCode(mine)) return R.string.update_wrong_old
        val theirs = signers(apk)
        // where the phone cannot read them from the file, it still checks the key itself when installing
        if (theirs.isNotEmpty() && theirs != signers(mine)) return R.string.update_wrong_key
        return null
    }

    private fun signers(p: PackageInfo): Set<String> {
        val sigs: List<Signature> = if (Build.VERSION.SDK_INT >= 28) {
            val s = p.signingInfo ?: return emptySet()
            if (s.hasMultipleSigners()) s.apkContentsSigners?.toList().orEmpty() else s.signingCertificateHistory?.takeLast(1).orEmpty()
        } else {
            @Suppress("DEPRECATION")
            p.signatures?.toList().orEmpty()
        }
        return sigs.map { hex(MessageDigest.getInstance("SHA-256").digest(it.toByteArray())) }.toSet()
    }

    private fun archive(pm: PackageManager, path: String, flags: Int): PackageInfo? =
        if (Build.VERSION.SDK_INT >= 33) pm.getPackageArchiveInfo(path, PackageManager.PackageInfoFlags.of(flags.toLong()))
        else @Suppress("DEPRECATION") pm.getPackageArchiveInfo(path, flags)

    private fun installed(pm: PackageManager, name: String, flags: Int): PackageInfo =
        if (Build.VERSION.SDK_INT >= 33) pm.getPackageInfo(name, PackageManager.PackageInfoFlags.of(flags.toLong()))
        else @Suppress("DEPRECATION") pm.getPackageInfo(name, flags)

    private fun myCode(c: Context): Long = PackageInfoCompat.getLongVersionCode(installed(c.packageManager, c.packageName, 0))

    // ---------------------------------------------------------------- installing

    private fun ready(a: MainActivity, info: UpdateInfo, f: File) {
        if (!a.packageManager.canRequestPackageInstalls()) {
            waitingFile = f
            waitingInfo = info
            var chosen = false
            Accent.dialog(a)
                .setTitle(R.string.update_allow_title)
                .setMessage(R.string.update_allow)
                .setPositiveButton(R.string.go_settings) { _, _ -> chosen = true; a.openInstallSettings() }
                .setNegativeButton(R.string.cancel) { _, _ -> chosen = true; drop(a, info) }
                .setOnDismissListener { if (!chosen) drop(a, info) }
                .show()
            return
        }
        install(a, info, f)
    }

    private fun drop(c: Context, info: UpdateInfo) {
        waitingFile?.delete()
        waitingFile = null
        waitingInfo = null
        quiet(c, info)
    }

    /** Back from 「安装未知应用」 (MainActivity's launcher): allowed now, or the download page offered instead. */
    fun onInstallSettingsBack(a: MainActivity) {
        val f = waitingFile ?: return
        val info = waitingInfo ?: return
        waitingFile = null
        waitingInfo = null
        if (a.packageManager.canRequestPackageInstalls()) { install(a, info, f); return }
        f.delete()
        Accent.dialog(a)
            .setTitle(R.string.update_allow_title)
            .setMessage(R.string.update_allow_no)
            .setPositiveButton(R.string.update_open_page) { _, _ -> a.openDownloadPage() }
            .setNegativeButton(R.string.cancel, null)
            .setOnDismissListener { quiet(a, info) }
            .show()
    }

    /** The phone's own installer gets the file; it asks the learner (「更新」 / 「安装」) every time. */
    private fun install(a: MainActivity, info: UpdateInfo, f: File) {
        quiet(a, info)  // asked once today, whatever the answer
        busy = true
        a.lifecycleScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    val installer = a.packageManager.packageInstaller
                    val params = PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL).apply {
                        setAppPackageName(a.packageName)
                        setSize(f.length())
                        if (Build.VERSION.SDK_INT >= 31) setRequireUserAction(PackageInstaller.SessionParams.USER_ACTION_REQUIRED)
                        if (Build.VERSION.SDK_INT >= 33) setPackageSource(PackageInstaller.PACKAGE_SOURCE_DOWNLOADED_FILE)
                    }
                    val id = installer.createSession(params)
                    session = id  // before commit: the first status can come at once
                    installer.openSession(id).use { s ->
                        s.openWrite("flow.apk", 0, f.length()).use { out -> f.inputStream().use { it.copyTo(out) }; s.fsync(out) }
                        // the system fills in the status and the confirmation screen: mutable (Android 12+ asks to say so),
                        // and only to our own receiver, which is not exported
                        val mutable = if (Build.VERSION.SDK_INT >= 31) PendingIntent.FLAG_MUTABLE else 0
                        val back = Intent(a, InstallReceiver::class.java).setAction(ACTION_STATUS)
                        val status = PendingIntent.getBroadcast(a, id, back, PendingIntent.FLAG_UPDATE_CURRENT or mutable)
                        s.commit(status.intentSender)
                    }
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                Log.w(TAG, "install session failed (${e.javaClass.simpleName})")
                failed(a, a, PackageInstaller.STATUS_FAILURE)
            } finally {
                f.delete()
            }
        }
    }

    /** InstallReceiver: what the installer says about our session. */
    internal fun onStatus(c: Context, i: Intent) {
        if (i.action != ACTION_STATUS || i.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -2) != session) return
        val a = activity?.get()?.takeIf { !it.isFinishing && !it.isDestroyed }
        when (val status = i.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE)) {
            PackageInstaller.STATUS_PENDING_USER_ACTION -> {
                val confirm = if (Build.VERSION.SDK_INT >= 33) i.getParcelableExtra(Intent.EXTRA_INTENT, Intent::class.java)
                    else @Suppress("DEPRECATION") i.getParcelableExtra(Intent.EXTRA_INTENT)
                try {
                    if (confirm == null) failed(c, a, status)
                    else if (a != null) a.startActivity(confirm)
                    else c.startActivity(confirm.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                } catch (e: Exception) {
                    Log.w(TAG, "no confirmation screen (${e.javaClass.simpleName})")
                    failed(c, a, status)
                }
            }
            PackageInstaller.STATUS_SUCCESS -> { session = -1; busy = false }  // seldom seen: the new version replaces this one
            PackageInstaller.STATUS_FAILURE_ABORTED -> {
                session = -1
                busy = false
                Toast.makeText(c, R.string.update_aborted, Toast.LENGTH_LONG).show()
            }
            else -> {
                Log.w(TAG, "install failed: $status ${i.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE)}")
                session = -1
                failed(c, a, status)
            }
        }
    }

    // ---------------------------------------------------------------- what went wrong

    private fun retry(a: MainActivity, info: UpdateInfo, title: Int, body: Int) {
        var chosen = false
        Accent.dialog(a)
            .setTitle(title)
            .setMessage(body)
            .setPositiveButton(R.string.update_retry) { _, _ -> chosen = true; download(a, info) }
            .setNegativeButton(R.string.cancel) { _, _ -> chosen = true; quiet(a, info) }
            .setOnDismissListener { if (!chosen) quiet(a, info) }
            .show()
    }

    private fun refuse(a: MainActivity, info: UpdateInfo, why: Int) {
        Accent.dialog(a)
            .setTitle(R.string.update_failed_title)
            .setMessage(a.getString(R.string.update_wrong, a.getString(why)))
            .setPositiveButton(R.string.update_open_page) { _, _ -> a.openDownloadPage() }
            .setNegativeButton(R.string.cancel, null)
            .setOnDismissListener { quiet(a, info) }
            .show()
    }

    private fun failed(c: Context, a: MainActivity?, status: Int) {
        busy = false
        val why = c.getString(when (status) {
            PackageInstaller.STATUS_FAILURE_STORAGE -> R.string.update_fail_storage
            PackageInstaller.STATUS_FAILURE_CONFLICT, PackageInstaller.STATUS_FAILURE_INCOMPATIBLE -> R.string.update_fail_conflict
            PackageInstaller.STATUS_FAILURE_BLOCKED -> R.string.update_fail_blocked
            else -> R.string.update_fail_other
        })
        val text = c.getString(R.string.update_install_failed, why)
        if (a == null) { Toast.makeText(c, text, Toast.LENGTH_LONG).show(); return }
        Accent.dialog(a)
            .setTitle(R.string.update_failed_title)
            .setMessage(text)
            .setPositiveButton(R.string.update_open_page) { _, _ -> a.openDownloadPage() }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    // ---------------------------------------------------------------- the network

    /** https to the server latest.json comes from, nothing else (a debug build's test server may be plain http). */
    private fun open(url: String): HttpURLConnection {
        val u = URL(url)
        val home = URL(source)
        val plainOk = BuildConfig.DEBUG && testUrl != null && u.protocol == "http"
        if ((u.protocol != "https" && !plainOk) || !u.host.equals(home.host, ignoreCase = true) || u.port != home.port) {
            throw IOException("not the update server")
        }
        return (u.openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 30_000
            instanceFollowRedirects = false
            useCaches = false
            setRequestProperty("User-Agent", Site.userAgent)
            setRequestProperty("Cache-Control", "no-cache")
        }
    }

    private fun fetchInfo(): UpdateInfo? {
        val c = open(source)
        try {
            c.setRequestProperty("Accept", "application/json")
            if (c.responseCode != 200) return null
            val text = c.inputStream.bufferedReader().use { r ->
                val sb = StringBuilder()
                val buf = CharArray(4096)
                while (sb.length <= MAX_JSON) { val n = r.read(buf); if (n < 0) break; sb.append(buf, 0, n) }
                sb.toString()
            }
            return if (text.length > MAX_JSON) null else UpdateInfo.parse(text, source)
        } finally {
            c.disconnect()
        }
    }

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }
    private fun mb(bytes: Long) = String.format(Locale.ROOT, "%.1f MB", bytes / 1048576.0)
}

/** Where the phone's installer reports on our session (not exported: only the installer, through our PendingIntent). */
class InstallReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, i: Intent) = Updater.onStatus(c, i)
}
