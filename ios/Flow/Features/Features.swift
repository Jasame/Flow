import Foundation

/// 「iOS 专属功能」 (我的 → 设置 → iOS 专属功能, FeaturesView): what the app does beyond the website, each switched on or
/// off on this phone only (UserDefaults `feature.<id>`, never sent anywhere). A feature this iOS is too old for is not
/// shown and counts as off. The owner's ask (2026-11-25): 「对 iOS 27 的特性做特殊优化，可以选择开启与关闭」.
nonisolated enum Feature: String, CaseIterable, Identifiable, Sendable {
    case lockScreenStudy = "lock-study"      // iOS 27: 语速, 单句循环 and 退回 5 秒 on the lock screen (LockScreen27)
    case smartResume = "smart-resume"        // after a call, Siri, an alarm: goes on when iOS says it may (LongPlayer)
    case offlinePacks = "offline-packs"      // today's recordings kept on the phone, fetched on Wi-Fi (Packs)
    case haptics = "haptics"                 // a light tap of the phone as the page asks (复习's ratings, answers: Haptics)
    case frugal = "frugal"                   // Low Power Mode, iOS 27's reduced resources: less ahead of time (Frugal)
    case reviewActivity = "review-activity"  // the word review's progress on the lock screen (ReviewActivities)

    enum Group: String, CaseIterable {
        case listen = "锁屏听读"
        case feel = "手感和省电"
        case glance = "不打开 App 也能学"

        /// under the group's switches: what has no switch of its own
        var footer: String? {
            switch self {
            case .glance: "小组件：长按主屏空白处 →「编辑」→「添加小组件」，搜「语流」，有「今天」一种（主屏、锁屏都能放）。控制中心：下拉控制中心，长按空白处 →「添加控件」，搜「语流」，有「开始复习」「今天的学习」两个按钮。"
            default: nil
            }
        }
    }

    var id: String { rawValue }
    var key: String { "feature." + rawValue }
    var group: Group {
        switch self {
        case .lockScreenStudy, .smartResume, .offlinePacks: .listen
        case .haptics, .frugal: .feel
        case .reviewActivity: .glance
        }
    }

    var title: String {
        switch self {
        case .lockScreenStudy: "锁屏上的学习按钮"
        case .smartResume: "来电以后接着放"
        case .offlinePacks: "离线朗读包"
        case .haptics: "复习时的轻触震动"
        case .frugal: "省电时少做事"
        case .reviewActivity: "复习进度的实时活动"
        }
    }

    /// one grey line under the title: what the learner gets
    var detail: String {
        switch self {
        case .lockScreenStudy: "锁屏和灵动岛上调语速（0.75× / 1× / 1.25×）、单句循环、退回 5 秒"
        case .smartResume: "来电、Siri、闹钟以后，系统说可以就接着放；关掉就停在那里，等你点播放"
        case .offlinePacks: "连着 Wi-Fi 时，把今天要学的 3 篇文章录音存到手机上，地铁里没网也能放；存满 7 天的自动删掉"
        case .haptics: "复习单词点「认识 / 模糊 / 不认识」、做题答对答错时，手机轻轻一震，手感各不一样"
        case .frugal: "开了低电量模式、或者系统提示要省着用时，少提前下载录音和文章，等用到再下"
        case .reviewActivity: "复习单词时，锁屏和灵动岛上显示「12 / 30」，切到别的 App 也看得到。锁屏上别人也看得到这个数字"
        }
    }

    var defaultOn: Bool {
        switch self {
        case .lockScreenStudy, .smartResume, .haptics, .frugal: true
        case .offlinePacks: false  // it takes room on the phone: the learner turns it on
        case .reviewActivity: false  // others can see the lock screen: the learner turns it on
        }
    }

    /// The system can do it (the switch is shown).
    var available: Bool {
        switch self {
        case .lockScreenStudy:  // iOS 27, and an app built with its SDK (LockScreen27)
            #if canImport(NowPlaying)
            if #available(iOS 27, *) { return true }
            #endif
            return false
        case .smartResume, .offlinePacks, .haptics, .frugal, .reviewActivity:
            return true
        }
    }
}

@MainActor
enum Features {
    /// a switch changed on the page (the parts that act at once: the lock screen, the offline packs)
    static var changed: [(Feature, Bool) -> Void] = []

    static func on(_ f: Feature) -> Bool {
        guard f.available else { return false }
        return UserDefaults.standard.object(forKey: f.key) == nil ? f.defaultOn : UserDefaults.standard.bool(forKey: f.key)
    }

    static func set(_ f: Feature, _ on: Bool) {
        UserDefaults.standard.set(on, forKey: f.key)
        for fn in changed { fn(f, on) }
    }

    /// what the page and the tests see: {"lock-study": true, …} for the features this iOS has
    static var state: [String: Bool] {
        Dictionary(uniqueKeysWithValues: Feature.allCases.filter(\.available).map { ($0.rawValue, on($0)) })
    }
}
