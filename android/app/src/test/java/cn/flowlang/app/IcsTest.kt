package cn.flowlang.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class IcsTest {
    // as vocab_service.ics writes it (CRLF, folded at 75 octets)
    private val ics = listOf("BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT", "UID:flow-review-20@flow", "DTSTAMP:20261125T040000Z",
        "DTSTART:20261125T120000Z", "DURATION:PT10M", "RRULE:FREQ=DAILY", "SUMMARY:语流：复习单词", "URL:https://flowlang.cn/#/review",
        "DESCRIPTION:打开语流复习今天到期的单词\\, 几分钟就好。", " https://flowlang.cn/#/review", "BEGIN:VALARM", "ACTION:DISPLAY",
        "DESCRIPTION:语流：复习单词", "TRIGGER:PT0M", "END:VALARM", "END:VEVENT", "END:VCALENDAR").joinToString("\r\n")

    @Test fun readsTheEvent() {
        val e = Ics.firstEvent(ics)
        assertNotNull(e)
        assertEquals(1795608000000L, e!!.start)          // 2026-11-25 12:00 UTC = 20:00 in Beijing
        assertEquals(e.start + 10 * 60_000, e.end)
        assertEquals("FREQ=DAILY", e.rrule)
        assertEquals("语流：复习单词", e.title)
        assertEquals("打开语流复习今天到期的单词, 几分钟就好。https://flowlang.cn/#/review", e.description)  // unfolded, unescaped
    }
}
