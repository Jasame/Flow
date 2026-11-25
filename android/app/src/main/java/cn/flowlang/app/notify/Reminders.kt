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
import cn.flowlang.app.Mute
import cn.flowlang.app.R
import cn.flowlang.app.net.Http
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter

/**
 * FlowApp.notify (docs/native-bridge.md §5): review reminders, and the day's plan, as the phone's own notifications. The
 * site stays the place where the hour and 这次什么时候复习 are set; the app reads them (with the WebView's cookies) when it
 * opens and when it goes to the background, and whenever the page says one changed (sync). Nothing leaves the phone.
 * Planner has the rules (the same as iOS). Exact to the minute where the phone allows exact alarms, else within ten minutes.
 */
object Reminders {
    const val CHANNEL = "review"
    private const val ACTION = "cn.flowlang.app.REMIND"
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var lastFetch = 0L
    private var generation = 0

    private fun prefs(c: Context) = c.getSharedPreferences("flow-remind", Context.MODE_PRIVATE)

    fun input(c: Context): Planner.Input =
        Planner.Input.fromJson(prefs(c).getString("input", null)?.let { try { JSONObject(it) } catch (e: Exception) { null } })

    private fun save(c: Context, x: Planner.Input) = prefs(c).edit().putString("input", x.toJson().toString()).apply()

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

    /**
     * 'granted': turned on in the app and allowed by the phone. 'undetermined': not turned on yet (or the system's question
     * can still come). 'denied': switched off in the settings, or refused for good (the page points to the settings).
     */
    fun permission(c: Context, askedBefore: Boolean, canAskAgain: Boolean): String = when {
        allowed(c) && input(c).app -> "granted"
        allowed(c) -> "undetermined"
        Build.VERSION.SDK_INT >= 33 && (!askedBefore || canAskAgain) -> "undetermined"
        else -> "denied"
    }

    /** Exact alarms are allowed here (always before Android 12; on 14+ only if the learner allowed 「闹钟和提醒」). */
    fun exact(c: Context): Boolean = Build.VERSION.SDK_INT < 31 || (c.getSystemService(AlarmManager::class.java)?.canScheduleExactAlarms() == true)

    /** The app's reminders on or off (ask() after the phone's permission; notify.off()). */
    fun setApp(c: Context, on: Boolean) {
        val x = input(c); x.app = on; save(c, x)
        schedule(c)
    }

    /**
     * The page's sync(r): r is its `reminder` ({hour, once, …}), maybe with forecast and `app` (true/false); null = off.
     * → {ok, permission, scheduled (how many), next (seconds), exact}
     */
    suspend fun sync(c: Context, r: JSONObject?, permission: String): JSONObject {
        val x = input(c)
        if (r == null) x.app = false else {
            if (r.has("app")) x.app = r.optBoolean("app")
            if (r.has("hour")) r.optInt("hour", -1).takeIf { it in Planner.HOURS }?.let { x.hour = it }
            if (r.has("once")) x.once = if (r.isNull("once")) null else r.optDouble("once").takeIf { !it.isNaN() }
            r.optJSONArray("forecast")?.let { a -> x.forecast = (0 until a.length()).map { a.optInt(it) } }
        }
        save(c, x)
        refresh(c, force = true)
        val list = scheduled(c)
        return JSONObject().put("ok", true).put("permission", permission).put("scheduled", list.size)
            .put("next", list.firstOrNull()?.let { it.at / 1000.0 } ?: JSONObject.NULL).put("exact", exact(c))
    }

    enum class Outcome { FRESH, SIGNED_OUT, PAUSED, OFFLINE }

    /** Ask the site for the counts and the reminder (when it is on), then put the next two weeks on the phone. */
    suspend fun refresh(c: Context, force: Boolean = false): Outcome {
        val app = c.applicationContext
        if (!input(app).app) { schedule(app); return Outcome.FRESH }
        if (!force && System.currentTimeMillis() - lastFetch < 10 * 60_000L) { schedule(app); return Outcome.FRESH }
        val mine = ++generation
        var outcome = Outcome.FRESH
        try {
            val r = Http.get("/api/next/vocab")
            if (mine != generation) return Outcome.FRESH  // a newer refresh is under way: its answer counts
            lastFetch = System.currentTimeMillis()
            when {
                r.code == 401 -> { save(app, Planner.signedOut(input(app))); outcome = Outcome.SIGNED_OUT }  // the plan stays
                // not agreed to 数据存放在香港: no reminders at all until it is (the hours are kept)
                r.code == 403 && r.json().optString("code") == "storage" -> { save(app, Planner.paused(input(app))); outcome = Outcome.PAUSED }
                r.ok -> save(app, Planner.input(r.json(), input(app)))
                else -> outcome = Outcome.OFFLINE
            }
        } catch (e: Exception) {
            outcome = Outcome.OFFLINE  // what was known last time
        }
        schedule(app)
        return outcome
    }

    fun refreshLater(c: Context, force: Boolean = false) {
        val app = c.applicationContext
        scope.launch { refresh(app, force) }
    }

    /** Put the planned reminders on the phone (taking off the old ones first). */
    fun schedule(c: Context): List<Planner.Slot> {
        cancelAll(c)
        var x = input(c)
        if (!x.app || !allowed(c)) { keep(c, emptyList()); return emptyList() }
        val slots = Planner.slots(x, Instant.now())
        x = Planner.remember(x, slots); save(c, x)
        val am = c.getSystemService(AlarmManager::class.java) ?: return emptyList()
        val exact = exact(c)
        slots.forEach { s ->
            val pi = pending(c, s)
            try {
                if (exact) am.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, s.at, pi)
                else am.setWindow(AlarmManager.RTC_WAKEUP, s.at, 10 * 60_000L, pi)
            } catch (e: SecurityException) {
                am.setWindow(AlarmManager.RTC_WAKEUP, s.at, 10 * 60_000L, pi)
            }
        }
        keep(c, slots)
        return slots
    }

    private fun intent(c: Context, id: String) = Intent(c, ReminderReceiver::class.java).setAction(ACTION).setData(Uri.parse("flow://remind/$id"))

    private fun pending(c: Context, s: Planner.Slot): PendingIntent = PendingIntent.getBroadcast(c, 0,
        intent(c, s.id).putExtra("id", s.id).putExtra("title", s.title).putExtra("body", s.body).putExtra("path", s.path),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

    /** What is on the phone now (kept by the app: the alarm manager cannot be asked). */
    private fun keep(c: Context, slots: List<Planner.Slot>) {
        val a = JSONArray()
        slots.forEach { a.put(JSONObject().put("id", it.id).put("at", it.at).put("title", it.title).put("body", it.body).put("path", it.path)) }
        prefs(c).edit().putString("slots", a.toString()).apply()
    }

    fun scheduled(c: Context): List<Planner.Slot> {
        val a = try { JSONArray(prefs(c).getString("slots", "[]")) } catch (e: Exception) { JSONArray() }
        val now = System.currentTimeMillis()
        return (0 until a.length()).mapNotNull { k -> a.optJSONObject(k) }
            .map { Planner.Slot(it.optString("id"), it.optLong("at"), it.optString("title"), it.optString("body"), it.optString("path")) }
            .filter { it.at > now }
    }

    /** FlowApp.notify.pending() → [{id, at (seconds), title, body}] */
    fun pendingJson(c: Context): JSONArray = JSONArray().also { a ->
        scheduled(c).forEach { a.put(JSONObject().put("id", it.id).put("at", it.at / 1000.0).put("title", it.title).put("body", it.body)) }
    }

    /** Is reminder [id] on the phone now (the tests). */
    fun isScheduled(c: Context, id: String): Boolean =
        PendingIntent.getBroadcast(c, 0, intent(c, id), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_NO_CREATE) != null

    fun cancelAll(c: Context) {
        val am = c.getSystemService(AlarmManager::class.java) ?: return
        val ids = scheduled(c).map { it.id } + (0 until 8).map { it.toString() }  // + the first version's numbered ones
        ids.forEach { id ->
            val pi = PendingIntent.getBroadcast(c, if (id.length == 1) id.toInt() else 0, intent(c, id), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_NO_CREATE)
                ?: return@forEach
            am.cancel(pi); pi.cancel()
        }
        keep(c, emptyList())
    }

    /**
     * 「加到手机日历」 tapped in the app and answered with 「App 通知」 (the phone's permission is given): the word review at its
     * hour, one time (`at`), or the day's plan. → the line to show.
     */
    suspend fun optIn(c: Context, plan: Boolean, hour: Int?, minutes: Int, at: Double?): String {
        val x = input(c)
        x.app = true
        if (plan) { x.planHour = (hour ?: 20).coerceIn(0, 23); x.planMinutes = minutes }
        else { hour?.takeIf { it in Planner.HOURS }?.let { x.hour = it }; at?.let { x.once = it } }
        save(c, x)
        val outcome = refresh(c, force = true)
        val list = scheduled(c)
        if (outcome == Outcome.PAUSED) return "先在页面上回答「数据存放在香港」那一问：同意以后，提醒会自己排上。"
        if (plan) return if (list.any { it.id.startsWith("plan-") }) "好，每天 ${input(c).planHour}:00 用通知提醒你今天的学习。不想要了，可以在手机的「设置 → 应用 → 语流 → 通知」里关掉。"
            else "没有排上，稍后再试一次。"
        if (outcome == Outcome.SIGNED_OUT) return "登录以后才能用通知提醒复习单词：先登录，再点一次。"
        val words = list.filter { it.id.startsWith("review-") }
        val h = input(c).hour
        if (at != null) return if (words.any { it.id == "review-once" }) "好，${label(at)} 用通知提醒你复习。"
            else "${label(at)} 那时还没有要复习的词，就不提醒了；之后每天 $h:00，有词要复习才提醒。"
        val off = if (outcome == Outcome.OFFLINE) "（现在没网，先按上次的情况排；连上网会自动更新）" else ""
        return if (words.isEmpty()) "好，每天 $h:00 有词要复习时用通知提醒你；这几天没有要复习的词。$off"
            else "好，每天 $h:00 用通知提醒你复习（那天有词要复习才提醒）。$off"
    }

    /** 「今天 12:30」「明天 8:00」 in China time. */
    fun label(secs: Double): String {
        val t = ZonedDateTime.ofInstant(Instant.ofEpochMilli((secs * 1000).toLong()), Planner.ZONE)
        val today = ZonedDateTime.now(Planner.ZONE).toLocalDate()
        val day = when (t.toLocalDate()) { today -> "今天"; today.plusDays(1) -> "明天"; else -> t.format(DateTimeFormatter.ofPattern("M月d日")) }
        return day + " " + t.format(DateTimeFormatter.ofPattern("H:mm"))
    }

    /** UI tests (beta builds): schedule from the given counts, without asking the server. */
    fun test(c: Context, a: JSONObject): JSONObject {
        var x = Planner.input(a, input(c))
        if (a.has("app")) x = x.copy(app = a.optBoolean("app"))
        if (a.has("planHour")) x = x.copy(planHour = if (a.isNull("planHour")) null else a.optInt("planHour"))
        save(c, x)
        schedule(c)
        return JSONObject().put("ok", true).put("pending", pendingJson(c))
    }

    /** The notification itself; a tap opens [path] (#/review, #/), the app running or not. */
    fun show(c: Context, id: String, title: String, body: String, path: String) {
        if (!allowed(c)) return
        channel(c)
        val open = PendingIntent.getActivity(c, id.hashCode(), Intent(c, MainActivity::class.java).setAction(Intent.ACTION_VIEW)
            .putExtra(MainActivity.EXTRA_PATH, "/" + path).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val n = NotificationCompat.Builder(c, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_flow)
            .setColor(ContextCompat.getColor(c, R.color.flow_green))
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(open)
            .setAutoCancel(true)
            .setSilent(Mute.on)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .build()
        try { NotificationManagerCompat.from(c).notify(if (id.startsWith("plan")) NOTE_PLAN else NOTE_REVIEW, n) } catch (e: SecurityException) { /* not allowed after all */ }
    }

    const val NOTE_REVIEW = 2001
    const val NOTE_PLAN = 2002
}

/** A reminder is due: show it, then put the rest back from what is kept (no network needed). */
class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, intent: Intent) {
        Reminders.show(c, intent.getStringExtra("id") ?: "review", intent.getStringExtra("title") ?: "该复习单词了",
            intent.getStringExtra("body") ?: "花几分钟，把今天到期的单词复习一下", intent.getStringExtra("path") ?: "#/review")
        Reminders.schedule(c)
    }
}

/** After a restart, an update, a change of time or time zone, or of the exact-alarm permission: put them back. */
class RescheduleReceiver : BroadcastReceiver() {
    override fun onReceive(c: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED, Intent.ACTION_TIME_CHANGED, Intent.ACTION_TIMEZONE_CHANGED,
            AlarmManager.ACTION_SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED -> Reminders.schedule(c)
        }
    }
}
