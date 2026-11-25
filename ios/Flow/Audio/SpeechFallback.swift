import AVFoundation

/// The iPhone's own voice, for one sentence the server voice could not give (offline, too slow, switched off): the
/// reading goes on instead of stopping, as the page's browser voice does.
@MainActor
final class SpeechFallback: NSObject, AVSpeechSynthesizerDelegate {
    private let synth = AVSpeechSynthesizer()
    private var token = -1
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
        synth.speak(u)
    }

    func stop() {
        token = -1
        if synth.isSpeaking { synth.stopSpeaking(at: .immediate) }
    }

    nonisolated func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) {
        Task { @MainActor in
            let t = self.token
            if t >= 0 { self.done?(t) }
        }
    }
}
