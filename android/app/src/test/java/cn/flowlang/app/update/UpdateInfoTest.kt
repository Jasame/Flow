package cn.flowlang.app.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class UpdateInfoTest {
    private val base = "https://flowlang.cn/download/latest.json"
    private val sha = "fca780b83882f1482428bf1230abedecff95ab1c910018eb08cc904e1c2a5cf1"

    // as A1 writes it (the windows and mac entries are beside it)
    private val json = """{"windows": {"version": "0.1.0"}, "android": {"version": "1.0.2", "code": 3, "file": "flow-android-1.0.2.apk",
        "size": 1100000, "sha256": "${sha.uppercase()}", "date": "2026-11-25", "cert": "76:88", "notes": "可以在 App 里更新了"}}"""

    @Test fun readsTheAndroidEntry() {
        val u = UpdateInfo.parse(json, base)
        assertNotNull(u)
        assertEquals("1.0.2", u!!.version)
        assertEquals(3L, u.code)
        assertEquals("https://flowlang.cn/download/flow-android-1.0.2.apk", u.url)  // next to latest.json
        assertEquals(1100000L, u.size)
        assertEquals(sha, u.sha256)                                                 // lower case, as the app's digest is
        assertEquals("可以在 App 里更新了", u.notes)
    }

    @Test fun withoutCodeOrNotes() {
        val u = UpdateInfo.parse("""{"android": {"version": "1.0.2", "file": "a.apk", "size": 5, "sha256": "$sha"}}""", base)!!
        assertNull(u.code)
        assertEquals("", u.notes)
        assertTrue(u.newerThan(2, "1.0.1"))       // the names are compared
        assertFalse(u.newerThan(3, "1.0.2"))
    }

    @Test fun changesListWhenNoNotes() {
        val u = UpdateInfo.parse("""{"android": {"version": "1.0.2", "file": "a.apk", "size": 5, "sha256": "$sha",
            "changes": ["在 App 里更新", " ", "修了提醒"]}}""", base)!!
        assertEquals("· 在 App 里更新\n· 修了提醒", u.notes)
    }

    @Test fun unusableEntries() {
        assertNull(UpdateInfo.parse("""{"windows": {"version": "0.1.0"}}""", base))                                        // no android
        assertNull(UpdateInfo.parse("""{"android": {"version": "1.0.2", "file": "a.apk", "size": 5, "sha256": "abc"}}""", base))  // bad sha
        assertNull(UpdateInfo.parse("""{"android": {"version": "1.0.2", "file": "a.apk", "sha256": "$sha"}}""", base))        // no size
        assertNull(UpdateInfo.parse("""{"android": {"version": "", "file": "a.apk", "size": 5, "sha256": "$sha"}}""", base))  // no version
        assertNull(UpdateInfo.parse("not json", base))
    }

    @Test fun versionCodeDecides() {
        val u = UpdateInfo.parse(json, base)!!
        assertTrue(u.newerThan(2, "1.0.1"))
        assertFalse(u.newerThan(3, "1.0.1"))       // same code: not newer, whatever the name says
        assertFalse(u.newerThan(109, "1.0.1"))     // a CI beta's code is 100 + run (only 语流 looks, but still)
    }

    @Test fun versionNames() {
        assertTrue(Versions.compare("1.0.10", "1.0.9") > 0)
        assertTrue(Versions.compare("1.1", "1.0.9") > 0)
        assertEquals(0, Versions.compare("1.0", "1.0.0"))
        assertEquals(0, Versions.compare("1.0.2-test", "1.0.2"))
        assertTrue(Versions.compare("0.9.9", "1.0.0") < 0)
    }

    @Test fun whenToLook() {
        assertTrue(UpdateGate.shouldCheck(false, "2026-11-25", "2026-11-25"))   // the app has just started
        assertFalse(UpdateGate.shouldCheck(true, "2026-11-25", "2026-11-25"))   // back to the front, same day
        assertTrue(UpdateGate.shouldCheck(true, "2026-11-25", "2026-11-26"))    // first time back on a new day
        assertTrue(UpdateGate.shouldCheck(true, null, "2026-11-25"))            // the check before failed (offline)
    }

    @Test fun laterKeepsThatVersionQuietForTheDay() {
        assertTrue(UpdateGate.quiet("1.0.2", "2026-11-25", "1.0.2", "2026-11-25"))
        assertFalse(UpdateGate.quiet("1.0.2", "2026-11-26", "1.0.2", "2026-11-25"))  // the next day it is offered again
        assertFalse(UpdateGate.quiet("1.0.3", "2026-11-25", "1.0.2", "2026-11-25"))  // a newer one the same day: offered
        assertFalse(UpdateGate.quiet("1.0.2", "2026-11-25", null, null))
    }
}
