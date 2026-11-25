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

    @MainActor func testLongestWAVFitsThePage() throws {
        // the page refuses more than 1.4 MB (MIC.payload), the server 1.5 MB: the recorder switches to AAC past 40 s
        let w = try XCTUnwrap(WAV.canonical(recorderWAV(samples: 16_000 * Int(Recorder.wavSeconds))))
        XCTAssertLessThan(w.count, 1_400_000)
        let over = try XCTUnwrap(WAV.canonical(recorderWAV(samples: 16_000 * 45)))
        XCTAssertGreaterThan(over.count, 1_400_000, "why 45 s cannot be WAV")
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
        XCTAssertTrue(ids.contains("review-2026-11-27"), "words not reviewed stay due (the mail counts them)")
        XCTAssertTrue(ids.contains("review-2026-12-08"), "after the forecast: every day while there are words")
        XCTAssertEqual(s.first?.date, at(25, 20))
        XCTAssertTrue(s.first!.body.contains("12 个词"))
        XCTAssertTrue(s.allSatisfy { $0.path == "#/review" })
    }

    @MainActor func testNoWordsAtAllNoReminders() {
        let s = ReminderPlan.slots(input { $0.due = 0; $0.forecast = [0, 0, 0, 0, 0, 0, 0]; $0.hasWords = false }, now: at(25, 9), calendar: cal)
        XCTAssertTrue(s.isEmpty, s.map(\.id).joined(separator: " "))
    }

    @MainActor func testChinaTimeByDefault() {
        // the hour is the mail's hour (UTC+8), wherever the phone is
        let s = ReminderPlan.slots(input { _ in }, now: at(25, 9))
        XCTAssertEqual(s.first?.date, at(25, 20))
    }

    @MainActor func testNothingLeftTodayMeansNoReminderToday() {
        let s = ReminderPlan.slots(input { $0.due = 0; $0.new = 0 }, now: at(25, 9), calendar: cal)
        XCTAssertFalse(s.map(\.id).contains("review-2026-11-25"))
        let later = ReminderPlan.slots(input { $0.due = 0; $0.new = 0; $0.later = 30 }, now: at(25, 9), calendar: cal)
        XCTAssertTrue(later.map(\.id).contains("review-2026-11-25"), "beyond the day's share counts too")
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

    @MainActor func testAOnceThatCameTakesThatDay() {
        // 12:30 came (the server forgot it, the app did not): no second reminder at 20:00 that day
        let s = ReminderPlan.slots(input { $0.once = nil; $0.onceSeen = self.at(25, 12, 30).timeIntervalSince1970 }, now: at(25, 13), calendar: cal)
        XCTAssertFalse(s.map(\.id).contains("review-once"))
        XCTAssertFalse(s.map(\.id).contains("review-2026-11-25"))
        XCTAssertEqual(s.first?.id, "review-2026-11-26")
    }

    @MainActor func testOnlyAOnceThatWasScheduledTakesItsDay() {
        // 15:00 chosen with words: scheduled and remembered; after it passed, 20:00 that day stays away
        let once = at(25, 15)
        var x = input { $0.once = once.timeIntervalSince1970 }
        x = ReminderPlan.remember(x, scheduled: ReminderPlan.slots(x, now: at(25, 9), calendar: cal))
        XCTAssertEqual(x.onceSeen, once.timeIntervalSince1970)
        x.once = nil  // the server forgot it
        XCTAssertFalse(ReminderPlan.slots(x, now: at(25, 16), calendar: cal).map(\.id).contains("review-2026-11-25"))
        // 15:00 chosen with nothing to review: not scheduled, not remembered; new words due by 20:00 still get their reminder
        var y = input { $0.once = once.timeIntervalSince1970; $0.due = 0; $0.new = 0; $0.later = 0 }
        y = ReminderPlan.remember(y, scheduled: ReminderPlan.slots(y, now: at(25, 9), calendar: cal))
        XCTAssertNil(y.onceSeen)
        y.once = nil
        y.due = 4
        XCTAssertTrue(ReminderPlan.slots(y, now: at(25, 16), calendar: cal).map(\.id).contains("review-2026-11-25"))
    }

    @MainActor func testOnceWithNothingToReviewDoesNotCome() {
        // tomorrow 8:00 chosen, nothing due then and no book: no reminder then, and none before it
        let s = ReminderPlan.slots(input { $0.once = self.at(26, 8).timeIntervalSince1970; $0.due = 0; $0.forecast = [0, 0, 0, 0, 0, 0, 0]; $0.hasWords = false },
                                   now: at(25, 9), calendar: cal)
        XCTAssertTrue(s.isEmpty, s.map(\.id).joined(separator: " "))
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
        let older = ReminderPlan.input(from: ["reminder": ["hour": 21]], keeping: x)
        XCTAssertEqual(older.once, 1_795_600_000, "a server without once leaves the app's alone")
        let finished = ReminderPlan.input(from: ["plan": ["daily_new": 10], "book": ["done": true]], keeping: x)
        XCTAssertEqual(finished.dailyNew, 0, "a finished book brings no new words")
        let bad = ReminderPlan.input(from: ["reminder": ["hour": 3]], keeping: x)
        XCTAssertEqual(bad.hour, 21, "hours outside REMIND_HOURS are not taken")
    }

    @MainActor func testSavedSettingsFromAnOlderVersionStillLoad() throws {
        // a copy saved before a field existed: the learner's own choices stay, the new field takes its default
        let old = Data(#"{"hour": 21, "planHour": 8, "planMinutes": 15, "app": false, "forecast": [1, 2]}"#.utf8)
        let x = try JSONDecoder().decode(ReminderPlan.Input.self, from: old)
        XCTAssertEqual(x.hour, 21)
        XCTAssertEqual(x.planHour, 8)
        XCTAssertEqual(x.planMinutes, 15)
        XCTAssertFalse(x.app, "the app's reminders stay off")
        XCTAssertEqual(x.later, 0)
        XCTAssertNil(x.onceSeen)
        XCTAssertFalse(x.paused)
    }

    @MainActor func testThePageSeesTheAppsOwnSwitch() {
        // docs/native-bridge.md §5: 'granted' only while they are on; after 关闭 the page offers to turn them on again
        XCTAssertEqual(Reminders.pageState(system: "granted", app: true), "granted")
        XCTAssertEqual(Reminders.pageState(system: "granted", app: false), "undetermined")
        XCTAssertEqual(Reminders.pageState(system: "undetermined", app: true), "undetermined")
        XCTAssertEqual(Reminders.pageState(system: "denied", app: false), "denied", "iOS's own no is said as it is")
        XCTAssertEqual(Reminders.pageState(system: "provisional", app: true), "provisional")
    }

    @MainActor func testNotAgreedToHongKongStorageNoRemindersUntilAgreed() {
        // 403 code storage (an older account before it answers, a paused one after 不同意): the site sends no reminders,
        // the app neither, not even the day's plan; agreeing brings them back on the next refresh
        let once = at(26, 12).timeIntervalSince1970
        var x = input { $0.planHour = 8; $0.once = once }
        x = ReminderPlan.paused(x)
        XCTAssertTrue(x.paused)
        XCTAssertEqual(x.planHour, 8, "the plan's hour is kept for later")
        XCTAssertTrue(ReminderPlan.slots(x, now: at(25, 7), calendar: cal).isEmpty)
        let saved = try? JSONDecoder().decode(ReminderPlan.Input.self, from: JSONEncoder().encode(x))
        XCTAssertEqual(saved?.paused, true, "still paused after the app is closed")
        let back = ReminderPlan.input(from: ["reminder": ["hour": 21], "due": 3, "forecast": [3, 2], "total": 40], keeping: x)
        XCTAssertFalse(back.paused)
        let s = ReminderPlan.slots(back, now: at(25, 7), calendar: cal)
        XCTAssertTrue(s.contains { $0.id == "review-2026-11-25" && $0.date == at(25, 21) })
        XCTAssertTrue(s.contains { $0.id == "plan-2026-11-25" })
        XCTAssertFalse(ReminderPlan.signedOut(x).paused, "signing out (or in as someone else) starts over")
    }

    @MainActor func testSignedOutKeepsOnlyThePlan() {
        var x = input { $0.planHour = 8 }
        x = ReminderPlan.signedOut(x)
        let s = ReminderPlan.slots(x, now: at(25, 7), calendar: cal)
        XCTAssertFalse(s.isEmpty)
        XCTAssertTrue(s.allSatisfy { $0.id.hasPrefix("plan-") })
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

    @MainActor func testServerVoiceRefusals() {
        // off, the day's limit, an account that has not agreed to 数据存放在香港: the rest of the text in the iPhone's voice
        for code in ["off", "cap", "storage"] {
            XCTAssertTrue(TTSFetcher.refused(SiteError.status(403, code: code, message: "")), code)
        }
        XCTAssertFalse(TTSFetcher.refused(SiteError.status(403, code: "guest", message: "")), "a guest still gets the stored ones")
        XCTAssertFalse(TTSFetcher.refused(URLError(.timedOut)))
        XCTAssertEqual(TTSFetcher.reason(SiteError.status(403, code: "storage", message: "")), "账号还没同意数据存放在香港，这句先用 iPhone 自带的声音")
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
