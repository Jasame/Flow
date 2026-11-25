import XCTest
@testable import Flow

/// The parts that are plain logic: the WAV the server gets, which reminders go on the phone, how the page's play()
/// is read, and the bridge's JSON.
final class WAVTests: XCTestCase {
    /// A WAV the way AVAudioRecorder writes one: RIFF, fmt, an FLLR padding chunk, then the samples.
    @MainActor private func recorderWAV(samples: Int, rate: UInt32 = 16_000, fllr: Int = 4044) -> Data {
        var d = Data("RIFF".utf8) + WAV.le32(0) + Data("WAVE".utf8)
        var fmt = Data()
        fmt += withUnsafeBytes(of: UInt16(1).littleEndian) { Data($0) }    // PCM
        fmt += withUnsafeBytes(of: UInt16(1).littleEndian) { Data($0) }    // mono
        fmt += WAV.le32(rate) + WAV.le32(rate * 2)
        fmt += withUnsafeBytes(of: UInt16(2).littleEndian) { Data($0) }    // block align
        fmt += withUnsafeBytes(of: UInt16(16).littleEndian) { Data($0) }   // bits
        d += Data("fmt ".utf8) + WAV.le32(UInt32(fmt.count)) + fmt
        d += Data("FLLR".utf8) + WAV.le32(UInt32(fllr)) + Data(count: fllr)
        let pcm = Data((0..<samples * 2).map { UInt8($0 % 251) })
        d += Data("data".utf8) + WAV.le32(UInt32(pcm.count)) + pcm
        return d
    }

    @MainActor func testCanonicalDropsPaddingAndKeepsTheSamples() throws {
        let w = try XCTUnwrap(WAV.canonical(recorderWAV(samples: 16_000)))
        XCTAssertEqual(w.count, 44 + 32_000)
        XCTAssertEqual(String(decoding: w.prefix(4), as: UTF8.self), "RIFF")
        XCTAssertEqual(String(decoding: w.subdata(in: 8..<12), as: UTF8.self), "WAVE")
        XCTAssertEqual(String(decoding: w.subdata(in: 36..<40), as: UTF8.self), "data")
        let d = try XCTUnwrap(WAV.describe(w))
        XCTAssertEqual(d.rate, 16_000)
        XCTAssertEqual(d.channels, 1)
        XCTAssertEqual(d.bits, 16)
        XCTAssertEqual(d.seconds, 1, accuracy: 0.001)
    }

    @MainActor func testCutRecordingKeepsWhatIsThere() throws {
        var raw = recorderWAV(samples: 8_000)
        raw = raw.prefix(raw.count - 1000)  // the data chunk says more than the file has
        let w = try XCTUnwrap(WAV.canonical(raw))
        XCTAssertEqual(w.count, 44 + 16_000 - 1000)
    }

    @MainActor func testNotAWav() {
        XCTAssertNil(WAV.canonical(Data("hello world, not a wav".utf8)))
        XCTAssertNil(WAV.canonical(Data()))
    }

    @MainActor func testUnder1Point5MBForFortyFiveSeconds() throws {
        // the server takes 1.5 MB (audio_validation.MAX_AUDIO_BYTES): 45 s of 16 kHz 16-bit mono WAV fits
        let w = try XCTUnwrap(WAV.canonical(recorderWAV(samples: 16_000 * 45)))
        XCTAssertLessThan(w.count, 1_500_000)
    }
}

final class ReminderPlanTests: XCTestCase {
    private var cal: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "Asia/Shanghai")!
        return c
    }()

    @MainActor private func at(_ day: Int, _ hour: Int, _ minute: Int = 0) -> Date {
        cal.date(from: DateComponents(year: 2026, month: 11, day: day, hour: hour, minute: minute))!
    }

    @MainActor private func input(_ f: (inout ReminderPlan.Input) -> Void) -> ReminderPlan.Input {
        var x = ReminderPlan.Input()
        x.hour = 20
        x.due = 12
        x.new = 0
        x.minutes = 6
        x.forecast = [12, 5, 0, 7, 3, 0, 2]
        x.hasWords = true
        f(&x)
        return x
    }

    @MainActor func testEveryDayAtTheHourOnlyWithWords() {
        let s = ReminderPlan.slots(input { _ in }, now: at(25, 9), calendar: cal)
        let ids = s.map(\.id)
        XCTAssertEqual(ids.first, "review-2026-11-25")
        XCTAssertTrue(ids.contains("review-2026-11-26"))
        XCTAssertFalse(ids.contains("review-2026-11-27"), "forecast 0 that day")
        XCTAssertFalse(ids.contains("review-2026-11-30"), "forecast 0 that day")
        XCTAssertTrue(ids.contains("review-2026-12-08"), "after the forecast: every day while there are words")
        XCTAssertEqual(s.first?.date, at(25, 20))
        XCTAssertTrue(s.first!.body.contains("12 个词"))
        XCTAssertTrue(s.allSatisfy { $0.path == "#/review" })
    }

    @MainActor func testNothingLeftTodayMeansNoReminderToday() {
        let s = ReminderPlan.slots(input { $0.due = 0; $0.new = 0 }, now: at(25, 9), calendar: cal)
        XCTAssertFalse(s.map(\.id).contains("review-2026-11-25"))
    }

    @MainActor func testPastTheHourTodayStartsTomorrow() {
        let s = ReminderPlan.slots(input { _ in }, now: at(25, 21), calendar: cal)
        XCTAssertEqual(s.first?.id, "review-2026-11-26")
    }

    @MainActor func testOnceReplacesTheDailyOnesUntilThenAndThatDay() {
        // 这次什么时候复习: tomorrow 12:30 — no 20:00 today, none tomorrow evening, then daily again
        let once = at(26, 12, 30)
        let s = ReminderPlan.slots(input { $0.once = once.timeIntervalSince1970 }, now: at(25, 9), calendar: cal)
        let ids = s.map(\.id)
        XCTAssertEqual(ids.first, "review-once")
        XCTAssertEqual(s.first?.date, once)
        XCTAssertFalse(ids.contains("review-2026-11-25"))
        XCTAssertFalse(ids.contains("review-2026-11-26"))
        XCTAssertTrue(ids.contains("review-2026-11-28"))
    }

    @MainActor func testOnceInThePastIsIgnored() {
        let s = ReminderPlan.slots(input { $0.once = self.at(25, 8).timeIntervalSince1970 }, now: at(25, 9), calendar: cal)
        XCTAssertFalse(s.map(\.id).contains("review-once"))
        XCTAssertEqual(s.first?.id, "review-2026-11-25")
    }

    @MainActor func testThePlanReminderAndNoDoubleAtTheSameHour() {
        let s = ReminderPlan.slots(input { $0.planHour = 20; $0.planMinutes = 15 }, now: at(25, 9), calendar: cal)
        let today = s.filter { cal.isDate($0.date, inSameDayAs: at(25, 9)) }
        XCTAssertEqual(today.map(\.id), ["plan-2026-11-25"], "the plan has the words in it")
        XCTAssertTrue(today[0].body.contains("15 分钟"))
        XCTAssertEqual(today[0].path, "#/")
    }

    @MainActor func testTurnedOffInTheApp() {
        XCTAssertTrue(ReminderPlan.slots(input { $0.app = false }, now: at(25, 9), calendar: cal).isEmpty)
    }

    @MainActor func testFitsInIOSLimit() {
        // iOS keeps at most 64 pending notifications per app
        let s = ReminderPlan.slots(input { $0.planHour = 8; $0.once = self.at(26, 7).timeIntervalSince1970 }, now: at(25, 0, 30), calendar: cal)
        XCTAssertLessThanOrEqual(s.count, 64)
    }

    @MainActor func testInputFromTheSite() {
        let j: [String: Any] = ["reminder": ["hour": 21, "once": 1_795_600_000.0, "enabled": false], "due": 4, "new": 10, "minutes": 7,
                                "forecast": [4, 3, 2, 1, 0, 0, 5], "plan": ["daily_new": 10, "book": "cet4"], "total": 120]
        var old = ReminderPlan.Input()
        old.planHour = 8
        let x = ReminderPlan.input(from: j, keeping: old)
        XCTAssertEqual(x.hour, 21)
        XCTAssertEqual(x.once, 1_795_600_000)
        XCTAssertEqual(x.due, 4)
        XCTAssertEqual(x.new, 10)
        XCTAssertEqual(x.forecast, [4, 3, 2, 1, 0, 0, 5])
        XCTAssertEqual(x.dailyNew, 10)
        XCTAssertTrue(x.hasWords)
        XCTAssertEqual(x.planHour, 8, "the app's own setting is kept")
        let cleared = ReminderPlan.input(from: ["reminder": ["hour": 21, "once": NSNull()]], keeping: x)
        XCTAssertNil(cleared.once)
    }
}

final class LongPlayerRequestTests: XCTestCase {
    private let base = URL(string: "https://flow.jasa.hk/#/study/x")!

    @MainActor func testARecording() throws {
        let r = try XCTUnwrap(LongPlayer.Request(json: [
            "key": "listen:abc", "title": "标题", "src": "/audio/us-f/abc.mp4?v=3", "sentences": [[0, 2.9], ["s": 3.1, "e": 5.0]],
            "from": 1, "loop": true, "rep": 3, "gap": [0, 800], "rate": 0.8,
        ], base: base))
        XCTAssertEqual(r.src?.absoluteString, "https://flow.jasa.hk/audio/us-f/abc.mp4?v=3")
        XCTAssertEqual(r.sentences, [.init(s: 0, e: 2.9), .init(s: 3.1, e: 5.0)])
        XCTAssertEqual(r.count, 2)
        XCTAssertFalse(r.straight)
        XCTAssertEqual(r.rep, 3)
        XCTAssertEqual(r.gap(1), 800)
        XCTAssertEqual(r.gap(5), 0)
        XCTAssertEqual(r.rate, 0.8, accuracy: 0.001)
    }

    @MainActor func testTextsAndOneGapForAll() throws {
        let r = try XCTUnwrap(LongPlayer.Request(json: ["key": "read:x", "texts": ["One.", "Two."], "voice": "uk-m", "gap": 500, "rate": 9], base: base))
        XCTAssertNil(r.src)
        XCTAssertEqual(r.count, 2)
        XCTAssertEqual(r.gap(0), 500)
        XCTAssertEqual(r.gap(1), 500)
        XCTAssertEqual(r.rate, 2, "clamped")
        XCTAssertEqual(r.voice, "uk-m")
    }

    @MainActor func testRefused() {
        XCTAssertNil(LongPlayer.Request(json: ["key": "x"], base: base), "nothing to read")
        XCTAssertNil(LongPlayer.Request(json: ["src": "/a.mp4"], base: base), "a recording without sentence times")
        XCTAssertNil(LongPlayer.Request(json: ["src": "javascript:alert(1)", "sentences": [[0, 1]]], base: base)?.src)
    }

    @MainActor func testSentenceLookupLikeTheWebPage() {
        let ss: [LongPlayer.Span] = [.init(s: 0, e: 2.9), .init(s: 3.4, e: 6), .init(s: 7, e: 9)]
        XCTAssertEqual(LongPlayer.sentence(at: 1, in: ss), 0)
        XCTAssertEqual(LongPlayer.sentence(at: 3.0, in: ss), 0, "0.25 s after the end still counts")
        XCTAssertNil(LongPlayer.sentence(at: 6.5, in: ss), "between two sentences")
        XCTAssertEqual(LongPlayer.sentenceAfter(6.5, in: ss), 2)
        XCTAssertEqual(LongPlayer.sentence(at: 8, in: ss), 2)
    }
}

final class BridgeTests: XCTestCase {
    @MainActor func testJSStringEscapes() {
        XCTAssertEqual(Bridge.js("#/review"), "\"#\\/review\"")
        XCTAssertEqual(Bridge.js("a\"b</script>"), "\"a\\\"b<\\/script>\"")
    }

    @MainActor func testJSON() {
        XCTAssertEqual(Bridge.json(["a": 1]), "{\"a\":1}")
        XCTAssertEqual(Bridge.json(Date()), "null", "not JSON: null, never a crash")
    }

    @MainActor func testOwnHostsOnly() {
        XCTAssertTrue(AppConfig.isOwn(URL(string: "https://flow.jasa.hk/#/")))
        XCTAssertFalse(AppConfig.isOwn(URL(string: "https://example.com/")))
        XCTAssertFalse(AppConfig.isOwn(URL(string: "https://flow.jasa.hk.example.com/")))
        XCTAssertTrue(AppConfig.isOwnOrigin(host: "flow.jasa.hk", scheme: "https"))
        XCTAssertFalse(AppConfig.isOwnOrigin(host: "flow.jasa.hk", scheme: "http"))
        XCTAssertFalse(AppConfig.isOwnOrigin(host: "evil.example", scheme: "https"))
    }

    @MainActor func testTheScriptIsInTheApp() {
        XCTAssertTrue(Bridge.script.contains("window.FlowApp"), "FlowBridge.js is copied into the app")
    }
}
