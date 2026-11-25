import UIKit
import XCTest

/// The app on the simulator, against the 内测版 (flow.jasa.hk, needs the network): it opens, the sign-in sheet, a whole
/// text played by the app (with the page away and in Control Center), the microphone question, reminders.
/// Screenshots are attached to the result (README.md: how to get them out). Run:
///   xcodebuild test -project ios/Flow.xcodeproj -scheme Flow-Beta -destination 'platform=iOS Simulator,name=iPhone 17e'
final class FlowUITests: XCTestCase {
    @MainActor private var made: XCUIApplication?
    @MainActor private var app: XCUIApplication {
        if let made { return made }
        let a = XCUIApplication()
        // no sound from tests (the owner's rule): the app plays at volume 0 and is checked by state and events
        a.launchArguments += ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN", "-FlowMuteAudio", "YES"]
        made = a
        return a
    }
    @MainActor private var springboard: XCUIApplication { XCUIApplication(bundleIdentifier: "com.apple.springboard") }

    override func setUp() {
        continueAfterFailure = false
    }

    // MARK: helpers

    @MainActor private func shot(_ name: String, screen: Bool = false) {
        let s = screen ? XCUIScreen.main.screenshot() : app.screenshot()
        let a = XCTAttachment(screenshot: s)
        a.name = "\(UIDevice.current.userInterfaceIdiom == .pad ? "ipad" : "iphone")-\(name)"
        a.lifetime = .keepAlways
        add(a)
    }

    @MainActor private var web: XCUIElement { app.webViews.firstMatch }

    /// a text on the page that starts with prefix (the bridge page's lines: 「state: playing …」)
    @MainActor private func line(_ prefix: String) -> XCUIElement {
        web.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", prefix)).firstMatch
    }

    @MainActor private func wait(_ e: XCUIElement, _ secs: TimeInterval = 20, _ what: String) {
        XCTAssertTrue(e.waitForExistence(timeout: secs), "not seen: \(what)")
    }

    @MainActor private func value(_ prefix: String) -> String { line(prefix).exists ? line(prefix).label : "" }

    @MainActor private func bridgePage() {
        app.launchEnvironment["FLOW_BRIDGE_TEST"] = "1"
        app.launch()
        wait(web.staticTexts["语流 App 桥测试"], 30, "the bridge test page")
        XCTAssertTrue(line("FlowApp: v1").waitForExistence(timeout: 5), "window.FlowApp is there: \(value("FlowApp:"))")
    }

    @MainActor private func tapButton(_ title: String) {
        let b = web.buttons[title]
        wait(b, 10, title)
        b.tap()
    }

    /// iOS's own question (microphone, notifications): answered yes; its text is returned.
    @discardableResult
    @MainActor private func allowSystemAlert(_ secs: TimeInterval = 15) -> String? {
        let alert = springboard.alerts.firstMatch
        guard alert.waitForExistence(timeout: secs) else { return nil }
        let text = ([alert.label] + alert.staticTexts.allElementsBoundByIndex.map(\.label)).joined(separator: " ")
        shot("system-alert", screen: true)
        let yes = alert.buttons.matching(NSPredicate(format: "label IN %@", ["允许", "Allow", "好", "OK"])).firstMatch
        if yes.exists { yes.tap() } else { alert.buttons.element(boundBy: alert.buttons.count - 1).tap() }
        return text
    }

    @MainActor private func dismissBetaSheet() {
        let stay = web.buttons["留在内测版"]
        if stay.waitForExistence(timeout: 8) { stay.tap() }
    }

    // MARK: tests

    @MainActor func test1OpensTheSite() {
        app.launch()
        wait(web, 30, "the web view")
        let first = web.staticTexts.matching(NSPredicate(format: "label CONTAINS %@ OR label CONTAINS %@ OR label CONTAINS %@", "你学英语主要为了什么", "今日", "语流")).firstMatch
        wait(first, 40, "the site's first page")
        shot("01-open")
    }

    @MainActor func test2SignInSheet() {
        app.launch()
        wait(web, 30, "the web view")
        let first = web.staticTexts.matching(NSPredicate(format: "label CONTAINS %@ OR label CONTAINS %@", "你学英语主要为了什么", "今日")).firstMatch
        wait(first, 60, "the site's first page")
        dismissBetaSheet()  // 「这里是语流内测版」 comes 0.7 s after the page
        let login = web.buttons["已有账号？登录"].exists ? web.buttons["已有账号？登录"] : web.buttons.matching(NSPredicate(format: "label CONTAINS %@", "登录")).firstMatch
        wait(login, 30, "a sign-in button")
        login.tap()
        if !web.staticTexts["登录语流"].waitForExistence(timeout: 8) {  // the 内测版 sheet came late and took the tap
            dismissBetaSheet()
            login.tap()
        }
        wait(web.staticTexts["登录语流"], 15, "the sign-in sheet")
        let field = web.textFields.firstMatch
        wait(field, 10, "the e-mail field")
        field.tap()
        field.typeText("learner@example.com")
        shot("02-sign-in")
    }

    @MainActor func test3PlaysAWholeTextInTheApp() {
        bridgePage()
        tapButton("播放全文")
        // the recording comes over the network first (「准备中」), then the app's time goes on
        let ticking = web.staticTexts.matching(NSPredicate(format: "label MATCHES %@", "t: [0-9]+\\.[0-9] i: [0-9]+")).firstMatch
        if !ticking.waitForExistence(timeout: 40) {
            // a weak line: 「录音没加载出来，网络好一点再点继续」 — 继续 loads the recording again (LongPlayer.resume)
            XCTAssertTrue(value("state: ").contains("why: error"), "neither playing nor an error: \(value("state: "))")
            tapButton("继续")
            wait(ticking, 40, "time from the app after 继续")
        }
        wait(line("state: playing"), 5, "playing")
        shot("03-playing")
        tapButton("下一句")
        Thread.sleep(forTimeInterval: 1)
        tapButton("暂停")
        wait(line("state: paused"), 5, "paused")
        let pausedAt = value("t: ")
        Thread.sleep(forTimeInterval: 2)
        XCTAssertEqual(value("t: "), pausedAt, "paused means paused")
        tapButton("继续")
        wait(line("state: playing"), 5, "playing again")

        // the page away (home screen): the app keeps reading
        XCUIDevice.shared.press(.home)
        Thread.sleep(forTimeInterval: 6)
        app.activate()
        wait(line("state: playing"), 5, "still playing after the home screen")
        tapButton("停止")
        wait(line("state: idle"), 5, "stopped")
    }

    @MainActor func test4LockScreenAndControlCenter() throws {
        bridgePage()
        tapButton("播放全文")
        wait(line("state: playing"), 30, "playing")
        // Control Center (swipe down from the top right): the Now Playing tile names the text and pauses it
        let w = springboard.frame.width
        let from = springboard.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: w - 30, dy: 4))
        from.press(forDuration: 0.1, thenDragTo: springboard.coordinate(withNormalizedOffset: .zero).withOffset(CGVector(dx: w - 30, dy: 420)))
        Thread.sleep(forTimeInterval: 2)
        shot("04-control-center", screen: true)
        let title = springboard.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "语流 ·")).firstMatch
        let seen = title.waitForExistence(timeout: 5)
        if seen {
            let pause = springboard.buttons.matching(NSPredicate(format: "label IN %@", ["暂停", "Pause"])).firstMatch
            if pause.exists {
                pause.tap()
                Thread.sleep(forTimeInterval: 1)
                shot("04-control-center-paused", screen: true)
            }
        }
        // close Control Center
        springboard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.95)).press(forDuration: 0.1, thenDragTo: springboard.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.2)))
        Thread.sleep(forTimeInterval: 1)
        app.activate()
        if seen {
            // back in front the app sends its state again (why: state), so only "paused" is checked here
            wait(line("state: paused"), 5, "paused from Control Center")
        } else {
            throw XCTSkip("this simulator shows no Now Playing tile in Control Center (a phone does)")
        }
    }

    @MainActor func test5MicrophoneQuestionAndWAV() {
        app.resetAuthorizationStatus(for: .microphone)
        bridgePage()
        tapButton("录音两秒")
        let asked = allowSystemAlert()
        XCTAssertNotNil(asked, "iOS asks for the microphone")
        if let asked { XCTAssertTrue(asked.contains("语流要用麦克风"), "the reason in Info.plist is shown: \(asked)") }
        let done = line("rec: ok")
        wait(done, 15, "a recording back from the app")
        XCTAssertTrue(done.label.contains("audio/wav RIFF/WAVE 16000 Hz"), done.label)
        shot("05-recorded")
    }

    @MainActor func test6ReviewReminders() {
        bridgePage()
        tapButton("排复习提醒")
        allowSystemAlert(8)
        let out = line("notify: allowed")
        wait(out, 15, "reminders scheduled")
        XCTAssertTrue(out.label.contains("first review-once"), out.label)
        let n = Int(out.label.components(separatedBy: "pending ").last?.split(separator: " ").first ?? "0") ?? 0
        XCTAssertGreaterThanOrEqual(n, 5, out.label)
        shot("06-reminders")
        // the plan page's 关闭, then 到点用 App 通知提醒 again: off clears them, the second tap brings them back
        tapButton("关了再开")
        let offon = line("offon: undetermined 0 allowed granted")
        wait(offon, 15, "turned off, then on again")
        let back = Int(offon.label.split(separator: " ").last ?? "0") ?? 0
        XCTAssertGreaterThanOrEqual(back, 5, offon.label)
    }
    /// the sentence the app is on, from the bridge page's state line (「state: playing i: 3 n: 18 …」)
    @MainActor private func sentenceNow() -> Int? {
        let parts = value("state: ").components(separatedBy: " ")
        guard let k = parts.firstIndex(of: "i:"), k + 1 < parts.count else { return nil }
        return Int(parts[k + 1])
    }

    @MainActor private func stateLine(_ needles: String...) -> XCUIElement {
        let p = NSPredicate(format: "label BEGINSWITH %@", "state: ")
        let all = NSCompoundPredicate(andPredicateWithSubpredicates: [p] + needles.map { NSPredicate(format: "label CONTAINS %@", $0) })
        return web.staticTexts.matching(all).firstMatch
    }

    /// iOS 27's lock screen buttons (LockScreen27), pressed through the bridge page: a simulator has no Now Playing
    @MainActor func test7LockScreenStudyButtons() {
        bridgePage()
        tapButton("播放全文")
        if !line("state: playing").waitForExistence(timeout: 40) {
            tapButton("继续")  // a weak line (test 3)
            wait(line("state: playing"), 40, "playing after 继续")
        }
        tapButton("锁屏 1.25×")
        wait(stateLine("rate: 1.25"), 5, "语速 1.25× from the lock screen")
        tapButton("锁屏单句循环")
        wait(stateLine("state: playing", "rep: 0", "loop: true"), 10, "单句循环 from the lock screen")
        let i = sentenceNow()
        XCTAssertNotNil(i)
        Thread.sleep(forTimeInterval: 9)  // a sentence is a few seconds: again and again, the same one
        XCTAssertEqual(sentenceNow(), i, "单句循环 stays on its sentence: \(value("state: "))")
        tapButton("锁屏退回 5 秒")
        wait(stateLine("state: playing", "i: \(i ?? -1) "), 5, "this sentence again")
        shot("07-lock-screen-buttons")
        tapButton("锁屏不循环")
        wait(stateLine("rep: 1", "loop: false"), 5, "the page's 复读 back (straight through)")
        tapButton("停止")
        wait(line("state: idle"), 5, "stopped")
    }

    /// 我的 → 设置 → 「iOS 专属功能」: the app's own page, its switches, the offline packs
    @MainActor func test8IOSFeaturesPage() {
        bridgePage()
        let feats = line("features: ")
        wait(feats, 10, "the switches as the page sees them")
        XCTAssertTrue(feats.label.contains("offline-packs:0") && feats.label.contains("smart-resume:1"), feats.label)
        tapButton("iOS 专属功能")
        wait(app.navigationBars["iOS 专属功能"], 10, "the app's own page")
        XCTAssertTrue(app.switches["feature.smart-resume"].exists)
        if feats.label.contains("lock-study") { XCTAssertTrue(app.switches["feature.lock-study"].exists, "iOS 27: the lock screen's buttons") }
        shot("08-ios-features")
        XCUIDevice.shared.appearance = .dark
        Thread.sleep(forTimeInterval: 3)  // the sheet takes the dark look a moment later
        shot("08-ios-features-dark", screen: true)
        XCUIDevice.shared.appearance = .light
        Thread.sleep(forTimeInterval: 1)
        let packs = app.switches["feature.offline-packs"]
        packs.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()  // the switch at the row's end
        let now = app.buttons["packs.now"]
        wait(now, 5, "离线朗读包's own part")
        wait(app.staticTexts["packs.note"], 90, "what fetching today's did")
        shot("08-offline-packs")
        let kept = app.staticTexts["packs.kept"]
        XCTAssertTrue(kept.label.contains("篇") || kept.value.debugDescription.contains("篇") || app.staticTexts["packs.note"].label.contains("登录"),
                      "kept: \(kept.label) note: \(app.staticTexts["packs.note"].label)")
        app.buttons["features.done"].tap()
        XCTAssertTrue(app.navigationBars["iOS 专属功能"].waitForNonExistence(timeout: 5))
        // today's text with its recording's address pointing nowhere: it plays all the same, from the copy on the phone
        tapButton("离线播放今天这篇")
        let ticking = web.staticTexts.matching(NSPredicate(format: "label MATCHES %@", "t: [0-9]+\\.[0-9] i: [0-9]+")).firstMatch
        wait(ticking, 20, "time from the app's own copy: \(value("state: ")) \(value("note: "))")
        wait(line("state: playing"), 5, "playing from the phone")
        tapButton("停止")
        wait(line("state: idle"), 5, "stopped")
        tapButton("iOS 专属功能")
        wait(app.navigationBars["iOS 专属功能"], 10, "the app's own page again")
        packs.coordinate(withNormalizedOffset: CGVector(dx: 0.92, dy: 0.5)).tap()
        XCTAssertTrue(now.waitForNonExistence(timeout: 5), "switched off: the part goes, and the files with it")
        app.buttons["features.done"].tap()
        XCTAssertTrue(app.navigationBars["iOS 专属功能"].waitForNonExistence(timeout: 5))
        tapButton("开关状态")
        let off = web.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@ AND label CONTAINS %@", "features: ", "offline-packs:0")).firstMatch
        wait(off, 5, "the page sees it off again")
    }
}
