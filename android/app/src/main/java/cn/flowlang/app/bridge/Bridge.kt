package cn.flowlang.app.bridge

import android.net.Uri
import android.util.Log
import android.webkit.WebView
import androidx.lifecycle.lifecycleScope
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.webkit.JavaScriptReplyProxy
import androidx.webkit.WebMessageCompat
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import cn.flowlang.app.BuildConfig
import cn.flowlang.app.MainActivity
import cn.flowlang.app.Site
import cn.flowlang.app.audio.FlowAudio
import cn.flowlang.app.notify.Reminders
import cn.flowlang.app.rec.Recorder
import cn.flowlang.app.speech.Speech
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/**
 * The page ↔ app bridge (docs/native-bridge.md): window.FlowApp, put in place before the page's scripts on the site's
 * own origin only (flowapp.js), and the `flowNative` message channel behind it. Only the main frame of the site is
 * heard. Where the phone's WebView is too old for either, nothing is added and the page works as in a browser.
 */
@OptIn(UnstableApi::class)
class Bridge(private val activity: MainActivity) : WebViewCompat.WebMessageListener {
    private var proxy: JavaScriptReplyProxy? = null

    val installed get() = supported

    fun install(web: WebView) {
        if (!supported) { Log.w(TAG, "WebView without message listeners or document-start scripts: no FlowApp"); return }
        val rules = setOf(Site.origin)
        WebViewCompat.addWebMessageListener(web, "flowNative", rules, this)
        WebViewCompat.addDocumentStartJavaScript(web, script(), rules)
        FlowAudio.sink = ::emit
        Recorder.sink = ::emit
        Speech.voicesChanged = { emit("speech-voices", Speech.voicesJson()) }
    }

    private fun script(): String {
        val js = activity.assets.open("flowapp.js").bufferedReader().use { it.readText() }
        return js.replace("__FLOW_CAPS__", JSONArray(CAPS).toString()).replace("__FLOW_APP__", JSONObject.quote(BuildConfig.FLOW_VERSION))
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
                reply.put("ok", false).put("error", e.message ?: "error")
            }
            if (id != 0) try { replyProxy.postMessage(reply.toString()) } catch (e: Exception) { /* the page is gone */ }
        }
    }

    private suspend fun handle(cmd: String, args: Any?): Any? {
        val o = args as? JSONObject ?: JSONObject()
        return when (cmd) {
            "hello" -> {
                Log.i(TAG, "page connected (bridge v1)")  // no address or content: only that the bridge is up
                FlowAudio.replay(); JSONObject().put("voices", Speech.voicesJson()).put("platform", "android")
            }

            "audio.play" -> FlowAudio.play(o)
            "audio.pause" -> FlowAudio.pause(o.optString("why").ifEmpty { "user" }.let { if (it == "other") it else "user" })
            "audio.resume" -> FlowAudio.resume()
            "audio.stop" -> FlowAudio.stop()
            "audio.step" -> FlowAudio.step(number(args, 1))
            "audio.seek" -> FlowAudio.seek(number(args, 0))
            "audio.set" -> FlowAudio.set(o)
            "audio.state" -> FlowAudio.stateJson()
            "audio.progress" -> FlowAudio.progressJson(args as? String ?: o.optString("key"))

            "rec.permission" -> activity.micPermission()
            "rec.ask" -> activity.askMic()
            "rec.start" -> {
                if (!activity.askMic()) JSONObject().put("ok", false).put("why", "denied").put("message", "没有拿到麦克风权限")
                else Recorder.start(activity, o.optInt("max", 60), o.optString("format").ifEmpty { null })
            }
            "rec.stop" -> Recorder.stop()
            "rec.cancel" -> { Recorder.cancel(); true }

            "notify.permission" -> activity.notifyPermission()
            "notify.ask" -> activity.askNotify()
            "notify.sync" -> Reminders.sync(activity, o)
            "notify.off" -> { Reminders.setOptedIn(activity, false); true }
            "notify.settings" -> { activity.openNotifySettings(); true }

            "speech.speak" -> {
                Speech.speak(o.optString("id"), o.optString("text"), o.optString("lang").ifEmpty { null }, o.optString("voice").ifEmpty { null },
                    o.optDouble("rate", 1.0).toFloat(), o.optDouble("pitch", 1.0).toFloat()) { type, d ->
                    emit("speech", d.put("id", o.optString("id")).put("type", type))
                }
                true
            }
            "speech.cancel" -> { Speech.stop(); true }

            else -> throw IllegalArgumentException("unknown command $cmd")
        }
    }

    private fun number(args: Any?, def: Int): Int = when (args) {
        is Number -> args.toInt()
        is JSONObject -> args.optInt("d", args.optInt("i", def))
        else -> def
    }

    /** App → page: FlowApp.on(type) and window 'flowapp:<type>'. */
    fun emit(type: String, detail: Any?) {
        val p = proxy ?: return
        try { p.postMessage(JSONObject().put("ev", type).put("detail", detail ?: JSONObject.NULL).toString()) } catch (e: Exception) { /* page gone */ }
    }

    companion object {
        private const val TAG = "FlowBridge"
        val CAPS = listOf("audio", "rec", "notify", "speech")
        val supported: Boolean
            get() = WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER) &&
                WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)

    }
}
