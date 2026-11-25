package cn.flowlang.app.notify

import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit

/**
 * Which review reminders to put on the phone, by the server's own rules (vocab_service.send_reminders, the
 * reminder `once` of 语流 11's remindOnce()):
 *  - every day at hour:00 for the next 7 days, but not on a day with no words due (forecast);
 *  - once (a time today or tomorrow the learner chose) replaces the daily reminders before it, and that day has no
 *    daily one; after it, every day again.
 * No Android here, so the JVM tests can check it.
 */
object Planner {
    enum class Kind { DAILY, ONCE }

    data class Slot(val atMillis: Long, val kind: Kind, val due: Int?)

    /**
     * @param hour the daily hour (6–23)
     * @param onceSec the once reminder, epoch seconds, or null
     * @param forecast words due on each of 7 days from [forecastDay] (index 0 = that day), or null when unknown
     */
    fun plan(hour: Int, onceSec: Double?, forecast: IntArray?, forecastDay: LocalDate?, now: Instant, zone: ZoneId, days: Int = 7): List<Slot> {
        val today = now.atZone(zone).toLocalDate()
        val once = onceSec?.let { Instant.ofEpochMilli((it * 1000).toLong()) }?.takeIf { it.isAfter(now) }
        val onceDay = once?.atZone(zone)?.toLocalDate()
        val out = ArrayList<Slot>()
        for (d in 0 until days) {
            val day = today.plusDays(d.toLong())
            val at = day.atTime(hour.coerceIn(0, 23), 0).atZone(zone).toInstant()
            if (!at.isAfter(now)) continue
            val due = dueOn(forecast, forecastDay, day)
            if (due == 0) continue
            if (once != null && (at.isBefore(once) || day == onceDay)) continue
            out += Slot(at.toEpochMilli(), Kind.DAILY, due)
        }
        if (once != null) out += Slot(once.toEpochMilli(), Kind.ONCE, dueOn(forecast, forecastDay, onceDay!!))
        return out.sortedBy { it.atMillis }
    }

    /** Words due on [day] by the forecast; null when the forecast does not reach that day. */
    fun dueOn(forecast: IntArray?, forecastDay: LocalDate?, day: LocalDate): Int? {
        if (forecast == null || forecastDay == null) return null
        val k = ChronoUnit.DAYS.between(forecastDay, day)
        return if (k in forecast.indices) forecast[k.toInt()] else null
    }
}
