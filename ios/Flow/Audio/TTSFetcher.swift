import CryptoKit
import Foundation

/// The server voice for one sentence (POST /api/next/tts {text, voice, pack} → {url}), downloaded to a file on the phone
/// so it plays at once and without the network; the same sentence is asked for once. Files older than 7 days go.
@MainActor
final class TTSFetcher {
    private let site: SiteClient
    private var made: [String: URL] = [:]
    private var running: [String: Task<URL, Error>] = [:]
    private let dir: URL

    init(site: SiteClient) {
        self.site = site
        dir = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("tts", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        prune()
    }

    private func key(_ text: String, _ voice: String, _ pack: String?) -> String { voice + "\u{1}" + (pack ?? "") + "\u{1}" + text }

    private func name(_ k: String) -> String { SHA256.hash(data: Data(k.utf8)).map { String(format: "%02x", $0) }.joined().prefix(32).description }

    /// A file made earlier, in memory or on disk (kept 7 days, so an offline listen after a relaunch still has it).
    private func onDisk(_ k: String) -> URL? {
        if let f = made[k], FileManager.default.fileExists(atPath: f.path) { return f }
        for ext in ["mp3", "wav", "m4a"] {
            let f = dir.appendingPathComponent(name(k) + "." + ext)
            if FileManager.default.fileExists(atPath: f.path) {
                made[k] = f
                return f
            }
        }
        return nil
    }

    func ready(text: String, voice: String, pack: String?) -> Bool { onDisk(key(text, voice, pack)) != nil }

    func prefetch(text: String, voice: String, pack: String?, csrf: String?) {
        _ = start(text: text, voice: voice, pack: pack, csrf: csrf)
    }

    func file(text: String, voice: String, pack: String?, csrf: String?) async throws -> URL {
        try await start(text: text, voice: voice, pack: pack, csrf: csrf).value
    }

    private func start(text: String, voice: String, pack: String?, csrf: String?) -> Task<URL, Error> {
        let k = key(text, voice, pack)
        if let f = onDisk(k) { return Task { f } }
        if let t = running[k] { return t }
        let name = name(k)
        let t = Task { [site, dir] () throws -> URL in
            defer { self.running[k] = nil }
            var body: [String: Any] = ["text": text, "voice": voice]
            if let pack { body["pack"] = pack }
            let j = try await site.json("/api/next/tts", body: body, csrf: csrf, timeout: 20)
            guard let u = j["url"] as? String else { throw SiteError.shape }
            let (data, http) = try await site.send(u, timeout: 20)
            guard (200..<300).contains(http.statusCode), data.count > 100 else { throw SiteError.status(http.statusCode, code: "file", message: "") }
            let ext = URL(string: u)?.pathExtension.isEmpty == false ? URL(string: u)!.pathExtension : "mp3"
            let f = dir.appendingPathComponent(name + "." + ext)
            try data.write(to: f, options: .atomic)
            self.made[k] = f
            return f
        }
        running[k] = t
        return t
    }

    /// A line for the page and the learner: why this sentence is in the iPhone's voice (tts_service's codes).
    static func reason(_ error: Error) -> String {
        let tail = "，这句先用 iPhone 自带的声音"
        if let e = error as? URLError {
            switch e.code {
            case .notConnectedToInternet, .networkConnectionLost, .dataNotAllowed: return "离线中" + tail
            case .timedOut: return "自然人声这次生成得太慢" + tail
            default: return "网络不好" + tail
            }
        }
        if case SiteError.signedOut = error { return "登录后可以用自然人声朗读" + tail }
        if case SiteError.status(_, let code, _) = error {
            switch code {
            case "guest": return "登录后可以用自然人声朗读" + tail
            case "off", "store": return "自然人声暂时用不了" + tail
            case "cap": return "今天的自然人声用完了" + tail
            case "import_cap": return "今天导入文章的自然人声用完了" + tail
            case "busy": return "今天用自然人声的人多" + tail
            default: break
            }
        }
        return "这句自然人声没做出来" + tail
    }

    /// The server said no for the rest of the day (switched off, the day's limit), as the page's SV.off: not worth asking
    /// again for the next sentences of this text. Anything else is per sentence (a guest still gets the stored ones, and
    /// so does an account that has not agreed to 数据存放在香港: /api/next/tts answers it as a guest).
    static func refused(_ error: Error) -> Bool {
        if case SiteError.status(_, let code, _) = error { return ["off", "cap"].contains(code) }
        return false
    }

    private func prune() {
        let old = Date(timeIntervalSinceNow: -7 * 86400)
        let fm = FileManager.default
        guard let list = try? fm.contentsOfDirectory(at: dir, includingPropertiesForKeys: [.contentModificationDateKey]) else { return }
        for f in list where ((try? f.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast) < old {
            try? fm.removeItem(at: f)
        }
    }
}

/// Where each text was left (the page keeps its own copy in localStorage: PROG); this one survives the app being closed
/// and is what FlowApp.audio.progress(key) answers. 30 days, 100 texts.
@MainActor
final class ProgressStore {
    private let key = "flow.progress"
    private let days = 30.0, most = 100

    private func all() -> [String: [String: Any]] {
        let cut = Date().timeIntervalSince1970 * 1000 - days * 86_400_000
        var o = (UserDefaults.standard.dictionary(forKey: key) as? [String: [String: Any]]) ?? [:]
        for (k, v) in o where ((v["at"] as? Double) ?? 0) < cut { o[k] = nil }
        return o
    }

    func get(_ k: String) -> [String: Any]? { k.isEmpty ? nil : all()[k] }

    func set(_ k: String, i: Int, t: Double?) {
        guard !k.isEmpty else { return }
        var o = all()
        if i > 0 || (t ?? 0) > 1 {  // a place to go on from (replaces an 'ended' mark)
            var v: [String: Any] = ["i": i, "at": Date().timeIntervalSince1970 * 1000]
            if let t, t.isFinite { v["t"] = t }
            o[k] = v
        } else {
            o[k] = nil
        }
        if o.count > most {
            for (k, _) in o.sorted(by: { (($0.value["at"] as? Double) ?? 0) < (($1.value["at"] as? Double) ?? 0) }).prefix(o.count - most) { o[k] = nil }
        }
        UserDefaults.standard.set(o, forKey: key)
    }

    func clear(_ k: String) {
        var o = all()
        o[k] = nil
        UserDefaults.standard.set(o, forKey: key)
    }

    /// Read to the end: {ended: true, at} instead of a place, so a page that missed the 'ended' event clears its own copy.
    func ended(_ k: String) {
        guard !k.isEmpty else { return }
        var o = all()
        o[k] = ["i": 0, "ended": true, "at": Date().timeIntervalSince1970 * 1000]
        UserDefaults.standard.set(o, forKey: key)
    }
}
