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
        a.launchArguments += ["-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
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
        wait(ticking, 40, "time from the app")
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
            wait(line("state: paused"), 5, "paused from Control Center")
            XCTAssertTrue(value("state: ").contains("why: remote"), value("state: "))
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
    }
}
