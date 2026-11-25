import AVFoundation
import UIKit

/// A whole text read aloud (听's 播放全文, 读's 伴读), played by the app: it goes on with the screen locked and while the
/// page's JavaScript sleeps, the lock screen and Control Center show 「语流 · 标题」 with play / pause and the previous /
/// next sentence, and after a call (or Siri, an alarm) it goes on by itself when iOS says it may.
/// The same rules as the page's LONG (01-audio-offline.js): a recording straight through, or sentence by sentence when
/// 复读 is set; without a recording the server voice sentence by sentence (the next two made ahead), and the iPhone's
/// own voice only for a sentence the server could not give, with the reason. 暂停 / 继续: a recording goes on from the
/// second it stopped, a sentence-by-sentence reading from the start of its sentence. Where it was is kept per text.
@MainActor
final class LongPlayer: NSObject {
    enum State: String { case waiting, playing, paused, idle }
    enum Why: String { case user, remote, interrupted, route, other, ended, error }

    struct Span: Equatable {
        var s: Double
        var e: Double
    }

    struct Request {
        var key = ""
        var title = ""
        var src: URL?
        var alt: URL?
        var sentences: [Span] = []
        var texts: [String] = []
        var voice = "us-f"
        var pack: String?
        var csrf: String?
        var from = 0
        var at: Double?
        var loop = false
        var rep = 1
        var gaps: [Int] = []
        var rate: Float = 1

        var count: Int { src != nil ? sentences.count : texts.count }
        var straight: Bool { src != nil && !loop }
        /// ms of quiet after sentence i, each time it was said (复读's 「留时间跟说」: sized by the sentence just read)
        func gap(_ i: Int) -> Int { gaps.isEmpty ? 0 : max(0, gaps.count == 1 ? gaps[0] : (i < gaps.count ? gaps[i] : 0)) }

        init() {}

        /// From the page's FlowApp.audio.play(o); relative addresses are on the site.
        init?(json o: [String: Any], base: URL) {
            key = (o["key"] as? String) ?? ""
            title = (o["title"] as? String) ?? ""
            let abs = { (v: Any?) -> URL? in
                guard let s = v as? String, !s.isEmpty, let u = URL(string: s, relativeTo: base)?.absoluteURL,
                      u.scheme == "https" || (AppConfig.isBeta && u.scheme == "http") else { return nil }
                return u
            }
            src = abs(o["src"])
            alt = abs(o["alt"])
            sentences = ((o["sentences"] as? [Any]) ?? []).compactMap { x in
                if let p = x as? [Any], p.count >= 2, let s = Bridge.double(p[0]), let e = Bridge.double(p[1]) { return Span(s: s, e: e) }
                if let d = x as? [String: Any], let s = Bridge.double(d["s"]), let e = Bridge.double(d["e"]) { return Span(s: s, e: e) }
                return nil
            }
            texts = ((o["texts"] as? [Any]) ?? []).compactMap { $0 as? String }
            voice = (o["voice"] as? String) ?? "us-f"
            pack = o["pack"] as? String
            csrf = o["csrf"] as? String
            from = Bridge.int(o["from"]) ?? 0
            at = Bridge.double(o["at"])
            loop = (o["loop"] as? Bool) ?? false
            rep = max(0, Bridge.int(o["rep"]) ?? 1)
            if let g = o["gap"] as? [Any] { gaps = g.compactMap(Bridge.int) } else if let g = Bridge.int(o["gap"]) { gaps = [g] }
            rate = Float(min(2, max(0.5, Bridge.double(o["rate"]) ?? 1)))
            if src != nil, sentences.isEmpty { return nil }  // a recording needs its sentence times
            if count == 0 { return nil }
        }
    }

    private(set) var req: Request?
    private(set) var state: State = .idle
    private(set) var index = 0
    private(set) var lastWhy: Why = .user
    private var reps = 0
    private var note = ""
    private var token = 0              // moves on every pause / stop / step: late callbacks of an older start are dropped
    private var midSentence = false    // a sentence (or the recording) is under way: 继续 goes on from where it stopped
    private var resumeAfterInterruption = false
    private var usedAlt = false
    private var altLoading = false     // the other line is being loaded: the first line's second failure report is the same one
    private var dead = false           // the recording failed for good: an AVPlayerItem that failed never plays again
    private var resumeAt: Double?      // where 继续 starts a recording that had to be loaded again (a new line, after a failure)
    private var seeking = 0            // seeks on their way: the time observer still reports the old second meanwhile
    private var serverVoiceOff: String? // the server said no for this text (signed out, switched off): no more asking
    private var player = AVPlayer()
    private var timeObserver: Any?
    private var statusWatch: NSKeyValueObservation?
    private var controlWatch: NSKeyValueObservation?
    private var loading = false        // the player is waiting for the network: the page shows 「准备中」, not playing
    private var waitTask: Task<Void, Never>?
    private var gapTask: Task<Void, Never>?
    private var noteTask: Task<Void, Never>?
    private var background = UIBackgroundTaskIdentifier.invalid
    private let speech = SpeechFallback()
    private let site: SiteClient
    private let tts: TTSFetcher
    private let store = ProgressStore()
    var emit: ((String, [String: Any]) -> Void)?

    init(site: SiteClient) {
        tts = TTSFetcher(site: site)
        self.site = site
        super.init()
        setUpPlayer()
        let nc = NotificationCenter.default
        nc.addObserver(forName: AVAudioSession.interruptionNotification, object: nil, queue: .main) { [weak self] note in
            let type = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            let options = note.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
            let reason = note.userInfo?[AVAudioSessionInterruptionReasonKey] as? UInt
            MainActor.assumeIsolated { self?.interruption(type, options, reason) }
        }
        nc.addObserver(forName: AVAudioSession.routeChangeNotification, object: nil, queue: .main) { [weak self] note in
            let reason = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            MainActor.assumeIsolated {
                if reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue { self?.pause(why: .route) }  // headphones out
            }
        }
        nc.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.servicesReset() }
        }
        nc.addObserver(forName: AVPlayerItem.didPlayToEndTimeNotification, object: nil, queue: .main) { [weak self] note in
            let item = (note.object as AnyObject?).map(ObjectIdentifier.init)
            MainActor.assumeIsolated { self?.itemEnded(item) }
        }
        nc.addObserver(forName: AVPlayerItem.failedToPlayToEndTimeNotification, object: nil, queue: .main) { [weak self] note in
            let item = (note.object as AnyObject?).map(ObjectIdentifier.init)
            MainActor.assumeIsolated { self?.itemFailed(item) }
        }
        speech.done = { [weak self] tok in self?.speechDone(tok) }
        RemoteCommands.install(self)
    }

    private func setUpPlayer() {
        player.isMuted = AppConfig.muted
        player.actionAtItemEnd = .pause
        player.automaticallyWaitsToMinimizeStalling = true
        timeObserver = player.addPeriodicTimeObserver(forInterval: CMTime(value: 1, timescale: 4), queue: .main) { [weak self] time in
            let t = time.seconds
            MainActor.assumeIsolated { self?.tick(t) }
        }
        controlWatch = player.observe(\.timeControlStatus, options: [.new]) { [weak self] p, _ in
            let s = p.timeControlStatus
            Task { @MainActor in self?.controlStatus(s) }
        }
    }

    // MARK: what the page and the lock screen call

    func play(_ r: Request) async -> [String: Any] {
        stopNow(save: true, why: nil)  // another text: where the last one was is kept
        token += 1
        let tok = token
        var r = r  // the page decides where to start (「从第 N 句继续」); the app's own copy is for progress(key)
        r.from = max(0, min(r.from, r.count - 1))
        req = r
        index = r.from
        reps = 0
        note = ""
        usedAlt = false
        altLoading = false
        dead = false
        resumeAt = nil
        serverVoiceOff = nil
        lastWhy = .user
        if let at = r.at, r.src != nil { index = Self.sentence(at: at, in: r.sentences) ?? Self.sentenceAfter(at, in: r.sentences) ?? index }
        guard AudioSessionManager.shared.activate() else {
            req = nil
            return ["ok": false, "why": "session", "message": "现在放不了声音（可能正在通话）"]
        }
        if let src = r.src {
            await load(src)
            guard token == tok, req != nil else { return ["ok": false, "why": "stopped"] }
        }
        state = .playing
        go(at: r.at)
        return ["ok": true, "state": snapshot()]
    }

    func pause(why: Why) {
        guard let r = req, state == .playing || state == .waiting else { return }
        token += 1
        gapTask?.cancel()
        noteTask?.cancel()
        player.pause()
        speech.stop()
        if r.src == nil { midSentence = false }  // the server voice: 继续 says that sentence again from its start
        loading = false
        if why == .interrupted { resumeAfterInterruption = true } else if why != .other { resumeAfterInterruption = false }
        lastWhy = why
        note = ""
        set(.paused, why: why)
        save()
        releaseBackground()
    }

    func resume(why: Why) {
        guard let r = req, state == .paused else { return }
        // the microphone is open, or iOS will not give the sound (a call): it stays paused, and the page is told so
        guard !AudioSessionManager.shared.recording, AudioSessionManager.shared.activate() else {
            set(.paused, why: .interrupted)
            return
        }
        lastWhy = why
        resumeAfterInterruption = false
        if dead, let src = r.src {  // 「录音没加载出来…」 then 继续: the recording anew, from where it was
            dead = false
            usedAlt = false
            note = ""
            token += 1
            let tok = token
            set(.playing, why: why)
            Task {
                await self.load(src)
                guard self.token == tok, self.req != nil, self.state == .playing || self.state == .waiting else { return }
                self.go(at: self.resumeAt)
            }
            return
        }
        if r.src != nil && midSentence {
            token += 1
            set(.playing, why: why)
            player.play()
        } else {
            set(.playing, why: why)
            go(at: resumeAt)
        }
    }

    func toggle() { if state == .paused { resume(why: .remote) } else { pause(why: .remote) } }

    /// previous / next sentence (the lock screen, the page)
    func step(_ d: Int) {
        guard let r = req else { return }
        if r.straight && !dead {  // as NAR.step: the sentence not yet over (or the last), then back to its start first
            let t = player.currentTime().seconds.finiteOr(0)
            let i = r.sentences.firstIndex { t < $0.e + 0.25 } ?? r.sentences.count - 1
            var dd = d
            if d < 0, t - r.sentences[i].s > 1.5 { dd = 0 }
            jump(to: i + dd)
            return
        }
        jump(to: index + d)
    }

    func seek(_ i: Int) { jump(to: i) }

    private func jump(to i: Int) {
        guard let r = req else { return }
        let j = max(0, min(r.count - 1, i))
        if dead {  // nothing to seek in: 继续 loads the recording again from there
            index = j
            reps = 0
            resumeAt = r.src != nil ? r.sentences[j].s : nil
            save()
            set(state, why: .user)
            return
        }
        if r.straight {
            index = j
            seekTo(r.sentences[j].s)
            save()
            set(state, why: .user)
            return
        }
        token += 1
        gapTask?.cancel()
        player.pause()
        speech.stop()
        index = j
        reps = 0
        midSentence = false
        set(.playing, why: .user)
        go()
    }

    /// The scrubber on the lock screen (a recording straight through)
    func scrub(to t: Double) {
        guard let r = req, r.straight else { return }
        seekTo(t)
        if let i = Self.sentence(at: t, in: r.sentences) ?? Self.sentenceAfter(t, in: r.sentences) { index = i }
        save(time: t)
        set(state, why: .remote)
    }

    /// 复读 changed on the page while it plays: rep (times each sentence), gap, rate
    func set(_ o: [String: Any]) {
        guard var r = req else { return }
        if let v = Bridge.int(o["rep"]) { r.rep = max(0, v) }
        if let g = o["gap"] as? [Any] { r.gaps = g.compactMap(Bridge.int) } else if let g = Bridge.int(o["gap"]) { r.gaps = [g] }
        if let v = Bridge.double(o["rate"]) {
            r.rate = Float(min(2, max(0.5, v)))
            player.defaultRate = r.rate
            if player.rate > 0 { player.rate = r.rate }
        }
        req = r
    }

    func stop(why: Why) { stopNow(save: true, why: why) }

    func progress(_ key: String?) -> [String: Any]? { key.flatMap { store.get($0) } }

    func snapshot(why: String? = nil) -> [String: Any] {
        var o: [String: Any] = ["state": state.rawValue, "i": index, "note": note]
        if let r = req {
            o["key"] = r.key
            o["n"] = r.count
            o["title"] = r.title
            if r.src != nil { o["t"] = player.currentTime().seconds.finiteOr(0) }
            o["rate"] = r.rate
        }
        if let why { o["why"] = why }
        return o
    }

    // MARK: playing

    private func seekTo(_ t: Double, then: (@MainActor () -> Void)? = nil) {
        seeking += 1
        player.seek(to: CMTime(seconds: t, preferredTimescale: 600), toleranceBefore: .zero, toleranceAfter: .zero) { [weak self] _ in
            Task { @MainActor in
                guard let self else { return }
                self.seeking = max(0, self.seeking - 1)
                then?()
            }
        }
    }

    private func load(_ src: URL) async {
        let cookies = AppConfig.isOwn(src) ? await site.cookies(for: src) : []
        let asset = AVURLAsset(url: src, options: [AVURLAssetHTTPCookiesKey: cookies])
        let item = AVPlayerItem(asset: asset)
        item.audioTimePitchAlgorithm = .timeDomain
        watch(item)
        player.replaceCurrentItem(with: item)
        player.defaultRate = req?.rate ?? 1
    }

    private func watch(_ item: AVPlayerItem) {
        let id = ObjectIdentifier(item)
        statusWatch = item.observe(\.status, options: [.new]) { [weak self] item, _ in
            let failed = item.status == .failed
            Task { @MainActor in if failed { self?.itemFailed(id) } }
        }
    }

    private func go(at: Double? = nil) {
        guard let r = req else { return }
        token += 1
        let tok = token
        gapTask?.cancel()
        noteTask?.cancel()
        if r.src != nil {
            let s = r.sentences[index]
            player.currentItem?.forwardPlaybackEndTime = r.straight ? .invalid : CMTime(seconds: s.e + 0.05, preferredTimescale: 600)
            let from = at ?? s.s
            resumeAt = nil
            midSentence = true
            set(.playing)
            seekTo(from) { [weak self] in
                guard let self, self.token == tok, self.state == .playing else { return }
                self.player.defaultRate = self.req?.rate ?? 1
                self.player.play()
            }
            return
        }
        say(tok)
    }

    /// One sentence in the server voice: made ahead when possible, a line while it is being made, else the iPhone's voice.
    private func say(_ tok: Int) {
        guard let r = req else { return }
        let i = index, text = r.texts[i]
        if let off = serverVoiceOff {
            midSentence = true
            note = off
            set(.playing)
            speech.say(text, voice: r.voice, rate: r.rate, token: tok)
            return
        }
        for k in [i + 1, i + 2] where k < r.texts.count { tts.prefetch(text: r.texts[k], voice: r.voice, pack: r.pack, csrf: r.csrf) }
        if !tts.ready(text: text, voice: r.voice, pack: r.pack) {
            noteTask = Task { [weak self] in
                try? await Task.sleep(for: .milliseconds(400))
                guard let self, !Task.isCancelled, self.token == tok, self.req != nil else { return }
                self.note = "正在准备朗读第 \(i + 1) 句…"
                self.set(.waiting)
            }
        }
        holdBackground()  // making a sentence may take a few seconds while the screen is locked
        Task { [weak self] in
            guard let self else { return }
            var file: URL?
            var why = ""
            do { file = try await self.tts.file(text: text, voice: r.voice, pack: r.pack, csrf: r.csrf) } catch {
                why = TTSFetcher.reason(error)
                if TTSFetcher.refused(error) { self.serverVoiceOff = why }
            }
            guard self.token == tok, self.req != nil, self.state != .paused else { return }
            self.noteTask?.cancel()  // this sentence's 「正在准备…」, never a newer one's
            self.midSentence = true
            if let file {
                let item = AVPlayerItem(url: file)
                item.audioTimePitchAlgorithm = .timeDomain
                self.watch(item)  // a file AVFoundation cannot open: the iPhone's voice for it (itemFailed)
                self.player.replaceCurrentItem(with: item)
                self.player.defaultRate = r.rate
                self.note = ""
                self.set(.playing)
                self.player.play()
            } else {
                self.note = why
                self.set(.playing)
                self.speech.say(text, voice: r.voice, rate: r.rate, token: tok)
            }
            self.releaseBackground()
        }
    }

    private var currentItem: ObjectIdentifier? { player.currentItem.map(ObjectIdentifier.init) }

    /// Sound actually coming out, or the player waiting for the network (the start of a recording, a weak line).
    private func controlStatus(_ s: AVPlayer.TimeControlStatus) {
        guard req != nil, midSentence else { return }
        switch s {
        case .waitingToPlayAtSpecifiedRate:  // every start passes here for a moment: only a real wait (0.6 s) is shown
            guard state == .playing, waitTask == nil else { return }
            waitTask = Task { [weak self] in
                try? await Task.sleep(for: .milliseconds(600))
                guard let self, !Task.isCancelled else { return }
                self.waitTask = nil
                guard self.state == .playing, self.midSentence, self.player.timeControlStatus == .waitingToPlayAtSpecifiedRate else { return }
                self.loading = true
                self.note = "正在加载录音…"
                self.set(.waiting)
            }
        case .playing:
            waitTask?.cancel()
            waitTask = nil
            if state == .waiting && loading {
                loading = false
                note = ""
                set(.playing)
            }
        default:
            break
        }
    }

    private func itemEnded(_ item: ObjectIdentifier?) {
        guard let r = req, let item, item == currentItem, state == .playing else { return }
        midSentence = false
        if r.straight { finish(); return }
        after()
    }

    private func speechDone(_ tok: Int) {
        guard tok == token, req != nil, state == .playing else { return }
        midSentence = false
        after()
    }

    /// One sentence said: again (复读), or the next one after its pause.
    private func after() {
        guard let r = req else { return }
        let said = index  // the pause after a sentence is that sentence's own (09, 2026-11-25), none after the last
        reps += 1
        if !(r.rep == 0 || reps < r.rep) {
            reps = 0
            index += 1
            if index >= r.count { finish(); return }
            save()
        }
        set(.playing)
        let g = r.gap(said), tok = token
        if g > 0 {
            holdBackground()
            gapTask = Task { [weak self] in
                try? await Task.sleep(for: .milliseconds(g))
                guard let self, !Task.isCancelled, self.token == tok, self.state == .playing else { return }
                self.releaseBackground()
                self.go()
            }
        } else {
            go()
        }
    }

    private func itemFailed(_ item: ObjectIdentifier?) {
        guard let r = req, state != .idle, !altLoading, !dead else { return }  // one failure is reported twice (KVO, notification)
        if let item, item != currentItem { return }
        let t = player.currentTime().seconds
        if let alt = r.alt, !usedAlt, r.src != nil {  // the other line, from the same second
            usedAlt = true
            altLoading = true
            let at = t.isFinite && t > 0 ? t : r.sentences[index].s
            let tok = token
            Task {
                await self.load(alt)
                self.altLoading = false
                guard self.req != nil else { return }
                let from = self.token == tok && r.straight ? at : nil  // moved meanwhile (a step): that sentence's start
                switch self.state {
                case .playing, .waiting: self.go(at: from)
                case .paused:  // 继续 starts the new line there (nothing on it is under way yet)
                    self.midSentence = false
                    self.resumeAt = from
                case .idle: break
                }
            }
            return
        }
        if r.src == nil, state == .playing || state == .waiting {  // a server-voice file that would not play: the iPhone's voice
            note = "这句自然人声放不出来，先用 iPhone 自带的声音"
            midSentence = true
            set(.playing)
            speech.say(r.texts[index], voice: r.voice, rate: r.rate, token: token)
            return
        }
        guard r.src != nil else { return }
        note = "录音没加载出来，网络好一点再点继续"
        if r.straight, t.isFinite, t > 0 { resumeAt = t }
        dead = true
        midSentence = false
        token += 1
        player.pause()
        lastWhy = .error
        set(.paused, why: .error)
        save()
    }

    private func finish() {
        guard let r = req else { return }
        store.ended(r.key)  // progress(key) says so: a page loaded again meanwhile clears its 「从第 N 句继续」
        stopNow(save: false, why: .ended)
    }

    private func stopNow(save keep: Bool, why: Why?) {
        guard let r = req else { return }
        if r.straight, let i = Self.sentence(at: player.currentTime().seconds, in: r.sentences) { index = i }
        if keep { save(time: r.straight ? player.currentTime().seconds : nil) }
        token += 1
        gapTask?.cancel()
        noteTask?.cancel()
        player.pause()
        player.replaceCurrentItem(with: nil)
        statusWatch = nil
        speech.stop()
        req = nil
        midSentence = false
        dead = false
        altLoading = false
        resumeAt = nil
        resumeAfterInterruption = false
        state = .idle
        note = ""
        NowPlaying.clear()
        releaseBackground()
        AudioSessionManager.shared.deactivate()
        if let why { emit?("audio", ["key": r.key, "state": "idle", "i": index, "n": r.count, "why": why.rawValue, "note": ""]) }
    }

    // MARK: the page, the lock screen, the progress kept

    private func set(_ s: State, why: Why? = nil) {
        state = s
        guard let r = req else { return }
        let t = r.src != nil ? player.currentTime().seconds.finiteOr(0) : nil
        NowPlaying.show(title: r.title, i: index, n: r.count, elapsed: r.straight ? t : nil,
                        duration: r.straight ? r.sentences.last?.e : nil, rate: r.rate, playing: s == .playing || s == .waiting)
        var o = snapshot()
        if let why { o["why"] = why.rawValue }
        emit?("audio", o)
    }

    private func tick(_ t: Double) {
        guard let r = req, state == .playing, r.src != nil, t.isFinite, seeking == 0 else { return }
        if r.straight, let i = Self.sentence(at: t, in: r.sentences), i != index {
            index = i
            save(time: t)
            set(.playing)
        }
        if UIApplication.shared.applicationState == .active {
            emit?("audio-tick", ["key": r.key, "i": index, "t": t, "at": Date().timeIntervalSince1970 * 1000, "rate": r.rate])
        }
    }

    private func save(time: Double? = nil) {
        guard let r = req else { return }
        store.set(r.key, i: index, t: time ?? (r.straight ? player.currentTime().seconds.finiteOr(0) : nil))
    }

    // MARK: calls, Siri, alarms, headphones, the media services

    private func interruption(_ type: UInt?, _ options: UInt, _ reason: UInt?) {
        guard let type, let t = AVAudioSession.InterruptionType(rawValue: type) else { return }
        switch t {
        case .began:
            if reason == 1 { return }  // AVAudioSession.InterruptionReason.appWasSuspended: not a real interruption
            if state == .playing || state == .waiting { pause(why: .interrupted) }
        case .ended:
            let go = AVAudioSession.InterruptionOptions(rawValue: options).contains(.shouldResume)
            if go, resumeAfterInterruption, state == .paused, lastWhy == .interrupted { resume(why: .interrupted) }
            resumeAfterInterruption = false
        @unknown default:
            break
        }
    }

    private func servicesReset() {
        let wasOn = state != .idle
        let t = player.currentTime().seconds
        if wasOn { pause(why: .error) }
        if let o = timeObserver { player.removeTimeObserver(o) }
        controlWatch = nil
        player = AVPlayer()
        setUpPlayer()
        AudioSessionManager.shared.prepare()
        if wasOn, let r = req {
            midSentence = false
            if r.straight, t.isFinite, t > 0 { resumeAt = t }
            if let src = r.src { Task { await self.load(src) } }
        }
    }

    private func holdBackground() {
        guard background == .invalid else { return }
        background = UIApplication.shared.beginBackgroundTask(withName: "long-text") { [weak self] in
            MainActor.assumeIsolated { self?.releaseBackground() }
        }
    }

    private func releaseBackground() {
        guard background != .invalid else { return }
        UIApplication.shared.endBackgroundTask(background)
        background = .invalid
    }

    // MARK: sentence lookup (as NAR.locate on the page)

    /// The sentence playing at t, or nil between two sentences.
    static func sentence(at t: Double, in ss: [Span]) -> Int? {
        for (i, s) in ss.enumerated() {
            if t >= s.s - 0.02 && t < s.e + 0.25 { return i }
            if t < s.s { break }
        }
        return nil
    }

    /// The first sentence that starts after t (t in a pause between two).
    static func sentenceAfter(_ t: Double, in ss: [Span]) -> Int? { ss.firstIndex { $0.s >= t } }
}

extension Double {
    func finiteOr(_ v: Double) -> Double { isFinite ? self : v }
}
