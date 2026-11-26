import ActivityKit
import SwiftUI
import WidgetKit

/// 「复习进度的实时活动」 on the lock screen and in the Dynamic Island: 「复习单词 12 / 30」 and a bar (ReviewActivity).
struct ReviewActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ReviewActivityAttributes.self) { context in
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(context.attributes.title).font(.headline)
                    ProgressView(value: context.state.share)
                }
                Text("\(context.state.done) / \(context.state.total)")
                    .font(.title2.weight(.semibold).monospacedDigit())
            }
            .padding(16)
            .widgetURL(SharedStore.link("#/review"))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Label(context.attributes.title, systemImage: "rectangle.stack").font(.subheadline)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(context.state.done) / \(context.state.total)").font(.headline.monospacedDigit())
                }
                DynamicIslandExpandedRegion(.bottom) {
                    ProgressView(value: context.state.share)
                }
            } compactLeading: {
                Image(systemName: "rectangle.stack")
            } compactTrailing: {
                Text("\(context.state.done)/\(context.state.total)").monospacedDigit()
            } minimal: {
                Text("\(context.state.done)").monospacedDigit()
            }
            .widgetURL(SharedStore.link("#/review"))
        }
    }
}
