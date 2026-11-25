import AVFoundation

/// The app's audio session. Playback (spoken audio): the ringer switch does not silence it, it goes on with the screen
/// locked, and other apps' music stops while 语流 reads (and comes back after). While recording: play-and-record, sound
/// out of the loudspeaker (not the earpiece), and straight back to playback the moment the recording ends.
@MainActor
final class AudioSessionManager {
    static let shared = AudioSessionManager()
    private let s = AVAudioSession.sharedInstance()
    private(set) var recording = false
    private(set) var active = false

    func prepare() { playback() }

    private func playback() {
        try? s.setCategory(.playback, mode: .spokenAudio, policy: .longFormAudio, options: [])
    }

    /// Before a sound starts. false: iOS said no (a call is going on).
    @discardableResult
    func activate() -> Bool {
        if !recording { playback() }  // whatever the page's own microphone (getUserMedia) left behind
        do {
            try s.setActive(true)
            active = true
            return true
        } catch {
            return false
        }
    }

    /// Nothing plays and nothing records any more: other apps' sound may go on (notifyOthersOnDeactivation).
    func deactivate() {
        guard active, !recording else { return }
        try? s.setActive(false, options: .notifyOthersOnDeactivation)
        active = false
    }

    func beginRecording() throws {
        recording = true
        do {
            try s.setCategory(.playAndRecord, mode: .default, options: [.defaultToSpeaker, .allowBluetoothHFP])
            try s.setActive(true)
            active = true
        } catch {
            recording = false
            playback()
            throw error
        }
    }

    func endRecording(stillPlaying: Bool) {
        guard recording else { return }
        recording = false
        playback()
        if !stillPlaying { deactivate() }
    }
}
