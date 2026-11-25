#if canImport(NowPlaying)  // the iOS 27 SDK (Xcode 27); CI's Xcode 26 builds the app without it (older lock screen only)
import NowPlaying
import Observation
import UIKit

/// The whole text's session as the NowPlaying framework (iOS 27) reads it: it watches these three and keeps the lock
/// screen, the Dynamic Island, Control Center and headphones up to date.
@available(iOS 27, *)
@MainActor
@Observable
final class StudySession: MediaSessionRepresentable {
    nonisolated let id = "cn.flowlang.long"  // Identifiable asks for it from anywhere
    var content: (any MediaContentRepresentable)?
    var playbackSnapshot: MediaPlaybackSnapshot?
    var commands: [MediaCommand] = []
}

/// iOS 27's lock screen (Feature.lockScreenStudy): besides play / pause and the previous / next sentence, what a
/// learner reaches for with the phone locked: 语速 (the page's own 0.75× / 1× / 1.25×), 单句循环 (this sentence again
/// and again, the page's 「单句循环」) and 退回 5 秒 (a recording straight through; read sentence by sentence: this
/// sentence from its start). The page hears of each change in its next `audio` event (rate, rep, loop).
@available(iOS 27, *)
@MainActor
enum LockScreen27 {
    static let rates: [Float] = [0.75, 1, 1.25]
    static let back: TimeInterval = 5
    static weak var player: LongPlayer?
    private static var shown: StudySession?
    private static var session: MediaSession<StudySession>?

    private static let art: Artwork? = UIImage(named: "NowPlayingArt") == nil ? nil : Artwork(id: "flow-now-playing") { @Sendable _ in
        guard let img = UIImage(named: "NowPlayingArt")?.cgImage else { throw ArtworkRepresentation.ArtworkRepresentationError.noRepresentationAvailable }
        return try ArtworkRepresentation(cgImage: img)
    }

    static func show(_ now: LockScreen.Now) {
        let s: StudySession
        if let shown { s = shown } else {
            s = StudySession()
            shown = s
            let m = MediaSession(s)
            session = m
            Task {
                try? await m.requestToBecomeApplicationPrimary()
                // the learner just pressed play in 语流: this is what the lock screen shows, not what played before
                if UIApplication.shared.applicationState == .active { try? await m.requestToBecomeSystemPrimary() }
            }
        }
        let label = LockScreen.labels(title: now.title, i: now.i, n: now.n)
        s.content = GenericContent(id: now.key.isEmpty ? "flow" : now.key, title: label.title, subtitle: label.artist, type: .audio,
                                   duration: now.duration.map { .finite($0) } ?? .continuous, artwork: art)
        s.playbackSnapshot = MediaPlaybackSnapshot(state: state(now), defaultPlaybackRate: now.rate, elapsedTime: now.elapsed, timestamp: Date())
        s.commands = commands(now)
    }

    static func clear() {
        shown = nil
        session = nil  // gone from the lock screen with it
    }

    /// what the system made of it (tests, the bridge page): whether this session is the app's and the phone's own
    static var info: [String: Any] {
        guard let session, let shown else { return ["on": false] }
        var o: [String: Any] = ["on": true, "app": session.isApplicationPrimary, "system": session.isSystemPrimary,
                                "commands": shown.commands.count]
        if let c = shown.content as? GenericContent { o["title"] = c.title; o["subtitle"] = c.subtitle ?? "" }
        return o
    }

    static func state(_ now: LockScreen.Now) -> MediaPlaybackSnapshot.PlaybackState {
        if now.waiting { return .buffering }
        if now.playing { return .playing(rate: now.rate) }
        return now.interrupted ? .interrupted : .paused
    }

    private static func commands(_ now: LockScreen.Now) -> [MediaCommand] {
        var c: [MediaCommand] = [
            .play { @MainActor in player?.resume(why: .remote) },
            .pause { @MainActor in player?.pause(why: .remote) },
            .togglePlayPause { @MainActor in player?.toggle() },
            .stop { @MainActor in player?.pause(why: .remote) },  // kept, like ✕ on the page
            .next { @MainActor in player?.step(1) },
            .previous { @MainActor in player?.step(-1) },
            .skipBackward(preferredIntervals: [back]) { @MainActor secs in player?.skipBack(secs) },
            .changePlaybackRate(supported: rates) { @MainActor rate in player?.setRate(rate) },
            .changeRepeatMode(current: now.repeatOne ? .one : .off, supported: [.off, .one]) { @MainActor mode in player?.setRepeatOne(mode == .one) },
        ]
        if now.elapsed != nil { c.append(.seekToPosition { @MainActor t in player?.scrub(to: t) }) }
        return c
    }
}
#endif
