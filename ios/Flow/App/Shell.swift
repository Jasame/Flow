import SwiftUI
import UIKit
import WebKit
import BackgroundTasks

/// Everything that lives as long as the app: the web view, the bridge and the native parts behind it.
@MainActor
final class Shell {
    static let shared = Shell()
    static let refreshTask = "cn.flowlang.app.refresh"

    let site: SiteClient
    let player: LongPlayer
    let recorder: Recorder
    let reminders: Reminders
    let bridge: Bridge
    let web: WebViewController

    private init() {
        site = SiteClient(base: AppConfig.site)
        player = LongPlayer(site: site)
        recorder = Recorder()
        reminders = Reminders(site: site)
        bridge = Bridge(player: player, recorder: recorder, reminders: reminders)
        web = WebViewController(bridge: bridge, reminders: reminders)
        site.cookieStore = web.webView.configuration.websiteDataStore.httpCookieStore
        bridge.webView = web.webView
        // the microphone opens: a whole text being read waits, paused where it was (as LONG.other() on the page)
        recorder.willRecord = { [weak player] in player?.pause(why: .other) }
    }

    func phase(_ p: ScenePhase) {
        switch p {
        case .active:
            bridge.resendState()
            Task { await reminders.refresh() }
        case .background:
            // the counts may have changed while the app was open (a review done): today's reminder follows them
            let id = UIApplication.shared.beginBackgroundTask(withName: "reminders")
            Task {
                await reminders.refresh(force: true)
                if id != .invalid { UIApplication.shared.endBackgroundTask(id) }
            }
            Shell.scheduleRefresh()
        default:
            break
        }
    }

    func open(path: String) { web.open(path: path) }

    // ---- once or twice a day, without the app being opened: the next two weeks of reminders follow the counts
    static func registerBackgroundRefresh() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: refreshTask, using: .main) { task in
            guard let task = task as? BGAppRefreshTask else { return }
            MainActor.assumeIsolated {
                let job = Task {
                    await Shell.shared.reminders.refresh(force: true)
                    task.setTaskCompleted(success: true)
                }
                task.expirationHandler = { job.cancel() }
                scheduleRefresh()
            }
        }
    }

    static func scheduleRefresh() {
        let r = BGAppRefreshTaskRequest(identifier: refreshTask)
        r.earliestBeginDate = Date(timeIntervalSinceNow: 6 * 3600)
        try? BGTaskScheduler.shared.submit(r)
    }
}

struct ShellView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> WebViewController { Shell.shared.web }
    func updateUIViewController(_ controller: WebViewController, context: Context) {}
}
