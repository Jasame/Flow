import Foundation
import UIKit
import WebKit

/// window.FlowApp, the page's way to the native parts (ios/README.md, 「网页和 App 之间的桥」).
/// Page → app: window.webkit.messageHandlers.flow.postMessage({cmd, args}) answers with a Promise.
/// App → page: FlowApp._emit(type, detail): FlowApp.on(type, fn) and a `flowapp:<type>` event on window.
@MainActor
final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    static let name = "flow"
    static let version = 1
    static let features = ["audio", "rec", "notify", "settings", "haptic", "frugal"]

    weak var webView: WKWebView?
    /// the page's 主题色 changed (Accent): the app's own controls take it
    var onAccent: ((String) -> Void)?
    /// 我的 → 设置 → iOS 专属功能: the app's own page (FeaturesView); false when it cannot be shown now
    var onSettings: (() -> Bool)?
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
        Frugal.shared.changed = { [weak self] on in self?.emit("frugal", ["on": on]) }
    }

    /// The wrapper the three apps share (native/flowapp.js, docs/native-bridge.md §2) after iOS's transport, at document
    /// start in the main frame, and the message handler, in the page's own world.
    func install(in ucc: WKUserContentController) {
        let cfg: [String: Any] = ["v": Self.version, "app": AppConfig.version, "build": AppConfig.build, "platform": "ios",
                                  "features": Self.features, "beta": AppConfig.isBeta]
        let src = Self.transport(cfg) + Self.script
        ucc.addUserScript(WKUserScript(source: src, injectionTime: .atDocumentStart, forMainFrameOnly: true, in: .page))
        ucc.addScriptMessageHandler(self, contentWorld: .page, name: Self.name)
        ucc.addUserScript(WKUserScript(source: Accent.script, injectionTime: .atDocumentEnd, forMainFrameOnly: true, in: .page))
        if AppConfig.muted { ucc.addUserScript(WKUserScript(source: Self.muteScript, injectionTime: .atDocumentStart, forMainFrameOnly: false, in: .page)) }
    }

    /// AppConfig.muted: the page's own sound silenced too (<audio>/<video>, Web Audio, the browser voice)
    static let muteScript = """
    (() => {
      const play = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function () { this.muted = true; this.volume = 0; return play.apply(this, arguments); };
      for (const name of ['AudioContext', 'webkitAudioContext']) {
        const AC = window[name]; if (!AC) continue;
        window[name] = class extends AC {
          constructor(...a) { super(...a); const g = this.createGain(); g.gain.value = 0; g.connect(super.destination); Object.defineProperty(this, 'destination', { get: () => g }); }
        };
      }
      if (window.speechSynthesis) { const speak = speechSynthesis.speak.bind(speechSynthesis); speechSynthesis.speak = u => { try { u.volume = 0; } catch (e) {} return speak(u); }; }
    })();
    """

    /// iOS's transport for native/flowapp.js: WKScriptMessageHandlerWithReply answers each postMessage with a Promise.
    static func transport(_ cfg: [String: Any]) -> String {
        """
        ((h, cfg) => { if (h) window.__flowAppTransport = { cfg, send: (cmd, args) => h.postMessage({ cmd, args }) }; })(
          window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.\(name), \(json(cfg)));

        """
    }

    /// native/flowapp.js, bundled from the repo's native/ folder (the project's group Shared)
    static let script: String = {
        guard let u = Bundle.main.url(forResource: "flowapp", withExtension: "js"), let s = try? String(contentsOf: u, encoding: .utf8) else { return "" }
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
            return ["v": Self.version, "app": AppConfig.version, "build": AppConfig.build, "platform": "ios", "features": Self.features]
        case "app.visible":
            resendState()
            return true
        case "app.accent":  // the page's html[data-accent] (Accent.script): 我的 → 外观
            let name = Accent.name(a["accent"] as? String)
            Accent.save(name)
            onAccent?(name)
            return true
        case "app.settings":  // 我的 → 设置 → 「iOS 专属功能」 (docs/native-bridge.md §2 settings)
            return ["ok": onSettings?() ?? false]
        case "app.features":  // which of them this phone has, and whether each is on
            return Features.state
        case "app.haptic":  // 「复习时的轻触震动」: {kind: tap | select | success | warning | error}
            return ["ok": Haptics.play((a["kind"] as? String) ?? "tap", in: webView)]
        case "app.frugal":  // 「省电时少做事」: the page preloads less while it is on (and hears `frugal` when it changes)
            return ["on": Frugal.shared.on]

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
        case "notify.off": return await reminders.sync(["app": false])
        case "notify.settings":  // the system's notification settings for this app
            if let u = URL(string: UIApplication.openNotificationSettingsURLString) { await UIApplication.shared.open(u) }
            return true
        #if BETA
        case "notify.test": return await reminders.testSchedule(a)
        case "audio.remote":  // the lock screen's buttons, for tests (a simulator has no Now Playing to press)
            switch a["cmd"] as? String {
            case "rate": player.setRate(Float(Self.double(a["v"]) ?? 1))
            case "repeat": player.setRepeatOne((a["on"] as? Bool) ?? true)
            case "back": player.skipBack(Self.double(a["v"]) ?? 5)
            default: return ["ok": false, "why": "bad command"]
            }
            return player.snapshot()
        case "app.feature":  // a switch of 「iOS 专属功能」, for tests
            guard let f = (a["id"] as? String).flatMap(Feature.init(rawValue:)) else { return ["ok": false, "why": "no such feature"] }
            Features.set(f, (a["on"] as? Bool) ?? f.defaultOn)
            return Features.state
        #endif
        default:
            return ["ok": false, "why": "unknown command"]
        }
    }

    /// After a page (re)load or coming back to the front: what plays now, so the page shows it without guessing.
    func resendState() {
        if player.state != .idle { emit("audio", player.snapshot(why: "state")) }
        Frugal.shared.update()  // Low Power Mode may have changed while the app was away
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
