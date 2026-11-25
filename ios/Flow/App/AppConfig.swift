import Foundation

/// Which site this build opens and how the app names itself to it. Beta.xcconfig / Release.xcconfig set the site
/// (Info.plist `FlowSiteURL`); the page knows it is inside the app from the User-Agent's last word, `FlowiOS/<version>`.
enum AppConfig {
    static let site: URL = {
        let s = (Bundle.main.object(forInfoDictionaryKey: "FlowSiteURL") as? String) ?? ""
        return URL(string: s).flatMap { $0.host == nil ? nil : $0 } ?? URL(string: "https://flow.jasa.hk")!
    }()
    static let version = (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "1.0.0"
    static let build = (Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String) ?? "1"

    /// Appended to WebKit's own User-Agent (it ends with `Mobile/15E148`): `… Mobile/15E148 FlowiOS/1.0.0`.
    static var userAgentSuffix: String { "Mobile/15E148 FlowiOS/\(version)" }

    #if BETA
    static let isBeta = true
    #else
    static let isBeta = false
    #endif

    /// Tests and automation make no sound (the owner, 2026-11-25: 「后台运行的应用不要播放系统声音」): launched with
    /// `-FlowMuteAudio YES` the app's player and the iPhone voice play at volume 0 and the page's own sound is muted;
    /// playing is checked by the state and the events, not by ear. The UI tests always pass it.
    static let muted = UserDefaults.standard.bool(forKey: "FlowMuteAudio")

    /// The page to open: the site, or (Beta builds only) the one a UI test asks for with FLOW_START_URL.
    static var start: URL {
        #if BETA
        if let s = ProcessInfo.processInfo.environment["FLOW_START_URL"], let u = URL(string: s), u.host != nil { return u }
        #endif
        return site
    }

    /// The origin of the page the app opens (scheme, host, port): the native side talks to the same server as the page.
    static var origin: URL {
        var c = URLComponents()
        c.scheme = start.scheme
        c.host = start.host
        c.port = start.port
        c.path = "/"
        return c.url ?? site
    }

    /// Hosts the web view keeps inside the app: the site (and, for UI tests, the local test server). Everything else
    /// opens in the system browser.
    static func isOwn(_ url: URL?) -> Bool {
        guard let host = url?.host?.lowercased() else { return false }
        if let mine = start.host?.lowercased(), host == mine { return true }
        if let mine = site.host?.lowercased(), host == mine || host == "www." + mine { return true }
        return false
    }

    /// Where the page's bridge calls may come from (the frame's security origin).
    static func isOwnOrigin(host: String, scheme: String) -> Bool {
        guard scheme == "https" || (isBeta && scheme == "http" && (host == "localhost" || host == "127.0.0.1")) else { return false }
        return isOwn(URL(string: "\(scheme)://\(host)/"))
    }
}
