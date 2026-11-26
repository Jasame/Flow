/** 16 kHz, mono, 16-bit PCM → a WAV file (44-byte header), the same as iOS, Android and the server's FLOW_SAY_WAV. */
export class Wav {
  static readonly RATE: number = 16000;

  static header(dataBytes: number): Uint8Array {
    const b = new ArrayBuffer(44);
    const v = new DataView(b);
    const str = (o: number, s: string) => {
      for (let i = 0; i < s.length; i++) {
        v.setUint8(o + i, s.charCodeAt(i));
      }
    };
    str(0, 'RIFF');
    v.setUint32(4, 36 + dataBytes, true);
    str(8, 'WAVE');
    str(12, 'fmt ');
    v.setUint32(16, 16, true);
    v.setUint16(20, 1, true);             // PCM
    v.setUint16(22, 1, true);             // mono
    v.setUint32(24, Wav.RATE, true);
    v.setUint32(28, Wav.RATE * 2, true);  // bytes a second
    v.setUint16(32, 2, true);
    v.setUint16(34, 16, true);
    str(36, 'data');
    v.setUint32(40, dataBytes, true);
    return new Uint8Array(b);
  }

  static file(chunks: ArrayBuffer[]): Uint8Array {
    let n = 0;
    chunks.forEach((c: ArrayBuffer) => {
      n += c.byteLength;
    });
    const out = new Uint8Array(44 + n);
    out.set(Wav.header(n), 0);
    let o = 44;
    chunks.forEach((c: ArrayBuffer) => {
      out.set(new Uint8Array(c), o);
      o += c.byteLength;
    });
    return out;
  }
}
