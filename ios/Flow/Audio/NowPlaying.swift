import MediaPlayer
import UIKit

/// What the lock screen, Control Center and the Dynamic Island show while a whole text plays: 「语流 · 标题」, the
/// sentence (第 3 / 18 句), and for a recording straight through its time.
@MainActor
enum NowPlaying {
    private static let art: MPMediaItemArtwork? = {
        guard let img = UIImage(named: "NowPlayingArt") else { return nil }
        return MPMediaItemArtwork(boundsSize: img.size) { @Sendable _ in img }
    }()

    static func show(title: String, i: Int, n: Int, elapsed: Double?, duration: Double?, rate: Float, playing: Bool) {
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: "语流 · " + (title.isEmpty ? "朗读" : title),
            MPMediaItemPropertyArtist: "语流 Flow",
            MPMediaItemPropertyAlbumTitle: "第 \(min(i + 1, n)) / \(n) 句",
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
}
