import Foundation
import UIKit

/// 「省电时少做事」 (Feature.frugal): Low Power Mode, or iOS 27 saying it prefers reduced resource usage
/// (UIApplication.systemPrefersReducedResourceUsage): the app makes one server-voice sentence ahead instead of two and
/// fetches no 离线朗读包 in the front; the page hears it (`frugal` event, `app.frugal`) and preloads less (its PRELOAD).
@MainActor
final class Frugal {
    static let shared = Frugal()
    /// it changed: the page is told (Bridge)
    var changed: ((Bool) -> Void)?
    private(set) var on = false

    private init() {
        let nc = NotificationCenter.default
        nc.addObserver(forName: .NSProcessInfoPowerStateDidChange, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.update() }
        }
        if #available(iOS 27, *) {
            nc.addObserver(forName: UIApplication.systemPrefersReducedResourceUsageDidChangeNotification, object: nil, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.update() }
            }
        }
        on = Self.decide(switchOn: Features.on(.frugal), lowPower: ProcessInfo.processInfo.isLowPowerModeEnabled, reduced: Self.reduced)
    }

    /// the system's hints read again (they changed, or the switch did)
    func update() {
        let now = Self.decide(switchOn: Features.on(.frugal), lowPower: ProcessInfo.processInfo.isLowPowerModeEnabled, reduced: Self.reduced)
        guard now != on else { return }
        on = now
        changed?(now)
    }

    nonisolated static func decide(switchOn: Bool, lowPower: Bool, reduced: Bool) -> Bool { switchOn && (lowPower || reduced) }

    static var reduced: Bool {
        if #available(iOS 27, *) { return UIApplication.shared.systemPrefersReducedResourceUsage }
        return false
    }
}
