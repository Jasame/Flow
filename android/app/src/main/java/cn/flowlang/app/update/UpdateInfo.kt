package cn.flowlang.app.update

import org.json.JSONObject
import java.net.URI

/**
 * The 安卓 entry of https://flowlang.cn/download/latest.json (语流 A1 writes it when a version goes up):
 *
 *     {"android": {"version": "1.0.2", "code": 3, "file": "flow-android-1.0.2.apk", "size": 1100000,
 *                  "sha256": "…64 hex…", "cert": "76:88:…", "date": "2026-11-25", "notes": "这一版改了什么"}}
 *
 * `code` (the versionCode) and `notes` may be missing: then the version names are compared, and nothing is said about
 * what changed. `changes` (a list of lines) is read when there is no `notes`. The file is resolved against the address
 * latest.json came from.
 */
data class UpdateInfo(
    val version: String,
    val code: Long?,
    val url: String,
    val size: Long,
    val sha256: String,
    val notes: String,
) {
    /** Newer than this app (versionCode [myCode], versionName [myName])? */
    fun newerThan(myCode: Long, myName: String): Boolean =
        if (code != null) code > myCode else Versions.compare(version, myName) > 0

    companion object {
        private val SHA256 = Regex("^[0-9a-f]{64}$")
        private const val MAX_NOTES = 600

        /** The android entry of [json], or null when it is missing or not usable (no file, size or SHA-256). */
        fun parse(json: String, base: String): UpdateInfo? = try {
            val a = JSONObject(json).optJSONObject("android")
            val version = a?.optString("version")?.trim().orEmpty()
            val file = a?.optString("file")?.trim().orEmpty()
            val sha = a?.optString("sha256")?.trim()?.lowercase().orEmpty()
            val size = a?.optLong("size", -1) ?: -1
            if (a == null || version.isEmpty() || file.isEmpty() || !SHA256.matches(sha) || size <= 0) null
            else {
                val notes = a.optString("notes").trim().ifEmpty {
                    a.optJSONArray("changes")?.let { c ->
                        (0 until c.length()).mapNotNull { i -> c.optString(i).trim().ifEmpty { null } }.joinToString("\n") { "· $it" }
                    }.orEmpty()
                }
                UpdateInfo(
                    version = version,
                    code = if (a.has("code") && !a.isNull("code")) a.optLong("code") else null,
                    url = URI(base).resolve(file).toString(),
                    size = size,
                    sha256 = sha,
                    notes = notes.take(MAX_NOTES),
                )
            }
        } catch (e: Exception) {
            null
        }
    }
}

object Versions {
    /** "1.0.10" against "1.0.9" → positive: number by number, a missing part counts as 0, anything after "-" is ignored. */
    fun compare(a: String, b: String): Int {
        fun parts(v: String) = v.trim().substringBefore('-').split('.').map { it.trim().toIntOrNull() ?: 0 }
        val x = parts(a)
        val y = parts(b)
        for (i in 0 until maxOf(x.size, y.size)) {
            val d = x.getOrElse(i) { 0 }.compareTo(y.getOrElse(i) { 0 })
            if (d != 0) return d
        }
        return 0
    }
}

/**
 * When to look, and when to keep quiet: when the app starts, then the first time each day it comes back to the front
 * (a check that failed, offline say, is tried again the next time); 「稍后」 keeps that version quiet for the rest of the
 * day, on every check (a newer version still shows).
 */
object UpdateGate {
    fun shouldCheck(checkedThisRun: Boolean, lastCheckDay: String?, today: String): Boolean = !checkedThisRun || lastCheckDay != today

    fun quiet(version: String, today: String, quietVersion: String?, quietDay: String?): Boolean =
        quietVersion == version && quietDay == today
}
