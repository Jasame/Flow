package cn.flowlang.app.rec

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class WavTest {
    private fun le32(b: ByteArray, at: Int) = (b[at].toInt() and 0xff) or ((b[at + 1].toInt() and 0xff) shl 8) or
        ((b[at + 2].toInt() and 0xff) shl 16) or ((b[at + 3].toInt() and 0xff) shl 24)
    private fun le16(b: ByteArray, at: Int) = (b[at].toInt() and 0xff) or ((b[at + 1].toInt() and 0xff) shl 8)

    @Test fun headerIs16kMono16bit() {
        val h = Wav.header(32_000)
        assertEquals(44, h.size)
        assertEquals("RIFF", String(h, 0, 4)); assertEquals("WAVE", String(h, 8, 4)); assertEquals("fmt ", String(h, 12, 4)); assertEquals("data", String(h, 36, 4))
        assertEquals(36 + 32_000, le32(h, 4))
        assertEquals(1, le16(h, 20))          // PCM
        assertEquals(1, le16(h, 22))          // mono
        assertEquals(16_000, le32(h, 24))     // sample rate
        assertEquals(32_000, le32(h, 28))     // bytes a second
        assertEquals(2, le16(h, 32))          // block align
        assertEquals(16, le16(h, 34))         // bits
        assertEquals(32_000, le32(h, 40))
    }

    @Test fun wrapKeepsThePcm() {
        val pcm = byteArrayOf(1, 2, 3, 4)
        val w = Wav.wrap(pcm)
        assertEquals(48, w.size)
        assertArrayEquals(pcm, w.copyOfRange(44, 48))
    }

    @Test fun millisecondsOfPcm() {
        assertEquals(1000L, Wav.ms(32_000))
        assertEquals(2992L, Wav.ms(95_744))   // the 3-second recording on the emulator
    }
}
