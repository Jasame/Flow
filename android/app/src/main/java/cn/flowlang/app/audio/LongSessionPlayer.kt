package cn.flowlang.app.audio

import android.graphics.BitmapFactory
import android.os.Looper
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.common.SimpleBasePlayer
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import cn.flowlang.app.R
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import java.io.ByteArrayOutputStream

/**
 * What the lock screen, the notification shade and the headphones see: one item, 「标题」 and 「AI 朗读 · 第 3 / 20 句」, playing or
 * paused, with previous / next sentence. It only describes [FlowAudio]; the buttons act on it (why = remote), so a
 * pause between sentences, a sentence being made or one read by the phone's own voice still shows as playing.
 */
@OptIn(UnstableApi::class)
class LongSessionPlayer(private val audio: FlowAudio) : SimpleBasePlayer(Looper.getMainLooper()) {

    private val artwork: ByteArray? by lazy {
        try {
            val res = audioContext?.resources ?: return@lazy null
            val bmp = BitmapFactory.decodeResource(res, R.drawable.flow_artwork) ?: return@lazy null
            ByteArrayOutputStream().also { bmp.compress(android.graphics.Bitmap.CompressFormat.PNG, 100, it) }.toByteArray()
        } catch (e: Exception) { null }
    }

    fun refresh() = invalidateState()

    override fun getState(): State {
        val j = audio.job
        if (j == null) {
            return State.Builder()
                .setAvailableCommands(Player.Commands.Builder().addAll(Player.COMMAND_GET_CURRENT_MEDIA_ITEM, Player.COMMAND_GET_TIMELINE, Player.COMMAND_GET_METADATA).build())
                .setPlaybackState(Player.STATE_IDLE)
                .setPlayWhenReady(false, Player.PLAY_WHEN_READY_CHANGE_REASON_USER_REQUEST)
                .build()
        }
        val line = buildString {
            // 「AI 朗读」: every whole text is a synthesized voice (Kokoro, CosyVoice, the phone's own), and the rules for
            // AI-generated content (人工智能生成合成内容标识办法) ask for a label where it is shown (语流 B7)
            append("AI 朗读 · 第 ").append(audio.i + 1).append(" / ").append(j.n).append(" 句")
            if (audio.state == "waiting") append(" · 准备中")
        }
        val meta = MediaMetadata.Builder()
            .setTitle(j.title)
            .setArtist(line)
            .setAlbumTitle("语流 Flow")
            .setDisplayTitle(j.title)
            .setSubtitle(line)
            .apply { artwork?.let { setArtworkData(it, MediaMetadata.PICTURE_TYPE_FRONT_COVER) } }
            .build()
        val item = MediaItemData.Builder("long:" + j.key)
            .setMediaItem(MediaItem.Builder().setMediaId(j.key).setMediaMetadata(meta).build())
            .setMediaMetadata(meta)
            .setDurationUs(audio.durationMs().let { if (it == C.TIME_UNSET) C.TIME_UNSET else it * 1000 })
            .build()
        val cmds = Player.Commands.Builder().addAll(
            Player.COMMAND_PLAY_PAUSE, Player.COMMAND_STOP,
            Player.COMMAND_SEEK_TO_PREVIOUS, Player.COMMAND_SEEK_TO_NEXT,
            Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM, Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM,
            Player.COMMAND_GET_CURRENT_MEDIA_ITEM, Player.COMMAND_GET_TIMELINE, Player.COMMAND_GET_METADATA,
        ).build()
        return State.Builder()
            .setAvailableCommands(cmds)
            .setPlaylist(listOf(item))
            .setCurrentMediaItemIndex(0)
            .setPlayWhenReady(audio.playing, Player.PLAY_WHEN_READY_CHANGE_REASON_USER_REQUEST)
            .setPlaybackState(if (audio.state == "waiting") Player.STATE_BUFFERING else Player.STATE_READY)
            .setContentPositionMs { audio.positionMs() }
            .build()
    }

    override fun handleSetPlayWhenReady(playWhenReady: Boolean): ListenableFuture<*> {
        if (playWhenReady) audio.resume("remote") else audio.pause("remote")
        return Futures.immediateVoidFuture()
    }

    override fun handleSeek(mediaItemIndex: Int, positionMs: Long, seekCommand: Int): ListenableFuture<*> {
        when (seekCommand) {
            Player.COMMAND_SEEK_TO_PREVIOUS, Player.COMMAND_SEEK_TO_PREVIOUS_MEDIA_ITEM -> audio.step(-1, "remote")
            Player.COMMAND_SEEK_TO_NEXT, Player.COMMAND_SEEK_TO_NEXT_MEDIA_ITEM -> audio.step(1, "remote")
        }
        return Futures.immediateVoidFuture()
    }

    override fun handleStop(): ListenableFuture<*> {
        audio.stop("remote")
        return Futures.immediateVoidFuture()
    }

    companion object {
        /** Set by FlowApplication: where the artwork is read from. */
        var audioContext: android.content.Context? = null
    }
}
