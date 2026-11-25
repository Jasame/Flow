package cn.flowlang.app

import android.app.Application
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import cn.flowlang.app.audio.FlowAudio
import cn.flowlang.app.audio.LongSessionPlayer
import cn.flowlang.app.notify.Reminders

@OptIn(UnstableApi::class)
class FlowApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        LongSessionPlayer.audioContext = this
        FlowAudio.init(this)
        Reminders.channel(this)
    }
}
