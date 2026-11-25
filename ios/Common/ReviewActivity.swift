import ActivityKit
import Foundation

/// 「复习进度的实时活动」 (Feature.reviewActivity, off until the learner turns it on): while the page's word review runs,
/// the lock screen and the Dynamic Island show 「复习单词 12 / 30」. The page says how far it is
/// (FlowApp.call('activity.review', {done, total}), docs/native-bridge.md §2); the app starts, updates and ends it
/// (ReviewActivities), the widget extension draws it (FlowWidgets/ReviewActivityWidget.swift). Local only: no push.
nonisolated struct ReviewActivityAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable, Sendable {
        var done: Int
        var total: Int

        /// 0…1 for the bar
        var share: Double { total > 0 ? min(1, max(0, Double(done) / Double(total))) : 0 }
    }

    var title: String  // 「复习单词」
}
