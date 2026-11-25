package cn.flowlang.app.audio

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioAttributes as SysAudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.CookieManager
import androidx.core.content.ContextCompat
import androidx.core.os.HandlerCompat
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.database.StandaloneDatabaseProvider
import androidx.media3.datasource.DataSpec
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.datasource.ResolvingDataSource
import androidx.media3.datasource.cache.CacheDataSource
import androidx.media3.datasource.cache.CacheWriter
import androidx.media3.datasource.cache.LeastRecentlyUsedCacheEvictor
import androidx.media3.datasource.cache.SimpleCache
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import cn.flowlang.app.Site
import cn.flowlang.app.net.Http
import cn.flowlang.app.speech.Speech
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * A whole text read aloud (听's 播放全文, 读's 伴读), played by the app instead of the page (docs/native-bridge.md,
 * FlowApp.audio): it goes on with the screen off and the app in the background, shows 「语流 · 标题」 with play / pause /
 * previous / next sentence on the lock screen and in the notification shade, pauses for a call or another app's
 * sound and goes on afterwards when the phone says it may, and pauses when the headphones come out.
 *
 * Two ways of making the sound, as on the page (LONG in 01-audio-offline.js):
 *  - a recording (Kokoro): one file and its sentences [s, e]; straight through, or sentence by sentence (复读);
 *  - no recording: the server voice sentence by sentence (POST /api/next/tts, the next two asked for while one plays);
 *    a sentence it cannot give is read by the phone's own voice, and note says why.
 *
 * The page hears of it through [sink]: `audio` {key, state, i, t, note, why} and, while it is on screen,
 * `audio-tick` {key, i, t} four times a second. state: waiting / playing / paused / idle. why (when it stopped or
 * paused): user / remote / interrupted / route / other / ended / error.
 *
 * Everything here runs on the main thread.
 */
@OptIn(UnstableApi::class)
object FlowAudio {
    private const val TAG = "FlowAudio"

    enum class Mode { REC, TTS }

    class Job(
        val key: String,
        val title: String,
        val mode: Mode,
        val src: String?,
        val spans: List<Span>,
        val texts: List<String>,
        val voice: String,
        val pack: String?,
        val loop: Boolean,
        var rep: Int,
        var gaps: IntArray?,
        var gap: Int,
        var rate: Float,
        /** the page's CSRF token (S.csrf): the server voice as the signed-in learner without asking /api/session */
        val csrf: String?,
        /** the page's second line for the recording (mediaAlt), else worked out from /api/session */
        val alt: String?,
    ) {
        val n get() = if (mode == Mode.REC) spans.size else texts.size
        fun gapAfter(i: Int) = gaps?.getOrNull(i) ?: gap
        /** sentence by sentence (and so 复读 and pauses apply): always without a recording, with one when asked */
        val bySentence get() = mode == Mode.TTS || loop
    }

    private lateinit var app: Context
    private val main = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var progress: ProgressStore
    private var exo: ExoPlayer? = null
    private var cache: SimpleCache? = null

    val session: LongSessionPlayer by lazy { LongSessionPlayer(this) }

    var job: Job? = null; private set
    var i = 0; private set
    var state = "idle"; private set
    var note = ""; private set
    private var said = 0          // times sentence i has been said (复读)
    private var tok = 0           // a new token cancels what is pending: a pause, a gap, a sentence being made
    private var onAlt = false     // the recording plays from the media domain (this server failed)
    private var resumeOnGain = false
    private var phoneVoice = false  // the phone's own voice is saying sentence i
    private var lastWhy = ""
    private var stopAtEnd = -1.0  // sentence by sentence on a recording: where sentence i ends

    /** The bridge: where `audio` / `audio-tick` go. */
    var sink: ((String, JSONObject) -> Unit)? = null
    /** The page is on screen (ticks are sent only then). */
    var visible = false
        set(v) { field = v; if (v) replay() }

    fun init(context: Context) {
        if (::app.isInitialized) return
        app = context.applicationContext
        progress = ProgressStore(app)
    }

    // ------------------------------------------------------------------ the page's commands

    fun play(o: JSONObject): JSONObject {
        val key = o.optString("key")
        val title = o.optString("title").ifEmpty { "朗读" }
        val src = o.optString("src").ifEmpty { null }
        val spans = o.optJSONArray("sentences")?.let { a ->
            (0 until a.length()).mapNotNull { k ->
                val x = a.optJSONArray(k) ?: a.optJSONObject(k)?.let { JSONArray().put(it.optDouble("s")).put(it.optDouble("e")) }
                x?.let { Span(it.optDouble(0), it.optDouble(1)) }
            }
        }.orEmpty()
        val texts = o.optJSONArray("texts")?.let { a -> (0 until a.length()).map { a.optString(it) } }.orEmpty()
        val mode = when {
            src != null && spans.isNotEmpty() -> Mode.REC
            texts.isNotEmpty() -> Mode.TTS
            else -> return fail("bad_args", "这篇没有能朗读的句子")
        }
        val gapsArr = o.optJSONArray("gap")?.let { a -> IntArray(a.length()) { a.optInt(it) } }
        val j = Job(
            key = key, title = title, mode = mode, src = src, spans = spans, texts = texts,
            voice = o.optString("voice").ifEmpty { "us-f" }, pack = o.optString("pack").ifEmpty { null },
            loop = o.optBoolean("loop", false), rep = o.optInt("rep", 1).coerceAtLeast(0),
            gaps = gapsArr, gap = if (gapsArr == null) o.optInt("gap", 0) else 0,
            rate = o.optDouble("rate", 1.0).toFloat().coerceIn(0.5f, 2f),
            csrf = o.optString("csrf").ifEmpty { null },
            alt = o.optString("alt").ifEmpty { null },
        )
        halt()  // another text: where it was is kept
        job = j
        tok++
        said = 0; onAlt = false; resumeOnGain = false; note = ""; serverOff = null
        i = o.optInt("from", 0).coerceIn(0, (j.n - 1).coerceAtLeast(0))
        val at = if (mode == Mode.REC && o.has("at")) o.optDouble("at", -1.0) else -1.0
        if (at >= 0) Sentences.locate(spans, at).takeIf { it >= 0 }?.let { i = it }
        PlaybackService.start(app)
        if (!takeFocus()) {
            state = "paused"; note = "现在有电话或别的声音在用，等一下再点继续"
            changed("interrupted")
            return JSONObject().put("ok", true).put("state", state)
        }
        state = if (mode == Mode.REC) "playing" else "waiting"
        listenForUnplug(true)
        when (mode) {
            Mode.REC -> playRecording(if (at >= 0) at else spans[i].s)
            Mode.TTS -> sentence()
        }
        changed("")
        startTicks()
        return JSONObject().put("ok", true)
    }

    fun pause(why: String = "user"): JSONObject {
        val j = job ?: return ok()
        if (state == "paused") return ok()
        tok++
        main.removeCallbacksAndMessages(GAP)
        when (j.mode) {
            Mode.REC -> exo?.pause()  // stays at that second: 继续 goes on from it
            Mode.TTS -> { exo?.stop(); if (phoneVoice) { phoneVoice = false; Speech.stop() } }  // 继续: from the sentence's start
        }
        state = "paused"
        note = ""
        save()
        stopTicks()
        if (why != "interrupted") { resumeOnGain = false; dropFocus() }
        changed(why)
        return ok()
    }

    fun resume(why: String = "user"): JSONObject {
        val j = job ?: return stateJson().put("ok", false).put("why", "idle")
        if (state != "paused") return stateJson().put("ok", true)
        if (!takeFocus()) { note = "现在有电话或别的声音在用，等一下再点继续"; changed("interrupted"); return stateJson().put("ok", false).put("why", "interrupted").put("message", note) }
        resumeOnGain = false
        tok++
        state = "playing"
        note = ""
        listenForUnplug(true)
        when (j.mode) {
            Mode.REC -> {
                val p = exo
                if (p != null && p.mediaItemCount > 0 && p.playbackState != Player.STATE_IDLE && p.playbackState != Player.STATE_ENDED) {
                    if (j.bySentence) stopAtEnd = j.spans[i].e
                    p.play()
                } else playRecording(j.spans[i].s)
            }
            Mode.TTS -> sentence()
        }
        changed("")
        startTicks()
        return stateJson().put("ok", true)
    }

    /** Stop reading (✕, leaving the page, another text): where it was is kept. */
    fun stop(why: String = "user"): JSONObject {
        if (job == null) return ok()
        halt()
        changed(why)
        return ok()
    }

    /** Previous / next sentence (the page, the lock screen, the headphones). */
    fun step(d: Int, why: String = "user"): JSONObject {
        val j = job ?: return ok()
        if (j.mode == Mode.REC && !j.loop) {
            val p = exo ?: return ok()
            val target = Sentences.stepTarget(j.spans, p.currentPosition / 1000.0, d)
            p.seekTo((j.spans[target].s * 1000).toLong())
            i = target
            save(); changed("")
            return ok()
        }
        return seek(i + d, why)
    }

    /** To sentence [to] (and play it, as LONG.step does). */
    fun seek(to: Int, @Suppress("UNUSED_PARAMETER") why: String = "user"): JSONObject {
        val j = job ?: return ok()
        tok++
        main.removeCallbacksAndMessages(GAP)
        if (phoneVoice) { phoneVoice = false; Speech.stop() }
        i = to.coerceIn(0, j.n - 1)
        said = 0
        if (j.mode == Mode.REC && !j.loop) {
            exo?.seekTo((j.spans[i].s * 1000).toLong())
            save(); changed("")
            return ok()
        }
        if (state == "paused") {
            if (!takeFocus()) { save(); changed("interrupted"); return ok() }
            resumeOnGain = false
            listenForUnplug(true)
        }
        state = "playing"; note = ""
        go()
        save(); changed("")
        startTicks()
        return ok()
    }

    /** 复读 changed while it plays: {rep, gap (a number or one per sentence), rate}. */
    fun set(o: JSONObject): JSONObject {
        val j = job ?: return ok()
        if (o.has("rep")) j.rep = o.optInt("rep", j.rep).coerceAtLeast(0)
        o.optJSONArray("gap")?.let { a -> j.gaps = IntArray(a.length()) { a.optInt(it) }; j.gap = 0 }
            ?: run { if (o.has("gap")) { j.gaps = null; j.gap = o.optInt("gap", 0) } }
        if (o.has("rate")) { j.rate = o.optDouble("rate", 1.0).toFloat().coerceIn(0.5f, 2f); exo?.setPlaybackSpeed(j.rate) }
        return ok()
    }

    fun stateJson(): JSONObject = JSONObject().put("key", job?.key ?: "").put("state", state).put("i", if (job == null) -1 else i)
        .put("t", seconds()).put("note", note).put("title", job?.title ?: "").put("n", job?.n ?: 0)

    fun progressJson(key: String): Any = progress.get(key) ?: JSONObject.NULL

    /** The page loaded again, or came back on screen: what is going on now, so it does not have to guess. */
    fun replay() = emit("audio", stateJson().put("why", lastWhy))

    // ------------------------------------------------------------------ making the sound

    private fun player(): ExoPlayer {
        exo?.let { return it }
        val http = DefaultHttpDataSource.Factory().setUserAgent(Site.userAgent).setAllowCrossProtocolRedirects(false)
            .setConnectTimeoutMs(10_000).setReadTimeoutMs(20_000)
        // the login cookie goes with this site's own files only (/audio/own/ needs it), never to the media domain
        val signed = ResolvingDataSource.Factory(http) { spec: DataSpec ->
            val u = spec.uri.toString()
            val c = if (Site.isOwn(u)) try { CookieManager.getInstance().getCookie(u) } catch (e: Exception) { null } else null
            if (c.isNullOrEmpty()) spec else spec.withAdditionalHeaders(mapOf("Cookie" to c))
        }
        val cached = CacheDataSource.Factory().setCache(cache()).setUpstreamDataSourceFactory(signed)
            .setFlags(CacheDataSource.FLAG_IGNORE_CACHE_ON_ERROR)
        val p = ExoPlayer.Builder(app)
            .setMediaSourceFactory(DefaultMediaSourceFactory(cached))
            // focus and unplugging are handled here (takeFocus, listenForUnplug), for the phone's own voice as well
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_SPEECH).build(), false)
            .setHandleAudioBecomingNoisy(false)
            .setWakeMode(C.WAKE_MODE_NETWORK)
            .build()
        p.addListener(listener)
        exo = p
        return p
    }

    private fun cache(): SimpleCache = cache ?: SimpleCache(File(app.cacheDir, "audio"), LeastRecentlyUsedCacheEvictor(150L * 1024 * 1024),
        StandaloneDatabaseProvider(app)).also { cache = it }

    private fun playRecording(fromSec: Double) {
        val j = job ?: return
        val p = player()
        val url = if (onAlt) altUrl(j.src!!) ?: Site.abs(j.src!!) else Site.abs(j.src!!)
        stopAtEnd = if (j.bySentence) j.spans[i].e else -1.0
        p.setMediaItem(MediaItem.Builder().setUri(url).setMediaId(j.key).build(), (fromSec * 1000).toLong().coerceAtLeast(0))
        p.setPlaybackSpeed(j.rate)
        p.prepare()
        p.play()
    }

    /** Sentence i again, or the one after the pause: a recording seeks, the server voice makes it. */
    private fun go() {
        val j = job ?: return
        when (j.mode) {
            Mode.REC -> {
                val p = exo
                stopAtEnd = j.spans[i].e
                if (p == null || p.mediaItemCount == 0 || p.playbackState == Player.STATE_IDLE) playRecording(j.spans[i].s)
                else { p.seekTo((j.spans[i].s * 1000).toLong()); p.play() }
            }
            Mode.TTS -> sentence()
        }
    }

    // ---- the server voice, sentence by sentence
    private val urls = HashMap<String, String>()
    private var serverOff: String? = null
    private fun urlKey(j: Job, k: Int) = j.voice + "|" + (j.pack ?: "") + "|" + j.texts[k]

    private suspend fun ttsUrl(j: Job, k: Int): String {
        urls[urlKey(j, k)]?.let { return it }
        serverOff?.let { throw Http.Failure(it, "") }
        val body = JSONObject().put("text", j.texts[k]).put("voice", j.voice)
        if (j.pack != null) body.put("pack", j.pack)
        val csrf = j.csrf ?: Http.csrf()
        var r = Http.post("/api/next/tts", body, csrf)
        // a token from before a new sign-in makes the server take the request as a guest's: ask once more with a fresh one
        if (!r.ok && csrf != null && r.json().optString("code") == "guest") r = Http.post("/api/next/tts", body, Http.csrf(force = true))
        val u = r.json().optString("url")
        if (!r.ok || u.isEmpty()) {
            val code = r.json().optString("code").ifEmpty { if (r.code >= 500) "gateway" else "other" }
            if (code == "off" || code == "cap") serverOff = code  // as SV.off on the page: not asked again for this text
            throw Http.Failure(code, r.json().optString("error").ifEmpty { "朗读没生成出来" }, r.code)
        }
        urls[urlKey(j, k)] = u
        return u
    }

    private fun prefetch(j: Job, k: Int) {
        if (k >= j.n) return
        val c = cache()
        scope.launch {
            val u = try { ttsUrl(j, k) } catch (e: Exception) { return@launch }
            withContext(Dispatchers.IO) {
                try {
                    val f = CacheDataSource.Factory().setCache(c).setUpstreamDataSourceFactory(
                        DefaultHttpDataSource.Factory().setUserAgent(Site.userAgent).setDefaultRequestProperties(
                            if (u.startsWith("/audio/own/")) mapOf("Cookie" to (CookieManager.getInstance().getCookie(Site.origin) ?: "")) else emptyMap()))
                    CacheWriter(f.createDataSource(), DataSpec(Uri.parse(Site.abs(u))), null, null).cache()
                } catch (e: Exception) { /* played from the network then */ }
            }
        }
    }

    private fun sentence() {
        val j = job ?: return
        val k = i
        val t = tok
        prefetch(j, k + 1); prefetch(j, k + 2)
        if (urls[urlKey(j, k)] == null) {
            HandlerCompat.postDelayed(main, {
                if (t == tok && i == k && state == "playing") { state = "waiting"; note = "正在准备朗读第 ${k + 1} 句…"; changed("") }
            }, GAP, 400)
        }
        scope.launch {
            val r = runCatching { withTimeout(20_000) { ttsUrl(j, k) } }
            if (t != tok || job !== j) return@launch  // paused, stopped or moved on meanwhile
            main.removeCallbacksAndMessages(GAP)
            state = "playing"
            val u = r.getOrNull()
            if (u != null) {
                note = ""; changed("")
                val p = player()
                p.setMediaItem(MediaItem.Builder().setUri(Site.abs(u)).setMediaId(j.key + "#" + k).build())
                p.setPlaybackSpeed(j.rate)
                p.prepare(); p.play()
            } else {
                note = why(r.exceptionOrNull()); changed("")
                phoneVoice = true
                Speech.say(j.texts[k], j.voice, j.rate) { spoken ->
                    if (t != tok || job !== j) return@say
                    phoneVoice = false
                    if (!spoken) note = "这句没能读出来，接着读下一句"
                    sentenceDone()
                }
            }
        }
    }

    private fun why(e: Throwable?): String {
        val code = (e as? Http.Failure)?.code ?: if (e is kotlinx.coroutines.TimeoutCancellationException) "slow" else "other"
        return when (code) {
            "net" -> "网络不好，这句先用手机自带的声音"
            "slow" -> "自然人声这次生成得太慢，这句先用手机自带的声音"
            "guest" -> "登录后能听 AI 朗读（自然人声），现在先用手机自带的声音"
            "off" -> "AI 朗读（自然人声）暂时没开，先用手机自带的声音"
            "cap" -> "今天的 AI 朗读用完了，先用手机自带的声音"
            else -> (e?.message?.takeIf { it.isNotBlank() && e is Http.Failure } ?: "AI 朗读（自然人声）这次没生成出来") + "，这句先用手机自带的声音"
        }
    }

    /** One sentence said: again (复读), or the next one after its pause, or the end. */
    private fun sentenceDone() {
        val j = job ?: return
        val justSaid = i
        val (next, count) = Sentences.after(i, said + 1, j.rep)
        said = count
        if (next >= j.n) { finish(); return }
        if (next != i) { i = next; save(); changed("") }
        val g = j.gapAfter(justSaid)
        val t = tok
        if (g > 0) {
            if (j.mode == Mode.REC) exo?.pause()
            HandlerCompat.postDelayed(main, { if (t == tok && state == "playing") go() }, GAP, g.toLong())
        } else go()
    }

    private val listener = object : Player.Listener {
        override fun onPlaybackStateChanged(s: Int) {
            val j = job ?: return
            when (s) {
                Player.STATE_BUFFERING -> if (state == "playing" && exo?.playWhenReady == true && !phoneVoice) { state = "waiting"; changed("") }
                Player.STATE_READY -> if (state == "waiting" && exo?.playWhenReady == true) { state = "playing"; note = ""; changed("") }
                Player.STATE_ENDED -> when {
                    j.bySentence -> if (state == "playing" || state == "waiting") { state = "playing"; sentenceDone() }
                    else -> finish()
                }
                else -> {}
            }
        }

        override fun onPlayerError(error: PlaybackException) {
            val j = job ?: return
            Log.w(TAG, "playback error", error)
            if (j.mode == Mode.REC && !onAlt && altUrl(j.src!!) != null) {  // the other line, keeping the place
                onAlt = true
                playRecording((exo?.currentPosition ?: 0) / 1000.0)
                return
            }
            if (j.mode == Mode.TTS && state != "paused") {  // that sentence's file would not play: the phone's voice
                note = "这句的录音没放出来，先用手机自带的声音"; changed("")
                val t = tok
                phoneVoice = true
                Speech.say(j.texts[i], j.voice, j.rate) { _ -> if (t == tok && job === j) { phoneVoice = false; sentenceDone() } }
                return
            }
            note = "音频暂时没加载出来，稍后再点一次"
            halt()
            changed("error")
        }
    }

    private fun altUrl(src: String): String? {
        job?.alt?.let { if (it.startsWith("https://")) return it }
        // as mediaAlt() on the page: the media domain keeps the recordings (not the server voice, not own articles)
        if (!src.startsWith("/audio/") || src.startsWith("/audio/tts/") || src.startsWith("/audio/own/")) return null
        val m = sessionMedia ?: return null
        val base = m.optString("base").ifEmpty { return null }
        val name = src.substringBefore('?').removePrefix("/audio/").removeSuffix(".mp4") + ".m4a"
        return "$base/$name?v=" + Uri.encode(m.optString("version"))
    }

    private var sessionMedia: JSONObject? = null
    private fun learnMedia() = scope.launch { sessionMedia = Http.session()?.optJSONObject("media") }

    // ---- the end, and stopping
    private fun finish() {
        val j = job ?: return
        progress.clear(j.key)
        release()
        note = ""
        changed("ended")
    }

    /** Stop the sound and forget the text; where it was is kept. */
    private fun halt() {
        val j = job ?: return
        if (j.mode == Mode.REC && !j.loop) exo?.let { p -> Sentences.locate(j.spans, p.currentPosition / 1000.0).takeIf { it >= 0 }?.let { i = it } }
        save()
        release()
    }

    private fun release() {
        tok++
        main.removeCallbacksAndMessages(GAP)
        if (phoneVoice) { phoneVoice = false; Speech.stop() }
        exo?.let { it.removeListener(listener); it.release() }
        exo = null
        job = null
        state = "idle"
        resumeOnGain = false
        stopTicks()
        listenForUnplug(false)
        dropFocus()
        PlaybackService.idle()
    }

    private fun save() {
        val j = job ?: return
        progress.set(j.key, i, seconds())
    }

    private fun seconds(): Double = (exo?.currentPosition ?: 0L) / 1000.0

    // ------------------------------------------------------------------ the page and the lock screen hear of it

    private fun changed(why: String) {
        lastWhy = why
        if (job != null && sessionMedia == null) learnMedia()
        session.refresh()
        emit("audio", stateJson().put("key", job?.key ?: lastKey).put("why", why))
        job?.let { lastKey = it.key }
    }

    private var lastKey = ""

    private fun emit(type: String, detail: JSONObject) {
        try { sink?.invoke(type, detail) } catch (e: Exception) { Log.w(TAG, "emit", e) }
    }

    private object GAP  // the token for the pause after a sentence and the 「准备中」 line
    private var tickN = 0
    private val tick = object : Runnable {
        override fun run() {
            val j = job ?: return
            val p = exo
            if (p != null && j.mode == Mode.REC) {
                val t = p.currentPosition / 1000.0
                if (j.bySentence) {
                    if (state == "playing" && p.isPlaying && stopAtEnd >= 0 && t >= stopAtEnd) { stopAtEnd = -1.0; p.pause(); sentenceDone() }
                } else {
                    val si = Sentences.locate(j.spans, t)
                    if (si >= 0 && si != i) { i = si; save(); changed("") }
                }
            }
            tickN++
            // at: when t was read (the page moves the word on between ticks: t + (now − at) × rate)
            if (visible && tickN % 5 == 0) emit("audio-tick", JSONObject().put("key", j.key).put("i", i).put("t", seconds())
                .put("at", System.currentTimeMillis()).put("rate", if (exo?.isPlaying == true) j.rate.toDouble() else 0.0))
            main.postDelayed(this, 50)
        }
    }

    private fun startTicks() { main.removeCallbacks(tick); main.post(tick) }
    private fun stopTicks() = main.removeCallbacks(tick)

    // ------------------------------------------------------------------ audio focus, headphones

    private val am by lazy { app.getSystemService(Context.AUDIO_SERVICE) as AudioManager }
    private var focus: AudioFocusRequest? = null

    private val focusChange = AudioManager.OnAudioFocusChangeListener { change ->
        main.post {
            when (change) {
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT, AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK ->
                    if (state == "playing" || state == "waiting") { resumeOnGain = true; pause("interrupted") }
                AudioManager.AUDIOFOCUS_GAIN -> if (resumeOnGain && state == "paused") { resumeOnGain = false; resume("interrupted") }
                AudioManager.AUDIOFOCUS_LOSS -> { resumeOnGain = false; if (state == "playing" || state == "waiting") pause("other"); dropFocus() }
            }
        }
    }

    private fun takeFocus(): Boolean {
        val f = focus ?: AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(SysAudioAttributes.Builder().setUsage(SysAudioAttributes.USAGE_MEDIA).setContentType(SysAudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setWillPauseWhenDucked(true)
            .setOnAudioFocusChangeListener(focusChange, main)
            .build().also { focus = it }
        return am.requestAudioFocus(f) == AudioManager.AUDIOFOCUS_REQUEST_GRANTED
    }

    private fun dropFocus() { focus?.let { am.abandonAudioFocusRequest(it) } }

    private var unplugListening = false
    private val unplug = object : BroadcastReceiver() {
        override fun onReceive(c: Context, intent: Intent) {
            if (intent.action == AudioManager.ACTION_AUDIO_BECOMING_NOISY && (state == "playing" || state == "waiting")) pause("route")
        }
    }

    private fun listenForUnplug(on: Boolean) {
        if (on == unplugListening) return
        unplugListening = on
        if (on) ContextCompat.registerReceiver(app, unplug, IntentFilter(AudioManager.ACTION_AUDIO_BECOMING_NOISY), ContextCompat.RECEIVER_NOT_EXPORTED)
        else try { app.unregisterReceiver(unplug) } catch (e: Exception) { /* not registered */ }
    }

    /** Another sound of the app's own begins (a recording): the text waits, paused where it was. */
    fun other() { if (state == "playing" || state == "waiting") pause("other") }

    val playing get() = state == "playing" || state == "waiting"

    /** For the lock screen: where in the current item, in ms. */
    fun positionMs(): Long = exo?.currentPosition ?: 0L
    fun durationMs(): Long = exo?.duration?.takeIf { it > 0 && job?.mode == Mode.REC } ?: C.TIME_UNSET

    private fun ok() = JSONObject().put("ok", true)
    private fun fail(why: String, message: String = "") = JSONObject().put("ok", false).put("why", why).put("message", message)
}
