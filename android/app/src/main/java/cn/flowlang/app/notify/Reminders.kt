package cn.flowlang.app.notify

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import cn.flowlang.app.MainActivity
import cn.flowlang.app.R
import cn.flowlang.app.net.Http
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

/**
 * FlowApp.notify: review reminders as the phone's own notifications, from the reminder the server keeps
 * (/api/next/vocab → reminder {hour, once, …} and forecast). The page calls sync() whenever the reminder changes;
 * the app also fetches it when it opens or comes back to the front, and puts them back after a restart.
 *
 * They are on only after the learner turned them on (ask(): 「到点用 App 通知提醒」), and only while the phone allows
 * notifications. On time to the minute where exact alarms are allowed, otherwise within about ten minutes.
 */
object Reminders {
    const val CHANNEL = "review"
    private const val MAX_SLOTS = 8
    private const val ACTION = "cn.flowlang.app.REMIND"
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private fun prefs(c: Context) = c.getSharedPreferences("flow-remind", Context.MODE_PRIVATE)

    fun channel(c: Context) {
        val nm = c.getSystemService(NotificationManager::class.java) ?: return
        nm.createNotificationChannel(NotificationChannel(CHANNEL, c.getString(R.string.channel_review), NotificationManager.IMPORTANCE_DEFAULT)
            .apply { description = c.getString(R.string.channel_review_about) })
    }

    /** The phone allows the app's notifications (Android 13+: the permission; before: not switched off in settings). */
    fun allowed(c: Context): Boolean {
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(c, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return false
        return NotificationManagerCompat.from(c).areNotificationsEnabled()
    }

    fun optedIn(c: Context) = prefs(c).getBoolean("on", false)

    fun setOptedIn(c: Context, on: Boolean) {
        prefs(c).edit().putBoolean("on", on).apply()
        if (on) reschedule(c) else cancelAll(c)
    }

    /**
     * 'granted' (turned on and allowed), 'denied' (the phone does not allow it: the page should point to the settings),
     * 'undetermined' (not turned on yet). [askedBefore]/[canAskAgain] come from MainActivity (Android 13+ dialog).
     */
    fun permission(c: Context, askedBefore: Boolean, canAskAgain: Boolean): String = when {
        allowed(c) && optedIn(c) -> "granted"
        allowed(c) -> "undetermined"  // the phone allows it; not turned on in the app yet
        Build.VERSION.SDK_INT >= 33 && (!askedBefore || canAskAgain) -> "undetermined"  // the system dialog can still come
        else -> "denied"  // switched off in the settings, or refused for good
    }

    /** Exact alarms are allowed here (always before Android 12; on 14+ only if the learner allowed 「闹钟和提醒」). */
    fun exact(c: Context): Boolean = Build.VERSION.SDK_INT < 31 || (c.getSystemService(AlarmManager::class.java)?.canScheduleExactAlarms() == true)

    /** The page's sync(r): r = reminder (+ forecast). Kept, and scheduled when reminders are on. */
    fun sync(c: Context, r: JSONObject): JSONObject {
        val p = prefs(c).edit()
        if (r.has("hour")) p.putInt("hour", r.optInt("hour", 20))
        if (r.has("once")) { val o = r.optDouble("once", Double.NaN); if (o.isNaN()) p.remove("once") else p.putString("once", o.toString()) }
        r.optJSONArray("forecast")?.let { p.putString("forecast", it.toString()).putString("forecastDay", LocalDate.now().toString()) }
        p.apply()
        val slots = reschedule(c)
        return JSONObject().put("ok", true).put("on", optedIn(c) && allowed(c)).put("exact", exact(c))
            .put("scheduled", JSONArray().also { a -> slots.forEach { s -> a.put(s.atMillis / 1000) } })
    }

    /** What is kept, planned from now: the reminders that will come. */
    fun planned(c: Context): List<Planner.Slot> {
        val sp = prefs(c)
        val fc = sp.getString("forecast", null)?.let { s -> try { JSONArray(s).let { a -> IntArray(a.length()) { a.optInt(it) } } } catch (e: Exception) { null } }
        val fDay = sp.getString("forecastDay", null)?.let { try { LocalDate.parse(it) } catch (e: Exception) { null } }
        return Planner.plan(sp.getInt("hour", 20), sp.getString("once", null)?.toDoubleOrNull(), fc, fDay, Instant.now(), ZoneId.systemDefault())
            .take(MAX_SLOTS)
    }

    /** Put the planned reminders on the phone (first taking off the old ones). */
    fun reschedule(c: Context): List<Planner.Slot> {
        cancelAll(c)
        if (!optedIn(c) || !allowed(c)) return emptyList()
        val am = c.getSystemService(AlarmManager::class.java) ?: return emptyList()
        val slots = planned(c)
        val exact = exact(c)
        slots.forEachIndexed { k, s ->
            val pi = pending(c, k, s)
            try {
                if (exact) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, s.atMillis, pi)
                else am.setWindow(AlarmManager.RTC_WAKEUP, s.atMillis, 10 * 60_000L, pi)
            } catch (e: SecurityException) {
                am.setWindow(AlarmManager.RTC_WAKEUP, s.atMillis, 10 * 60_000L, pi)
            }
        }
        prefs(c).edit().putInt("count", slots.size).apply()
        return slots
    }

    private fun pending(c: Context, k: Int, s: Planner.Slot?): PendingIntent {
        val i = Intent(c, ReminderReceiver::class.java).setAction(ACTION).setData(Uri.parse("flow://remind/$k"))
        if (s != null) i.putExtra("kind", s.kind.name).putExtra("due", s.due ?: -1).putExtra("at", s.atMillis)
        return PendingIntent.getBroadcast(c, k, i, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }

    /** Is reminder [k] on the phone now (the tests). */
    fun isScheduled(c: Context, k: Int): Boolean =
        PendingIntent.getBroadcast(c, k, Intent(c, ReminderReceiver::class.java).setAction(ACTION).setData(Uri.parse("flow://remind/$k")),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_NO_CREATE) != null

    fun cancelAll(c: Context) {
        val am = c.getSystemService(AlarmManager::class.java) ?: return
        for (k in 0 until MAX_SLOTS) {
            val pi = PendingIntent.getBroadcast(c, k, Intent(c, ReminderReceiver::class.java).setAction(ACTION).setData(Uri.parse("flow://remind/$k")),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_NO_CREATE) ?: continue
            am.cancel(pi); pi.cancel()
        }
    }

    /** The app opened or came back to the front: the reminder as the server has it now (only when they are on). */
    fun refresh(c: Context) {
        if (!optedIn(c)) return
        val app = c.applicationContext
        scope.launch {
            val r = try { Http.get("/api/next/vocab") } catch (e: Exception) { return@launch }
            if (r.code == 401) { cancelAll(app); return@launch }  // signed out: no reminders for that account
            if (!r.ok) return@launch
            val o = r.json()
            val rem = o.optJSONObject("reminder") ?: return@launch
            o.optJSONArray("forecast")?.let { rem.put("forecast", it) }
            sync(app, rem)
        }
    }

    /** The notification itself. */
    fun show(c: Context, kind: String, due: Int) {
        if (!allowed(c)) return
        channel(c)
        val open = PendingIntent.getActivity(c, 1, Intent(c, MainActivity::class.java).setAction(Intent.ACTION_VIEW)
            .putExtra(MainActivity.EXTRA_PATH, "/#/review").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val title = if (kind == Planner.Kind.ONCE.name) "你约的复习时间到了" else "该复习单词了"
        val text = if (due > 0) "今天有 $due 个词到期，花几分钟复习一下" else "花几分钟，把今天到期的单词复习一下"
        val n = NotificationCompat.Builder(c, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_flow)
            .setColor(ContextCompat.getColor(c, R.color.flow_green))
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(open)
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .build()
        try { NotificationManagerCompat.from(c).notify(NOTE_ID, n) } catch (e: SecurityException) { /* not allowed after all */ }
    }

    const val NOTE_ID = 2001
}

/** A reminder is due: show it, then put the next week's back (the plan rolls forward one day at a time). */
class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, intent: Intent) {
        val kind = intent.getStringExtra("kind") ?: Planner.Kind.DAILY.name
        if (kind == Planner.Kind.ONCE.name) c.getSharedPreferences("flow-remind", Context.MODE_PRIVATE).edit().remove("once").apply()
        Reminders.show(c, kind, intent.getIntExtra("due", -1))
        Reminders.reschedule(c)
    }
}

/** After a restart, an update, a change of time or time zone, or of the exact-alarm permission: put them back. */
class RescheduleReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED, Intent.ACTION_TIME_CHANGED, Intent.ACTION_TIMEZONE_CHANGED,
            AlarmManager.ACTION_SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED -> Reminders.reschedule(c)
        }
    }
}
