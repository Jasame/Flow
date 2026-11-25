import UIKit

/// 「复习时的轻触震动」 (Feature.haptics): the page asks for a light tap of the phone (FlowApp.call('app.haptic', {kind}),
/// docs/native-bridge.md §2) when the learner rates a word or answers. Safari cannot do it (iOS has no navigator.vibrate).
/// The system's own 「系统触感反馈」 setting still decides whether anything is felt.
@MainActor
enum Haptics {
    /// tap: a light tap (a rating, a choice); success / warning / error: answered right, half right, wrong
    nonisolated static let kinds = ["tap", "select", "success", "warning", "error"]

    /// false: switched off on 「iOS 专属功能」, or a kind this app does not know
    @discardableResult
    static func play(_ kind: String, in view: UIView?) -> Bool {
        guard Features.on(.haptics), kinds.contains(kind) else { return false }
        if #available(iOS 17.5, *), let view {
            switch kind {
            case "success": UINotificationFeedbackGenerator(view: view).notificationOccurred(.success)
            case "warning": UINotificationFeedbackGenerator(view: view).notificationOccurred(.warning)
            case "error": UINotificationFeedbackGenerator(view: view).notificationOccurred(.error)
            case "select": UISelectionFeedbackGenerator(view: view).selectionChanged()
            default: UIImpactFeedbackGenerator(style: .light, view: view).impactOccurred()
            }
        } else {
            switch kind {
            case "success": UINotificationFeedbackGenerator().notificationOccurred(.success)
            case "warning": UINotificationFeedbackGenerator().notificationOccurred(.warning)
            case "error": UINotificationFeedbackGenerator().notificationOccurred(.error)
            case "select": UISelectionFeedbackGenerator().selectionChanged()
            default: UIImpactFeedbackGenerator(style: .light).impactOccurred()
            }
        }
        return true
    }
}
