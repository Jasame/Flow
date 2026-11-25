import Foundation
import UserNotifications

/// What the learner asked for from a 「加到手机日历」 link: the daily word review, the day's plan, or one time.
struct ReminderAsk {
    enum Kind { case vocab, plan }
    var kind: Kind
    var hour: Int?
    var minutes: Int
    var at: Date?

    var when: String {
        if let at { return Reminders.label(at) + " 提醒一次" }
        return "每天 \(hour ?? 20):00（北京时间）" + (kind == .plan ? " 提醒今天的学习" : " 提醒复习单词")
    }
}

/// Review reminders as local notifications (no server push, nothing leaves the phone). The site stays the place
/// where the hour and 这次什么时候复习 are set; the app reads them (with the web view's cookies) when it opens, goes to
/// the background, a few times a day by itself, and whenever the page says it changed one (FlowApp.notify.sync).
@MainActor
final class Reminders {
    enum OptIn { case scheduled(String), denied, failed(String) }
    enum Outcome { case fresh, signedOut, offline }

    private let site: SiteClient
    private let center = UNUserNotificationCenter.current()
    private let key = "flow.reminders"
    private var lastFetch: Date?
    private var generation = 0  // refreshes overlap (opening, the page's sync, the background): the newest one wins
    private(set) var input: ReminderPlan.Input

    init(site: SiteClient) {
        self.site = site
        if let d = UserDefaults.standard.data(forKey: key), let x = try? JSONDecoder().decode(ReminderPlan.Input.self, from: d) {
            input = x
        } else {
            input = ReminderPlan.Input()
        }
    }

    func permission() async -> String {
        switch await center.notificationSettings().authorizationStatus {
        case .authorized, .ephemeral: return "granted"
        case .provisional: return "provisional"
        case .denied: return "denied"
        default: return "undetermined"
        }
    }

    /// iOS's question, asked once; true when notifications may be shown.
    func ask() async -> Bool {
        if await allowed() { return true }
        return (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    /// Notifications may be shown (quietly too: provisional)
    private func allowed() async -> Bool {
        let p = await permission()
        return p == "granted" || p == "provisional"
    }

    /// The page changed a reminder (or the learner turned the app's reminders on/off): r is the page's `reminder`
    /// ({hour, once, …}), optionally with forecast, `app` (true/false) and `ask` (ask iOS's permission first).
    func sync(_ r: [String: Any]) async -> [String: Any] {
        if let on = r["app"] as? Bool { input.app = on }
        if (r["ask"] as? Bool) == true { _ = await ask() }
        if let h = Bridge.int(r["hour"]), ReminderPlan.hours.contains(h) { input.hour = h }
        if r.keys.contains("once") {
            input.once = Bridge.double(r["once"])
            if let o = input.once { input.onceSeen = max(o, input.onceSeen ?? 0) }
        }
        if let f = r["forecast"] as? [Any] { input.forecast = f.compactMap(Bridge.int) }
        save()
        await refresh(force: true)
        let list = await scheduled()
        let next: Any = list.first.map { $0.date.timeIntervalSince1970 as Any } ?? NSNull()
        return ["ok": true, "permission": await permission(), "scheduled": list.count, "next": next]
    }

    /// From a 「加到手机日历」 link tapped in the app, after 「用 App 通知提醒」.
    func optIn(_ a: ReminderAsk) async -> OptIn {
        guard await ask() else { return .denied }
        input.app = true
        if a.kind == .plan {
            input.planHour = a.hour ?? 20
            input.planMinutes = a.minutes
        } else {
            if let h = a.hour { input.hour = h }
            if let at = a.at {
                input.once = at.timeIntervalSince1970
                input.onceSeen = max(at.timeIntervalSince1970, input.onceSeen ?? 0)
            }
        }
        save()
        let outcome = await refresh(force: true)
        let pending = await scheduled()
        if a.kind == .plan {
            guard pending.contains(where: { $0.id.hasPrefix("plan-") }) else { return .failed("没有排上，稍后再试一次。") }
            return .scheduled("每天 \(input.planHour ?? 20):00 用通知提醒你今天的学习。不想要了，可以在 iPhone 的「设置 → 通知」里关掉。")
        }
        if case .signedOut = outcome { return .failed("登录以后才能用通知提醒复习单词：先登录，再点一次。") }
        let words = pending.filter { $0.id.hasPrefix("review-") }
        if let at = a.at {
            return words.contains(where: { $0.id == "review-once" })
                ? .scheduled("\(Self.label(at)) 用通知提醒你复习。")
                : .scheduled("\(Self.label(at)) 那时还没有要复习的词，就不提醒了；之后每天 \(input.hour):00，有词要复习才提醒。")
        }
        let off = outcome == .offline ? "（现在没网，先按上次的情况排；连上网会自动更新）" : ""
        return words.isEmpty
            ? .scheduled("好，每天 \(input.hour):00 有词要复习时用通知提醒你；这几天没有要复习的词。\(off)")
            : .scheduled("每天 \(input.hour):00 用通知提醒你复习（那天有词要复习才提醒）。\(off)")
    }

    /// Ask the site for the counts and the reminder, then put the next two weeks on the phone.
    @discardableResult
    func refresh(force: Bool = false) async -> Outcome {
        if !force, let last = lastFetch, Date().timeIntervalSince(last) < 600 { return .fresh }
        generation += 1
        let mine = generation
        var outcome = Outcome.fresh
        do {
            let j = try await site.json("/api/next/vocab")
            guard mine == generation else { return .fresh }  // a newer refresh is under way: its answer counts
            lastFetch = Date()
            input = ReminderPlan.input(from: j, keeping: input)
        } catch SiteError.signedOut {
            guard mine == generation else { return .signedOut }
            lastFetch = Date()
            input = ReminderPlan.signedOut(input)  // no word reminders for an account that is not here; the plan stays
            outcome = .signedOut
        } catch {
            outcome = .offline  // what was known last time
        }
        save()
        await schedule()
        return outcome
    }

    func schedule() async {
        let slots = await allowed() ? ReminderPlan.slots(input, now: Date()) : []
        await clear()
        for s in slots { await add(s) }
    }

    private func add(_ s: ReminderPlan.Slot) async {
        let c = UNMutableNotificationContent()
        c.title = s.title
        c.body = s.body
        c.sound = .default
        c.threadIdentifier = s.id.hasPrefix("plan") ? "plan" : "review"
        c.userInfo = ["path": s.path]
        let comps = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute, .second], from: s.date)
        let req = UNNotificationRequest(identifier: s.id, content: c, trigger: UNCalendarNotificationTrigger(dateMatching: comps, repeats: false))
        try? await center.add(req)
    }

    private func clear() async {
        let ids = await center.pendingNotificationRequests().map(\.identifier).filter { $0.hasPrefix("review-") || $0.hasPrefix("plan-") }
        center.removePendingNotificationRequests(withIdentifiers: ids)
    }

    private struct Pending { var id: String; var date: Date; var title: String; var body: String }

    private func scheduled() async -> [Pending] {
        await center.pendingNotificationRequests().compactMap { r in
            guard let t = r.trigger as? UNCalendarNotificationTrigger, let d = t.nextTriggerDate() else { return nil }
            return Pending(id: r.identifier, date: d, title: r.content.title, body: r.content.body)
        }.sorted { $0.date < $1.date }
    }

    func pending() async -> [[String: Any]] {
        await scheduled().map { ["id": $0.id, "at": $0.date.timeIntervalSince1970, "title": $0.title, "body": $0.body] }
    }

    #if BETA
    /// UI tests: schedule from the given counts without asking the server.
    func testSchedule(_ a: [String: Any]) async -> [String: Any] {
        input = ReminderPlan.input(from: a, keeping: input)
        if let on = a["app"] as? Bool { input.app = on }
        save()
        await schedule()
        return ["ok": true, "permission": await permission(), "pending": await pending()]
    }
    #endif

    private func save() {
        if let d = try? JSONEncoder().encode(input) { UserDefaults.standard.set(d, forKey: key) }
    }

    /// 「今天 12:30」「明天 8:00」 in China time, as the page's onceLabel on a phone set to it
    static func label(_ d: Date) -> String {
        let cal = ReminderPlan.serverCalendar
        let f = DateFormatter()
        f.calendar = cal
        f.timeZone = cal.timeZone
        f.dateFormat = "H:mm"
        let g = DateFormatter()
        g.calendar = cal
        g.timeZone = cal.timeZone
        g.dateFormat = "M月d日"
        let day = cal.isDateInToday(d) ? "今天" : cal.isDateInTomorrow(d) ? "明天" : g.string(from: d)
        return day + " " + f.string(from: d)
    }
}
