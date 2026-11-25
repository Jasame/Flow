package cn.flowlang.app

import android.Manifest
import android.os.Build
import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.filters.LargeTest
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import cn.flowlang.app.notify.Reminders
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.FixMethodOrder
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.MethodSorters
import java.util.regex.Pattern

/**
 * On the emulator, against the site the flavor opens (beta: flow.jasa.hk), as a guest, without a sound (the app's test
 * switch, docs/native-bridge.md §9; start the emulator with -no-audio too). Run by ./gradlew connectedBetaDebugAndroidTest
 * (android/README.md). The app is installed fresh for the run, so the microphone is not allowed yet when e_ runs.
 */
@RunWith(AndroidJUnit4::class)
@LargeTest
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
class AppTest {
    private val inst = InstrumentationRegistry.getInstrumentation()
    private val device = UiDevice.getInstance(inst)
    private lateinit var scenario: ActivityScenario<MainActivity>
    private lateinit var page: Page

    @Before fun open() {
        Mute.on = true
        scenario = ActivityScenario.launch(MainActivity::class.java)
        page = Page(scenario)
        page.ready()
    }

    @After fun close() {
        try { page.await("FlowApp.audio.stop()") } catch (e: Throwable) { /* nothing playing */ }
        device.pressHome()
        scenario.close()
    }

    @Test fun a_opensTheSiteWithTheBridge() {
        assertTrue(page.js("navigator.userAgent").contains("FlowAndroid/" + BuildConfig.FLOW_VERSION))
        assertTrue(page.js("location.origin").contains(Site.host))
        assertEquals("\"android\"", page.js("FlowApp.platform"))
        assertEquals("[true,true,true,true]", page.js("['audio','rec','notify','speech'].map(k=>FlowApp.has(k))"))
        assertEquals("true", page.js("FlowApp.beta === true && FlowApp.v === 1 && typeof FlowApp.call === 'function' && Object.isFrozen(FlowApp)"))
        assertEquals("\"android\"", page.js("JSON.parse(JSON.stringify(FlowApp.platform))"))
        assertTrue("the page's title", page.js("document.title").contains("语流"))
    }

    @Test fun b_loginPage() {
        // as a learner gets there: the beta's notice closed (the back button's way), 单词, 「登录 / 注册」
        page.js("(FlowApp._back(), location.hash = '#/cards', 1)")
        page.waitFor("the 登录 button", "[...document.querySelectorAll('main button, main a')].some(x => /登录/.test(x.textContent))")
        page.js("([...document.querySelectorAll('main button, main a')].find(x => /登录/.test(x.textContent)).click(), 1)")
        page.waitFor("the login sheet", "!document.getElementById('sheet').hidden && document.querySelector('#sheetCard input[name=username]')")
        assertTrue(page.js("document.getElementById('sheetTitle').textContent").contains("登录"))
        assertEquals("true", page.js("!!document.querySelector('#sheetCard input[type=password]')"))
    }

    @Test fun c_playsAnArticle() {
        val n = page.pickArticle().toInt()
        assertTrue(n > 2)
        assertEquals(true, JSONObject(page.await("FlowApp.audio.play(Object.assign({from:0}, __item))")).getBoolean("ok"))
        waitState("playing", minT = 1.0)
        page.await("FlowApp.audio.step(1)")
        val st = JSONObject(page.await("FlowApp.audio.state()"))
        assertEquals(1, st.getInt("i"))
        page.await("FlowApp.audio.pause()")
        waitState("paused")
        val p = JSONObject(page.await("FlowApp.audio.progress(__item.key)"))
        assertEquals(1, p.getInt("i"))
    }

    @Test fun d_notificationControls() {
        page.pickArticle()
        page.await("FlowApp.audio.play(Object.assign({from:0}, __item))")
        waitState("playing", minT = 0.5)
        page.js("(window.__why = '', FlowApp.on('audio', d => { if (d.state === 'paused') window.__why = d.why; }), 1)")
        device.openNotification()
        val pause = device.wait(Until.findObject(By.desc(Pattern.compile("(?i).*(pause|暂停).*"))), 10_000)
        assertTrue("the media controls in the shade", pause != null)
        pause.click()
        waitState("paused")
        page.waitFor("the page told why", "window.__why === 'remote'", 5_000)
        val next = device.wait(Until.findObject(By.desc(Pattern.compile("(?i).*(next|下一).*"))), 5_000)
        assertTrue("the next button; the shade has: " + device.findObjects(By.desc(Pattern.compile(".+"))).map { it.contentDescription }, next != null)
        val i0 = JSONObject(page.await("FlowApp.audio.state()")).getInt("i")
        next.click()
        val end = SystemClock.uptimeMillis() + 5_000
        while (SystemClock.uptimeMillis() < end && JSONObject(page.await("FlowApp.audio.state()")).getInt("i") == i0) SystemClock.sleep(200)
        assertTrue("next sentence from the shade", JSONObject(page.await("FlowApp.audio.state()")).getInt("i") > i0)
        device.pressBack()
    }

    @Test fun e_microphonePermissionDialog() {
        if (page.await("FlowApp.rec.permission()") != "granted") {
            page.js("(window.__rec = FlowApp.rec.start({max: 2}), 1)")
            val allow = device.wait(Until.findObject(By.res(Pattern.compile("com.android.permissioncontroller:id/permission_allow_(foreground_only_)?button"))), 10_000)
            assertTrue("the system's microphone dialog", allow != null)
            allow.click()
            assertEquals(true, JSONObject(page.await("__rec")).getBoolean("ok"))
        } else {
            assertEquals(true, JSONObject(page.await("FlowApp.rec.start({max: 2})")).getBoolean("ok"))
        }
        SystemClock.sleep(2_500)
        val r = JSONObject(page.await("FlowApp.rec.stop()"))
        assertTrue(r.getBoolean("ok"))
        assertEquals("audio/wav", r.getString("mime_type"))
        assertTrue("about two seconds of 16 kHz WAV", r.getInt("bytes") > 30_000 && r.getString("data").length > 40_000)
        assertEquals("none", JSONObject(page.await("FlowApp.rec.stop()")).getString("why"))  // nothing more to give
        assertEquals("granted", page.await("FlowApp.rec.permission()"))
    }

    @Test fun f_reminderSchedule() {
        val ctx = inst.targetContext
        if (Build.VERSION.SDK_INT >= 33) inst.uiAutomation.grantRuntimePermission(ctx.packageName, Manifest.permission.POST_NOTIFICATIONS)
        assertEquals("true", page.await("FlowApp.notify.ask()"))
        SystemClock.sleep(2_000)  // the app's own refresh as a guest (signed out: no word reminders) is done
        assertEquals("granted", page.await("FlowApp.notify.permission()"))
        // as a signed-in learner with 12 words left today and a forecast (the beta's test command: no server, no account)
        val r = JSONObject(page.await("FlowApp.call('notify.test', {reminder: {hour: 20}, due: 12, forecast: [12,5,0,7,3,0,2], total: 40, planHour: null})"))
        val list = r.getJSONArray("pending")
        val ids = (0 until list.length()).map { list.getJSONObject(it).getString("id") }
        assertTrue("two weeks of daily reviews: $ids", ids.count { it.startsWith("review-") } >= 13)
        assertTrue(ids.first(), Reminders.isScheduled(ctx, ids.first()))
        assertEquals(list.length(), org.json.JSONArray(page.await("FlowApp.notify.pending()")).length())
        page.await("FlowApp.notify.off()")
        assertEquals("[]", page.await("FlowApp.notify.pending()"))
        assertTrue(!Reminders.isScheduled(ctx, ids.first()))
        assertEquals("undetermined", page.await("FlowApp.notify.permission()"))
    }

    @Test fun g_aSentenceTheServerCannotGiveSaysWhy() {
        // a guest asks for a sentence nobody made yet: the phone's own voice reads it, and `fail` {code, server} says why
        page.js("(window.__fail = null, FlowApp.on('audio', d => { if (d.fail) window.__fail = d.fail; }), 1)")
        val text = "Android test sentence " + System.currentTimeMillis() + " is not made yet."
        assertEquals(true, JSONObject(page.await("FlowApp.audio.play({key: '', title: 't', items: [{text: '$text', url: null}], voice: 'us-f'})")).getBoolean("ok"))
        page.waitFor("an audio event with fail", "window.__fail && window.__fail.code", 30_000)
        assertTrue(page.js("window.__fail.code").length > 2)
    }

    private fun waitState(state: String, minT: Double = -1.0, timeoutMs: Long = 30_000) {
        val end = SystemClock.uptimeMillis() + timeoutMs
        var last = ""
        while (SystemClock.uptimeMillis() < end) {
            val s = JSONObject(page.await("FlowApp.audio.state()"))
            last = s.toString()
            if (s.getString("state") == state && s.optDouble("t", 0.0) >= minT) return
            SystemClock.sleep(250)
        }
        throw AssertionError("not $state: $last")
    }
}
