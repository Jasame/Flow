import BackgroundTasks
import Foundation
import Network
import Observation
import os

/// 离线朗读包 (Feature.offlinePacks): the recordings of today's texts kept in this app, so a whole text plays in the app
/// without a connection (the page keeps its own copy for itself, sw.js; the app's player cannot read that one). The
/// same texts as the page's 存到手机 of the day (06-offline.js keepTodayOffline): 今天这篇 and the next two of 今日, in
/// the learner's voice. Fetched over Wi-Fi only (never on mobile data or Low Data Mode): when the app comes to the
/// front, and once a night while the phone charges (a background task). Kept in Library/Caches/packs (not in backups,
/// iOS may clear it when space runs low); a file kept 7 days goes, all of them when the switch goes off.
@MainActor
@Observable
final class Packs {
    /// switched off meanwhile (the files were going when the app stopped): nothing from before is played
    static let shared: Packs = {
        let p = Packs()
        if !Features.on(.offlinePacks), !p.entries.isEmpty { p.clear() }
        return p
    }()
    static let task = "cn.flowlang.app.packs"
    nonisolated static let perDay = 3     // as the page: 今天这篇 and the next two
    static let most = 9                   // files at most (three days' worth), the oldest go first
    static let keepDays = 7.0
    static let again: TimeInterval = 3 * 3600  // in front again within 3 hours: no new look
    private static let log = Logger(subsystem: "cn.flowlang.app", category: "packs")

    struct Entry: Codable, Equatable {
        var id: String
        var voice: String
        var version: String
        var file: String
        var bytes: Int
        var title: String
        var kept: Date
    }

    private(set) var entries: [String: Entry] = [:]   // by the recording's address on the site: /audio/<voice>/<id>.mp4?v=<version>
    private(set) var busy = false
    private(set) var lastRun: Date?
    private(set) var note = ""                           // what the last look did, for the settings page
    /// the phone's connection: nil until the first report (counted as online then)
    private(set) var path: (online: Bool, wifi: Bool)?

    var site: SiteClient?
    private let monitor = NWPathMonitor()
    private let dir: URL
    private let index: URL
    private let session: URLSession

    init(dir: URL? = nil) {
        let base = dir ?? FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0].appendingPathComponent("packs", isDirectory: true)
        self.dir = base
        index = base.appendingPathComponent("index.json")
        let c = URLSessionConfiguration.default
        c.allowsExpensiveNetworkAccess = false     // mobile data, a phone's hotspot: no
        c.allowsConstrainedNetworkAccess = false   // Low Data Mode: no
        c.httpShouldSetCookies = false
        c.httpCookieAcceptPolicy = .never
        c.urlCache = nil
        c.timeoutIntervalForRequest = 30
        c.timeoutIntervalForResource = 600
        c.httpAdditionalHeaders = ["User-Agent": "Yuliu/\(AppConfig.version) \(AppConfig.userAgentSuffix)"]
        session = URLSession(configuration: c)
        load()
        monitor.pathUpdateHandler = { @Sendable [weak self] p in
            let online = p.status == .satisfied, wifi = online && !p.isExpensive && !p.isConstrained
            Task { @MainActor in self?.path = (online, wifi) }
        }
        monitor.start(queue: .global(qos: .utility))
    }

    var online: Bool { path?.online ?? true }
    var wifi: Bool { path?.wifi ?? false }
    var bytes: Int { entries.values.reduce(0) { $0 + $1.bytes } }

    // MARK: the player asks

    /// The kept file for a recording on the site (same voice, same version), if there is one.
    func local(for url: URL) -> URL? {
        guard let key = Self.key(url), let e = entries[key] else { return nil }
        let f = dir.appendingPathComponent(e.file)
        guard FileManager.default.fileExists(atPath: f.path) else {
            entries[key] = nil
            save()
            return nil
        }
        return f
    }

    /// /audio/<voice>/<id>.mp4?v=<version> on any of the site's hosts: the key the files are kept by
    nonisolated static func key(_ url: URL) -> String? {
        guard let c = URLComponents(url: url, resolvingAgainstBaseURL: true), c.path.hasPrefix("/audio/"), c.path.hasSuffix(".mp4") else { return nil }
        let parts = c.path.split(separator: "/")
        guard parts.count == 3 else { return nil }
        let v = c.queryItems?.first { $0.name == "v" }?.value ?? ""
        return c.path + "?v=" + v
    }

    nonisolated static func address(id: String, voice: String, version: String) -> String {
        let enc = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/?#"))) ?? id
        return "/audio/\(voice)/\(enc).mp4?v=\(version)"
    }

    /// What the page keeps of a day (keepTodayOffline): the 今天这篇 step's text first, then 今日's, no repeats, three.
    nonisolated static func todaysTexts(_ home: [String: Any]) -> [String] {
        var ids: [String] = []
        if let path = home["path"] as? [String: Any], let steps = path["steps"] as? [[String: Any]],
           let read = steps.first(where: { ($0["key"] as? String) == "read" }), let href = read["href"] as? String {
            let parts = href.split(separator: "/", omittingEmptySubsequences: false)
            if parts.count > 2, let id = String(parts[2]).removingPercentEncoding, !id.isEmpty { ids.append(id) }
        }
        for m in (home["today"] as? [[String: Any]]) ?? [] { if let id = m["id"] as? String, !id.isEmpty { ids.append(id) } }
        var seen = Set<String>()
        return Array(ids.filter { seen.insert($0).inserted }.prefix(perDay))
    }

    /// the voice of a recording the page played: the next pack is in it (the profile's own when the site says it)
    nonisolated static func voice(of url: URL) -> String? {
        let parts = url.path.split(separator: "/")
        return parts.count == 3 && parts[0] == "audio" ? String(parts[1]) : nil
    }

    // MARK: fetching

    /// Fresh enough, on Wi-Fi and switched on: look at today's texts and fetch what is missing.
    func refresh(force: Bool = false) async {
        guard Features.on(.offlinePacks), !busy, let site else { return }
        if !force, let lastRun, Date().timeIntervalSince(lastRun) < Self.again { return }
        if !force, Frugal.shared.on { return }  // 省电时少做事: tonight, while it charges
        guard wifi || path == nil else {
            note = "没连 Wi-Fi：连上以后再存"
            return
        }
        busy = true
        defer { busy = false }
        lastRun = Date()
        note = "正在看今天要学哪几篇…"
        do {
            let home = try await again { try await site.json("/api/next/home") }
            let ids = Self.todaysTexts(home)
            let voice = ((home["profile"] as? [String: Any])?["voice"] as? String) ?? UserDefaults.standard.string(forKey: "packs.voice") ?? "us-f"
            var kept = 0, none = 0, failed: Error?
            for (n, id) in ids.enumerated() {
                guard Features.on(.offlinePacks), !Task.isCancelled else { break }
                note = "正在存第 \(n + 1) / \(ids.count) 篇…"
                do {  // one text that does not come is no reason to leave the others
                    if try await again({ try await self.keep(id, voice: voice, site: site) }) { kept += 1 } else { none += 1 }
                } catch {
                    if Self.offline(error) { throw error }
                    Self.log.error("packs: \(id, privacy: .public) not kept: \(String(describing: error), privacy: .public)")
                    failed = error
                }
            }
            prune(today: ids)
            let missed = ids.count - kept - none
            if ids.isEmpty {
                note = "今天还没有要读的文章"
            } else if missed == 0 {
                note = "今天的 \(ids.count) 篇已经存好" + (none > 0 ? "（有 \(none) 篇没有录音）" : "")
            } else {
                note = (kept > 0 ? "存好 \(kept) 篇，" : "") + "\(missed) 篇这次没存成（\(Self.why(failed))），下次连着 Wi-Fi 时再试"
            }
        } catch SiteError.signedOut {
            note = "登录以后才会存"
        } catch SiteError.status(403, "storage", _) {
            note = "先在页面上同意用户协议和隐私说明，才会存"
        } catch {
            Self.log.error("packs: today's not fetched: \(String(describing: error), privacy: .public)")
            note = Self.offline(error) ? "没连 Wi-Fi：连上以后再存" : "这次没存成（\(Self.why(error))），下次连着 Wi-Fi 时再试"
        }
    }

    /// A request that failed for a passing reason (the server busy or restarting, a slow line): once more after 2 s.
    private func again<T>(_ work: () async throws -> T) async throws -> T {
        do { return try await work() } catch {
            guard !Self.offline(error), !Task.isCancelled, Self.passing(error) else { throw error }
            try await Task.sleep(for: .seconds(2))
            return try await work()
        }
    }

    nonisolated static func offline(_ error: Error) -> Bool {
        guard let e = error as? URLError else { return false }
        return e.networkUnavailableReason != nil || [.notConnectedToInternet, .dataNotAllowed].contains(e.code)
    }

    /// worth one more try: a timeout, a dropped line, the server's 5xx or 429
    nonisolated static func passing(_ error: Error) -> Bool {
        if let e = error as? URLError { return [.timedOut, .networkConnectionLost, .cannotConnectToHost, .badServerResponse].contains(e.code) }
        if case SiteError.status(let s, _, _) = error { return s >= 500 || s == 429 }
        return false
    }

    /// the reason in a few words, for the settings page
    nonisolated static func why(_ error: Error?) -> String {
        if let e = error as? URLError { return e.code == .timedOut ? "网络太慢" : "网络不稳" }
        if case SiteError.status(let s, _, _)? = error { return s >= 500 || s == 429 ? "服务器忙" : "服务器没给" }
        return "出了点问题"
    }

    /// One text's recording, if the site has one in this voice (else its first voice). true: it is on the phone now.
    private func keep(_ id: String, voice: String, site: SiteClient) async throws -> Bool {
        let enc = id.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed.subtracting(CharacterSet(charactersIn: "&+=?#"))) ?? id
        let m = try await site.json("/api/next/material?id=\(enc)")
        guard let audio = m["audio"] as? [String: Any], let voices = audio["voices"] as? [String], !voices.isEmpty else { return false }
        let version = (audio["version"] as? String) ?? (audio["version"] as? NSNumber)?.stringValue ?? ""
        let v = voices.contains(voice) ? voice : voices[0]
        guard let url = site.url(Self.address(id: id, voice: v, version: version)), let k = Self.key(url) else { return false }
        if let e = entries[k], FileManager.default.fileExists(atPath: dir.appendingPathComponent(e.file).path) { return true }
        var req = URLRequest(url: url)
        let cs = await site.cookies(for: url)
        for (k, val) in HTTPCookie.requestHeaderFields(with: cs) { req.setValue(val, forHTTPHeaderField: k) }
        let (tmp, resp) = try await session.download(for: req)
        guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else {
            try? FileManager.default.removeItem(at: tmp)
            throw SiteError.status((resp as? HTTPURLResponse)?.statusCode ?? 0, code: "file", message: "")
        }
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let name = Self.fileName(id: id, voice: v, version: version)
        let dest = dir.appendingPathComponent(name)
        try? FileManager.default.removeItem(at: dest)
        try FileManager.default.moveItem(at: tmp, to: dest)
        let size = (try? dest.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        put(k, Entry(id: id, voice: v, version: version, file: name, bytes: size, title: (m["title"] as? String) ?? id, kept: Date()))
        return true
    }

    /// a file now on the phone, kept by its address (tests put theirs here too)
    func put(_ key: String, _ e: Entry) {
        entries[key] = e
        save()
    }

    nonisolated static func fileName(id: String, voice: String, version: String) -> String {
        let safe = { (s: String) in String(s.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) || "-_.".unicodeScalars.contains($0) ? Character($0) : "_" }) }
        return "\(safe(voice))__\(safe(id))__\(safe(version)).mp4"
    }

    /// Files kept 7 days go (unless they are today's), then the oldest past nine.
    func prune(today: [String] = [], now: Date = Date()) {
        let keepNow = Set(today)
        for (k, e) in entries where !keepNow.contains(e.id) && now.timeIntervalSince(e.kept) > Self.keepDays * 86400 { drop(k) }
        let old = entries.sorted { $0.value.kept < $1.value.kept }
        if old.count > Self.most { for (k, _) in old.prefix(old.count - Self.most) { drop(k) } }
        save()
    }

    /// The switch went off: nothing stays.
    func clear() {
        for k in entries.keys { drop(k) }
        try? FileManager.default.removeItem(at: dir)
        note = ""
        lastRun = nil
        save()
    }

    private func drop(_ k: String) {
        if let e = entries.removeValue(forKey: k) { try? FileManager.default.removeItem(at: dir.appendingPathComponent(e.file)) }
    }

    private func load() {
        guard let d = try? Data(contentsOf: index), let e = try? JSONDecoder().decode([String: Entry].self, from: d) else { return }
        entries = e
    }

    private func save() {
        if entries.isEmpty { try? FileManager.default.removeItem(at: index); return }
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        if let d = try? JSONEncoder().encode(entries) { try? d.write(to: index, options: .atomic) }
    }

    // MARK: once a night, while the phone charges on Wi-Fi

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: task, using: .main) { task in
            guard let task = task as? BGProcessingTask else { return }
            MainActor.assumeIsolated {
                var done = false
                let job = Task {
                    await Packs.shared.refresh(force: true)
                    if !done { done = true; task.setTaskCompleted(success: true) }
                }
                task.expirationHandler = {
                    MainActor.assumeIsolated {
                        job.cancel()
                        if !done { done = true; task.setTaskCompleted(success: false) }
                    }
                }
                schedule()
            }
        }
    }

    /// The next night's look (on: asked again each time; off: the asked one is taken back).
    static func schedule() {
        guard Features.on(.offlinePacks) else {
            BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: task)
            return
        }
        let r = BGProcessingTaskRequest(identifier: task)
        r.requiresNetworkConnectivity = true
        r.requiresExternalPower = true
        r.earliestBeginDate = Date(timeIntervalSinceNow: 4 * 3600)
        try? BGTaskScheduler.shared.submit(r)
    }
}
