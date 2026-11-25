package cn.flowlang.app.audio

import org.junit.Assert.assertEquals
import org.junit.Test

class SentencesTest {
    // the first three sentences of v5-travel-b1-street-food (us-f), as the server's timeline has them
    private val spans = listOf(Span(0.0, 4.779), Span(5.079, 8.364), Span(8.664, 10.093))

    @Test fun locateFollowsThePagesRule() {
        assertEquals(0, Sentences.locate(spans, 0.0))
        assertEquals(0, Sentences.locate(spans, 4.9))          // up to 0.25 s after the end
        assertEquals(1, Sentences.locate(spans, 5.06))         // from 0.02 s before the start
        assertEquals(2, Sentences.locate(spans, 10.3))
        assertEquals(-1, Sentences.locate(spans, 10.4))        // after the last one
        assertEquals(-1, Sentences.locate(spans, 5.05))        // between two sentences
    }

    @Test fun previousGoesBackToTheStartFirst() {
        assertEquals(1, Sentences.stepTarget(spans, 7.0, -1))  // 1.9 s into sentence 1: its start
        assertEquals(0, Sentences.stepTarget(spans, 5.5, -1))  // just started: the one before
        assertEquals(2, Sentences.stepTarget(spans, 5.5, 1))
        assertEquals(2, Sentences.stepTarget(spans, 9.0, 1))   // never past the last
        assertEquals(0, Sentences.stepTarget(spans, 0.5, -1))  // never before the first
    }

    @Test fun repeatsThenMovesOn() {
        assertEquals(0 to 1, Sentences.after(0, 1, 2))         // 复读 2: once more
        assertEquals(1 to 0, Sentences.after(0, 2, 2))         // then the next
        assertEquals(1 to 0, Sentences.after(0, 1, 1))         // no 复读
        assertEquals(0 to 7, Sentences.after(0, 7, 0))         // 0 = until stopped
    }
}
