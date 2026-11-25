package cn.flowlang.app.notify

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId

class PlannerTest {
    private val zone = ZoneId.of("Asia/Shanghai")
    private fun at(s: String) = LocalDateTime.parse(s).atZone(zone).toInstant()
    private fun show(slots: List<Planner.Slot>) = slots.map { java.time.Instant.ofEpochMilli(it.atMillis).atZone(zone).toLocalDateTime().toString() + " " + it.kind }

    @Test fun everyDayAtTheHourForAWeek() {
        val p = Planner.plan(20, null, null, null, at("2026-11-25T10:00"), zone)
        assertEquals(7, p.size)
        assertEquals("2026-11-25T20:00 DAILY", show(p).first())
        assertEquals("2026-12-01T20:00 DAILY", show(p).last())
    }

    @Test fun todaysHourGoneStartsTomorrow() {
        val p = Planner.plan(8, null, null, null, at("2026-11-25T10:00"), zone)
        assertEquals("2026-11-26T08:00 DAILY", show(p).first())
        assertEquals(6, p.size)
    }

    @Test fun noReminderOnADayWithNothingDue() {
        val p = Planner.plan(20, null, intArrayOf(3, 0, 5, 2, 0, 1, 4), LocalDate.parse("2026-11-25"), at("2026-11-25T10:00"), zone)
        assertEquals(listOf("2026-11-25T20:00 DAILY", "2026-11-27T20:00 DAILY", "2026-11-28T20:00 DAILY", "2026-11-30T20:00 DAILY", "2026-12-01T20:00 DAILY"), show(p))
        assertEquals(3, p.first().due)
    }

    @Test fun onceReplacesTheDailiesBeforeItAndItsOwnDay() {
        // once tomorrow 12:30: today 20:00 (before it) and tomorrow 20:00 (its day) go; every day again after
        val once = at("2026-11-26T12:30").epochSecond.toDouble()
        val p = Planner.plan(20, once, null, null, at("2026-11-25T10:00"), zone)
        assertEquals(listOf("2026-11-26T12:30 ONCE", "2026-11-27T20:00 DAILY"), show(p).take(2))
        assertEquals(6, p.size)
    }

    @Test fun onceLaterTodayKeepsTomorrow() {
        val once = at("2026-11-25T21:00").epochSecond.toDouble()
        val p = Planner.plan(20, once, null, null, at("2026-11-25T10:00"), zone)
        assertEquals(listOf("2026-11-25T21:00 ONCE", "2026-11-26T20:00 DAILY"), show(p).take(2))
    }

    @Test fun aPastOnceIsForgotten() {
        val once = at("2026-11-25T09:00").epochSecond.toDouble()
        val p = Planner.plan(20, once, null, null, at("2026-11-25T10:00"), zone)
        assertTrue(p.none { it.kind == Planner.Kind.ONCE })
        assertEquals("2026-11-25T20:00 DAILY", show(p).first())
    }

    @Test fun theForecastIsReadFromTheDayItWasMade() {
        // made yesterday: today is its index 1
        val p = Planner.plan(20, null, intArrayOf(9, 0, 4, 4, 4, 4, 4), LocalDate.parse("2026-11-24"), at("2026-11-25T10:00"), zone)
        assertEquals("2026-11-26T20:00 DAILY", show(p).first())
        assertEquals(4, p.first().due)
        assertEquals(null, p.last().due)  // beyond the forecast: still reminded, count unknown
    }
}
