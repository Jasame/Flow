package cn.flowlang.app.notify

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.temporal.ChronoUnit

/**
 * Which reminders to put on the phone, from what the site says (GET /api/next/vocab): docs/native-bridge.md §5, the same
 * rules and words as the iOS app's ReminderPlan (and the server's mail, vocab_service.send_reminders):
 * - Hours are China time, as the mail and the site's .ics are (next_service.TZ, UTC+8).
 * - Every day at the reminder hour, only on a day with words to review: today, what is left now (beyond the day's share
 *   too); a later day, the forecast up to that day (words not reviewed stay due) plus the book's new words while the book
 *   is not finished; after the forecast, every day while there are words or a book. Refreshed whenever the app opens or
 *   goes to the background, so a day done is taken off.
 * - 这次什么时候复习 (once): while it is ahead, no daily one before it; at that time it comes if that day has words; then no
 *   daily one that day; after it, every day again. A once with nothing to review lapses (that day's hour comes as usual).
 * - The day's plan (我的 → 每天提醒, chosen in the app): every day at its hour; a word reminder at the same time is left out
 *   (the plan has the words in it). It needs no account.
 * - An account that has not agreed to 数据存放在香港 (403 code storage): no reminders at all, the plan's neither, until the
 *   site answers again (the site sends that account none either, privacy_service).
 * No Android here, so the JVM tests can check it.
 */
object Planner {
    const val DAYS = 14
    val HOURS = 6..23  // vocab_service.REMIND_HOURS
    /** China time, as the server's mail, its forecast days and its .ics. */
    val ZONE: ZoneId = ZoneOffset.ofHours(8)

    data class Input(
        var hour: Int = 20,
        var once: Double? = null,       // seconds since 1970, ahead (the server forgets it once past)
        var onceSeen: Double? = null,   // the latest once that went on the phone, kept after it passed
        var due: Int = 0,               // today, still to review now
        var new: Int = 0,               // today's new words still to learn
        var later: Int = 0,             // due today beyond the day's share
        var minutes: Int = 0,
        var forecast: List<Int> = emptyList(),  // reviews due on each of the next days (0 = today, overdue in it)
        var dailyNew: Int = 0,          // the book's new words a day, while the book is not finished
        var hasWords: Boolean = false,  // any word cards at all
        var planHour: Int? = null,      // the day's plan reminder (from the app; null = off)
        var planMinutes: Int = 10,
        // The learner turned the app's reminders on (notify.ask / 「到点用 App 通知提醒」). Off until then on Android: before
        // Android 13 the phone allows notifications without asking, so that cannot be the question (iOS: it is).
        var app: Boolean = false,
        var paused: Boolean = false,    // the account has not agreed to 数据存放在香港 (403 code storage): no reminders at all
    ) {
        fun toJson(): JSONObject = JSONObject().put("hour", hour).put("once", once ?: JSONObject.NULL).put("onceSeen", onceSeen ?: JSONObject.NULL)
            .put("due", due).put("new", new).put("later", later).put("minutes", minutes).put("forecast", JSONArray(forecast))
            .put("dailyNew", dailyNew).put("hasWords", hasWords).put("planHour", planHour ?: JSONObject.NULL).put("planMinutes", planMinutes)
            .put("app", app).put("paused", paused)

        companion object {
            fun fromJson(o: JSONObject?): Input {
                if (o == null) return Input()
                return Input(
                    hour = o.optInt("hour", 20), once = o.optDoubleOrNull("once"), onceSeen = o.optDoubleOrNull("onceSeen"),
                    due = o.optInt("due"), new = o.optInt("new"), later = o.optInt("later"), minutes = o.optInt("minutes"),
                    forecast = o.optJSONArray("forecast").ints(), dailyNew = o.optInt("dailyNew"), hasWords = o.optBoolean("hasWords"),
                    planHour = if (o.isNull("planHour") || !o.has("planHour")) null else o.optInt("planHour"),
                    planMinutes = o.optInt("planMinutes", 10), app = o.optBoolean("app", false), paused = o.optBoolean("paused", false),
                )
            }
        }
    }

    data class Slot(val id: String, val at: Long, val title: String, val body: String, val path: String)

    fun slots(x: Input, now: Instant, zone: ZoneId = ZONE): List<Slot> {
        if (!x.app || x.paused) return emptyList()
        val out = ArrayList<Slot>()
        val today = now.atZone(zone).toLocalDate()
        fun dayOf(i: Instant) = ChronoUnit.DAYS.between(today, i.atZone(zone).toLocalDate()).toInt()
        // words to review on day k (k = 0: today, what is left now); -1: not known, but there are words
        fun count(k: Int): Int = when {
            k <= 0 -> x.due + x.new + x.later
            k < x.forecast.size -> x.forecast.subList(0, k + 1).sum() + x.dailyNew
            else -> if (x.hasWords || x.dailyNew > 0) -1 else 0
        }
        val once = x.once?.let { secs(it) }?.takeIf { it.isAfter(now) }
        val onceCounts = once?.let { count(dayOf(it)) != 0 } ?: false
        // the day of a once that already came (or will, with words): its daily one does not
        val onceDay: LocalDate? = ((if (once != null && onceCounts) once else null)
            ?: x.onceSeen?.let { secs(it) }?.takeIf { !it.isAfter(now) })?.atZone(zone)?.toLocalDate()
        val soon = now.plusSeconds(60)
        for (k in 0 until DAYS) {
            val day = today.plusDays(k.toLong())
            val tag = day.toString()
            var planAt: Instant? = null
            x.planHour?.let { ph ->
                val t = day.atTime(ph.coerceIn(0, 23), 0).atZone(zone).toInstant()
                if (t.isAfter(soon)) {
                    planAt = t
                    out += Slot("plan-$tag", t.toEpochMilli(), "今天的学习", "打开今天的计划：到期的单词、今天这篇材料、该复习的语法点，大约 ${x.planMinutes} 分钟。", "#/")
                }
            }
            val t = day.atTime(x.hour.coerceIn(0, 23), 0).atZone(zone).toInstant()
            if (!t.isAfter(soon)) continue
            if (once != null && t.isBefore(once)) continue      // waiting for the chosen time
            if (onceDay != null && day == onceDay) continue      // that day's reminder was the chosen one
            if (planAt != null && planAt == t) continue
            val n = count(k)
            if (n == 0) continue
            val due = if (k < x.forecast.size) x.forecast[k] else 0
            val body = when {
                k == 0 -> "今天还有 $n 个词等你复习" + (if (x.minutes > 0) "，大约 ${x.minutes} 分钟。" else "。") + "记忆曲线到点了，现在复习效果最好。"
                due > 0 -> "今天大约有 $due 个词到期。记忆曲线到点了，现在复习效果最好。"
                n > x.dailyNew -> "还有没复习完的词在等你，几分钟就好。"
                x.dailyNew > 0 -> "今天的新词准备好了，复习加新词几分钟就好。"
                else -> "到期的单词在等你，记忆曲线到点了，现在复习效果最好。"
            }
            out += Slot("review-$tag", t.toEpochMilli(), "该复习单词了", body, "#/review")
        }
        if (once != null && onceCounts) {
            val n = count(dayOf(once))
            out += Slot("review-once", once.toEpochMilli(), "到你选的复习时间了",
                if (n > 0) "你选的复习时间到了：$n 个词等你，现在复习记得最牢。" else "你选的复习时间到了，现在复习记得最牢。", "#/review")
        }
        return out.sortedBy { it.at }
    }

    /** From GET /api/next/vocab (reminder, forecast, counts, plan, book, total); keeps what only the app knows. */
    fun input(j: JSONObject, old: Input): Input {
        val x = old.copy()
        j.optJSONObject("reminder")?.let { r ->
            if (r.has("hour")) r.optInt("hour", -1).takeIf { it in HOURS }?.let { x.hour = it }
            if (r.has("once")) x.once = r.optDoubleOrNull("once")  // an older server does not know it: the app's stays
        }
        x.due = j.optInt("due"); x.new = j.optInt("new"); x.later = j.optInt("later"); x.minutes = j.optInt("minutes")
        x.forecast = j.optJSONArray("forecast").ints()
        val plan = j.optJSONObject("plan"); val book = j.optJSONObject("book")
        val bookOn = if (book != null) !book.optBoolean("done", false) else plan != null
        val paused = j.optBoolean("new_paused", false)
        x.dailyNew = if (bookOn && !paused) (plan?.optInt("daily_new", 0) ?: 0).coerceAtLeast(0) else 0
        x.hasWords = j.optInt("total", 0) > 0
        x.paused = false  // the site answered: the account is in use again
        return x
    }

    /** After scheduling: a once that went on the phone is remembered, so after it passed (and the server forgot it) that
     *  day's daily reminder still stays away. A once with nothing to review was not scheduled: it lapses. */
    fun remember(x: Input, scheduled: List<Slot>): Input {
        val o = x.once ?: return x
        return if (scheduled.any { it.id == "review-once" }) x.copy(onceSeen = maxOf(o, x.onceSeen ?: 0.0)) else x
    }

    /** Signed out: no word reminders for an account that is not here (the day's plan needs none). */
    fun signedOut(old: Input) = Input(planHour = old.planHour, planMinutes = old.planMinutes, app = old.app)

    /**
     * The account has not given a consent the site needs: 数据存放在香港 (code storage: an older account until it answers,
     * a paused one after 不同意) or the current 用户协议 and 隐私和数据 (code terms: asked again whenever their version
     * changes), or one this app does not know yet. Every signed-in request is then 403 and the site sends it no reminders;
     * neither does the app, not even the day's plan. The hours are kept: the next answer from the site brings them back.
     */
    fun paused(old: Input) = signedOut(old).copy(paused = true)

    /** What 「App 通知」 says while paused, by the 403's code (the page itself shows what to agree to). */
    fun pausedLine(code: String?): String = when (code) {
        "storage" -> "先在页面上回答「数据存放在香港」那一问：同意以后，提醒会自己排上。"
        "terms" -> "先在页面上同意《用户协议》和《隐私和数据》：同意以后，提醒会自己排上。"
        else -> "这个账号现在排不了提醒：先按页面上的提示处理，处理好以后提醒会自己排上。"
    }

    private fun secs(s: Double): Instant = Instant.ofEpochMilli((s * 1000).toLong())
    private fun JSONObject.optDoubleOrNull(k: String): Double? = if (!has(k) || isNull(k)) null else optDouble(k).takeIf { !it.isNaN() }
    private fun JSONArray?.ints(): List<Int> = if (this == null) emptyList() else (0 until length()).map { optInt(it) }
}
