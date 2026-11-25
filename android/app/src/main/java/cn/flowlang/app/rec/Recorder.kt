package cn.flowlang.app.rec

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.util.Log
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import cn.flowlang.app.audio.FlowAudio
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File

/**
 * FlowApp.rec (docs/native-bridge.md §4): one spoken answer (跟读、口语对话、发音练习), 16 kHz mono. 'wav' is 16-bit PCM
 * in a WAV file (32 KB a second), 'm4a' is AAC; over 40 s the default is m4a (the page's MIC.payload takes at most 1.4 MB:
 * 40 s of WAV is 1,280,044 bytes). stop() gives the shape of MIC.payload(blob): {ok, mime_type, data (base64), ms, bytes, cut}.
 *
 * While it records, a whole text being read waits (why = other) and other apps' sound is asked to wait too; a call
 * (or the app leaving the screen) cuts it short: what was recorded so far is kept, and `rec` says 'cut'.
 */
@OptIn(UnstableApi::class)
object Recorder {
    private const val TAG = "FlowRec"
    const val RATE = 16_000
    private val main = Handler(Looper.getMainLooper())

    private var record: AudioRecord? = null
    private var media: MediaRecorder? = null
    private var mediaFile: File? = null
    private var thread: Thread? = null
    @Volatile private var running = false
    private var pcm = ByteArrayOutputStream()
    private var startedAt = 0L
    private var format = "wav"
    private var result: JSONObject? = null
    private var cutShort = false
    /** A start waiting for the permission dialog is called off by a stop() or cancel() meanwhile (§4). */
    private var request = 0
    fun begin(): Int = ++request
    fun stillWanted(token: Int) = token == request
    private var focus: AudioFocusRequest? = null
    private lateinit var app: Context

    /** `rec` {state: 'recording' | 'done' | 'cut', ms} */
    var sink: ((String, JSONObject) -> Unit)? = null

    val busy get() = running

    /**
     * Start recording (the microphone permission is already given: MainActivity asks first). max seconds; format 'wav'
     * or 'm4a'. → {ok:true} or {ok:false, why:'busy'|'error', message}.
     */
    @SuppressLint("MissingPermission")
    fun start(context: Context, max: Int, fmt: String?): JSONObject {
        app = context.applicationContext
        if (running) return JSONObject().put("ok", false).put("why", "busy").put("message", "正在录音")
        val seconds = max.coerceIn(1, 300)
        format = when (fmt) { "wav", "m4a" -> fmt; else -> if (seconds > 40) "m4a" else "wav" }
        result = null
        cutShort = false
        FlowAudio.other()
        takeFocus()
        return try {
            if (format == "wav") startPcm() else startM4a(seconds)
            running = true
            startedAt = System.currentTimeMillis()
            main.postDelayed(limit, seconds * 1000L)
            emit("recording", 0)
            JSONObject().put("ok", true).put("format", format).put("max", seconds)
        } catch (e: Exception) {
            Log.w(TAG, "start", e)
            cleanUp()
            dropFocus()
            JSONObject().put("ok", false).put("why", "error").put("message", "麦克风打不开：${e.message ?: "未知原因"}")
        }
    }

    @SuppressLint("MissingPermission")
    private fun startPcm() {
        val min = AudioRecord.getMinBufferSize(RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        if (min <= 0) throw IllegalStateException("这台手机不支持 16 kHz 录音")
        val size = maxOf(min * 2, RATE)  // at least half a second
        // tuned for speech (less automatic gain and noise shaping than MIC on most phones); MIC where it is not there
        fun open(source: Int): AudioRecord? = try {
            AudioRecord(source, RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, size).let { a ->
                if (a.state == AudioRecord.STATE_INITIALIZED) a else { a.release(); null }
            }
        } catch (e: Exception) { null }
        val r = open(MediaRecorder.AudioSource.VOICE_RECOGNITION) ?: open(MediaRecorder.AudioSource.MIC)
            ?: throw IllegalStateException("麦克风被别的 App 占用了")
        pcm = ByteArrayOutputStream(RATE * 2 * 10)
        record = r
        stopping = false
        r.startRecording()
        val buf = ByteArray(min)
        val out = pcm
        thread = Thread({
            while (!stopping) {
                val n = r.read(buf, 0, buf.size)
                if (n > 0) synchronized(out) { out.write(buf, 0, n) } else if (n < 0) break
            }
        }, "flow-rec").also { it.start() }
    }

    @Volatile private var stopping = false

    private fun startM4a(seconds: Int) {
        val f = File(app.cacheDir, "rec-${System.currentTimeMillis()}.m4a")
        mediaFile = f
        val m = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(app) else @Suppress("DEPRECATION") MediaRecorder()
        m.setAudioSource(MediaRecorder.AudioSource.VOICE_RECOGNITION)
        m.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
        m.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
        m.setAudioSamplingRate(RATE)
        m.setAudioChannels(1)
        m.setAudioEncodingBitRate(32_000)
        m.setMaxDuration(seconds * 1000)
        m.setOnInfoListener { _, what, _ -> if (what == MediaRecorder.MEDIA_RECORDER_INFO_MAX_DURATION_REACHED) main.post { end("done") } }
        m.setOutputFile(f.absolutePath)
        m.prepare()
        m.start()
        media = m
    }

    private val limit = Runnable { end("done") }

    /** The recording ends by itself: at max ('done'), or a call / the app leaving the screen ('cut'). */
    private fun end(how: String) {
        if (!running) return
        cutShort = how == "cut"
        result = finishNow()
        emit(how, result?.optLong("ms") ?: 0)
    }

    /** → {mime_type, data, ms}; after an end by itself, what was recorded then. */
    fun stop(): JSONObject {
        if (running) result = finishNow() else request++  // a start still waiting for the permission does not begin
        val r = result
        result = null  // given once, as on iOS (the recording is let go)
        if (r == null || r.optInt("bytes") <= 64) return JSONObject().put("ok", false).put("why", "none").put("message", "没有录到声音，再试一次")
        return JSONObject(r.toString()).put("ok", true).put("cut", cutShort)
    }

    fun cancel() {
        if (running) finishNow() else request++
        result = null
    }

    /** The app left the screen (Android lets only apps in front use the microphone). */
    fun cut() = end("cut")

    private fun finishNow(): JSONObject {
        main.removeCallbacks(limit)
        val ms = System.currentTimeMillis() - startedAt
        running = false
        stopping = true
        val out: JSONObject
        if (format == "wav") {
            try { record?.stop() } catch (e: Exception) { /* already stopped */ }
            try { thread?.join(600) } catch (e: InterruptedException) { /* go on */ }
            val bytes = synchronized(pcm) { pcm.toByteArray() }
            val wav = Wav.wrap(bytes, RATE)
            out = JSONObject().put("mime_type", "audio/wav").put("data", Base64.encodeToString(wav, Base64.NO_WRAP))
                .put("ms", Wav.ms(bytes.size, RATE)).put("bytes", wav.size)
        } else {
            try { media?.stop() } catch (e: Exception) { /* too short: nothing was written */ }
            val f = mediaFile
            val bytes = try { f?.readBytes() } catch (e: Exception) { null } ?: ByteArray(0)
            out = JSONObject().put("mime_type", "audio/mp4").put("data", Base64.encodeToString(bytes, Base64.NO_WRAP)).put("ms", ms).put("bytes", bytes.size)
        }
        cleanUp()
        dropFocus()
        return out
    }

    private fun cleanUp() {
        running = false
        try { record?.release() } catch (e: Exception) { /* gone */ }
        record = null
        thread = null
        stopping = false
        try { media?.release() } catch (e: Exception) { /* gone */ }
        media = null
        mediaFile?.delete()
        mediaFile = null
    }

    private fun emit(state: String, ms: Long) {
        try { sink?.invoke("rec", JSONObject().put("state", state).put("ms", ms)) } catch (e: Exception) { /* page gone */ }
    }

    // other apps' sound waits while the learner speaks; a call takes the focus away: the recording is cut
    private fun takeFocus() {
        val am = app.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val f = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_SPEECH).build())
            .setOnAudioFocusChangeListener({ change -> if (change == AudioManager.AUDIOFOCUS_LOSS || change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT) main.post { cut() } }, main)
            .build()
        focus = f
        am.requestAudioFocus(f)
    }

    private fun dropFocus() {
        val f = focus ?: return
        focus = null
        (app.getSystemService(Context.AUDIO_SERVICE) as AudioManager).abandonAudioFocusRequest(f)
    }
}
