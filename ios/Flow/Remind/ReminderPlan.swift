import Foundation

/// Which reminders to put on the phone, worked out from what the site says (GET /api/next/vocab): the same rules as
/// the server's mail (vocab_service.send_reminders), as local notifications for the next two weeks.
/// - Hours are China time, as the mail and the site's .ics are (next_service.TZ, UTC+8).
/// - Every day at the reminder hour, only on a day with words to review: today, what is left now (beyond the day's
///   share too); a later day, the server's forecast up to that day (words not reviewed stay due) plus the book's new
///   words while the book is not finished; after the forecast, every day while there are words or a book.
///   The app refreshes this whenever it opens or goes to the background, so a day done is taken off.
/// - 这次什么时候复习 (once): while it is ahead, no daily one before it; at that time it comes if that day has words;
///   then no daily one that day (the server's last_sent); after it, every day again.
/// - The day's plan (我的 → 每天提醒, chosen in the app): every day at its hour; a word reminder at the same time is
///   left out (the plan has the words in it). It needs no account.
struct ReminderPlan {
    struct Input: Codable, Equatable {
        var hour = 20
        var once: Double?           // seconds since 1970, ahead (the server forgets it once past)
        var onceSeen: Double?       // the latest once the app put on the phone (that day had words): kept after it passed, that day's daily is skipped
        var due = 0                 // today, still to review now
        var new = 0                 // today's new words still to learn
        var later = 0               // due today beyond the day's share (the mail counts them too)
        var minutes = 0
        var forecast: [Int] = []    // reviews due on each of the next days (0 = today, overdue in it)
        var dailyNew = 0            // the book's new words a day, while the book is not finished
        var hasWords = false        // any word cards at all
        var planHour: Int?          // the day's plan reminder (from the app; nil = off)
        var planMinutes = 10
        var app = true              // the learner wants the app's reminders (FlowApp.notify.sync {app: false} turns them off)

        init() {}

        // a field the saved copy does not have yet (an older app version) takes its default; the others are kept
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            let d = Input()
            hour = try c.decodeIfPresent(Int.self, forKey: .hour) ?? d.hour
            once = try c.decodeIfPresent(Double.self, forKey: .once)
            onceSeen = try c.decodeIfPresent(Double.self, forKey: .onceSeen)
            due = try c.decodeIfPresent(Int.self, forKey: .due) ?? d.due
            new = try c.decodeIfPresent(Int.self, forKey: .new) ?? d.new
            later = try c.decodeIfPresent(Int.self, forKey: .later) ?? d.later
            minutes = try c.decodeIfPresent(Int.self, forKey: .minutes) ?? d.minutes
            forecast = try c.decodeIfPresent([Int].self, forKey: .forecast) ?? d.forecast
            dailyNew = try c.decodeIfPresent(Int.self, forKey: .dailyNew) ?? d.dailyNew
            hasWords = try c.decodeIfPresent(Bool.self, forKey: .hasWords) ?? d.hasWords
            planHour = try c.decodeIfPresent(Int.self, forKey: .planHour)
            planMinutes = try c.decodeIfPresent(Int.self, forKey: .planMinutes) ?? d.planMinutes
            app = try c.decodeIfPresent(Bool.self, forKey: .app) ?? d.app
        }
    }

    struct Slot: Equatable {
        var id: String
        var date: Date
        var title: String
        var body: String
        var path: String
    }

    static let days = 14
    static let hours = 6...23  // vocab_service.REMIND_HOURS
    static let planMinutes: Set<Int> = [5, 10, 15, 20, 30, 45, 60]  // the profile's MINUTES (the server's .ics clamps 45/60 to 10: its bug)

    /// China time (UTC+8), as the server's mail, its forecast days and its .ics.
    static var serverCalendar: Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(secondsFromGMT: 8 * 3600) ?? .current
        return c
    }

    static func slots(_ x: Input, now: Date, calendar cal: Calendar = serverCalendar) -> [Slot] {
        guard x.app else { return [] }
        var out: [Slot] = []
        let today = cal.startOfDay(for: now)
        let fmt = DateFormatter()
        fmt.calendar = cal
        fmt.timeZone = cal.timeZone
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.dateFormat = "yyyy-MM-dd"
        let dayOf = { (d: Date) in cal.dateComponents([.day], from: today, to: cal.startOfDay(for: d)).day ?? 0 }
        // words to review on day k (k = 0: today, what is left now); -1: not known, but there are words
        let count = { (k: Int) -> Int in
            if k <= 0 { return x.due + x.new + x.later }
            if k < x.forecast.count { return x.forecast[0...k].reduce(0, +) + x.dailyNew }
            return x.hasWords || x.dailyNew > 0 ? -1 : 0
        }
        let once = x.once.map { Date(timeIntervalSince1970: $0) }.flatMap { $0 > now ? $0 : nil }
        let onceCounts = once.map { count(dayOf($0)) != 0 } ?? false
        // the day of a once that already came (or will, with words): its daily one does not
        let onceDay = once.flatMap { onceCounts ? $0 : nil } ?? x.onceSeen.map { Date(timeIntervalSince1970: $0) }.flatMap { $0 <= now ? $0 : nil }
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
            if let once, t < once { continue }                                   // waiting for the chosen time
            if let onceDay, cal.isDate(t, inSameDayAs: onceDay) { continue }       // that day's reminder was the chosen one
            if let planAt, planAt == t { continue }
            let n = count(k)
            if n == 0 { continue }
            let due = k < x.forecast.count ? x.forecast[k] : 0
            let body: String
            if k == 0 {
                body = "今天还有 \(n) 个词等你复习" + (x.minutes > 0 ? "，大约 \(x.minutes) 分钟。" : "。") + "记忆曲线到点了，现在复习效果最好。"
            } else if due > 0 {
                body = "今天大约有 \(due) 个词到期。记忆曲线到点了，现在复习效果最好。"
            } else if n > x.dailyNew {
                body = "还有没复习完的词在等你，几分钟就好。"
            } else if x.dailyNew > 0 {
                body = "今天的新词准备好了，复习加新词几分钟就好。"
            } else {
                body = "到期的单词在等你，记忆曲线到点了，现在复习效果最好。"
            }
            out.append(Slot(id: "review-" + tag, date: t, title: "该复习单词了", body: body, path: "#/review"))
        }
        if let once, onceCounts {
            let n = count(dayOf(once))
            let body = n > 0 ? "你选的复习时间到了：\(n) 个词等你，现在复习记得最牢。" : "你选的复习时间到了，现在复习记得最牢。"
            out.append(Slot(id: "review-once", date: once, title: "到你选的复习时间了", body: body, path: "#/review"))
        }
        return out.sorted { $0.date < $1.date }
    }

    /// From GET /api/next/vocab (reminder, forecast, counts, plan, book, total); keeps what only the app knows.
    static func input(from j: [String: Any], keeping old: Input) -> Input {
        var x = old
        if let r = j["reminder"] as? [String: Any] {
            if let h = Bridge.int(r["hour"]), hours.contains(h) { x.hour = h }
            if r.keys.contains("once") { x.once = Bridge.double(r["once"]) }  // an older server does not know it: the app's stays
        }
        x.due = Bridge.int(j["due"]) ?? 0
        x.new = Bridge.int(j["new"]) ?? 0
        x.later = Bridge.int(j["later"]) ?? 0
        x.minutes = Bridge.int(j["minutes"]) ?? 0
        x.forecast = ((j["forecast"] as? [Any]) ?? []).compactMap(Bridge.int)
        let plan = j["plan"] as? [String: Any], book = j["book"] as? [String: Any]
        let bookOn = book.map { !(($0["done"] as? Bool) ?? false) } ?? (plan != nil)
        let paused = (j["new_paused"] as? Bool) ?? false
        x.dailyNew = bookOn && !paused ? max(0, Bridge.int(plan?["daily_new"]) ?? 0) : 0
        x.hasWords = (Bridge.int(j["total"]) ?? 0) > 0
        return x
    }

    /// After scheduling: a once that went on the phone is remembered, so once it has passed (and the server forgot it) that
    /// day's daily reminder still stays away. A once with nothing to review was not scheduled: it lapses, and that day's
    /// hour comes as usual (vocab_service.send_reminders).
    static func remember(_ x: Input, scheduled: [Slot]) -> Input {
        var x = x
        if let o = x.once, scheduled.contains(where: { $0.id == "review-once" }) { x.onceSeen = max(o, x.onceSeen ?? 0) }
        return x
    }

    /// Signed out: no word reminders for an account that is not here (the day's plan needs none).
    static func signedOut(_ old: Input) -> Input {
        var x = Input()
        x.planHour = old.planHour
        x.planMinutes = old.planMinutes
        x.app = old.app
        return x
    }
}
