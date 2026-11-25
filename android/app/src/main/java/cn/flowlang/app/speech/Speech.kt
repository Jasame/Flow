package cn.flowlang.app.speech

import android.content.Context
import android.media.AudioAttributes
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.tts.TextToSpeech
import android.speech.tts.UtteranceProgressListener
import android.speech.tts.Voice
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/**
 * The phone's own voice (TextToSpeech). Android's WebView has speechSynthesis but no voice behind it, so the page's
 * 「浏览器的声音」 never speaks in it (as in WeChat on Android); the app puts this one behind speechSynthesis instead
 * (flowapp.js), and the whole-text player uses it for a sentence the server voice could not give.
 */
object Speech {
    private val main = Handler(Looper.getMainLooper())
    private var tts: TextToSpeech? = null
    private var ready = false
    private var failed = false
    private val onReady = mutableListOf<() -> Unit>()
    private val callbacks = HashMap<String, (String, JSONObject) -> Unit>()

    /** Called when the voices are known (or known to be none): the page's voiceschanged. */
    var voicesChanged: (() -> Unit)? = null

    fun init(context: Context) {
        if (tts != null) return
        tts = TextToSpeech(context.applicationContext) { status ->
            main.post {
                ready = status == TextToSpeech.SUCCESS
                failed = !ready
                if (ready) setUp()
                onReady.toList().forEach { it() }
                onReady.clear()
                voicesChanged?.invoke()
            }
        }
    }

    private fun setUp() {
        val t = tts ?: return
        t.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
        t.setOnUtteranceProgressListener(object : UtteranceProgressListener() {
            override fun onStart(id: String) = fire(id, "start", JSONObject())
            override fun onDone(id: String) = fire(id, "end", JSONObject(), last = true)
            @Deprecated("Deprecated in Java")
            override fun onError(id: String) = fire(id, "error", JSONObject().put("error", "synthesis-failed"), last = true)
            override fun onError(id: String, code: Int) = fire(id, "error", JSONObject().put("error", "synthesis-failed").put("code", code), last = true)
            override fun onStop(id: String, interrupted: Boolean) = fire(id, "error", JSONObject().put("error", "interrupted"), last = true)
            override fun onRangeStart(id: String, start: Int, end: Int, frame: Int) =
                fire(id, "boundary", JSONObject().put("name", "word").put("charIndex", start).put("charLength", end - start))
        })
    }

    private fun fire(id: String, type: String, detail: JSONObject, last: Boolean = false) {
        main.post {
            val cb = callbacks[id] ?: return@post
            if (last) callbacks.remove(id)
            cb(type, detail)
        }
    }

    val available get() = ready

    /** English voices, as speechSynthesis.getVoices() gives them: [{voiceURI, name, lang, localService, default}]. */
    fun voicesJson(): JSONArray {
        val out = JSONArray()
        val t = tts ?: return out
        if (!ready) return out
        val vs = try { t.voices.orEmpty() } catch (e: Exception) { emptySet<Voice>() }
        val def = try { t.defaultVoice?.name } catch (e: Exception) { null }
        vs.filter { it.locale.language == "en" && !it.features.orEmpty().contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED) }
            .sortedWith(compareBy({ it.isNetworkConnectionRequired }, { it.locale.toLanguageTag() }, { it.name }))
            .forEach { v ->
                out.put(JSONObject().put("voiceURI", v.name).put("name", v.name).put("lang", v.locale.toLanguageTag())
                    .put("localService", !v.isNetworkConnectionRequired).put("default", v.name == def))
            }
        return out
    }

    /** Every voice the engine knows, with why some are left out of getVoices() (debug builds: what a phone has). */
    fun allVoicesJson(): JSONArray {
        val out = JSONArray()
        val t = tts ?: return out
        val vs = try { t.voices.orEmpty() } catch (e: Exception) { emptySet<Voice>() }
        vs.filter { it.locale.language == "en" }.sortedBy { it.name }.forEach { v ->
            out.put(JSONObject().put("name", v.name).put("lang", v.locale.toLanguageTag()).put("network", v.isNetworkConnectionRequired)
                .put("notInstalled", v.features.orEmpty().contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED)))
        }
        return out
    }

    /**
     * Say [text]. [cb] gets start / boundary / end / error (the speechSynthesis events). With no engine on the phone
     * nothing happens at all, as with the WebView's own speechSynthesis: the page's 2.5 s check then says so.
     */
    fun speak(id: String, text: String, lang: String?, voice: String?, rate: Float, pitch: Float, cb: (String, JSONObject) -> Unit) {
        if (failed) return
        if (!ready) { onReady += { speak(id, text, lang, voice, rate, pitch, cb) }; return }
        val t = tts ?: return
        val v = voice?.let { n -> try { t.voices?.firstOrNull { it.name == n } } catch (e: Exception) { null } }
        if (v != null) t.voice = v else t.language = Locale.forLanguageTag(if (lang.isNullOrEmpty()) "en-US" else lang)
        t.setSpeechRate(rate.coerceIn(0.3f, 3f))
        t.setPitch(pitch.coerceIn(0.5f, 2f))
        callbacks[id] = cb
        val params = Bundle().apply { putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, if (cn.flowlang.app.Mute.on) 0f else 1f) }
        val r = t.speak(text, TextToSpeech.QUEUE_FLUSH, params, id)
        if (r != TextToSpeech.SUCCESS) fire(id, "error", JSONObject().put("error", "synthesis-failed"), last = true)
    }

    /** The whole-text player's fallback: one sentence in the accent of the voice asked for ('uk-…' or 'us-…'). */
    fun say(text: String, accent: String, rate: Float, done: (Boolean) -> Unit) {
        if (failed) { done(false); return }
        val id = "long-" + System.nanoTime()
        speak(id, text, if (accent.startsWith("uk")) "en-GB" else "en-US", null, rate, 1f) { type, _ ->
            if (type == "end") done(true) else if (type == "error") done(false)
        }
    }

    fun stop() {
        try { tts?.stop() } catch (e: Exception) { /* engine gone */ }
    }

    fun pause() = stop()  // TextToSpeech cannot pause; the page's own speechSynthesis on Android does not either
}
