import MediaPlayer
import UIKit

/// What the lock screen, Control Center and the Dynamic Island show while a whole text plays: 「AI 朗读 · 标题」, then
/// 「语流 · 第 3 / 18 句」, and for a recording straight through its time. On iOS 27 with 「锁屏上的学习按钮」 on
/// (Feature.lockScreenStudy) the NowPlaying framework shows it, with 语速, 单句循环 and 退回 5 秒 (LockScreen27).
@MainActor
enum LockScreen {
    /// what is playing, as the long player has it
    struct Now {
        var key = ""
        var title = ""
        var i = 0
        var n = 0
        var elapsed: Double?      // a recording straight through: where it is, and how long it is
        var duration: Double?
        var rate: Float = 1
        var playing = false       // sound coming (or about to: 「准备中」)
        var waiting = false
        var interrupted = false   // paused by a call, Siri, an alarm
        var repeatOne = false     // 单句循环 from the lock screen
    }

    private static let art: MPMediaItemArtwork? = {
        guard let img = UIImage(named: "NowPlayingArt") else { return nil }
        return MPMediaItemArtwork(boundsSize: img.size) { @Sendable _ in img }
    }()

    /// Every voice 语流 plays is synthesized (Kokoro recordings, CosyVoice, the iPhone's own voice): 《人工智能生成合成内容
    /// 标识办法》 wants it said where it plays, as the page's aiVoice() does. It leads the title, the line every one of
    /// these screens shows; the sentence goes on the second line.
    nonisolated static func labels(title: String, i: Int, n: Int) -> (title: String, artist: String) {
        let t = title.trimmingCharacters(in: .whitespacesAndNewlines)
        return (t.isEmpty ? "AI 朗读" : "AI 朗读 · " + t, n > 0 ? "语流 · 第 \(min(max(i, 0) + 1, n)) / \(n) 句" : "语流")
    }

    static func show(_ now: Now) {
        #if canImport(NowPlaying)  // the iOS 27 SDK (Xcode 27); CI's Xcode 26 builds the app without it (older lock screen only)
        if #available(iOS 27, *) {
            if Features.on(.lockScreenStudy) {
                RemoteCommands.enable(false)  // the session's own buttons: the older ones would answer as well
                LockScreen27.show(now)
                return
            }
            LockScreen27.clear()  // switched off while a text plays: the older lock screen from here on
        }
        #endif
        RemoteCommands.enable(true)
        let (title, i, n, elapsed, duration, rate, playing) = (now.title, now.i, now.n, now.elapsed, now.duration, now.rate, now.playing)
        let shown = labels(title: title, i: i, n: n)
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: shown.title,
            MPMediaItemPropertyArtist: shown.artist,
            MPMediaItemPropertyAlbumTitle: "语流 Flow",
            MPNowPlayingInfoPropertyPlaybackRate: playing ? Double(rate) : 0.0,
            MPNowPlayingInfoPropertyDefaultPlaybackRate: Double(rate),
            MPNowPlayingInfoPropertyMediaType: MPNowPlayingInfoMediaType.audio.rawValue,
        ]
        if let elapsed, let duration, duration > 0 {
            info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = elapsed
            info[MPMediaItemPropertyPlaybackDuration] = duration
        }
        if let art { info[MPMediaItemPropertyArtwork] = art }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
        RemoteCommands.scrubbing(elapsed != nil)
    }

    static func clear() {
        #if canImport(NowPlaying)
        if #available(iOS 27, *) { LockScreen27.clear() }
        #endif
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    }
}

/// The buttons on the lock screen, in Control Center, on headphones and in the car: play, pause, previous / next
/// sentence, and the scrubber for a recording straight through.
@MainActor
enum RemoteCommands {
    private static weak var player: LongPlayer?

    static func install(_ p: LongPlayer) {
        player = p
        let cc = MPRemoteCommandCenter.shared()
        cc.playCommand.addTarget { @Sendable _ in
            Task { @MainActor in RemoteCommands.player?.resume(why: .remote) }
            return .success
        }
        cc.pauseCommand.addTarget { @Sendable _ in
            Task { @MainActor in RemoteCommands.player?.pause(why: .remote) }
            return .success
        }
        cc.togglePlayPauseCommand.addTarget { @Sendable _ in
            Task { @MainActor in RemoteCommands.player?.toggle() }
            return .success
        }
        cc.stopCommand.addTarget { @Sendable _ in
            Task { @MainActor in RemoteCommands.player?.pause(why: .remote) }  // kept, like ✕ on the page
            return .success
        }
        cc.nextTrackCommand.addTarget { @Sendable _ in
            Task { @MainActor in RemoteCommands.player?.step(1) }
            return .success
        }
        cc.previousTrackCommand.addTarget { @Sendable _ in
            Task { @MainActor in RemoteCommands.player?.step(-1) }
            return .success
        }
        cc.changePlaybackPositionCommand.addTarget { @Sendable e in
            guard let e = e as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            let t = e.positionTime
            Task { @MainActor in RemoteCommands.player?.scrub(to: t) }
            return .success
        }
        for c in [cc.skipForwardCommand, cc.skipBackwardCommand, cc.seekForwardCommand, cc.seekBackwardCommand,
                  cc.changeRepeatModeCommand, cc.changeShuffleModeCommand, cc.likeCommand, cc.dislikeCommand, cc.bookmarkCommand] {
            c.isEnabled = false
        }
    }

    static func scrubbing(_ on: Bool) { MPRemoteCommandCenter.shared().changePlaybackPositionCommand.isEnabled = on }

    /// iOS 27's study buttons (LockScreen27) in use: these do not answer meanwhile, so nothing happens twice
    static func enable(_ on: Bool) {
        let cc = MPRemoteCommandCenter.shared()
        for c in [cc.playCommand, cc.pauseCommand, cc.togglePlayPauseCommand, cc.stopCommand, cc.nextTrackCommand, cc.previousTrackCommand] where c.isEnabled != on {
            c.isEnabled = on
        }
        if !on { cc.changePlaybackPositionCommand.isEnabled = false }
    }
}
