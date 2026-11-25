package cn.flowlang.app.privacy

import cn.flowlang.app.privacy.Consent.State
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class ConsentTest {
    private val v = "2026-11-25/2026-11-25"

    @Test
    fun theFirstStartAsks() = assertEquals(State.ASK, Consent.state(null, false, v))

    @Test
    fun agreedToTheseTexts() = assertEquals(State.AGREED, Consent.state(v, false, v))

    @Test
    fun aBuildWithANewerVersionAsksAgain() {
        assertEquals(State.ASK, Consent.state("2026-11-25/2026-11-24", false, v))
        assertEquals(State.ASK, Consent.state("missing", false, v))
    }

    @Test
    fun notAgreedStaysInBasicModeAndIsNotAskedAgainByItself() {
        assertEquals(State.BASIC, Consent.state(null, true, v))
        assertEquals(State.BASIC, Consent.state(null, true, "2027-01-01/2027-01-01"))
    }

    @Test
    fun signingInOrUpIsWhatBasicModeAnswersItself() {
        for (p in listOf("/api/login", "/api/register", "/api/auth/code", "/api/auth/reset", "/api/register/")) assertTrue(p, Consent.signIn(p))
        for (p in listOf(null, "", "/api/logout", "/api/next/vocab", "/api/next/guide", "/api/loginx")) assertFalse("$p", Consent.signIn(p))
    }

    /** The routes are the server's (flow/app.py SIGN_IN_ROUTES): a new one there must be one here too. */
    @Test
    fun theSignInRoutesAreTheServers() {
        val app = listOf(File("../../flow/app.py"), File("../flow/app.py"), File("flow/app.py")).firstOrNull { it.exists() } ?: return
        val line = app.readLines().first { it.startsWith("SIGN_IN_ROUTES") }
        val routes = Regex("'(/api/[^']+)'").findAll(line).map { it.groupValues[1] }.toSet()
        assertEquals(routes, Consent.SIGN_IN)
    }

    @Test
    fun thePageIsToldWhy() {
        val o = JSONObject(Consent.SIGN_IN_ANSWER)
        assertTrue(o.getString("error").contains("《用户协议》和《隐私和数据》"))
        assertEquals("app-consent", o.getString("code"))
    }

    @Test
    fun theBuildsTextsAreRead() {
        val d = Consent.parse("""{"version":"$v","docs":{"terms":{"title":"语流用户协议","html":"<p>a</p>"},"privacy":{"title":"隐私和数据","html":"<p>b</p>"}}}""")
        assertNotNull(d)
        assertEquals(v, d!!.version)
        assertEquals("语流用户协议", d.titles["terms"])
        assertEquals("<p>b</p>", d.html["privacy"])
    }

    @Test
    fun aBrokenFileIsNotTakenForTexts() {
        assertNull(Consent.parse("{}"))
        assertNull(Consent.parse("""{"version":"","docs":{"terms":{"title":"t","html":"h"},"privacy":{"title":"p","html":"h"}}}"""))
        assertNull(Consent.parse("""{"version":"$v","docs":{"terms":{"title":"t","html":"h"}}}"""))
        assertNull(Consent.parse("not json"))
    }
}
