import Foundation
import WebKit

/// window.FlowApp, the page's way to the native parts (ios/README.md, 「网页和 App 之间的桥」).
/// Page → app: window.webkit.messageHandlers.flow.postMessage({cmd, args}) answers with a Promise.
/// App → page: FlowApp._emit(type, detail): FlowApp.on(type, fn) and a `flowapp:<type>` event on window.
@MainActor
final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    static let name = "flow"
    static let version = 1
    static let features = ["audio", "rec", "notify"]

    weak var webView: WKWebView?
    let player: LongPlayer
    let recorder: Recorder
    let reminders: Reminders

    init(player: LongPlayer, recorder: Recorder, reminders: Reminders) {
        self.player = player
        self.recorder = recorder
        self.reminders = reminders
        super.init()
        player.emit = { [weak self] type, detail in self?.emit(type, detail) }
        recorder.emit = { [weak self] type, detail in self?.emit(type, detail) }
    }

    /// The script (FlowBridge.js) at document start in the main frame, and the message handler, in the page's own world.
    func install(in ucc: WKUserContentController) {
        let cfg: [String: Any] = ["v": Self.version, "app": AppConfig.version, "build": AppConfig.build,
                                  "features": Self.features, "beta": AppConfig.isBeta]
        let src = "window.__flowAppConfig = \(Self.json(cfg));\n" + Self.script
        ucc.addUserScript(WKUserScript(source: src, injectionTime: .atDocumentStart, forMainFrameOnly: true, in: .page))
        ucc.addScriptMessageHandler(self, contentWorld: .page, name: Self.name)
    }

    static let script: String = {
        guard let u = Bundle.main.url(forResource: "FlowBridge", withExtension: "js"), let s = try? String(contentsOf: u, encoding: .utf8) else { return "" }
        return s
    }()

    func userContentController(_ ucc: WKUserContentController, didReceive message: WKScriptMessage) async -> (Any?, String?) {
        let origin = message.frameInfo.securityOrigin
        guard message.frameInfo.isMainFrame, AppConfig.isOwnOrigin(host: origin.host, scheme: origin.protocol) else {
            return (nil, "not allowed here")
        }
        guard let body = message.body as? [String: Any], let cmd = body["cmd"] as? String else { return (nil, "bad message") }
        let args = body["args"] as? [String: Any] ?? [:]
        return (await handle(cmd, args), nil)
    }

    func handle(_ cmd: String, _ a: [String: Any]) async -> Any {
        switch cmd {
        case "hello":
            return ["v": Self.version, "app": AppConfig.version, "build": AppConfig.build, "features": Self.features]
        case "app.visible":
            resendState()
            return true

        case "audio.play":
            guard let r = LongPlayer.Request(json: a, base: webView?.url ?? AppConfig.site) else { return ["ok": false, "why": "bad request"] }
            return await player.play(r)
        case "audio.pause": player.pause(why: .user); return player.snapshot()
        case "audio.resume": player.resume(why: .user); return player.snapshot()
        case "audio.stop": player.stop(why: .user); return player.snapshot()
        case "audio.step": player.step(Self.int(a["d"]) ?? 1); return player.snapshot()
        case "audio.seek": player.seek(Self.int(a["i"]) ?? 0); return player.snapshot()
        case "audio.set": player.set(a); return player.snapshot()
        case "audio.state": return player.snapshot()
        case "audio.progress": return player.progress(a["key"] as? String) ?? NSNull()

        case "rec.permission": return recorder.permission()
        case "rec.ask": return await recorder.ask()
        case "rec.start": return await recorder.start(a)
        case "rec.stop": return await recorder.stop()
        case "rec.cancel": recorder.cancel(); return true

        case "notify.permission": return await reminders.permission()
        case "notify.ask": return await reminders.ask()
        case "notify.sync": return await reminders.sync(a)
        case "notify.pending": return await reminders.pending()
        #if BETA
        case "notify.test": return await reminders.testSchedule(a)
        #endif
        default:
            return ["ok": false, "why": "unknown command"]
        }
    }

    /// After a page (re)load or coming back to the front: what plays now, so the page shows it without guessing.
    func resendState() {
        if player.state != .idle { emit("audio", player.snapshot(why: "state")) }
    }

    func emit(_ type: String, _ detail: [String: Any]) {
        guard let webView else { return }
        webView.evaluateJavaScript("window.FlowApp && FlowApp._emit(\(Self.js(type)), \(Self.json(detail)))", completionHandler: nil)
    }

    // ---- small helpers
    static func json(_ o: Any) -> String {
        guard JSONSerialization.isValidJSONObject(o), let d = try? JSONSerialization.data(withJSONObject: o) else { return "null" }
        return String(data: d, encoding: .utf8) ?? "null"
    }

    static func js(_ s: String) -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: [s]), let t = String(data: d, encoding: .utf8) else { return "\"\"" }
        return String(t.dropFirst().dropLast())
    }

    static func int(_ v: Any?) -> Int? { (v as? NSNumber)?.intValue ?? (v as? String).flatMap(Int.init) }
    static func double(_ v: Any?) -> Double? { (v as? NSNumber)?.doubleValue ?? (v as? String).flatMap(Double.init) }
}
