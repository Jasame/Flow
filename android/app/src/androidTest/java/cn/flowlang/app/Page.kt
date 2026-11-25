package cn.flowlang.app

import android.os.SystemClock
import androidx.test.core.app.ActivityScenario
import org.json.JSONObject
import org.json.JSONTokener
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicReference

/** The page in the app's WebView, from a test: run JavaScript, wait for Promises, wait for conditions. */
class Page(private val scenario: ActivityScenario<MainActivity>) {
    /** Evaluate [expr] (not awaited) and return its value as JSON text. */
    fun js(expr: String): String {
        val out = AtomicReference<String>()
        val done = CountDownLatch(1)
        scenario.onActivity { a -> a.web.evaluateJavascript("(function(){try{return JSON.stringify($expr)}catch(e){return JSON.stringify('EXC '+e)}})()") { r -> out.set(r); done.countDown() } }
        done.await(10, TimeUnit.SECONDS)
        // evaluateJavascript gives the JSON of a string: decode it once, then the inner JSON is the value
        return (JSONTokener(out.get() ?: "null").nextValue() as? String) ?: "null"
    }

    /** Evaluate [expr], await it if it is a Promise, and return the value as JSON text. */
    fun await(expr: String, timeoutMs: Long = 30_000): String {
        val slot = "__t" + SystemClock.uptimeMillis()
        js("(window.$slot=null, Promise.resolve($expr).then(v=>window.$slot={v:v===undefined?null:v}, e=>window.$slot={e:String(e)}), 1)")
        val end = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < end) {
            val r = js("window.$slot")
            if (r != "null") {
                val o = JSONObject(r)
                if (o.has("e")) throw AssertionError("page: " + o.getString("e"))
                return o.get("v").toString()
            }
            SystemClock.sleep(150)
        }
        throw AssertionError("timed out: $expr")
    }

    fun waitFor(what: String, expr: String, timeoutMs: Long = 30_000) {
        val end = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < end) { if (js("!!($expr)") == "true") return; SystemClock.sleep(200) }
        throw AssertionError("timed out waiting for $what")
    }

    /** The site is open and window.FlowApp is there. */
    fun ready() = waitFor("the page and FlowApp", "document.readyState==='complete' && window.FlowApp && FlowApp.v===1", 60_000)

    /**
     * A text with a recording, from today's materials: sets window.__item = {key, title, src, sentences}.
     * Guests see the same materials; the recording and its timeline are public files.
     */
    fun pickArticle() = await("""(async()=>{
        const home = await fetch('/api/next/home').then(r=>r.json());
        for (const t of home.today || []) {
          const m = await fetch('/api/next/material?id='+encodeURIComponent(t.id)+'&level='+encodeURIComponent(t.level||'B1')).then(r=>r.json());
          if (!m.audio || !m.audio.voices || !m.audio.voices.length) continue;
          const v = m.audio.voices[0], meta = await fetch('/audio/'+v+'/'+m.id+'.json?v='+m.audio.version).then(r=>r.json());
          window.__item = {key:'listen:'+m.id, title:m.title, src:'/audio/'+v+'/'+m.id+'.mp4?v='+m.audio.version, sentences: meta.sentences.map(s=>[s.s,s.e])};
          return window.__item.sentences.length;
        }
        throw new Error('no material with a recording today');
      })()""", 60_000)
}
