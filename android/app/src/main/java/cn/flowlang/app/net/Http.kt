package cn.flowlang.app.net

import android.webkit.CookieManager
import cn.flowlang.app.Site
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * The app's own requests to the site (the server voice, the reminder), signed in as the WebView is: its cookies go
 * along, and a renewed session cookie the server sends back is handed to the WebView. Nothing goes anywhere else.
 */
object Http {
    class Resp(val code: Int, val body: String) {
        val ok get() = code in 200..299
        fun json(): JSONObject = try { JSONObject(body) } catch (e: Exception) { JSONObject() }
    }

    class Failure(val code: String, message: String, val status: Int = 0) : IOException(message)

    private fun cookies() = try { CookieManager.getInstance() } catch (e: Exception) { null }

    suspend fun get(path: String, timeoutMs: Int = 15_000): Resp = withContext(Dispatchers.IO) { call("GET", path, null, null, timeoutMs) }

    suspend fun post(path: String, body: JSONObject, csrf: String?, timeoutMs: Int = 20_000): Resp =
        withContext(Dispatchers.IO) { call("POST", path, body, csrf, timeoutMs) }

    private fun call(method: String, path: String, body: JSONObject?, csrf: String?, timeoutMs: Int): Resp {
        val url = Site.abs(path)
        if (!Site.isOwn(url)) throw Failure("other", "not our site")
        val c = URL(url).openConnection() as HttpURLConnection
        try {
            c.requestMethod = method
            c.connectTimeout = 10_000
            c.readTimeout = timeoutMs
            c.instanceFollowRedirects = false
            c.useCaches = false
            c.setRequestProperty("User-Agent", Site.userAgent)
            c.setRequestProperty("Accept", "application/json")
            cookies()?.getCookie(url)?.let { c.setRequestProperty("Cookie", it) }
            if (body != null) {
                c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                if (!csrf.isNullOrEmpty()) c.setRequestProperty("X-CSRF-Token", csrf)
                c.outputStream.use { it.write(body.toString().toByteArray()) }
            }
            val code = c.responseCode
            c.headerFields["Set-Cookie"]?.forEach { cookies()?.setCookie(Site.origin, it) }
            val stream = if (code >= 400) c.errorStream else c.inputStream
            val text = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            return Resp(code, text)
        } catch (e: Failure) {
            throw e
        } catch (e: IOException) {
            throw Failure("net", e.message ?: "network")
        } finally {
            c.disconnect()
        }
    }

    // ---- the session: the CSRF token (a POST counts as the signed-in learner only with it) and the second audio line
    private var session: JSONObject? = null
    private var sessionAt = 0L
    private var sessionCookie: String? = null

    /** GET /api/session, kept for five minutes while the login cookie stays the same. */
    suspend fun session(force: Boolean = false): JSONObject? {
        val now = System.currentTimeMillis()
        val cookie = cookies()?.getCookie(Site.origin)
        if (!force && session != null && now - sessionAt < 5 * 60_000 && cookie == sessionCookie) return session
        return try {
            val r = get("/api/session")
            if (!r.ok) null else r.json().also { session = it; sessionAt = now; sessionCookie = cookie }
        } catch (e: Exception) {
            session
        }
    }

    suspend fun csrf(force: Boolean = false): String? = session(force)?.optJSONObject("user")?.optString("csrf")?.ifEmpty { null }

    fun forgetSession() { session = null; sessionAt = 0 }
}
