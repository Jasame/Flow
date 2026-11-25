package cn.flowlang.app

import org.junit.Assert.assertEquals
import org.junit.Test

class AccentTest {
    @Test fun whatThePageSends() {
        assertEquals("indigo", Accent.normalize("indigo"))
        assertEquals("green", Accent.normalize("green"))
        assertEquals("green", Accent.normalize(""))      // <html> without data-accent: 松绿
        assertEquals("green", Accent.normalize(null))
        assertEquals("green", Accent.normalize("purple")) // a colour this app does not know yet: the default
    }

    @Test fun thePagesOwnValues() {
        // flow/public/src/next/00-base.css and 99-accent.css (--green), light and dark
        assertEquals(0xFF1F9D55.toInt(), Accent.colorOf("green", night = false))
        assertEquals(0xFF3CCF7C.toInt(), Accent.colorOf("green", night = true))
        assertEquals(0xFF3461D1.toInt(), Accent.colorOf("indigo", night = false))
        assertEquals(0xFF8EAEFC.toInt(), Accent.colorOf("indigo", night = true))
    }
}
