package cn.flowlang.app.rec

/** A WAV file around 16-bit PCM: the same format as the page's FLOW_SAY_WAV (16 kHz, mono). */
object Wav {
    fun header(pcmBytes: Int, sampleRate: Int = 16_000, channels: Int = 1, bits: Int = 16): ByteArray {
        val byteRate = sampleRate * channels * bits / 8
        val h = ByteArray(44)
        fun str(at: Int, s: String) = s.forEachIndexed { k, c -> h[at + k] = c.code.toByte() }
        fun int(at: Int, v: Int) { for (k in 0 until 4) h[at + k] = (v ushr (8 * k) and 0xff).toByte() }
        fun short(at: Int, v: Int) { h[at] = (v and 0xff).toByte(); h[at + 1] = (v ushr 8 and 0xff).toByte() }
        str(0, "RIFF"); int(4, 36 + pcmBytes); str(8, "WAVE")
        str(12, "fmt "); int(16, 16); short(20, 1); short(22, channels); int(24, sampleRate); int(28, byteRate)
        short(32, channels * bits / 8); short(34, bits)
        str(36, "data"); int(40, pcmBytes)
        return h
    }

    fun wrap(pcm: ByteArray, sampleRate: Int = 16_000): ByteArray = header(pcm.size, sampleRate) + pcm

    /** Milliseconds of 16-bit mono PCM at [sampleRate]. */
    fun ms(pcmBytes: Int, sampleRate: Int = 16_000): Long = pcmBytes * 1000L / (sampleRate * 2)
}
