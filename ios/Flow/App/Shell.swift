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
    private let cookies = CookieKeeper()

    private init() {
        site = SiteClient(base: AppConfig.origin)
        player = LongPlayer(site: site)
        recorder = Recorder()
        reminders = Reminders(site: site)
        bridge = Bridge(player: player, recorder: recorder, reminders: reminders)
        web = WebViewController(bridge: bridge, reminders: reminders, site: site)
        let store = web.webView.configuration.websiteDataStore.httpCookieStore
        site.cookieStore = store
        bridge.webView = web.webView
        // the saved session back in WebKit before the first page and before any native request (a refresh in the
        // background launches the app without a page at all)
        let keeper = cookies, site = site
        keeper.changed = { [weak site] in site?.forgetSession() }
        site.ready = Task { if let host = AppConfig.origin.host { await keeper.start(store, host: host) } }
        // the microphone opens: a whole text being read waits, paused where it was (as LONG.other() on the page);
        // when it closes, the audio session stays ours while that text is still there to go on with
        recorder.willRecord = { [weak player] in player?.pause(why: .other) }
        recorder.keepSession = { [weak player] in (player?.state ?? .idle) != .idle }
        // 「iOS 专属功能」 switched on the app's page: what acts at once
        Packs.shared.site = site
        Features.changed.append { [weak player] f, on in
            switch f {
            case .lockScreenStudy: player?.lockScreenChanged()
            case .offlinePacks:
                if on { Task { await Packs.shared.refresh(force: true) } } else { Packs.shared.clear() }
                Packs.schedule()
            case .frugal: Frugal.shared.update()
            case .reviewActivity: if !on { Task { await ReviewActivities.endAll() } }
            case .localCheck:
                if on { Task { _ = await LocalCheck.shared.prepare() } } else { LocalCheck.shared.forget() }
                Shell.shared.bridge.featuresChanged()  // FlowApp.has('localcheck') follows the switch
            case .smartResume, .haptics, .siri: break
            }
        }
    }

    func phase(_ p: ScenePhase) {
        switch p {
        case .active:
            bridge.resendState()
            Task { [reminders, site] in
                let outcome = await reminders.refresh()
                await WidgetsFeed.publish(reminders.input, outcome: outcome, site: site)  // the widgets' numbers too
            }
            Task { await Packs.shared.refresh() }  // 离线朗读包: today's, over Wi-Fi (at most every 3 hours)
        case .background:
            recorder.cutNow()  // no recording behind the learner's back
            LocalCheck.shared.forget()  // nor a take kept for the offline check
            // the counts may have changed while the app was open (a review done): today's reminder follows them
            BackgroundWork.run("reminders") { [reminders] in await reminders.refresh(force: true) }
            Shell.scheduleRefresh()
            Packs.schedule()
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
                var done = false
                let job = Task {
                    let outcome = await Shell.shared.reminders.refresh(force: true)
                    await WidgetsFeed.publish(Shell.shared.reminders.input, outcome: outcome, site: Shell.shared.site)
                    if !done { done = true; task.setTaskCompleted(success: true) }
                }
                task.expirationHandler = {  // out of time: say so now (the cookie calls do not stop on cancel)
                    MainActor.assumeIsolated {
                        job.cancel()
                        if !done { done = true; task.setTaskCompleted(success: false) }
                    }
                }
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

/// A few seconds of work after the app went to the background. iOS ends an app whose background task is not ended
/// in time, so it ends when the work is done or when iOS says time is up (the work is cancelled then).
@MainActor
final class BackgroundWork {
    private var id = UIBackgroundTaskIdentifier.invalid
    private var job: Task<Void, Never>?

    static func run(_ name: String, _ work: @escaping @MainActor () async -> Void) {
        let w = BackgroundWork()
        w.id = UIApplication.shared.beginBackgroundTask(withName: name) { [w] in
            MainActor.assumeIsolated {
                w.job?.cancel()
                w.end()
            }
        }
        w.job = Task { [w] in
            await work()
            w.end()
        }
    }

    private func end() {
        guard id != .invalid else { return }
        UIApplication.shared.endBackgroundTask(id)
        id = .invalid
    }
}

struct ShellView: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> WebViewController { Shell.shared.web }
    func updateUIViewController(_ controller: WebViewController, context: Context) {}
}
