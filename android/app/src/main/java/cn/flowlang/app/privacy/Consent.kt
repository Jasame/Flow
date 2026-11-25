package cn.flowlang.app.privacy

import android.content.Context
import org.json.JSONObject

/**
 * The question on the first start (android/README.md 「第一次打开」), before the app reaches anything on the network: no
 * page, no update check, no reminder look-up until it is answered.
 *   同意   → as before.
 *   不同意 → 基本模式: the site without signing in (the page keeps its progress on the phone); no reminders, no microphone, no
 *           update check; signing in or up, recording or reminders ask again first. Asked once: never again by itself.
 * The answer is kept on this phone with the version of the two texts it was for (their 生效日期, written as
 * privacy_service.CONSENT_VERSION is); a build with a newer version asks again. 撤回同意 (privacy.withdraw) forgets it.
 * The account's own consents (数据存放在香港, the 用户协议 tick) stay the site's, asked and kept on the server.
 */
object Consent {
    enum class State { ASK, AGREED, BASIC }

    val DOCS = listOf("terms", "privacy")

    /** From what this phone answered and the version of the texts in this build. */
    fun state(agreed: String?, basic: Boolean, current: String): State = when {
        agreed != null && agreed == current -> State.AGREED
        basic -> State.BASIC
        else -> State.ASK
    }

    /** The site's sign-in routes (flow/app.py SIGN_IN_ROUTES): in 基本模式 the app answers them itself, and asks first. */
    val SIGN_IN = setOf("/api/login", "/api/register", "/api/auth/code", "/api/auth/reset", "/api/recovery/request",
        "/api/recovery/reset", "/api/teacher/check")

    fun signIn(path: String?): Boolean = path != null && path.trimEnd('/') in SIGN_IN

    /** The answer the page gets instead, as 403 (its form shows `error`). */
    const val SIGN_IN_ANSWER =
        """{"error":"要登录或注册，请先在弹出的窗口里同意《用户协议》和《隐私和数据》，然后再点一次。","code":"app-consent"}"""

    /** The two texts as this build has them (assets legal/legal.json, made by tools/legal_docs.py). */
    class Docs(val version: String, val titles: Map<String, String>, val html: Map<String, String>)

    fun parse(json: String): Docs? = try {
        val o = JSONObject(json)
        val d = o.getJSONObject("docs")
        val titles = HashMap<String, String>()
        val html = HashMap<String, String>()
        for (id in DOCS) d.getJSONObject(id).let { titles[id] = it.getString("title"); html[id] = it.getString("html") }
        Docs(o.getString("version").also { require(it.isNotBlank()) }, titles, html)
    } catch (e: Exception) {
        null
    }

    /** Never in a build (the Gradle task legalDocs makes the file); only so the app opens if the file were missing. */
    private val MISSING = Docs("missing", mapOf("terms" to "语流用户协议", "privacy" to "隐私和数据"),
        mapOf("terms" to GONE, "privacy" to GONE))
    private const val GONE = "<p>这个版本的 App 里少了这一章。请到语流网站的「操作指南」里看。</p>"

    @Volatile private var docs: Docs? = null

    fun docs(c: Context): Docs = docs ?: (try {
        c.assets.open("legal/legal.json").bufferedReader().use { parse(it.readText()) }
    } catch (e: Exception) {
        null
    } ?: MISSING).also { docs = it }

    // ---------------------------------------------------------------- the answer, on this phone

    private fun prefs(c: Context) = c.getSharedPreferences("flow-consent", Context.MODE_PRIVATE)

    fun state(c: Context): State = prefs(c).let { state(it.getString("version", null), it.getBoolean("basic", false), docs(c).version) }

    fun agree(c: Context) {
        prefs(c).edit().putString("version", docs(c).version).putBoolean("basic", false).putLong("at", System.currentTimeMillis()).apply()
    }

    fun decline(c: Context) {
        prefs(c).edit().remove("version").putBoolean("basic", true).putLong("at", System.currentTimeMillis()).apply()
    }

    fun withdraw(c: Context) {
        prefs(c).edit().clear().apply()
    }

    /** For the page (privacy.state): 'agreed' or 'basic' (the question is never open while a page is). */
    fun name(s: State): String = when (s) {
        State.AGREED -> "agreed"
        State.BASIC -> "basic"
        State.ASK -> "ask"
    }
}
