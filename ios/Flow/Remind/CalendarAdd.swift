import EventKit
import EventKitUI
import UIKit

/// 「加到系统日历」 in the app: the same event the site's .ics gives (vocab_service.ics), shown in iOS's own editor so
/// the learner saves it with one tap. Since iOS 17 that needs no calendar permission (the editor runs outside the app).
@MainActor
enum CalendarAdd {
    private static let store = EKEventStore()
    private static let delegate = Done()

    static func present(from vc: WebViewController, ask: ReminderAsk) {
        let e = EKEvent(eventStore: store)
        let site = AppConfig.site.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let length: Int
        if ask.kind == .plan {
            length = ask.minutes
            e.title = "语流：今天的学习（约 \(ask.minutes) 分钟）"
            e.notes = "打开今天的计划：到期的单词、今天这篇材料、该复习的语法点，按顺序做完就好。"
            e.url = URL(string: site + "/#/")
        } else {
            length = 10
            e.title = "语流：背单词（约 10 分钟）"
            e.notes = "按遗忘曲线复习今天到期的单词。"
            e.url = URL(string: site + "/#/review")
        }
        // China time, as the site's .ics (vocab_service.ics: next_service.TZ)
        let start = ask.at ?? ReminderPlan.serverCalendar.date(bySettingHour: ask.hour ?? 20, minute: 0, second: 0, of: Date()) ?? Date()
        e.startDate = start
        e.endDate = start.addingTimeInterval(TimeInterval(length * 60))
        if ask.at == nil { e.addRecurrenceRule(EKRecurrenceRule(recurrenceWith: .daily, interval: 1, end: nil)) }
        e.addAlarm(EKAlarm(relativeOffset: 0))
        let editor = EKEventEditViewController()
        editor.eventStore = store
        editor.event = e
        editor.editViewDelegate = delegate
        vc.present(editor)
    }

    final class Done: NSObject, EKEventEditViewDelegate {
        func eventEditViewController(_ controller: EKEventEditViewController, didCompleteWith action: EKEventEditViewAction) {
            controller.dismiss(animated: true)
        }
    }
}
