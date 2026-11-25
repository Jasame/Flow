package cn.flowlang.app.audio

import android.content.Context
import org.json.JSONObject

/**
 * Where a whole text was left, per key ('listen:<id>' / 'read:<id>', the page's PROG keys), kept by the app too so it
 * can go on after the app was closed: {i, t, at} (sentence, second, when). 30 days, at most 100, like the page.
 */
class ProgressStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("flow-progress", Context.MODE_PRIVATE)

    private fun all(): JSONObject {
        val o = try { JSONObject(prefs.getString("all", "{}") ?: "{}") } catch (e: Exception) { JSONObject() }
        val cut = System.currentTimeMillis() - DAYS * 86_400_000L
        o.keys().asSequence().toList().forEach { k -> if ((o.optJSONObject(k)?.optLong("at") ?: 0L) < cut) o.remove(k) }
        return o
    }

    fun get(key: String): JSONObject? = if (key.isEmpty()) null else all().optJSONObject(key)

    fun set(key: String, i: Int, t: Double) {
        if (key.isEmpty()) return
        val o = all()
        if (i > 0 || t > 1.0) o.put(key, JSONObject().put("i", i).put("t", t).put("at", System.currentTimeMillis())) else o.remove(key)
        val keys = o.keys().asSequence().toList()
        if (keys.size > MAX) keys.sortedBy { o.optJSONObject(it)?.optLong("at") ?: 0L }.take(keys.size - MAX).forEach { o.remove(it) }
        prefs.edit().putString("all", o.toString()).apply()
    }

    /** Read to the end: both sides clear theirs; this mark is for a page that missed the event (`{ended: true, at}`). */
    fun ended(key: String) {
        if (key.isEmpty()) return
        val o = all(); o.put(key, JSONObject().put("ended", true).put("at", System.currentTimeMillis()))
        prefs.edit().putString("all", o.toString()).apply()
    }

    fun clear(key: String) {
        if (key.isEmpty()) return
        val o = all(); o.remove(key)
        prefs.edit().putString("all", o.toString()).apply()
    }

    companion object {
        const val DAYS = 30
        const val MAX = 100
    }
}
