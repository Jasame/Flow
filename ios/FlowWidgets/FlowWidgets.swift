import AppIntents
import SwiftUI
import WidgetKit

/// 语流's widgets, in one extension of the app (the project's FlowWidgets target): 「今天」 for the home screen and the
/// lock screen, the review's Live Activity, and two Control Center buttons (iOS 18). None of them goes to the network:
/// the app writes what they show into the App Group (Common/TodayCard.swift).
@main
struct FlowWidgets: WidgetBundle {
    var body: some Widget {
        TodayWidget()
        ReviewActivityWidget()
        if #available(iOS 18, *) {
            ReviewControl()
            TodayControl()
        }
    }
}

/// Control Center: 「开始复习」 opens the app on 复习 (its own link: Common/TodayCard.swift).
@available(iOS 18, *)
struct ReviewControl: ControlWidget {
    var body: some ControlWidgetConfiguration {
        StaticControlConfiguration(kind: "review") {
            ControlWidgetButton(action: OpenURLIntent(SharedStore.link("#/review"))) {
                Label("开始复习", systemImage: "rectangle.stack")
            }
        }
        .displayName("开始复习")
        .description("打开语流，直接复习今天的单词。")
    }
}

/// Control Center: 「今天的学习」 opens the app on 今日.
@available(iOS 18, *)
struct TodayControl: ControlWidget {
    var body: some ControlWidgetConfiguration {
        StaticControlConfiguration(kind: "today") {
            ControlWidgetButton(action: OpenURLIntent(SharedStore.link("#/"))) {
                Label("今天的学习", systemImage: "sun.max")
            }
        }
        .displayName("今天的学习")
        .description("打开语流的今日页。")
    }
}
