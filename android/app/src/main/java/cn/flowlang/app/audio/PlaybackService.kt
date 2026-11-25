package cn.flowlang.app.audio

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.session.DefaultMediaNotificationProvider
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import cn.flowlang.app.MainActivity
import cn.flowlang.app.R

/**
 * Keeps a whole text going with the screen off or the app in the background, and puts its controls on the lock screen
 * and in the notification shade (Media3 makes the notification and the foreground service from [FlowAudio.session]).
 */
@OptIn(UnstableApi::class)
class PlaybackService : MediaSessionService() {
    private var session: MediaSession? = null

    override fun onCreate() {
        super.onCreate()
        FlowAudio.init(this)
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        setMediaNotificationProvider(DefaultMediaNotificationProvider.Builder(this)
            .setChannelId(CHANNEL)
            .setChannelName(R.string.channel_playback)
            .build()
            .also { it.setSmallIcon(R.drawable.ic_stat_flow) })
        val s = MediaSession.Builder(this, FlowAudio.session).setId("flow-long").setSessionActivity(open).build()
        session = s
        addSession(s)
        running = this
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    // Swiped away from the recent apps: a text playing goes on (that is the point); a paused one is put away.
    override fun onTaskRemoved(rootIntent: Intent?) {
        if (!FlowAudio.playing) { FlowAudio.stop("other"); stopSelf() }
    }

    override fun onDestroy() {
        running = null
        session?.release()
        session = null
        super.onDestroy()
    }

    companion object {
        const val CHANNEL = "playback"
        private var running: PlaybackService? = null
        private val main = Handler(Looper.getMainLooper())
        private val stopLater = Runnable { if (FlowAudio.job == null) running?.stopSelf() }

        /** A text starts: the service (and so the session) is there before the sound. The app is in front then. */
        fun start(context: Context) {
            main.removeCallbacks(stopLater)
            if (running != null) return
            try { context.startService(Intent(context, PlaybackService::class.java)) } catch (e: Exception) { /* not allowed from the background */ }
        }

        /** Nothing left to play: the notification goes (Media3) and, a moment later unless another text starts, the service. */
        fun idle() {
            main.removeCallbacks(stopLater)
            main.postDelayed(stopLater, 1500)
        }
    }
}
