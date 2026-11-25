package cn.flowlang.app.audio

/** One sentence of a recording: where it starts and ends, in seconds (the Kokoro timeline's s and e). */
data class Span(val s: Double, val e: Double)

/**
 * The page's rules for a whole text (01-audio-offline.js NAR.locate / NAR.step / LONG.after), kept here without any
 * Android so the JVM tests can check them.
 */
object Sentences {
    /** The sentence playing at t: from 0.02 s before its start to 0.25 s after its end; -1 between or before them. */
    fun locate(spans: List<Span>, t: Double): Int {
        for (i in spans.indices) {
            val x = spans[i]
            if (t >= x.s - 0.02 && t < x.e + 0.25) return i
            if (t < x.s) break
        }
        return -1
    }

    /** The sentence a previous / next press counts from: the one at t, else the last one that started before t. */
    fun current(spans: List<Span>, t: Double): Int {
        var i = spans.indexOfFirst { t < it.e + 0.25 }
        if (i < 0) i = spans.size - 1
        return i.coerceAtLeast(0)
    }

    /**
     * Previous / next sentence of a recording played straight through (NAR.step): well into a sentence (more than
     * 1.5 s), "previous" goes back to its start first, as players do.
     */
    fun stepTarget(spans: List<Span>, t: Double, d: Int): Int {
        if (spans.isEmpty()) return 0
        val i = current(spans, t)
        val dd = if (d < 0 && t - spans[i].s > 1.5) 0 else d
        return (i + dd).coerceIn(0, spans.size - 1)
    }

    /**
     * After sentence [i] has been said for the [said]-th time: say it again (复读: [rep] times, 0 = until stopped), or go
     * on to the next one. Returns the next index and how many times that one has been said; index == n means the end.
     */
    fun after(i: Int, said: Int, rep: Int): Pair<Int, Int> =
        if (rep == 0 || said < rep) i to said else (i + 1) to 0
}
