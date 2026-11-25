import { audio } from '@kit.AudioKit';
import { media } from '@kit.MediaKit';
import { fileIo } from '@kit.CoreFileKit';
import { util } from '@kit.ArkTS';
import { AppState } from '../common/AppState';
import { FlowAudio } from '../audio/FlowAudio';
import { Wav } from './Wav';

/**
 * FlowApp.rec (docs/native-bridge.md §4): the microphone, only while the learner looks at the app. WAV through
 * AudioCapturer (voice recognition source), m4a (AAC 16 kHz) through AVRecorder for takes over 40 seconds. A call or the
 * app going to the background cuts it: what was recorded is kept, stop() still has it. The app's long playback pauses
 * while recording (why = other).
 */
export class Recorder {
  private static token: number = 0;
  private static wanted: number = 0;
  private static capturer: audio.AudioCapturer | undefined = undefined;
  private static avr: media.AVRecorder | undefined = undefined;
  private static file: string = '';
  private static fd: number = -1;
  private static chunks: ArrayBuffer[] = [];
  private static format: string = 'wav';
  private static started: number = 0;
  private static ended: number = 0;
  private static cut: boolean = false;
  private static state: string = 'idle';   // idle | recording | done
  private static timer: number = -1;

  static init(): void {
    AppState.onBackground.push(() => {
      if (Recorder.state === 'recording') {
        Recorder.finish(true);
      }
    });
  }

  /** A start is asked for (the permission may still be asked): a stop before it starts means it does not start. */
  static begin(): number {
    Recorder.wanted = ++Recorder.token;
    return Recorder.wanted;
  }

  static stillWanted(t: number): boolean {
    return Recorder.wanted === t;
  }

  static async start(max: number, format: string): Promise<Object> {
    if (Recorder.state === 'recording') {
      const busy: Record<string, Object> = { 'ok': false, 'why': 'busy', 'message': '正在录音' };
      return busy;
    }
    const secs = Math.max(1, Math.min(600, Math.floor(max)));
    const fmt = format === 'm4a' || format === 'wav' ? format : (secs > 40 ? 'm4a' : 'wav');
    FlowAudio.pause('other');
    Recorder.chunks = [];
    Recorder.cut = false;
    Recorder.format = fmt;
    try {
      if (fmt === 'wav') {
        await Recorder.startWav();
      } else {
        await Recorder.startM4a();
      }
    } catch (e) {
      AppState.warn('rec start: ' + JSON.stringify(e));
      await Recorder.release();
      const err: Record<string, Object> = { 'ok': false, 'why': 'error', 'message': '录音没能开始' };
      return err;
    }
    Recorder.state = 'recording';
    Recorder.started = Date.now();
    Recorder.ended = 0;
    Recorder.timer = setTimeout(() => {
      if (Recorder.state === 'recording') {
        Recorder.finish(false);
      }
    }, secs * 1000);
    AppState.emit('rec', { 'state': 'recording', 'ms': 0 } as Record<string, Object>);
    const ok: Record<string, Object> = { 'ok': true, 'format': fmt, 'max': secs };
    return ok;
  }

  private static async startWav(): Promise<void> {
    const options: audio.AudioCapturerOptions = {
      streamInfo: {
        samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_16000,
        channels: audio.AudioChannel.CHANNEL_1,
        sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW,
      },
      capturerInfo: { source: audio.SourceType.SOURCE_TYPE_VOICE_RECOGNITION, capturerFlags: 0 },
    };
    const c = await audio.createAudioCapturer(options);
    Recorder.capturer = c;
    c.on('readData', (buf: ArrayBuffer) => {
      if (Recorder.state === 'recording') {
        Recorder.chunks.push(buf.slice(0));
      }
    });
    c.on('audioInterrupt', (ev: audio.InterruptEvent) => {
      if (ev.forceType === audio.InterruptForceType.INTERRUPT_FORCE && Recorder.state === 'recording') {
        Recorder.finish(true);  // a call: cut, keep what there is
      }
    });
    await c.start();
  }

  private static async startM4a(): Promise<void> {
    const ctx = AppState.context;
    if (!ctx) {
      throw new Error('no context');
    }
    Recorder.file = ctx.cacheDir + '/rec-' + Date.now() + '.m4a';
    const f = fileIo.openSync(Recorder.file, fileIo.OpenMode.CREATE | fileIo.OpenMode.READ_WRITE | fileIo.OpenMode.TRUNC);
    Recorder.fd = f.fd;
    const r = await media.createAVRecorder();
    Recorder.avr = r;
    r.on('audioInterrupt', (ev: audio.InterruptEvent) => {
      if (ev.forceType === audio.InterruptForceType.INTERRUPT_FORCE && Recorder.state === 'recording') {
        Recorder.finish(true);
      }
    });
    const config: media.AVRecorderConfig = {
      audioSourceType: media.AudioSourceType.AUDIO_SOURCE_TYPE_MIC,
      profile: {
        audioBitrate: 32000,
        audioChannels: 1,
        audioCodec: media.CodecMimeType.AUDIO_AAC,
        audioSampleRate: 16000,
        fileFormat: media.ContainerFormatType.CFT_MPEG_4A,
      },
      url: 'fd://' + Recorder.fd,
    };
    await r.prepare(config);
    await r.start();
  }

  /** Stopped by the time limit (done) or by a call or the background (cut); stop() takes the result. */
  private static async finish(cut: boolean): Promise<void> {
    if (Recorder.state !== 'recording') {
      return;
    }
    Recorder.state = 'done';
    Recorder.cut = cut;
    Recorder.ended = Date.now();
    clearTimeout(Recorder.timer);
    try {
      if (Recorder.capturer) {
        await Recorder.capturer.stop();
      }
      if (Recorder.avr) {
        await Recorder.avr.stop();
      }
    } catch (e) {
      AppState.warn('rec stop: ' + JSON.stringify(e));
    }
    AppState.emit('rec', { 'state': cut ? 'cut' : 'done', 'ms': Recorder.ended - Recorder.started } as Record<string, Object>);
  }

  /** → {ok, mime_type, data (base64), ms, bytes, cut}; the upload takes only mime_type and data. */
  static async stop(): Promise<Object> {
    Recorder.wanted = 0;
    if (Recorder.state === 'idle') {
      const none: Record<string, Object> = { 'ok': false, 'why': 'none' };
      return none;
    }
    if (Recorder.state === 'recording') {
      await Recorder.finish(false);
    }
    let bytes: Uint8Array;
    let mime: string;
    if (Recorder.format === 'wav') {
      bytes = Wav.file(Recorder.chunks);
      mime = 'audio/wav';
    } else {
      bytes = Recorder.readFile();
      mime = 'audio/mp4';
    }
    const ms = (Recorder.ended || Date.now()) - Recorder.started;
    const cut = Recorder.cut;
    await Recorder.release();
    const data = new util.Base64Helper().encodeToStringSync(bytes);
    const out: Record<string, Object> = { 'ok': true, 'mime_type': mime, 'data': data, 'ms': ms, 'bytes': bytes.length, 'cut': cut };
    return out;
  }

  static async cancel(): Promise<void> {
    Recorder.wanted = 0;
    if (Recorder.state === 'recording') {
      Recorder.state = 'done';
      clearTimeout(Recorder.timer);
      try {
        if (Recorder.capturer) {
          await Recorder.capturer.stop();
        }
        if (Recorder.avr) {
          await Recorder.avr.stop();
        }
      } catch (e) {
        // already stopped
      }
    }
    await Recorder.release();
  }

  private static readFile(): Uint8Array {
    try {
      const st = fileIo.statSync(Recorder.file);
      const f = fileIo.openSync(Recorder.file, fileIo.OpenMode.READ_ONLY);
      const buf = new ArrayBuffer(st.size);
      fileIo.readSync(f.fd, buf);
      fileIo.closeSync(f);
      return new Uint8Array(buf);
    } catch (e) {
      return new Uint8Array(0);
    }
  }

  private static async release(): Promise<void> {
    try {
      if (Recorder.capturer) {
        await Recorder.capturer.release();
      }
      if (Recorder.avr) {
        await Recorder.avr.release();
      }
    } catch (e) {
      // released already
    }
    Recorder.capturer = undefined;
    Recorder.avr = undefined;
    if (Recorder.fd >= 0) {
      try {
        fileIo.closeSync(Recorder.fd);
      } catch (e) {
        // closed
      }
      Recorder.fd = -1;
    }
    if (Recorder.file) {
      try {
        fileIo.unlinkSync(Recorder.file);
      } catch (e) {
        // gone
      }
      Recorder.file = '';
    }
    Recorder.chunks = [];
    Recorder.state = 'idle';
  }
}
