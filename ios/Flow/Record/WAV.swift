import Foundation

/// 16 kHz mono 16-bit PCM WAV, the format the pronunciation line expects (PR #125, FLOW_SAY_WAV). AVAudioRecorder may
/// put extra chunks (FLLR padding) before the samples; what goes to the server is the plain 44-byte-header form.
enum WAV {
    static let sampleRate = 16_000

    /// The plain RIFF/WAVE form of a WAV file (fmt + data only), or nil when d is not a WAV with samples.
    static func canonical(_ input: Data) -> Data? {
        let d = Data(input)  // indices from 0
        guard d.count >= 12, d.prefix(4) == Data("RIFF".utf8), d.subdata(in: 8..<12) == Data("WAVE".utf8) else { return nil }
        var p = 12
        var fmt: Data?
        var pcm: Data?
        while p + 8 <= d.count {
            let id = String(decoding: d.subdata(in: p..<p + 4), as: UTF8.self)
            let size = Int(u32(d, p + 4))
            let start = p + 8
            let end = min(d.count, start + size)  // a header not finished (the recording was cut): what is there
            if id == "fmt " { fmt = d.subdata(in: start..<end) } else if id == "data" { pcm = d.subdata(in: start..<end) }
            if id == "data" && size > d.count - start { break }
            p = start + size + (size & 1)
        }
        guard let fmt, fmt.count >= 16, let pcm, !pcm.isEmpty else { return nil }
        var out = Data()
        out.append(Data("RIFF".utf8)); out.append(le32(UInt32(36 + pcm.count)))
        out.append(Data("WAVE".utf8))
        out.append(Data("fmt ".utf8)); out.append(le32(16)); out.append(fmt.prefix(16))
        out.append(Data("data".utf8)); out.append(le32(UInt32(pcm.count)))
        out.append(pcm)
        return out
    }

    /// What a WAV says about itself: sample rate, channels, bits per sample, seconds of sound.
    static func describe(_ input: Data) -> (rate: Int, channels: Int, bits: Int, seconds: Double)? {
        guard let w = canonical(input) else { return nil }
        let channels = Int(u16(w, 22)), rate = Int(u32(w, 24)), bits = Int(u16(w, 34)), bytes = Int(u32(w, 40))
        guard rate > 0, channels > 0, bits > 0 else { return nil }
        return (rate, channels, bits, Double(bytes) / Double(rate * channels * bits / 8))
    }

    static func le32(_ v: UInt32) -> Data { withUnsafeBytes(of: v.littleEndian) { Data($0) } }

    private static func u32(_ d: Data, _ at: Int) -> UInt32 {
        guard at + 4 <= d.count else { return 0 }
        return d.subdata(in: at..<at + 4).withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) }.littleEndian
    }

    private static func u16(_ d: Data, _ at: Int) -> UInt16 {
        guard at + 2 <= d.count else { return 0 }
        return d.subdata(in: at..<at + 2).withUnsafeBytes { $0.loadUnaligned(as: UInt16.self) }.littleEndian
    }
}
