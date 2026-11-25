import AVFoundation

/// The microphone for 跟读, 口语对话 and 发音: AVAudioRecorder, 16 kHz mono. WAV (16-bit PCM) by default; AAC (m4a) for answers
/// longer than 40 s, since WAV takes 32 KB a second and the page takes 1.4 MB (the server 1.5 MB). stop() answers in the shape the page uploads
/// ({mime_type, data}, as MIC.payload). The microphone is open only while recording; then the session is playback again.
@MainActor
final class Recorder: NSObject, AVAudioRecorderDelegate {
    enum Format: String { case wav, m4a }
    static let wavSeconds = 40.0

    private var rec: AVAudioRecorder?
    private var file: URL?
    private var format = Format.wav
    private var startedAt: Date?
    private var lengthMs: Int?
    private var cut = false
    private var starting = false       // start() is waiting for iOS's answer
    private var dropStart = false      // stop() or cancel() came meanwhile: the recording does not begin
    var emit: ((String, [String: Any]) -> Void)?
    var willRecord: (() -> Void)?
    /// true while a whole text is still there to go on with: the audio session stays ours after the recording
    var keepSession: (() -> Bool)?

    override init() {
        super.init()
        NotificationCenter.default.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] note in
            let type = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            MainActor.assumeIsolated {
                // a call, Siri: what was said so far is kept, stop() still gives it. iOS may already have stopped the
                // recorder (and then sends no "finished"), so it is handled here whether or not it still records.
                guard type == AVAudioSession.InterruptionType.began.rawValue else { return }
                self?.cutNow()
            }
        }
    }

    var busy: Bool { rec?.isRecording == true }

    /// The recording ends here with what was said so far ('cut'): a call came, or the app left the screen — the
    /// microphone is open only while the learner is in front of it (the usage text promises that).
    func cutNow() {
        guard let r = rec, lengthMs == nil else { return }
        cut = true
        lengthMs = r.isRecording ? Int(r.currentTime * 1000) : Int(Date().timeIntervalSince(startedAt ?? Date()) * 1000)
        r.stop()
        finished(ObjectIdentifier(r))
    }

    func permission() -> String {
        switch AVAudioApplication.shared.recordPermission {
        case .granted: return "granted"
        case .denied: return "denied"
        default: return "undetermined"
        }
    }

    /// iOS's question (asked once; the answer is kept): true when the microphone may be used.
    func ask() async -> Bool {
        switch AVAudioApplication.shared.recordPermission {
        case .granted: return true
        case .denied: return false
        default: return await AVAudioApplication.requestRecordPermission()
        }
    }

    func start(_ a: [String: Any]) async -> [String: Any] {
        if busy { return ["ok": false, "why": "busy", "message": "正在录音"] }
        LocalCheck.shared.forget()  // the take before this one is not the one to check any more
        let maxSecs = min(300, max(1, Bridge.double(a["max"]) ?? 30))
        // WAV is 32 KB a second: past 40 s it would be over the page's 1.4 MB (MIC.payload) — AAC then
        let fmt = Format(rawValue: (a["format"] as? String) ?? "") ?? (maxSecs > Self.wavSeconds ? .m4a : .wav)
        starting = true
        dropStart = false
        let granted = await ask()
        starting = false
        if dropStart { return ["ok": false, "why": "cancelled", "message": "录音已取消"] }
        guard granted else {
            return ["ok": false, "why": "denied", "message": "麦克风没有打开：到 iPhone 的「设置 → \(Bundle.main.displayName) → 麦克风」打开，再点一次录音。"]
        }
        discard()
        willRecord?()
        do {
            try AudioSessionManager.shared.beginRecording()
        } catch {
            return ["ok": false, "why": "error", "message": "麦克风现在用不了（可能正在通话），稍后再试"]
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("rec-\(UUID().uuidString).\(fmt.rawValue)")
        let settings: [String: Any] = fmt == .wav
            ? [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: WAV.sampleRate, AVNumberOfChannelsKey: 1,
               AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false]
            : [AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: WAV.sampleRate, AVNumberOfChannelsKey: 1,
               AVEncoderBitRateKey: 32_000, AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue]
        do {
            let r = try AVAudioRecorder(url: url, settings: settings)
            r.delegate = self
            guard r.prepareToRecord(), r.record(forDuration: maxSecs) else { throw NSError(domain: "Recorder", code: 1) }
            rec = r
            file = url
            format = fmt
            startedAt = Date()
            lengthMs = nil
            cut = false
            emit?("rec", ["state": "recording", "max": maxSecs, "format": fmt.rawValue])
            return ["ok": true, "format": fmt.rawValue, "max": maxSecs]
        } catch {
            AudioSessionManager.shared.endRecording(stillPlaying: keepSession?() ?? false)
            try? FileManager.default.removeItem(at: url)
            return ["ok": false, "why": "error", "message": "录音没能开始，再试一次"]
        }
    }

    /// The recording: {ok, mime_type, data (base64), ms, bytes}. Stops it first if it still runs.
    func stop() async -> [String: Any] {
        if starting { dropStart = true }
        if let r = rec, r.isRecording {
            lengthMs = Int(r.currentTime * 1000)
            r.stop()
        }
        AudioSessionManager.shared.endRecording(stillPlaying: keepSession?() ?? false)
        defer { discard() }
        guard let file, var data = try? Data(contentsOf: file), data.count > 64 else {
            return ["ok": false, "why": "none", "message": "没有录到声音，再试一次"]
        }
        if format == .wav { data = WAV.canonical(data) ?? data }
        let ms = lengthMs ?? Int(Date().timeIntervalSince(startedAt ?? Date()) * 1000)
        let mime = format == .wav ? "audio/wav" : "audio/mp4"
        LocalCheck.shared.keep(data, mime: mime)  // only while 「本机快速检查（离线）」 is on, for rec.localcheck
        return ["ok": true, "mime_type": mime, "data": data.base64EncodedString(),
                "ms": ms, "bytes": data.count, "cut": cut]
    }

    func cancel() {
        if starting { dropStart = true }
        rec?.stop()
        AudioSessionManager.shared.endRecording(stillPlaying: keepSession?() ?? false)
        discard()
    }

    private func discard() {
        if let file { try? FileManager.default.removeItem(at: file) }
        rec = nil
        file = nil
    }

    // the recording reached max by itself, or was stopped (a call, stop())
    nonisolated func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        let id = ObjectIdentifier(recorder)
        Task { @MainActor in self.finished(id) }
    }

    private var reported: ObjectIdentifier?  // the recording whose end was already told to the page

    private func finished(_ id: ObjectIdentifier) {
        guard let rec, ObjectIdentifier(rec) == id, reported != id else { return }  // a late call, or told already
        reported = id
        let ms = lengthMs ?? Int(Date().timeIntervalSince(startedAt ?? Date()) * 1000)
        lengthMs = ms
        AudioSessionManager.shared.endRecording(stillPlaying: keepSession?() ?? false)
        emit?("rec", ["state": cut ? "cut" : "done", "ms": ms])
    }
}
