package cn.flowlang.app.bridge

import android.annotation.SuppressLint
import android.net.Uri
import android.util.Log
import android.webkit.WebView
import androidx.annotation.OptIn
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.util.UnstableApi
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import cn.flowlang.app.Accent
import cn.flowlang.app.BuildConfig
import cn.flowlang.app.MainActivity
import cn.flowlang.app.Mute
import cn.flowlang.app.Site
import cn.flowlang.app.audio.FlowAudio
import cn.flowlang.app.notify.Reminders
import cn.flowlang.app.rec.Recorder
import cn.flowlang.app.speech.Speech
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/**
 * The page ↔ app bridge (docs/native-bridge.md, FlowApp v1): window.FlowApp, put in place before the page's scripts on
 * the site's own origin only (assets/flowapp-android.js + the shared native/flowapp.js), and the `flowNative` message
 * channel behind it (WebMessageListener:
 * {id, cmd, args} in, {id, ok, result | error} back, {ev, detail} for events). Only the main frame of the site is heard.
 * Where the phone's WebView is too old for either, nothing is added and the page works as in a browser.
 */
@OptIn(UnstableApi::class)
@SuppressLint("RequiresFeature")  // install() checks both features first; a reply proxy exists only after it
class Bridge(private val activity: MainActivity) : WebViewCompat.WebMessageListener {
    private var proxy: JavaScriptReplyProxy? = null

    fun install(web: WebView) {
        if (!supported) { Log.w(TAG, "WebView without message listeners or document-start scripts: no FlowApp"); return }
        val rules = setOf(Site.origin)
        WebViewCompat.addWebMessageListener(web, "flowNative", rules, this)
        WebViewCompat.addDocumentStartJavaScript(web, script(), rules)
        FlowAudio.sink = ::emit
        Recorder.sink = ::emit
        Speech.voicesChanged = { emit("speech-voices", Speech.voicesJson()) }
    }

    private fun config() = JSONObject().put("v", 1).put("app", BuildConfig.FLOW_VERSION).put("build", BuildConfig.FLOW_BUILD)
        .put("beta", BuildConfig.FLAVOR == "beta").put("platform", "android").put("features", JSONArray(FEATURES)).put("mute", Mute.on)

    /** Android's own lines (assets/flowapp-android.js: the transport, _back, speech, the test switch), then the wrapper the
     *  three apps share (native/flowapp.js, copied into the assets when the app is built). */
    private fun script(): String {
        fun asset(name: String) = activity.assets.open(name).bufferedReader().use { it.readText() }
        return asset("flowapp-android.js").replace("__FLOW_CONFIG__", config().toString()) + "\n" + asset("flowapp.js")
    }

    override fun onPostMessage(view: WebView, message: WebMessageCompat, sourceOrigin: Uri, isMainFrame: Boolean, replyProxy: JavaScriptReplyProxy) {
        if (!isMainFrame || !Site.isOwn(sourceOrigin)) return
        proxy = replyProxy  // the page now on screen: events go to it (a page loaded again sends hello first)
        val m = try { JSONObject(message.data ?: return) } catch (e: Exception) { return }
        val id = m.optInt("id", 0)
        val cmd = m.optString("cmd")
        val args = m.opt("args")
        activity.lifecycleScope.launch {
            val reply = JSONObject().put("id", id)
            try {
                reply.put("ok", true).put("result", handle(cmd, args) ?: JSONObject.NULL)
            } catch (e: Exception) {
                Log.w(TAG, "$cmd failed", e)
                reply.put("ok", false).put("error", e.message ?: "error")  // transport errors and unknown commands only (§2)
            }
            if (id != 0) try { replyProxy.postMessage(reply.toString()) } catch (e: Exception) { /* the page is gone */ }
        }
    }

    private suspend fun handle(cmd: String, args: Any?): Any? {
        val o = args as? JSONObject ?: JSONObject()
        return when (cmd) {
            "hello" -> {
                Log.i(TAG, "page connected (bridge v1)")  // no address or content: only that the bridge is up
                FlowAudio.replay()
                JSONObject().put("v", 1).put("app", BuildConfig.FLOW_VERSION).put("build", BuildConfig.FLOW_BUILD)
                    .put("platform", "android").put("features", JSONArray(FEATURES)).put("voices", Speech.voicesJson())
            }
            "app.visible" -> { FlowAudio.replay(); true }
            // Android's own (assets/flowapp-android.js): the page's 主题色, for the app's dialogs and notifications
            "app.accent" -> { Accent.set(activity, o.optString("accent")); true }

            "audio.play" -> FlowAudio.play(o)
            "audio.pause" -> FlowAudio.pause(if (o.optString("why") == "other") "other" else "user")
            "audio.resume" -> FlowAudio.resume()
            "audio.stop" -> FlowAudio.stop()
            "audio.step" -> FlowAudio.step(number(args, "d", 1))
            "audio.seek" -> FlowAudio.seek(number(args, "i", 0))
            "audio.set" -> FlowAudio.set(o)
            "audio.state" -> FlowAudio.stateJson()
            "audio.progress" -> FlowAudio.progressJson(args as? String ?: o.optString("key"))

            "rec.permission" -> activity.micPermission()
            "rec.ask" -> activity.askMic()
            "rec.start" -> {
                val token = Recorder.begin()
                when {
                    !activity.askMic() -> JSONObject().put("ok", false).put("why", "denied").put("message", "没有拿到麦克风权限")
                    !Recorder.stillWanted(token) -> JSONObject().put("ok", false).put("why", "cancelled")  // stopped while asking
                    else -> Recorder.start(activity, o.optInt("max", 60), o.optString("format").ifEmpty { null })
                }
            }
            "rec.stop" -> Recorder.stop()
            "rec.cancel" -> { Recorder.cancel(); true }

            "notify.permission" -> activity.notifyPermission()
            "notify.ask" -> activity.askNotify()
            "notify.sync" -> {
                val off = args == null || args == JSONObject.NULL
                if (!off && o.optBoolean("ask")) activity.askNotify()
                Reminders.sync(activity, if (off) null else o, activity.notifyPermission())
            }
            "notify.pending" -> Reminders.pendingJson(activity)
            "notify.off" -> Reminders.sync(activity, JSONObject().put("app", false), activity.notifyPermission())
            "notify.settings" -> { activity.openNotifySettings(); true }
            // UI tests on the beta: schedule from the given counts without asking the server (as iOS's)
            "notify.test" -> if (BuildConfig.FLAVOR == "beta") Reminders.test(activity, o) else throw IllegalArgumentException("unknown command $cmd")

            "speech.speak" -> {
                Speech.speak(o.optString("id"), o.optString("text"), o.optString("lang").ifEmpty { null }, o.optString("voice").ifEmpty { null },
                    o.optDouble("rate", 1.0).toFloat(), o.optDouble("pitch", 1.0).toFloat()) { type, d ->
                    emit("speech", d.put("id", o.optString("id")).put("type", type))
                }
                true
            }
            "speech.cancel" -> { Speech.stop(); true }
            "speech.all" -> if (BuildConfig.DEBUG) Speech.allVoicesJson() else throw IllegalArgumentException("unknown command $cmd")

            else -> throw IllegalArgumentException("unknown command $cmd")
        }
    }

    private fun number(args: Any?, field: String, def: Int): Int = when (args) {
        is Number -> args.toInt()
        is JSONObject -> args.optInt(field, def)
        else -> def
    }

    /** App → page: FlowApp.on(type) and window 'flowapp:<type>'. */
    fun emit(type: String, detail: Any?) {
        val p = proxy ?: return
        try { p.postMessage(JSONObject().put("ev", type).put("detail", detail ?: JSONObject.NULL).toString()) } catch (e: Exception) { /* page gone */ }
    }

    companion object {
        private const val TAG = "FlowBridge"
        val FEATURES = listOf("audio", "rec", "notify", "speech")
        val supported: Boolean
            get() = WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER) &&
                WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)
    }
}
