import JavaScriptCore
import MediaPlayer
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
        // switched off, the day's limit: the rest of the text in the iPhone's voice
        for code in ["off", "cap"] {
            XCTAssertTrue(TTSFetcher.refused(SiteError.status(403, code: code, message: "")), code)
        }
        // a guest (and an account that has not agreed to 数据存放在香港, answered as one) still gets the stored ones
        XCTAssertFalse(TTSFetcher.refused(SiteError.status(403, code: "guest", message: "")))
        XCTAssertFalse(TTSFetcher.refused(URLError(.timedOut)))
    }

    @MainActor func testWhyThePhonesVoiceIsForThePageToSay() {
        // docs/native-bridge.md §3: fail {code, server}, worded by the page's SV.why; the codes as the page's own and Android's
        XCTAssertEqual(TTSFetcher.failure(URLError(.notConnectedToInternet)), ["code": "offline", "server": ""])
        XCTAssertEqual(TTSFetcher.failure(URLError(.timedOut)), ["code": "slow", "server": ""])
        XCTAssertEqual(TTSFetcher.failure(URLError(.cannotFindHost)), ["code": "net", "server": ""])
        XCTAssertEqual(TTSFetcher.failure(SiteError.signedOut), ["code": "guest", "server": ""])
        XCTAssertEqual(TTSFetcher.failure(SiteError.status(429, code: "cap", message: "今天的额度用完了")), ["code": "cap", "server": "今天的额度用完了"])
        XCTAssertEqual(TTSFetcher.failure(SiteError.status(502, code: "", message: "")), ["code": "gateway", "server": ""])
        XCTAssertEqual(TTSFetcher.failure(SiteError.status(404, code: "file", message: "")), ["code": "net", "server": ""], "the file itself did not come")
        XCTAssertEqual(TTSFetcher.failure(SiteError.shape), ["code": "other", "server": ""])
    }

    @MainActor func testItemsBringTheAddressesThePageHas() throws {
        // §3 play: items [{text, url}]: a known address is fetched as it is, null is asked of the server (and reported back)
        let r = try XCTUnwrap(LongPlayer.Request(json: ["key": "listen:x", "voice": "us-f", "items": [
            ["text": "One.", "url": "/audio/tts/us-f/ab12.mp3"], ["text": "Two.", "url": NSNull()],
            ["text": "Three.", "url": "https://evil.example/x.mp3"], ["text": "Four.", "url": "https://flow.jasa.hk/audio/tts/cd.mp3"],
        ]], base: base))
        XCTAssertEqual(r.texts, ["One.", "Two.", "Three.", "Four."])
        XCTAssertEqual(r.known(0), "/audio/tts/us-f/ab12.mp3")
        XCTAssertNil(r.known(1))
        XCTAssertNil(r.known(2), "another host's address is not fetched with the learner's cookies")
        XCTAssertEqual(r.known(3), "https://flow.jasa.hk/audio/tts/cd.mp3")
        XCTAssertNil(r.known(9))
        let old = try XCTUnwrap(LongPlayer.Request(json: ["key": "read:x", "texts": ["One."]], base: base))
        XCTAssertNil(old.known(0), "the older form: no address known")
    }

    @MainActor func testTheLockScreenSaysAIVoice() {
        // 《人工智能生成合成内容标识办法》: a synthesized voice is said so where it plays (every voice 语流 has is one)
        let a = LockScreen.labels(title: "今日好句", i: 2, n: 18)
        XCTAssertEqual(a.title, "AI 朗读 · 今日好句")
        XCTAssertEqual(a.artist, "语流 · 第 3 / 18 句")
        XCTAssertEqual(LockScreen.labels(title: " ", i: 0, n: 1).title, "AI 朗读", "no title: the label alone")
        XCTAssertEqual(LockScreen.labels(title: "x", i: 30, n: 18).artist, "语流 · 第 18 / 18 句")
        XCTAssertEqual(LockScreen.labels(title: "x", i: 0, n: 0).artist, "语流")
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
        XCTAssertFalse(AppConfig.isOwn(URL(string: "http://flow.jasa.hk/#/")), "the site over http is not kept in the app")
        XCTAssertFalse(AppConfig.isOwn(URL(string: "ftp://flow.jasa.hk/")))
        XCTAssertFalse(AppConfig.isOwn(URL(string: "http://localhost:8771/#/")), "the local test server only when the app was started on it (FLOW_START_URL)")
    }

    @MainActor func testTheSiteThemeColour() {
        // 我的 → 外观 (html data-accent, PR #282): the app's own controls in 松绿 (default) or 靛蓝, light and dark as the site
        func hex(_ c: UIColor, _ style: UIUserInterfaceStyle) -> String {
            var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
            c.resolvedColor(with: UITraitCollection(userInterfaceStyle: style)).getRed(&r, green: &g, blue: &b, alpha: &a)
            return String(format: "%02x%02x%02x", Int((r * 255).rounded()), Int((g * 255).rounded()), Int((b * 255).rounded()))
        }
        XCTAssertEqual(hex(Accent.color("indigo"), .light), "3461d1")
        XCTAssertEqual(hex(Accent.color("indigo"), .dark), "8eaefc")
        XCTAssertEqual(hex(Accent.color("green"), .light), "1f9d55")
        XCTAssertEqual(hex(Accent.color(nil), .dark), "3ccf7c", "nothing chosen yet: the default green")
        XCTAssertEqual(Accent.name("indigo"), "indigo")
        XCTAssertEqual(Accent.name("purple"), "green", "a name the app does not know: the default")
        XCTAssertTrue(Accent.script.contains("data-accent") || Accent.script.contains("dataset.accent"))
    }

    @MainActor func testOnlyWebsitesMailAndPhoneLeaveTheApp() {
        // security-threat-model.md L9: a link put into the page cannot start another app
        for s in ["https://example.com/", "http://example.com/", "mailto:i@example.com", "tel:10086"] {
            XCTAssertTrue(AppConfig.opensOutside(URL(string: s)), s)
        }
        for s in ["weixin://dl/scan", "alipays://platformapi/startapp", "itms-services://?action=download-manifest", "javascript:alert(1)", "file:///etc/hosts", "sms:10086"] {
            XCTAssertFalse(AppConfig.opensOutside(URL(string: s)), s)
        }
        XCTAssertFalse(AppConfig.opensOutside(nil))
    }

    @MainActor func testTheScriptIsInTheApp() {
        XCTAssertTrue(Bridge.script.contains("window.__flowAppTransport"), "native/flowapp.js is copied into the app")
    }

    /// A page without WebKit: a global object with just what native/flowapp.js touches
    @MainActor private func page() throws -> (JSContext, () -> [String]) {
        let js = try XCTUnwrap(JSContext())
        var errors: [String] = []
        js.exceptionHandler = { _, e in errors.append(e?.toString() ?? "?") }
        js.evaluateScript("""
          var window = globalThis, sent = [], events = [], classes = [], listeners = {}, logged = [];
          var console = { error: function () { logged.push([].slice.call(arguments).join(' ')); } };
          var document = { visibilityState: 'visible', documentElement: { classList: { add: function (c) { classes.push(c); } } },
                           addEventListener: function (t, f) { listeners[t] = f; } };
          function CustomEvent(type, o) { this.type = type; this.detail = o && o.detail; }
          window.dispatchEvent = function (e) { events.push(e.type + ' ' + JSON.stringify(e.detail)); return true; };
        """)
        return (js, { errors })
    }

    /// native/flowapp.js, the wrapper the three apps share (docs/native-bridge.md §2), with a made-up transport
    @MainActor func testTheSharedWrapper() throws {
        let (js, errors) = try page()
        js.evaluateScript("""
          window.__flowAppTransport = { cfg: { v: 1, app: '1.0.0', build: 'abc1234', beta: true, platform: 'android', features: ['audio', 'notify'] },
            send: function (cmd, args) { if (cmd === 'boom') throw new Error('no'); sent.push([cmd, args]); return { ok: true }; },
            extend: function (A, call) { A._extra = function () { return call('extra.one'); }; },
            ready: function (A) { window.readyWith = A.platform; } };
        """)
        js.evaluateScript(Bridge.script)
        js.evaluateScript("""
          FlowApp.notify.sync(null); FlowApp.notify.sync({ hour: 21 }); FlowApp.audio.step(-1); FlowApp.rec.stop();
          FlowApp.call('hello'); FlowApp.call('x', null); FlowApp._extra(); listeners.visibilitychange();
          var got = [], un = FlowApp.on('audio', function (d) { got.push(d.i); });
          FlowApp._emit('audio', { i: 2 }); un(); FlowApp._emit('audio', { i: 3 });
          FlowApp.on('audio', function () { throw new Error('a listener'); }); FlowApp._emit('audio', { i: 4 });
          window.isPromise = FlowApp.call('y') instanceof Promise;
          FlowApp.call('boom').then(function () { window.boom = 'resolved'; }, function (e) { window.boom = e.message; });
          FlowApp.x = 1; window.added = 'x' in FlowApp;
        """)
        let v = { (s: String) in js.evaluateScript(s)?.toString() ?? "" }
        XCTAssertEqual(errors(), [])
        XCTAssertEqual(v("JSON.stringify(sent)"), #"[["notify.sync",{"app":false}],["notify.sync",{"hour":21}],["audio.step",{"d":-1}],["rec.stop",{}],["hello",{}],["x",{}],["extra.one",{}],["app.visible",{}],["y",{}]]"#)
        XCTAssertEqual(v("JSON.stringify(got)"), "[2]", "on() gives back its own off")
        XCTAssertEqual(v("JSON.stringify(events)"), #"["flowapp:audio {\"i\":2}","flowapp:audio {\"i\":3}","flowapp:audio {\"i\":4}"]"#)
        XCTAssertEqual(v("logged.length"), "1", "a listener that throws is logged, the others still run")
        XCTAssertEqual(v("[FlowApp.v, FlowApp.app, FlowApp.build, FlowApp.beta, FlowApp.platform].join(' ')"), "1 1.0.0 abc1234 true android")
        XCTAssertEqual(v("[FlowApp.has('audio'), FlowApp.has('rec'), Object.isFrozen(FlowApp), Object.isFrozen(FlowApp.notify), window.added].join(' ')"), "true false true true false")
        XCTAssertEqual(v("JSON.stringify(classes)"), #"["flow-android"]"#)
        XCTAssertEqual(v("[window.readyWith, typeof window.__flowAppTransport, window.isPromise, window.boom].join(' ')"), "android undefined true no",
                       "ready() after install, the transport gone from window, every call a Promise, a throwing send a rejected one")
        // a second copy (a page that injects again) leaves the first one alone
        js.evaluateScript("window.__flowAppTransport = { cfg: { build: 'other' }, send: function () {} };")
        js.evaluateScript(Bridge.script)
        XCTAssertEqual(v("FlowApp.build + ' ' + typeof window.__flowAppTransport"), "abc1234 undefined")
    }

    /// iOS's own few lines of transport in front of it: WKScriptMessageHandlerWithReply's postMessage({cmd, args})
    @MainActor func testTheIOSTransport() throws {
        let (js, errors) = try page()
        js.evaluateScript("""
          var posted = [];
          window.webkit = { messageHandlers: { flow: { postMessage: function (m) { posted.push(m); return Promise.resolve('answer'); } } } };
        """)
        js.evaluateScript(Bridge.transport(["v": 1, "app": "1.0.0", "platform": "ios", "features": ["audio", "rec", "notify"], "beta": false]) + Bridge.script)
        js.evaluateScript("FlowApp.audio.pause().then(function (r) { window.answer = r; }); FlowApp.notify.permission();")
        let v = { (s: String) in js.evaluateScript(s)?.toString() ?? "" }
        XCTAssertEqual(errors(), [])
        XCTAssertEqual(v("JSON.stringify(posted)"), #"[{"cmd":"audio.pause","args":{}},{"cmd":"notify.permission","args":{}}]"#)
        XCTAssertEqual(v("[window.answer, FlowApp.platform, FlowApp.has('rec'), JSON.stringify(classes)].join(' ')"), #"answer ios true ["flow-ios"]"#)
        // not in the app (no message handler): no transport, no FlowApp, and the page does what it does in Safari
        let (bare, bareErrors) = try page()
        bare.evaluateScript(Bridge.transport(["platform": "ios"]) + Bridge.script)
        XCTAssertEqual(bare.evaluateScript("typeof window.FlowApp")?.toString(), "undefined")
        XCTAssertEqual(bareErrors(), [])
    }
}

/// 「iOS 专属功能」: the switches, the offline packs, the lock screen's study buttons (iOS 27)
final class FeatureTests: XCTestCase {
    override func setUp() {
        for f in Feature.allCases { UserDefaults.standard.removeObject(forKey: f.key) }
    }

    override func tearDown() {
        for f in Feature.allCases { UserDefaults.standard.removeObject(forKey: f.key) }
    }

    @MainActor func testDefaultsAndSwitches() {
        // as on the plan (ios-27-features.md): the lock screen and going on after a call on, the packs off (they take room)
        XCTAssertEqual(Features.on(.smartResume), true)
        XCTAssertEqual(Features.on(.offlinePacks), false)
        XCTAssertEqual(Features.on(.lockScreenStudy), Feature.lockScreenStudy.available, "on where the system has it; elsewhere not shown, counts as off")
        var heard: [(Feature, Bool)] = []
        Features.changed.append { heard.append(($0, $1)) }
        defer { Features.changed.removeLast() }
        Features.set(.offlinePacks, true)
        XCTAssertTrue(Features.on(.offlinePacks))
        XCTAssertEqual(heard.map(\.0), [.offlinePacks])
        XCTAssertEqual(Features.state["offline-packs"], true)
        XCTAssertEqual(Set(Features.state.keys), Set(Feature.allCases.filter(\.available).map(\.rawValue)))
        for f in Feature.allCases { XCTAssertFalse(f.title.isEmpty || f.detail.isEmpty, f.rawValue) }
    }

    @MainActor func testTheBridgeSaysItHasTheSettingsPage() async {
        XCTAssertTrue(Bridge.features.contains("settings"), "the page's 「iOS 专属功能」 row shows for has('settings')")
        let b = Shell.shared.bridge, was = b.onSettings
        defer { b.onSettings = was }
        b.onSettings = nil
        let none = await b.handle("app.settings", [:]) as? [String: Bool]
        XCTAssertEqual(none?["ok"], false, "nothing to show it on: says so")
        b.onSettings = { true }
        let shown = await b.handle("app.settings", [:]) as? [String: Bool]
        XCTAssertEqual(shown?["ok"], true)
        let state = await b.handle("app.features", [:]) as? [String: Bool]
        XCTAssertEqual(state?["offline-packs"], false)
    }

    @MainActor func testAKeptRecordingIsFoundByItsAddress() throws {
        let k = try XCTUnwrap(Packs.key(URL(string: "https://flow.jasa.hk/audio/us-f/v5-campus-a2.mp4?v=41")!))
        XCTAssertEqual(k, "/audio/us-f/v5-campus-a2.mp4?v=41")
        XCTAssertEqual(Packs.key(URL(string: "https://flowlang.cn/audio/us-f/v5-campus-a2.mp4?v=41")!), k, "any of the site's hosts")
        XCTAssertNotEqual(Packs.key(URL(string: "https://flow.jasa.hk/audio/us-f/v5-campus-a2.mp4?v=42")!), k, "a newer recording is another file")
        XCTAssertNil(Packs.key(URL(string: "https://flow.jasa.hk/audio/tts/us-f/ab.mp3")!), "sentences of the server voice are not packed")
        XCTAssertNil(Packs.key(URL(string: "https://flow.jasa.hk/api/next/home")!))
        XCTAssertEqual(Packs.voice(of: URL(string: "https://flow.jasa.hk/audio/uk-m/x.mp4?v=1")!), "uk-m")
        XCTAssertEqual(Packs.address(id: "a b", voice: "us-f", version: "3"), "/audio/us-f/a%20b.mp4?v=3")
        XCTAssertEqual(Packs.key(URL(string: "https://flow.jasa.hk" + Packs.address(id: "a b", voice: "us-f", version: "3"))!), "/audio/us-f/a b.mp4?v=3")
        let odd = Packs.fileName(id: "../x/y", voice: "us-f", version: "3")
        XCTAssertEqual(odd, "us-f__.._x_y__3.mp4")
        XCTAssertFalse(odd.contains("/"), "one name in the folder, nothing outside it")
    }

    @MainActor func testTodaysTextsAsThePageKeepsThem() {
        // 06-offline.js keepTodayOffline: 今天这篇 first, then 今日's, no repeats, three
        let home: [String: Any] = [
            "path": ["steps": [["key": "review", "href": "#/review"], ["key": "read", "href": "#/m/v5-x%20y"]]],
            "today": [["id": "v5-a"], ["id": "v5-x y"], ["id": "v5-b"], ["id": "v5-c"]],
        ]
        XCTAssertEqual(Packs.todaysTexts(home), ["v5-x y", "v5-a", "v5-b"])
        XCTAssertEqual(Packs.todaysTexts(["today": [["id": "v5-a"]]]), ["v5-a"])
        XCTAssertEqual(Packs.todaysTexts([:]), [])
    }

    @MainActor func testKeptFilesGoAfterAWeekAndNineAtMost() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("packs-test-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let p = Packs(dir: dir)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let now = Date()
        func add(_ id: String, daysAgo: Double) throws {
            let name = Packs.fileName(id: id, voice: "us-f", version: "1")
            try Data([1, 2, 3]).write(to: dir.appendingPathComponent(name))
            p.put("/audio/us-f/\(id).mp4?v=1", .init(id: id, voice: "us-f", version: "1", file: name, bytes: 3, title: id, kept: now.addingTimeInterval(-daysAgo * 86400)))
        }
        try add("old", daysAgo: 8)
        try add("today-old", daysAgo: 8)
        try add("new", daysAgo: 1)
        XCTAssertEqual(p.local(for: URL(string: "https://flow.jasa.hk/audio/us-f/new.mp4?v=1")!)?.lastPathComponent, "us-f__new__1.mp4")
        XCTAssertNil(p.local(for: URL(string: "https://flow.jasa.hk/audio/us-f/new.mp4?v=2")!), "another version is not this file")
        p.prune(today: ["today-old"], now: now)
        XCTAssertEqual(Set(p.entries.values.map(\.id)), ["today-old", "new"], "a week old goes, unless it is today's")
        XCTAssertFalse(FileManager.default.fileExists(atPath: dir.appendingPathComponent(Packs.fileName(id: "old", voice: "us-f", version: "1")).path))
        for i in 0..<10 { try add("n\(i)", daysAgo: Double(i) / 10) }
        p.prune(now: now)
        XCTAssertEqual(p.entries.count, Packs.most)
        XCTAssertNil(p.entries.values.first { $0.id == "today-old" }, "the oldest go first")
        // a file iOS cleared meanwhile (Caches): not played from there
        try FileManager.default.removeItem(at: dir.appendingPathComponent(Packs.fileName(id: "n0", voice: "us-f", version: "1")))
        XCTAssertNil(p.local(for: URL(string: "https://flow.jasa.hk/audio/us-f/n0.mp4?v=1")!))
        let again = Packs(dir: dir)
        XCTAssertEqual(again.entries.count, Packs.most - 1, "the list is kept on the phone")
        again.clear()
        XCTAssertTrue(again.entries.isEmpty)
        XCTAssertFalse(FileManager.default.fileExists(atPath: dir.path), "switched off: nothing stays")
    }

    @MainActor func testNoConnectionHandsARecordingBackToThePage() {
        XCTAssertTrue(LongPlayer.handBack(kept: false, online: false), "the page plays it from its own copy (sw.js)")
        XCTAssertFalse(LongPlayer.handBack(kept: true, online: false), "the app's own copy: the app plays it")
        XCTAssertFalse(LongPlayer.handBack(kept: false, online: true))
    }

    #if canImport(NowPlaying)  // the iOS 27 SDK: CI's Xcode 26 has no NowPlaying
    @MainActor func testTheLockScreenStates() throws {
        guard #available(iOS 27, *) else { throw XCTSkip("iOS 27's NowPlaying") }
        var n = LockScreen.Now(key: "k", title: "t", i: 0, n: 3, rate: 1.25, playing: true)
        XCTAssertEqual(LockScreen27.state(n), .playing(rate: 1.25))
        n.waiting = true
        XCTAssertEqual(LockScreen27.state(n), .buffering, "「准备中」")
        n = LockScreen.Now(playing: false, interrupted: true)
        XCTAssertEqual(LockScreen27.state(n), .interrupted, "a call took the sound")
        n.interrupted = false
        XCTAssertEqual(LockScreen27.state(n), .paused)
        XCTAssertEqual(LockScreen27.rates, [0.75, 1, 1.25], "the page's own three (21-study-listen.js)")
    }

    @MainActor func testTheLockScreenSessionCarriesTheAILabel() async throws {
        guard #available(iOS 27, *) else { throw XCTSkip("iOS 27's NowPlaying") }
        Features.set(.lockScreenStudy, true)
        LockScreen.show(LockScreen.Now(key: "listen:x", title: "Radio host", i: 2, n: 10, elapsed: 12, duration: 100, rate: 1, playing: true))
        let info = LockScreen27.info
        XCTAssertEqual(info["title"] as? String, "AI 朗读 · Radio host")
        XCTAssertEqual(info["subtitle"] as? String, "语流 · 第 3 / 10 句")
        XCTAssertEqual(info["commands"] as? Int, 10, "play, pause, toggle, stop, next, previous, back 5 s, rate, repeat, the scrubber")
        XCTAssertFalse(MPRemoteCommandCenter.shared().playCommand.isEnabled, "the older buttons do not answer as well")
        Features.set(.lockScreenStudy, false)
        LockScreen.show(LockScreen.Now(key: "listen:x", title: "Radio host", i: 2, n: 10, rate: 1, playing: true))
        XCTAssertEqual(LockScreen27.info["on"] as? Bool, false, "switched off: the older lock screen")
        XCTAssertTrue(MPRemoteCommandCenter.shared().playCommand.isEnabled)
        XCTAssertEqual(MPNowPlayingInfoCenter.default().nowPlayingInfo?[MPMediaItemPropertyTitle] as? String, "AI 朗读 · Radio host")
        LockScreen.clear()
    }
    #endif
}
