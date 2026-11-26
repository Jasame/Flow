import AppIntents
import Foundation

// 「Siri 和专注模式」 (iOS 专属功能, group 4): what Siri, the Shortcuts app and a Focus can ask of 语流. Each only opens
// one of the site's pages or reads this phone's own numbers (the reminders' counts); nothing of the learner's goes to
// Siri's language model: no entities for Apple Intelligence's index, no assistant schemas, no model delegation
// (the plan's red line, ios-27-features.md).

/// 「语流开始复习」: the app on 复习.
nonisolated struct StartReviewIntent: AppIntent {
    static let title: LocalizedStringResource = "开始复习"
    static let description = IntentDescription("打开语流，直接复习今天的单词。")
    static let openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult {
        guard Features.on(.siri) else { throw SiriOff() }
        Shell.shared.open(path: "#/review")
        return .result()  // the app on 复习 says it all: no card left over it
    }
}

/// 「用语流打开今天这篇」: the plan's text for today (今日's 读), or 今日 when there is none yet.
nonisolated struct OpenTodayTextIntent: AppIntent {
    static let title: LocalizedStringResource = "打开今天这篇"
    static let description = IntentDescription("打开语流今天要读的文章；还没有的话打开今日页。")
    static let openAppWhenRun = true

    @MainActor
    func perform() async throws -> some IntentResult {
        guard Features.on(.siri) else { throw SiriOff() }
        Shell.shared.open(path: AskLines.todayPath(SharedStore.load()))
        return .result()
    }
}

/// 「语流还有多少词要复习」: said back without opening the app (the reminders' numbers, asked of the site at most every
/// 10 minutes as when the app comes to the front). The phone has to be unlocked: the numbers are the learner's.
nonisolated struct DueCountIntent: AppIntent {
    static let title: LocalizedStringResource = "还要复习几个词"
    static let description = IntentDescription("说出今天还有几个词要复习、几个新词、大约几分钟，不用打开语流。")
    static let authenticationPolicy: IntentAuthenticationPolicy = .requiresAuthentication

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        guard Features.on(.siri) else { throw SiriOff() }
        let shell = Shell.shared
        let outcome = await shell.reminders.refresh()
        await WidgetsFeed.publish(shell.reminders.input, outcome: outcome, site: shell.site)
        // offline: a phone that was signed out (or not agreed) last time still is, as far as we know
        let said = outcome == .offline && shell.reminders.known != .fresh ? shell.reminders.known : outcome
        return .result(dialog: "\(AskLines.due(shell.reminders.input, outcome: said))")
    }
}

/// 「快捷指令和 Siri」 switched off: Siri and Shortcuts show this instead of doing anything.
nonisolated struct SiriOff: Error, CustomLocalizedStringResourceConvertible {
    var localizedStringResource: LocalizedStringResource { "\(AskLines.off)" }
}

/// What the intents say: plain functions, so the tests can read them.
nonisolated enum AskLines {
    static let off = "语流的「快捷指令和 Siri」关着。在语流的「我的 → 设置 → iOS 专属功能」里打开就能用。"

    static func due(_ x: ReminderPlan.Input, outcome: Reminders.Outcome) -> String {
        switch outcome {
        case .signedOut: return "登录语流以后，我才知道你今天要复习几个词。"
        case .paused: return "先在语流里同意用户协议和隐私说明，才能看到要复习的词。"
        case .fresh, .offline: break
        }
        let old = { if case .offline = outcome { return "（没连上网，这是上次的数字）" } else { return "" } }()
        guard x.hasWords || x.due + x.new > 0 else { return "你还没开始背单词。在语流的「单词」里选一本词书就能开始。" }
        if x.due + x.new == 0 { return "今天的单词都复习完了。" + old }
        var parts = [x.due > 0 ? "今天还有 \(x.due) 个词要复习" : "今天没有要复习的词"]
        if x.new > 0 { parts.append("新词 \(x.new) 个") }
        if x.minutes > 0 { parts.append("大约 \(x.minutes) 分钟") }
        return parts.joined(separator: "，") + "。" + old
    }

    /// 今天这篇 (written by WidgetsFeed from 今日), else 今日 itself
    static func todayPath(_ card: TodayCard?) -> String {
        guard let p = card?.read?.path, p.hasPrefix("#/m/"), card?.state == .ok, card?.stale() == false else { return "#/" }
        return p
    }
}

/// The phrases Siri and Spotlight know without the learner setting anything up (the Shortcuts app lists them too).
nonisolated struct FlowShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: StartReviewIntent(),
                    phrases: ["\(.applicationName)开始复习", "用\(.applicationName)开始复习", "在\(.applicationName)复习单词"],
                    shortTitle: "开始复习", systemImageName: "rectangle.stack")
        AppShortcut(intent: DueCountIntent(),
                    phrases: ["\(.applicationName)还有多少词要复习", "\(.applicationName)今天要复习几个词"],
                    shortTitle: "还要复习几个词", systemImageName: "number")
        AppShortcut(intent: OpenTodayTextIntent(),
                    phrases: ["用\(.applicationName)打开今天这篇", "\(.applicationName)今天读什么"],
                    shortTitle: "今天这篇", systemImageName: "book")
    }
}

// MARK: 专注模式

/// Which of 语流's reminders a Focus lets through (设置 → 专注模式 → a Focus → 添加过滤条件 → 语流).
nonisolated enum FocusReminders: String, AppEnum {
    case all, review, off

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "语流的提醒"
    static let caseDisplayRepresentations: [FocusReminders: DisplayRepresentation] = [
        .all: "都提醒",
        .review: "只提醒复习单词",
        .off: "都不提醒",
    ]

    /// The reminders' kinds as their notifications carry them (UNNotificationContent.filterCriteria, Reminders.kind)
    /// that this choice lets through; nil: all of them.
    var kinds: [String]? {
        switch self {
        case .all: nil
        case .review: [Reminders.reviewKind]
        case .off: []
        }
    }

    /// The predicate iOS checks each notification's filterCriteria with while the Focus is on.
    var predicate: NSPredicate? { kinds.map { NSPredicate(format: "SELF IN %@", $0) } }
}

/// The Focus filter: with 「只提醒复习单词」 the day's plan reminder stays quiet, with 「都不提醒」 both do. The
/// system does the filtering (the predicate), the app keeps nothing of it.
struct ReminderFocusFilter: SetFocusFilterIntent {
    static let title: LocalizedStringResource = "语流的提醒"
    static let description: IntentDescription? = "这个专注模式打开时，语流提醒哪些：都提醒、只提醒复习单词、都不提醒。"

    @Parameter(title: "提醒", default: .all)
    var reminders: FocusReminders

    var displayRepresentation: DisplayRepresentation {
        FocusReminders.caseDisplayRepresentations[reminders] ?? DisplayRepresentation(title: "都提醒")
    }

    var appContext: FocusFilterAppContext { FocusFilterAppContext(notificationFilterPredicate: reminders.predicate) }

    func perform() async throws -> some IntentResult { .result() }
}
