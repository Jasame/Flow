package cn.flowlang.app

import android.app.AlertDialog
import android.content.Context
import android.content.res.Configuration

/**
 * The page's 主题色 (「我的 → 外观」, EIDOS #282): 松绿 (the default) or 靛蓝, for what the app draws itself: its dialogs,
 * the reminder notification, the update's progress bar. The page says which (assets/flowapp-android.js reads
 * <html data-accent> and sends app.accent when it changes); it is kept, so a reminder shown with the app closed matches.
 * Only the accent changes: the logo, right/wrong colours and the 「AI 朗读」 label stay as they are.
 */
object Accent {
    const val GREEN = "green"
    const val INDIGO = "indigo"

    /** What the page sent → one of the two (anything else, or nothing, is 松绿). */
    fun normalize(value: String?): String = if (value == INDIGO) INDIGO else GREEN

    /** The accent in the page's own values (flow/public/src/next/00-base.css and 99-accent.css). */
    fun colorOf(name: String, night: Boolean): Int = when {
        name == INDIGO && night -> 0xFF8EAEFC.toInt()
        name == INDIGO -> 0xFF3461D1.toInt()
        night -> 0xFF3CCF7C.toInt()
        else -> 0xFF1F9D55.toInt()
    }

    private fun prefs(c: Context) = c.getSharedPreferences("flow-app", Context.MODE_PRIVATE)

    fun name(c: Context): String = normalize(prefs(c).getString("accent", GREEN))

    /** app.accent from the page. */
    fun set(c: Context, value: String?) {
        val v = normalize(value)
        if (v != name(c)) prefs(c).edit().putString("accent", v).apply()
    }

    private fun night(c: Context) =
        c.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES

    fun color(c: Context): Int = colorOf(name(c), night(c))

    /** Every dialog the app shows: its buttons in the accent (Flow.Dialog.Green / Indigo in res/values and values-night). */
    fun dialog(c: Context): AlertDialog.Builder =
        AlertDialog.Builder(c, if (name(c) == INDIGO) R.style.Flow_Dialog_Indigo else R.style.Flow_Dialog_Green)
}
