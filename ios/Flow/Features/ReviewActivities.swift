import ActivityKit
import Foundation

/// 「复习进度的实时活动」 (Feature.reviewActivity, off until turned on): the page's word review says how far it is
/// (FlowApp.call('activity.review', {done, total}); 'activity.end' when it finishes or is left), and the lock screen
/// and the Dynamic Island show it (FlowWidgets/ReviewActivityWidget.swift). One at a time; local updates only.
@MainActor
enum ReviewActivities {
    static let title = "复习单词"

    static func update(done: Int, total: Int) async -> [String: Any] {
        guard Features.on(.reviewActivity) else { return ["ok": false, "why": "off"] }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return ["ok": false, "why": "denied"] }
        let state = ReviewActivityAttributes.ContentState(done: max(0, min(done, total)), total: max(0, total))
        let content = ActivityContent(state: state, staleDate: Date(timeIntervalSinceNow: 2 * 3600))
        if let a = Activity<ReviewActivityAttributes>.activities.first {
            await a.update(content)
            return ["ok": true]
        }
        do {
            _ = try Activity.request(attributes: ReviewActivityAttributes(title: title), content: content, pushType: nil)
            return ["ok": true]
        } catch {
            return ["ok": false, "why": "denied"]  // iOS would not start one (the app not in front, too many)
        }
    }

    /// Finished or left: the last numbers stay a moment, then it goes.
    static func end(done: Int? = nil, total: Int? = nil) async {
        for a in Activity<ReviewActivityAttributes>.activities {
            var s = a.content.state
            if let done { s.done = done }
            if let total { s.total = total }
            await a.end(ActivityContent(state: s, staleDate: nil), dismissalPolicy: .after(Date(timeIntervalSinceNow: 60)))
        }
    }

    static var count: Int { Activity<ReviewActivityAttributes>.activities.filter { $0.activityState == .active }.count }

    /// Switched off, or the app starting again: none left on the lock screen from before.
    static func endAll() async {
        for a in Activity<ReviewActivityAttributes>.activities { await a.end(nil, dismissalPolicy: .immediate) }
    }
}
