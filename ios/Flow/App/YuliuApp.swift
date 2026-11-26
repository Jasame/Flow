import SwiftUI
import CoreSpotlight
import UIKit
import UserNotifications

/// 语流: the website in a native shell. The page draws everything (it lays itself out under the status bar and the
/// home indicator, viewport-fit=cover); the app adds what a web page on an iPhone cannot do well: a whole text that keeps
/// playing with the screen locked, recording, and local reminders (Shell).
@main
struct YuliuApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @Environment(\.scenePhase) private var phase

    var body: some Scene {
        WindowGroup {
            ShellView()
                .ignoresSafeArea()
                .background(Color("LaunchBackground"))
                // a widget or a Control Center button: yuliu://open?path=%23/review (only the site's own pages)
                .onOpenURL { url in if let p = SharedStore.path(from: url) { Shell.shared.open(path: p) } }
                // a word picked in the iPhone's search (在系统搜索里找生词): that card in 单词
                .onContinueUserActivity(CSSearchableItemActionType) { a in
                    if let id = a.userInfo?[CSSearchableItemActivityIdentifier] as? String, let p = WordSearch.path(forIdentifier: id) {
                        Shell.shared.open(path: p)
                    }
                }
        }
        .onChange(of: phase) { _, now in Shell.shared.phase(now) }
    }
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        AudioSessionManager.shared.prepare()
        UNUserNotificationCenter.current().delegate = self
        Shell.registerBackgroundRefresh()
        Task { await ReviewActivities.endAll() }  // a review's progress left from before the app last stopped
        #if BETA
        if UserDefaults.standard.bool(forKey: "FlowWidgetSample") {  // screenshots of the widgets: an example card
            var c = TodayCard.sample
            c.updated = Date()
            SharedStore.save(c)
        }
        #endif
        Packs.register()
        _ = Shell.shared
        return true
    }

    // A reminder while the app is open: show it all the same (a banner), the learner may be on another page.
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }

    // Tapped: open the page it points to (复习 for a word reminder, 今日 for the day's plan).
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        let path = response.notification.request.content.userInfo["path"] as? String
        await MainActor.run { Shell.shared.open(path: path ?? "#/") }
    }
}
