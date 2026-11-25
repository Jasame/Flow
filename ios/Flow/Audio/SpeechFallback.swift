import AVFoundation

/// The iPhone's own voice, for one sentence the server voice could not give (offline, too slow, switched off): the
/// reading goes on instead of stopping, as the page's browser voice does.
@MainActor
final class SpeechFallback: NSObject, AVSpeechSynthesizerDelegate {
    private let synth = AVSpeechSynthesizer()
    private var token = -1
    private var current: AVSpeechUtterance?  // the one being said (held, so no other can share its identity)
    var done: ((Int) -> Void)?

    override init() {
        super.init()
        synth.delegate = self
        synth.usesApplicationAudioSession = true
    }

    func say(_ text: String, voice: String, rate: Float, token: Int) {
        self.token = token
        synth.stopSpeaking(at: .immediate)
        let u = AVSpeechUtterance(string: text)
        u.voice = AVSpeechSynthesisVoice(language: voice.hasPrefix("uk") ? "en-GB" : "en-US")
        u.rate = min(AVSpeechUtteranceMaximumSpeechRate, max(AVSpeechUtteranceMinimumSpeechRate, AVSpeechUtteranceDefaultSpeechRate * rate))
        if AppConfig.muted { u.volume = 0 }  // tests make no sound (AppConfig.muted)
        current = u
        synth.speak(u)
    }

    func stop() {
        token = -1
        current = nil
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        let id = ObjectIdentifier(utterance)
        Task { @MainActor in
            guard let c = self.current, ObjectIdentifier(c) == id, self.token >= 0 else { return }  // a late "finished" of an older one
            self.current = nil
            self.done?(self.token)
        }
    }
}
