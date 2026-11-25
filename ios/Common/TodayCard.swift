import Foundation

/// What the widgets show (FlowWidgets), written by the app into the App Group they share (WidgetsFeed): the widgets
/// never ask the site themselves. In the app and in the widget extension alike (Common/).
nonisolated struct TodayCard: Codable, Equatable, Sendable {
    enum State: String, Codable, Sendable {
        case ok
        case signedOut   // nobody signed in on this phone: no words of anyone's
        case paused      // the account has not agreed to the terms / 数据存放在香港 yet (403 storage)
    }

    struct Read: Codable, Equatable, Sendable {
        var title: String
        var path: String  // #/m/<id>
    }

    /// 今日好句 as the site gives it (daily_line.py): its label (「公版名句」「语流文章」) and source go with it
    struct Line: Codable, Equatable, Sendable {
        var en: String
        var zh: String
        var label: String
        var source: String
    }

    var updated: Date
    var state: State = .ok
    var due = 0       // words to review today
    var new = 0       // new words today
    var minutes = 0   // about how long that takes
    var read: Read?   // 今天这篇
    var line: Line?   // 今日好句
    var accent = "green"

    /// Written before today began (China time, as the site counts days): the widget says to open the app.
    func stale(now: Date = Date()) -> Bool {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "Asia/Shanghai") ?? .current
        return updated < cal.startOfDay(for: now)
    }

    static let sample = TodayCard(updated: Date(), due: 12, new: 5, minutes: 8,
                                  read: Read(title: "新学期 1：第一天", path: "#/m/sample"),
                                  line: Line(en: "Well begun is half done.", zh: "好的开始是成功的一半。", label: "公版名句", source: "Aristotle"))
}

/// The App Group, the link scheme and the card stored in it.
nonisolated enum SharedStore {
    static let key = "today-card"

    static var group: String? { Bundle.main.object(forInfoDictionaryKey: "FlowAppGroup") as? String }
    static var scheme: String { (Bundle.main.object(forInfoDictionaryKey: "FlowURLScheme") as? String) ?? "yuliu" }
    static var defaults: UserDefaults? { group.flatMap { UserDefaults(suiteName: $0) } }

    static func load(_ d: UserDefaults? = defaults) -> TodayCard? {
        guard let data = d?.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(TodayCard.self, from: data)
    }

    static func save(_ c: TodayCard, _ d: UserDefaults? = defaults) {
        guard let data = try? JSONEncoder().encode(c) else { return }
        d?.set(data, forKey: key)
    }

    /// The app's own link to one of its pages: yuliu://open?path=%23/review
    static func link(_ path: String, scheme: String = scheme) -> URL {
        var c = URLComponents()
        c.scheme = scheme
        c.host = "open"
        c.queryItems = [URLQueryItem(name: "path", value: path)]
        return c.url ?? URL(string: "\(scheme)://open")!
    }

    /// The page a link asks for, if it is one of the site's own (#/…): anything else is not opened.
    static func path(from url: URL, scheme: String = scheme) -> String? {
        guard url.scheme?.lowercased() == scheme.lowercased(), url.host == "open",
              let p = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "path" })?.value,
              p.hasPrefix("#/"), p.count <= 200,
              p.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.contains($0) || "#/-_.%=&?".unicodeScalars.contains($0) })
        else { return nil }
        return p
    }
}
