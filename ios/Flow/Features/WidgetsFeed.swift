import Foundation
import WidgetKit

/// What the widgets show (FlowWidgets: 「今天」, Control Center), put into the App Group whenever the app has fresh
/// counts: after the reminders ask the site (Reminders.refresh: the app in front, the background refresh), with
/// 今日好句 and 今天这篇 from /api/next/home (at most every 30 minutes). Only on this phone; the next one overwrites it.
@MainActor
enum WidgetsFeed {
    private static var homeAt: Date?
    private static var home: (line: TodayCard.Line?, read: TodayCard.Read?)

    static func publish(_ input: ReminderPlan.Input, outcome: Reminders.Outcome, site: SiteClient) async {
        #if BETA
        if UserDefaults.standard.bool(forKey: "FlowWidgetSample") { return }  // screenshots: the example card stays
        #endif
        if outcome == .offline { return }  // nothing new: the card keeps what it had
        if homeAt.map({ Date().timeIntervalSince($0) > 1800 }) ?? true, outcome != .paused {
            if let j = try? await site.json("/api/next/home") {
                home = (Self.line(j), Self.read(j))
                homeAt = Date()
            }
        }
        let state: TodayCard.State = outcome == .signedOut ? .signedOut : outcome == .paused ? .paused : .ok
        let card = Self.card(input, state: state, line: home.line, read: home.read, accent: Accent.saved ?? "green")
        guard card != SharedStore.load() else { return }
        SharedStore.save(card)
        WidgetCenter.shared.reloadAllTimelines()
    }

    nonisolated static func card(_ x: ReminderPlan.Input, state: TodayCard.State, line: TodayCard.Line?, read: TodayCard.Read?,
                                 accent: String, now: Date = Date()) -> TodayCard {
        var c = TodayCard(updated: now, state: state, line: line, accent: accent)
        if state == .ok {  // nobody's words when nobody is signed in (or not agreed yet)
            c.due = x.due
            c.new = x.new
            c.minutes = x.minutes
            c.read = read
        }
        return c
    }

    /// 今日好句 (daily_line.py) with the label and source the site gives it
    nonisolated static func line(_ home: [String: Any]) -> TodayCard.Line? {
        guard let l = home["line"] as? [String: Any], let en = l["en"] as? String, !en.isEmpty else { return nil }
        return TodayCard.Line(en: en.replacingOccurrences(of: " / ", with: "\n"), zh: (l["zh"] as? String) ?? "",
                              label: (l["label"] as? String) ?? "", source: (l["source"] as? String) ?? "")
    }

    /// 今天这篇: the plan's 读 step (#/m/<id>) with the text's title from 今日
    nonisolated static func read(_ home: [String: Any]) -> TodayCard.Read? {
        guard let id = Packs.todaysTexts(home).first else { return nil }
        let today = (home["today"] as? [[String: Any]]) ?? []
        let title = (today.first { ($0["id"] as? String) == id }?["title"] as? String) ?? id
        let enc = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/?#"))) ?? id
        return TodayCard.Read(title: title, path: "#/m/" + enc)
    }
}
