import Foundation

/// Which reminders to put on the phone, worked out from what the site says (GET /api/next/vocab): the same rules as
/// the server's mail (vocab_service.send_reminders), as local notifications for the next two weeks.
/// - every day at the reminder hour, only on a day with words to review (today: what is still due now; the next six
///   days: the server's forecast; after that, every day while the learner has words or a book);
/// - 这次什么时候复习 (once): the next reminder at that time instead — no daily one before it, none more that day;
/// - the day's plan (我的 → 每天提醒, chosen in the app): every day at its hour; a word reminder at the same time is
///   left out (the plan has the words in it).
struct ReminderPlan {
    struct Input: Codable, Equatable {
        var hour = 20
        var once: Double?           // seconds since 1970
        var due = 0                 // today, still to review now
        var new = 0                 // today's new words still to learn
        var minutes = 0
        var forecast: [Int] = []    // reviews due on each of the next days (0 = today, overdue in it)
        var dailyNew = 0            // the book plan's new words a day
        var hasWords = false        // any word cards at all
        var planHour: Int?          // the day's plan reminder (from the app; nil = off)
        var planMinutes = 10
        var app = true              // the learner wants the app's reminders (FlowApp.notify.sync {app: false} turns them off)
    }

    struct Slot: Equatable {
        var id: String
        var date: Date
        var title: String
        var body: String
        var path: String
    }

    static let days = 14

    static func slots(_ x: Input, now: Date, calendar cal: Calendar = .current) -> [Slot] {
        guard x.app else { return [] }
        var out: [Slot] = []
        let today = cal.startOfDay(for: now)
        let once = x.once.map { Date(timeIntervalSince1970: $0) }.flatMap { $0 > now ? $0 : nil }
        let fmt = DateFormatter()
        fmt.calendar = cal
        fmt.timeZone = cal.timeZone
        fmt.dateFormat = "yyyy-MM-dd"
        for k in 0..<days {
            guard let day = cal.date(byAdding: .day, value: k, to: today) else { continue }
            let tag = fmt.string(from: day)
            var planAt: Date?
            if let ph = x.planHour, let t = cal.date(bySettingHour: ph, minute: 0, second: 0, of: day), t > now.addingTimeInterval(60) {
                planAt = t
                out.append(Slot(id: "plan-" + tag, date: t, title: "今天的学习",
                                body: "打开今天的计划：到期的单词、今天这篇材料、该复习的语法点，大约 \(x.planMinutes) 分钟。", path: "#/"))
            }
            guard let t = cal.date(bySettingHour: x.hour, minute: 0, second: 0, of: day), t > now.addingTimeInterval(60) else { continue }
            if let once, t < once || cal.isDate(t, inSameDayAs: once) { continue }
            if let planAt, planAt == t { continue }
            let n: Int
            if k == 0 { n = x.due + x.new } else if k < x.forecast.count { n = x.forecast[k] + x.dailyNew } else { n = x.hasWords || x.dailyNew > 0 ? -1 : 0 }
            if n == 0 { continue }
            let body: String
            if k == 0 {
                body = "今天还有 \(n) 个词等你复习" + (x.minutes > 0 ? "，大约 \(x.minutes) 分钟。" : "。") + "记忆曲线到点了，现在复习效果最好。"
            } else if k < x.forecast.count && x.forecast[k] > 0 {
                body = "今天大约有 \(x.forecast[k]) 个词要复习。记忆曲线到点了，现在复习效果最好。"
            } else if x.dailyNew > 0 {
                body = "今天的新词准备好了，复习加新词几分钟就好。"
            } else {
                body = "到期的单词在等你，记忆曲线到点了，现在复习效果最好。"
            }
            out.append(Slot(id: "review-" + tag, date: t, title: "该复习单词了", body: body, path: "#/review"))
        }
        if let once {
            let k = cal.dateComponents([.day], from: today, to: cal.startOfDay(for: once)).day ?? 0
            let n = k == 0 ? x.due + x.new : (k < x.forecast.count ? x.forecast[k] : 0)
            let body = n > 0 ? "你选的复习时间到了：\(n) 个词等你，现在复习记得最牢。" : "你选的复习时间到了，现在复习记得最牢。"
            out.append(Slot(id: "review-once", date: once, title: "到你选的复习时间了", body: body, path: "#/review"))
        }
        return out.sorted { $0.date < $1.date }
    }

    /// From GET /api/next/vocab (reminder, forecast, counts, plan, total); keeps what only the app knows.
    static func input(from j: [String: Any], keeping old: Input) -> Input {
        var x = old
        if let r = j["reminder"] as? [String: Any] {
            if let h = Bridge.int(r["hour"]), (0..<24).contains(h) { x.hour = h }
            x.once = Bridge.double(r["once"])
        }
        x.due = Bridge.int(j["due"]) ?? 0
        x.new = Bridge.int(j["new"]) ?? 0
        x.minutes = Bridge.int(j["minutes"]) ?? 0
        x.forecast = ((j["forecast"] as? [Any]) ?? []).compactMap(Bridge.int)
        let plan = j["plan"] as? [String: Any]
        x.dailyNew = (Bridge.int(plan?["daily_new"]) ?? 0) > 0 && !((j["new_paused"] as? Bool) ?? false) ? (Bridge.int(plan?["daily_new"]) ?? 0) : 0
        x.hasWords = (Bridge.int(j["total"]) ?? 0) > 0
        return x
    }
}
