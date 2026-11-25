import Foundation
import Network
import Speech

/// 「本机快速检查（离线）」 (iOS 专属功能, item 13; the owner's conditions of 2026-11-25, ios-27-features.md): with no
/// network, a 跟读 take is heard once by iOS's own speech recognition **on this phone**; the page lines what was heard
/// up with the sentence (its compare_words, the same for every app: 语流 B3) and marks only the words not heard (漏读).
/// Nothing else: no score, no 错题本, no statistics, nothing uploaded later; with a network the server does the checking
/// and this never runs. Recognition is on-device only (requiresOnDeviceRecognition):
/// where this iPhone cannot recognise English on the device, the answer is 'unavailable', never Apple's servers.
/// The take is kept in memory only while the switch is on, from rec.stop() until the check, the next recording or
/// two minutes, whichever comes first.
@MainActor
final class LocalCheck {
    static let shared = LocalCheck()

    private var take: (data: Data, ext: String, at: Date)?
    private let path = NWPathMonitor()
    private var online = true
    #if BETA
    /// tests: the check as if there were no network (-FlowPretendOffline YES)
    private var pretendOffline: Bool { UserDefaults.standard.bool(forKey: "FlowPretendOffline") }
    #else
    private var pretendOffline: Bool { false }
    #endif

    private init() {
        Self.watch(path) { up in Task { @MainActor in LocalCheck.shared.online = up } }
    }

    /// the network's state as it changes (off the main thread: the handler must not be the main actor's)
    nonisolated private static func watch(_ m: NWPathMonitor, _ set: @escaping @Sendable (Bool) -> Void) {
        m.pathUpdateHandler = { set($0.status == .satisfied) }
        m.start(queue: DispatchQueue(label: "cn.flowlang.app.localcheck.path"))
    }

    /// rec.stop() gave the page this take: kept for a check only while the switch is on
    func keep(_ data: Data, mime: String) {
        guard Features.on(.localCheck) else { take = nil; return }
        take = (data, mime == "audio/mp4" ? "m4a" : "wav", Date())
    }

    /// a new recording began, the switch went off, the app left the screen: the old take goes
    func forget() { take = nil }

    /// what this iPhone can do: 'ready', 'unavailable' (no on-device English), 'denied' / 'undetermined' (speech permission)
    var state: String {
        guard Self.recognizer?.supportsOnDeviceRecognition == true else { return "unavailable" }
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized: return "ready"
        case .denied, .restricted: return "denied"
        default: return "undetermined"
        }
    }

    /// The switch was turned on: iOS asks for speech recognition once (the usage text says what for).
    func prepare() async -> String {
        if SFSpeechRecognizer.authorizationStatus() == .notDetermined { await Self.askSpeech() }
        return state
    }

    /// FlowApp.rec.localcheck({lang}) after rec.stop(): {ok: true, heard} ('' when nothing was heard) or {ok: false, why}
    func check(lang: String = "en-US") async -> [String: Any] {
        guard Features.on(.localCheck) else { return ["ok": false, "why": "off"] }
        guard !online || pretendOffline else { take = nil; return ["ok": false, "why": "online"] }
        guard let t = take, Date().timeIntervalSince(t.at) < 120 else { take = nil; return ["ok": false, "why": "none"] }
        take = nil  // one check per take
        switch state {
        case "ready": break
        case "unavailable": return ["ok": false, "why": "unavailable"]
        default: return ["ok": false, "why": "denied"]
        }
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("localcheck-\(UUID().uuidString).\(t.ext)")
        defer { try? FileManager.default.removeItem(at: file) }
        do { try t.data.write(to: file, options: .completeFileProtection) } catch { return ["ok": false, "why": "error"] }
        guard let heard = await Self.recognize(file, locale: Self.locale(lang)) else { return ["ok": false, "why": "error"] }
        return ["ok": true, "heard": heard]
    }

    /// iOS's question; its answer comes on a queue of its own
    nonisolated private static func askSpeech() async {
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            SFSpeechRecognizer.requestAuthorization { _ in c.resume() }
        }
    }

    nonisolated private static var recognizer: SFSpeechRecognizer? { SFSpeechRecognizer(locale: Locale(identifier: "en-US")) }

    /// the page's lang: American or British English; anything else is heard as American
    nonisolated static func locale(_ lang: String) -> Locale { Locale(identifier: lang == "en-GB" ? "en-GB" : "en-US") }

    /// iOS's recognition of the file, on this phone only; nil when it failed ("" when nothing was heard)
    nonisolated private static func recognize(_ file: URL, locale: Locale) async -> String? {
        guard let r = SFSpeechRecognizer(locale: locale), r.supportsOnDeviceRecognition else { return nil }
        let req = SFSpeechURLRecognitionRequest(url: file)
        req.requiresOnDeviceRecognition = true  // never Apple's servers (the owner's condition)
        req.shouldReportPartialResults = false
        req.addsPunctuation = false
        return await withCheckedContinuation { (c: CheckedContinuation<String?, Never>) in
            let once = Once(c)
            once.task = r.recognitionTask(with: req) { result, error in
                if let result, result.isFinal { once.resume(result.bestTranscription.formattedString) }
                else if let error = error as NSError? {
                    // "no speech detected": nothing of the sentence was heard
                    once.resume(error.domain == "kAFAssistantErrorDomain" && error.code == 1110 ? "" : nil)
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 9) { once.timeout() }  // the page waits 10 s
        }
    }
}

/// A continuation resumed once: the recogniser can answer twice (a final result, then an error), the timer later still.
nonisolated private final class Once: @unchecked Sendable {
    private var c: CheckedContinuation<String?, Never>?
    private let lock = NSLock()
    var task: SFSpeechRecognitionTask?  // cancelled if iOS has not answered in time
    init(_ c: CheckedContinuation<String?, Never>) { self.c = c }
    func resume(_ s: String?) {
        lock.lock(); let k = c; c = nil; lock.unlock()
        k?.resume(returning: s)
    }
    func timeout() {
        task?.cancel()
        resume(nil)
    }
}
