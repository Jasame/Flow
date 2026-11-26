package cn.flowlang.app.notify

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId

/** The same examples as the iOS app's ReminderPlanTests (docs/native-bridge.md §5), so the platforms agree. */
class PlannerTest {
    private val zone = ZoneId.of("Asia/Shanghai")
    private fun at(day: Int, hour: Int, minute: Int = 0): Instant = LocalDateTime.of(2026, 11, day, hour, minute).atZone(zone).toInstant()
    private fun secs(i: Instant) = i.epochSecond.toDouble()

    private fun input(f: Planner.Input.() -> Unit = {}): Planner.Input =
        Planner.Input(hour = 20, due = 12, new = 0, minutes = 6, forecast = listOf(12, 5, 0, 7, 3, 0, 2), hasWords = true, app = true).apply(f)

    private fun ids(s: List<Planner.Slot>) = s.map { it.id }

    @Test fun everyDayAtTheHourOnlyWithWords() {
        val s = Planner.slots(input(), at(25, 9), zone)
        val ids = ids(s)
        assertEquals("review-2026-11-25", ids.first())
        assertTrue(ids.contains("review-2026-11-26"))
        assertTrue("words not reviewed stay due (the mail counts them)", ids.contains("review-2026-11-27"))
        assertTrue("after the forecast: every day while there are words", ids.contains("review-2026-12-08"))
        assertEquals(at(25, 20).toEpochMilli(), s.first().at)
        assertTrue(s.first().body.contains("12 个词"))
        assertTrue(s.all { it.path == "#/review" })
    }

    @Test fun noWordsAtAllNoReminders() {
        val s = Planner.slots(input { due = 0; forecast = listOf(0, 0, 0, 0, 0, 0, 0); hasWords = false }, at(25, 9), zone)
        assertTrue(ids(s).joinToString(" "), s.isEmpty())
    }

    @Test fun chinaTimeByDefault() {
        val s = Planner.slots(input(), at(25, 9))  // Planner.ZONE: UTC+8 whatever the phone's zone
        assertEquals(at(25, 20).toEpochMilli(), s.first().at)
    }

    @Test fun nothingLeftTodayMeansNoReminderToday() {
        assertFalse(ids(Planner.slots(input { due = 0; new = 0 }, at(25, 9), zone)).contains("review-2026-11-25"))
        assertTrue("beyond the day's share counts too", ids(Planner.slots(input { due = 0; new = 0; later = 30 }, at(25, 9), zone)).contains("review-2026-11-25"))
    }

    @Test fun pastTheHourTodayStartsTomorrow() {
        assertEquals("review-2026-11-26", Planner.slots(input(), at(25, 21), zone).first().id)
    }

    @Test fun onceReplacesTheDailyOnesUntilThenAndThatDay() {
        // 这次什么时候复习: tomorrow 12:30 — no 20:00 today, none tomorrow evening, then daily again
        val once = at(26, 12, 30)
        val s = Planner.slots(input { this.once = secs(once) }, at(25, 9), zone)
        val ids = ids(s)
        assertEquals("review-once", ids.first())
        assertEquals(once.toEpochMilli(), s.first().at)
        assertFalse(ids.contains("review-2026-11-25"))
        assertFalse(ids.contains("review-2026-11-26"))
        assertTrue(ids.contains("review-2026-11-28"))
    }

    @Test fun aOnceThatCameTakesThatDay() {
        // 12:30 came (the server forgot it, the app did not): no second reminder at 20:00 that day
        val s = Planner.slots(input { once = null; onceSeen = secs(at(25, 12, 30)) }, at(25, 13), zone)
        assertFalse(ids(s).contains("review-once"))
        assertFalse(ids(s).contains("review-2026-11-25"))
        assertEquals("review-2026-11-26", s.first().id)
    }

    @Test fun onlyAOnceThatWasScheduledTakesItsDay() {
        // 15:00 chosen with words: scheduled and remembered; after it passed, 20:00 that day stays away
        val once = at(25, 15)
        var x = input { this.once = secs(once) }
        x = Planner.remember(x, Planner.slots(x, at(25, 9), zone))
        assertEquals(secs(once), x.onceSeen)
        x.once = null  // the server forgot it
        assertFalse(ids(Planner.slots(x, at(25, 16), zone)).contains("review-2026-11-25"))
        // 15:00 chosen with nothing to review: not scheduled, not remembered; new words due by 20:00 still get their reminder
        var y = input { this.once = secs(once); due = 0; new = 0; later = 0 }
        y = Planner.remember(y, Planner.slots(y, at(25, 9), zone))
        assertNull(y.onceSeen)
        y.once = null
        y.due = 4
        assertTrue(ids(Planner.slots(y, at(25, 16), zone)).contains("review-2026-11-25"))
    }

    @Test fun onceWithNothingToReviewDoesNotCome() {
        // tomorrow 8:00 chosen, nothing due then and no book: no reminder then, and none before it
        val s = Planner.slots(input { once = secs(at(26, 8)); due = 0; forecast = listOf(0, 0, 0, 0, 0, 0, 0); hasWords = false }, at(25, 9), zone)
        assertTrue(ids(s).joinToString(" "), s.isEmpty())
    }

    @Test fun thePlanReminderAndNoDoubleAtTheSameHour() {
        val s = Planner.slots(input { planHour = 20; planMinutes = 15 }, at(25, 9), zone)
        val today = s.filter { it.id.endsWith("2026-11-25") }
        assertEquals("the plan has the words in it", listOf("plan-2026-11-25"), today.map { it.id })
        assertTrue(today[0].body.contains("15 分钟"))
        assertEquals("#/", today[0].path)
    }

    @Test fun turnedOffInTheApp() {
        assertTrue(Planner.slots(input { app = false }, at(25, 9), zone).isEmpty())
    }

    @Test fun offUntilTheLearnerTurnsItOnOnAndroid() {
        assertFalse(Planner.Input().app)
    }

    @Test fun inputFromTheSite() {
        val j = JSONObject().put("reminder", JSONObject().put("hour", 21).put("once", 1_795_600_000.0).put("enabled", false))
            .put("due", 4).put("new", 10).put("minutes", 7).put("forecast", JSONArray(listOf(4, 3, 2, 1, 0, 0, 5)))
            .put("plan", JSONObject().put("daily_new", 10).put("book", "cet4")).put("total", 120)
        val x = Planner.input(j, Planner.Input(planHour = 8))
        assertEquals(21, x.hour)
        assertEquals(1_795_600_000.0, x.once!!, 0.0)
        assertEquals(4, x.due)
        assertEquals(10, x.new)
        assertEquals(listOf(4, 3, 2, 1, 0, 0, 5), x.forecast)
        assertEquals(10, x.dailyNew)
        assertTrue(x.hasWords)
        assertEquals("the app's own setting is kept", 8, x.planHour)
        assertNull(Planner.input(JSONObject().put("reminder", JSONObject().put("hour", 21).put("once", JSONObject.NULL)), x).once)
        assertEquals("a server without once leaves the app's alone", 1_795_600_000.0, Planner.input(JSONObject().put("reminder", JSONObject().put("hour", 21)), x).once!!, 0.0)
        assertEquals("a finished book brings no new words", 0,
            Planner.input(JSONObject().put("plan", JSONObject().put("daily_new", 10)).put("book", JSONObject().put("done", true)), x).dailyNew)
        assertEquals("hours outside REMIND_HOURS are not taken", 21, Planner.input(JSONObject().put("reminder", JSONObject().put("hour", 3)), x).hour)
    }

    @Test fun theLineSaysWhichConsentIsMissing() {
        // 403 code storage, terms (用户协议 and 隐私和数据, asked again when their version changes) or one not known yet:
        // all pause the reminders (Reminders.refresh); 「App 通知」 says what the page will ask for
        assertTrue(Planner.pausedLine("storage").contains("数据存放在香港"))
        assertTrue(Planner.pausedLine("terms").contains("《用户协议》"))
        assertTrue(Planner.pausedLine("something-new").contains("页面上的提示"))
        assertTrue(Planner.pausedLine(null).contains("页面上的提示"))
        // the site answers code storage for every missing consent and says which one in `need` (B6, 2026-11-25)
        assertEquals("terms", Planner.consentNeeded(JSONObject().put("code", "storage").put("need", "terms")))
        assertEquals("storage", Planner.consentNeeded(JSONObject().put("code", "storage").put("need", "storage")))
        assertEquals("storage", Planner.consentNeeded(JSONObject().put("code", "storage")))   // a site from before `need`
        assertEquals(null, Planner.consentNeeded(JSONObject()))
    }

    @Test fun notAgreedToHongKongStorageNoRemindersUntilAgreed() {
        // 403 code storage (an older account before it answers, a paused one after 不同意): the site sends no reminders,
        // the app neither, not even the day's plan; agreeing brings them back on the next refresh
        val once = secs(at(26, 12))
        val x = Planner.paused(input { planHour = 8; this.once = once })
        assertTrue(x.paused)
        assertEquals("the plan's hour is kept for later", 8, x.planHour)
        assertTrue(Planner.slots(x, at(25, 7), zone).isEmpty())
        assertTrue("still paused after the app is closed", Planner.Input.fromJson(JSONObject(x.toJson().toString())).paused)
        val back = Planner.input(JSONObject().put("reminder", JSONObject().put("hour", 21)).put("due", 3)
            .put("forecast", JSONArray(listOf(3, 2))).put("total", 40), x)
        assertFalse(back.paused)
        val s = Planner.slots(back, at(25, 7), zone)
        assertTrue(s.any { it.id == "review-2026-11-25" && it.at == at(25, 21).toEpochMilli() })
        assertTrue(s.any { it.id == "plan-2026-11-25" })
        assertFalse("signing out (or in as someone else) starts over", Planner.signedOut(x).paused)
    }

    /** account.changed (Reminders.accountChanged): the last account's hour, counts and 这次什么时候复习 go; this phone's stay. */
    @Test fun anotherAccountKeepsOnlyThisPhonesSettings() {
        val last = input {
            hour = 7; once = 1_795_600_000.0; onceSeen = 1_795_600_000.0; due = 12; forecast = listOf(3, 4); dailyNew = 10
            hasWords = true; planHour = 8; planMinutes = 15; app = true; paused = true
        }
        val x = Planner.signedOut(last)
        assertTrue("the switch is this phone's", x.app)
        assertEquals(8, x.planHour)
        assertEquals(15, x.planMinutes)
        assertEquals(20, x.hour)
        assertNull(x.once)
        assertNull(x.onceSeen)
        assertEquals(0, x.due)
        assertTrue(x.forecast.isEmpty())
        assertFalse(x.hasWords)
        assertFalse(x.paused)
    }

    @Test fun signedOutKeepsOnlyThePlan() {
        val x = Planner.signedOut(input { planHour = 8 })
        val s = Planner.slots(x, at(25, 7), zone)
        assertFalse(s.isEmpty())
        assertTrue(s.all { it.id.startsWith("plan-") })
    }

    @Test fun keptAndReadBack() {
        val x = input { once = 1_795_600_000.0; planHour = 8 }
        assertEquals(x, Planner.Input.fromJson(JSONObject(x.toJson().toString())))
    }
}
