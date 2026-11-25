import { media } from '@kit.MediaKit';
import { audio } from '@kit.AudioKit';
import { avSession } from '@kit.AVSessionKit';
import { backgroundTaskManager } from '@kit.BackgroundTasksKit';
import { bundleManager, wantAgent, WantAgent } from '@kit.AbilityKit';
import { webview } from '@kit.ArkWeb';
import { http } from '@kit.NetworkKit';
import { connection } from '@kit.NetworkKit';
import { preferences } from '@kit.ArkData';
import { AppState } from '../common/AppState';
import { Site } from '../common/Site';
import { Sentences, Span } from './Sentences';

enum Mode { REC, TTS }

class Job {
  key: string = '';
  title: string = '';
  mode: Mode = Mode.REC;
  src: string = '';
  spans: Span[] = [];
  texts: string[] = [];
  voice: string = 'us-f';
  pack: string = '';
  loop: boolean = false;
  rep: number = 1;
  gaps: number[] | null = null;
  gap: number = 0;
  rate: number = 1;
  csrf: string = '';
  alt: string = '';

  n(): number {
    return this.mode === Mode.REC ? this.spans.length : this.texts.length;
  }

  /** the pause after sentence i, each time it is read (复读 too) */
  gapAfter(i: number): number {
    return this.gaps !== null && i < this.gaps.length ? this.gaps[i] : this.gap;
  }

  /** sentence by sentence (and so 复读 and pauses apply): always without a recording, with one when asked */
  bySentence(): boolean {
    return this.mode === Mode.TTS || this.loop;
  }
}

/** Why the server could not give a sentence: {code, server}, as the page's SV gives it (SV.why writes the line). */
class Failure extends Error {
  code: string;
  server: string;

  constructor(code: string, server: string) {
    super(code);
    this.code = code;
    this.server = server;
  }
}

/**
 * A whole text read aloud (听's 播放全文, 读's 伴读), played by the app instead of the page: docs/native-bridge.md §3,
 * FlowApp.audio. AVPlayer plays it; an AVSession puts 「标题」 and 「AI 朗读 · 第 3 / 20 句」 with play, pause, previous and
 * next sentence on the lock screen and in the control centre (播控中心); a continuous task (AUDIO_PLAYBACK) keeps it
 * going with the screen off and the app in the background. A call pauses it and it goes on afterwards when the system
 * says it may; another app's sound pauses it; it pauses when the headphones come out.
 *
 * As on the page (LONG): a recording (Kokoro: one file and its sentences [s, e], straight through or sentence by
 * sentence), or `items` [{text, url}] sentence by sentence, a url the page does not know yet asked of the server
 * (POST /api/next/tts, the next two while one plays) and told back (`audio-made`). There is no phone's own voice here
 * (HarmonyOS's is Core Speech Kit, not used: C4 plan §5): a sentence the server cannot give pauses the text
 * (why = error) with `fail` {code, server}; 继续 asks again.
 */
export class FlowAudio {
  private static player: media.AVPlayer | undefined = undefined;
  private static session: avSession.AVSession | undefined = undefined;
  private static running: boolean = false;     // the continuous task is on
  private static job: Job | null = null;
  private static i: number = 0;
  private static state: string = 'idle';
  private static said: number = 0;
  private static tok: number = 0;              // a new token cancels what is pending: a pause, a gap, a sentence being made
  private static onAlt: boolean = false;
  private static reload: boolean = false;
  private static resumeOnGain: boolean = false;
  private static fail: Record<string, Object> | null = null;
  private static lastKey: string = '';
  private static stopAtEnd: number = -1;
  private static tickTimer: number = -1;
  private static tickN: number = 0;
  private static gapTimer: number = -1;
  private static waitTimer: number = -1;
  private static urls: Map<string, string> = new Map<string, string>();
  private static serverOff: string = '';
  private static loadedUrl: string = '';
  private static pendingSeekMs: number = -1;
  private static media: Record<string, Object> | null = null;
  /** The page is on screen: ticks are sent only then. */
  static visible: boolean = true;

  static init(): void {
    AppState.onForeground.push(() => {
      FlowAudio.visible = true;
      FlowAudio.replay();
    });
    AppState.onBackground.push(() => {
      FlowAudio.visible = false;
      FlowAudio.save();
    });
  }

  // ------------------------------------------------------------------ the page's commands

  static async play(o: Record<string, Object>): Promise<Object> {
    const j = new Job();
    j.key = FlowAudio.str(o['key']);
    j.title = FlowAudio.str(o['title']) || '朗读';
    j.src = FlowAudio.str(o['src']);
    const sentences = o['sentences'];
    if (Array.isArray(sentences)) {
      (sentences as Object[]).forEach((x: Object) => {
        if (Array.isArray(x)) {
          const a = x as number[];
          j.spans.push(new Span(Number(a[0]), Number(a[1])));
        } else if (x !== null && typeof x === 'object') {
          const r = x as Record<string, Object>;
          j.spans.push(new Span(Number(r['s']), Number(r['e'])));
        }
      });
    }
    const items = o['items'];
    const knownUrls: string[] = [];
    if (Array.isArray(items)) {
      (items as Object[]).forEach((x: Object) => {
        const r = (x !== null && typeof x === 'object') ? x as Record<string, Object> : {} as Record<string, Object>;
        j.texts.push(FlowAudio.str(r['text']));
        const u = FlowAudio.str(r['url']);
        knownUrls.push(u && u !== 'null' ? u : '');
      });
    } else if (Array.isArray(o['texts'])) {
      (o['texts'] as Object[]).forEach((x: Object) => {
        j.texts.push(String(x));
        knownUrls.push('');
      });
    }
    if (j.src && j.spans.length > 0) {
      j.mode = Mode.REC;
    } else if (j.texts.length > 0) {
      j.mode = Mode.TTS;
    } else {
      return FlowAudio.failed('bad_args', '这篇没有能朗读的句子');
    }
    j.voice = FlowAudio.str(o['voice']) || 'us-f';
    j.pack = FlowAudio.str(o['pack']);
    j.loop = o['loop'] === true;
    j.rep = Math.max(0, FlowAudio.num(o['rep'], 1));
    if (Array.isArray(o['gap'])) {
      j.gaps = (o['gap'] as Object[]).map((g: Object) => Number(g) || 0);
    } else {
      j.gap = FlowAudio.num(o['gap'], 0);
    }
    j.rate = FlowAudio.clampRate(FlowAudio.num(o['rate'], 1));
    j.csrf = FlowAudio.str(o['csrf']);
    j.alt = FlowAudio.str(o['alt']);

    await FlowAudio.halt();  // another text: where it was is kept
    FlowAudio.job = j;
    FlowAudio.tok++;
    FlowAudio.said = 0;
    FlowAudio.onAlt = false;
    FlowAudio.reload = false;
    FlowAudio.resumeOnGain = false;
    FlowAudio.fail = null;
    FlowAudio.serverOff = '';
    knownUrls.forEach((u: string, k: number) => {
      if (u) {
        FlowAudio.urls.set(FlowAudio.urlKey(j, k), u);
      }
    });
    FlowAudio.i = Math.min(Math.max(0, j.n() - 1), Math.max(0, FlowAudio.num(o['from'], 0)));
    let at = -1;
    if (j.mode === Mode.REC && typeof o['at'] === 'number') {
      at = o['at'] as number;
      const si = Sentences.locate(j.spans, at);
      if (si >= 0) {
        FlowAudio.i = si;
      }
    }
    await FlowAudio.startSession();
    FlowAudio.state = j.mode === Mode.REC ? 'playing' : 'waiting';
    if (j.mode === Mode.REC) {
      await FlowAudio.playRecording(at >= 0 ? at : j.spans[FlowAudio.i].s);
    } else {
      FlowAudio.sentence();
    }
    FlowAudio.changed('');
    FlowAudio.startTicks();
    return FlowAudio.snapshot(true);
  }

  static async pause(why: string): Promise<Object> {
    const j = FlowAudio.job;
    if (!j || FlowAudio.state === 'paused') {
      return FlowAudio.snapshot(true);
    }
    FlowAudio.tok++;
    FlowAudio.clearTimers();
    const p = FlowAudio.player;
    try {
      if (p && j.mode === Mode.REC) {
        await p.pause();  // stays at that second: 继续 goes on from it
      } else if (p) {
        await p.stop();   // 继续: from the sentence's start
      }
    } catch (e) {
      // not playing yet
    }
    FlowAudio.state = 'paused';
    FlowAudio.save();
    FlowAudio.stopTicks();
    if (why !== 'interrupted') {
      FlowAudio.resumeOnGain = false;
    }
    FlowAudio.changed(why);
    return FlowAudio.snapshot(true);
  }

  static async resume(): Promise<Object> {
    const j = FlowAudio.job;
    if (!j) {
      const o = FlowAudio.snapshot(false);
      o['why'] = 'idle';
      return o;
    }
    if (FlowAudio.state !== 'paused') {
      return FlowAudio.snapshot(true);
    }
    FlowAudio.resumeOnGain = false;
    FlowAudio.tok++;
    FlowAudio.state = 'playing';
    await FlowAudio.startSession();
    if (j.mode === Mode.REC) {
      const p = FlowAudio.player;
      if (!FlowAudio.reload && p && (p.state === 'paused' || p.state === 'prepared')) {
        if (j.bySentence()) {
          FlowAudio.stopAtEnd = j.spans[FlowAudio.i].e;
        }
        await p.play();
      } else {
        const from = FlowAudio.reload && p ? p.currentTime / 1000 : j.spans[FlowAudio.i].s;
        if (FlowAudio.reload) {
          FlowAudio.onAlt = false;  // this server first again, then the other line
        }
        FlowAudio.reload = false;
        await FlowAudio.playRecording(Math.max(from, j.bySentence() ? j.spans[FlowAudio.i].s : 0));
      }
    } else {
      FlowAudio.sentence();
    }
    FlowAudio.changed('');
    FlowAudio.startTicks();
    return FlowAudio.snapshot(true);
  }

  /** Stop reading (✕, leaving the page, another text): where it was is kept. */
  static async stop(): Promise<Object> {
    if (!FlowAudio.job) {
      return FlowAudio.snapshot(true);
    }
    await FlowAudio.halt();
    FlowAudio.changed('user');
    return FlowAudio.snapshot(true);
  }

  /** Previous / next sentence (the page, the lock screen, the headphones). */
  static async step(d: number): Promise<Object> {
    const j = FlowAudio.job;
    if (!j) {
      return FlowAudio.snapshot(true);
    }
    if (j.mode === Mode.REC && !j.loop) {
      const p = FlowAudio.player;
      if (!p) {
        return FlowAudio.snapshot(true);
      }
      const target = Sentences.stepTarget(j.spans, p.currentTime / 1000, d);
      p.seek(Math.round(j.spans[target].s * 1000), media.SeekMode.SEEK_CLOSEST);
      FlowAudio.i = target;
      FlowAudio.save();
      FlowAudio.changed('');
      return FlowAudio.snapshot(true);
    }
    return FlowAudio.seek(FlowAudio.i + d);
  }

  /** To sentence `to` (and play it, as LONG.step does). */
  static async seek(to: number): Promise<Object> {
    const j = FlowAudio.job;
    if (!j) {
      return FlowAudio.snapshot(true);
    }
    FlowAudio.tok++;
    FlowAudio.clearTimers();
    FlowAudio.i = Math.min(j.n() - 1, Math.max(0, Math.floor(to)));
    FlowAudio.said = 0;
    if (j.mode === Mode.REC && !j.loop) {
      if (FlowAudio.player) {
        FlowAudio.player.seek(Math.round(j.spans[FlowAudio.i].s * 1000), media.SeekMode.SEEK_CLOSEST);
      }
      FlowAudio.save();
      FlowAudio.changed('');
      return FlowAudio.snapshot(true);
    }
    if (FlowAudio.state === 'paused') {
      await FlowAudio.startSession();
    }
    FlowAudio.state = 'playing';
    await FlowAudio.go();
    FlowAudio.save();
    FlowAudio.changed('');
    FlowAudio.startTicks();
    return FlowAudio.snapshot(true);
  }

  /** 语速、复读 changed while it plays: {rate, rep, gap}, at once. */
  static async set(o: Record<string, Object>): Promise<Object> {
    const j = FlowAudio.job;
    if (!j) {
      return FlowAudio.snapshot(true);
    }
    if (typeof o['rep'] === 'number') {
      j.rep = Math.max(0, o['rep'] as number);
    }
    if (Array.isArray(o['gap'])) {
      j.gaps = (o['gap'] as Object[]).map((g: Object) => Number(g) || 0);
      j.gap = 0;
    } else if (typeof o['gap'] === 'number') {
      j.gaps = null;
      j.gap = o['gap'] as number;
    }
    if (typeof o['rate'] === 'number') {
      j.rate = FlowAudio.clampRate(o['rate'] as number);
      FlowAudio.applyRate();
    }
    return FlowAudio.snapshot(true);
  }

  /** state() → {key, state, i, n, t, title, rate} */
  static stateJson(): Record<string, Object> {
    const j = FlowAudio.job;
    const o: Record<string, Object> = {
      'key': j ? j.key : '', 'state': FlowAudio.state, 'i': j ? FlowAudio.i : -1, 'n': j ? j.n() : 0,
      't': FlowAudio.seconds(), 'title': j ? j.title : '', 'rate': j ? j.rate : 1,
    };
    return o;
  }

  private static snapshot(ok: boolean): Record<string, Object> {
    const o = FlowAudio.stateJson();
    o['ok'] = ok;
    return o;
  }

  /** progress(key) → {i, t, at}, {ended: true, at}, or null */
  static async progressJson(key: string): Promise<Object | null> {
    const v = key ? FlowAudio.progressAll().get(key) : undefined;
    return v !== undefined ? v : null;
  }

  /** The page loaded again, or came back on screen: what is going on now (why = state). */
  static replay(): void {
    const d = FlowAudio.stateJson();
    d['key'] = FlowAudio.job ? FlowAudio.job.key : FlowAudio.lastKey;
    d['why'] = 'state';
    AppState.emit('audio', d);
  }

  // ------------------------------------------------------------------ making the sound

  private static async getPlayer(): Promise<media.AVPlayer> {
    if (FlowAudio.player) {
      return FlowAudio.player;
    }
    const p = await media.createAVPlayer();
    p.on('stateChange', (s: string) => FlowAudio.onState(s));
    p.on('error', (e: Error) => FlowAudio.onError(e));
    p.on('audioInterrupt', (ev: audio.InterruptEvent) => FlowAudio.onInterrupt(ev));
    p.on('audioOutputDeviceChangeWithInfo', (info: audio.AudioStreamDeviceChangeInfo) => {
      if (info.changeReason === audio.AudioStreamDeviceChangeReason.REASON_OLD_DEVICE_UNAVAILABLE &&
        (FlowAudio.state === 'playing' || FlowAudio.state === 'waiting')) {
        FlowAudio.pause('route');  // the headphones came out
      }
    });
    FlowAudio.player = p;
    return p;
  }

  /** Load one file (a recording, or one sentence of the server voice) and play it from fromMs. */
  private static async load(u: string, fromMs: number): Promise<void> {
    const p = await FlowAudio.getPlayer();
    if (p.state !== 'idle') {
      await p.reset();
    }
    FlowAudio.loadedUrl = u;
    FlowAudio.pendingSeekMs = fromMs > 0 ? fromMs : -1;
    const headers: Record<string, string> = { 'User-Agent': Site.userAgent };
    // the login cookie goes with this site's own files only (/audio/own/ needs it), never to the media domain
    if (Site.isOwn(u)) {
      try {
        const c = webview.WebCookieManager.fetchCookieSync(u);
        if (c) {
          headers['Cookie'] = c;
        }
      } catch (e) {
        // a guest
      }
    }
    const src = media.createMediaSourceWithUrl(u, headers);
    await p.setMediaSource(src, { preferredBufferDuration: 20 } as media.PlaybackStrategy);
  }

  private static onState(s: string): void {
    const p = FlowAudio.player;
    const j = FlowAudio.job;
    if (!p) {
      return;
    }
    switch (s) {
      case 'initialized':
        p.audioRendererInfo = { usage: audio.StreamUsage.STREAM_USAGE_AUDIOBOOK, rendererFlags: 0 };
        p.prepare().catch((e: Error) => FlowAudio.onError(e));
        break;
      case 'prepared':
        if (Site.mute) {
          p.setVolume(0);  // tests make no sound (docs/native-bridge.md §9)
        }
        FlowAudio.applyRate();
        if (FlowAudio.pendingSeekMs > 0) {
          p.seek(FlowAudio.pendingSeekMs, media.SeekMode.SEEK_CLOSEST);
          FlowAudio.pendingSeekMs = -1;
        }
        if (FlowAudio.state === 'playing' || FlowAudio.state === 'waiting') {
          p.play().catch((e: Error) => FlowAudio.onError(e));
        }
        break;
      case 'playing':
        if (FlowAudio.state === 'waiting') {
          FlowAudio.state = 'playing';
          FlowAudio.changed('');
        }
        break;
      case 'completed':
        if (!j) {
          return;
        }
        if (j.bySentence()) {
          if (FlowAudio.state === 'playing' || FlowAudio.state === 'waiting') {
            FlowAudio.state = 'playing';
            FlowAudio.sentenceDone();
          }
        } else {
          FlowAudio.finish();
        }
        break;
      default:
        break;
    }
  }

  private static onError(e: Error): void {
    const j = FlowAudio.job;
    if (!j) {
      return;
    }
    AppState.warn('playback error: ' + (e && e.message ? e.message : ''));
    if (j.mode === Mode.REC && !FlowAudio.onAlt && FlowAudio.altUrl(j.src)) {  // the other line, from the same second
      FlowAudio.onAlt = true;
      const t = FlowAudio.player ? FlowAudio.player.currentTime / 1000 : 0;
      FlowAudio.playRecording(t);
      return;
    }
    if (j.mode === Mode.TTS && FlowAudio.state !== 'paused') {
      FlowAudio.noVoice(j, FlowAudio.i, FlowAudio.tok, new Failure('net', ''));
      return;
    }
    // the recording would not load: paused (why = error); 继续 loads it again from where it stopped
    FlowAudio.tok++;
    FlowAudio.clearTimers();
    FlowAudio.reload = true;
    FlowAudio.state = 'paused';
    FlowAudio.save();
    FlowAudio.stopTicks();
    FlowAudio.resumeOnGain = false;
    FlowAudio.changed('error');
  }

  /** A call, a navigation voice, another app: the system says pause, resume or stop (ArkWeb's page sound too). */
  private static onInterrupt(ev: audio.InterruptEvent): void {
    if (ev.hintType === audio.InterruptHint.INTERRUPT_HINT_PAUSE) {
      if (FlowAudio.state === 'playing' || FlowAudio.state === 'waiting') {
        FlowAudio.resumeOnGain = true;
        FlowAudio.pause('interrupted');
      }
    } else if (ev.hintType === audio.InterruptHint.INTERRUPT_HINT_RESUME) {
      if (FlowAudio.resumeOnGain && FlowAudio.state === 'paused') {
        FlowAudio.resumeOnGain = false;
        FlowAudio.resume();
      }
    } else if (ev.hintType === audio.InterruptHint.INTERRUPT_HINT_STOP) {
      FlowAudio.resumeOnGain = false;
      if (FlowAudio.state === 'playing' || FlowAudio.state === 'waiting') {
        FlowAudio.pause('other');
      }
    }
  }

  private static async playRecording(fromSec: number): Promise<void> {
    const j = FlowAudio.job;
    if (!j) {
      return;
    }
    const alt = FlowAudio.onAlt ? FlowAudio.altUrl(j.src) : '';
    const u = alt ? alt : Site.abs(j.src);
    FlowAudio.stopAtEnd = j.bySentence() ? j.spans[FlowAudio.i].e : -1;
    try {
      await FlowAudio.load(u, Math.max(0, Math.round(fromSec * 1000)));
    } catch (e) {
      FlowAudio.onError(e as Error);
    }
  }

  /** Sentence i again, or the one after the pause: a recording seeks, the server voice makes it. */
  private static async go(): Promise<void> {
    const j = FlowAudio.job;
    if (!j) {
      return;
    }
    if (j.mode === Mode.REC) {
      const p = FlowAudio.player;
      FlowAudio.stopAtEnd = j.spans[FlowAudio.i].e;
      if (!p || p.state === 'idle' || p.state === 'error' || p.state === 'released') {
        await FlowAudio.playRecording(j.spans[FlowAudio.i].s);
      } else {
        p.seek(Math.round(j.spans[FlowAudio.i].s * 1000), media.SeekMode.SEEK_CLOSEST);
        await p.play();
      }
    } else {
      FlowAudio.sentence();
    }
  }

  // ---- the server voice, sentence by sentence
  private static urlKey(j: Job, k: number): string {
    return j.voice + '|' + j.pack + '|' + j.texts[k];
  }

  private static async ttsUrl(j: Job, k: number): Promise<string> {
    const known = FlowAudio.urls.get(FlowAudio.urlKey(j, k));
    if (known) {
      return known;
    }
    if (FlowAudio.serverOff) {
      throw new Failure(FlowAudio.serverOff, '');
    }
    const body: Record<string, string> = { 'text': j.texts[k], 'voice': j.voice };
    if (j.pack) {
      body['pack'] = j.pack;
    }
    let a = await AppState.request('/api/next/tts', http.RequestMethod.POST, JSON.stringify(body), j.csrf || undefined)
      .catch(async (): Promise<never> => {
        throw new Failure(await FlowAudio.offline() ? 'offline' : 'net', '');
      });
    const r = a.json();
    const u = typeof r['url'] === 'string' ? r['url'] as string : '';
    if (!a.ok() || !u) {
      const code = typeof r['code'] === 'string' && r['code'] ? r['code'] as string : (a.code >= 500 ? 'gateway' : 'store');
      if (code === 'off' || code === 'cap') {
        FlowAudio.serverOff = code;  // as SV.off on the page: not asked again for this text
      }
      throw new Failure(code, typeof r['error'] === 'string' ? r['error'] as string : '');
    }
    FlowAudio.urls.set(FlowAudio.urlKey(j, k), u);
    AppState.emit('audio-made', { 'key': j.key, 'i': k, 'url': u } as Record<string, Object>);  // into the page's SV
    return u;
  }

  private static async offline(): Promise<boolean> {
    try {
      return !(await connection.hasDefaultNet());
    } catch (e) {
      return false;
    }
  }

  private static prefetch(j: Job, k: number): void {
    if (k >= j.n()) {
      return;
    }
    FlowAudio.ttsUrl(j, k).catch(() => {});  // the address now; the file comes when it plays
  }

  private static sentence(): void {
    const j = FlowAudio.job;
    if (!j) {
      return;
    }
    const k = FlowAudio.i;
    const t = FlowAudio.tok;
    FlowAudio.prefetch(j, k + 1);
    FlowAudio.prefetch(j, k + 2);
    if (!FlowAudio.urls.get(FlowAudio.urlKey(j, k))) {
      FlowAudio.waitTimer = setTimeout(() => {
        if (t === FlowAudio.tok && FlowAudio.i === k && FlowAudio.state === 'playing') {
          FlowAudio.state = 'waiting';  // 「正在准备朗读第 N 句」 on the page
          FlowAudio.changed('');
        }
      }, 400);
    }
    const timeout = new Promise<string>((resolve, reject) => {
      setTimeout(() => reject(new Failure('slow', '')), 20000);
    });
    Promise.race([FlowAudio.ttsUrl(j, k), timeout]).then(async (u: string) => {
      if (t !== FlowAudio.tok || FlowAudio.job !== j) {
        return;  // paused, stopped or moved on meanwhile
      }
      clearTimeout(FlowAudio.waitTimer);
      FlowAudio.state = 'playing';
      FlowAudio.changed('');
      try {
        await FlowAudio.load(Site.abs(u), 0);
      } catch (e) {
        FlowAudio.onError(e as Error);
      }
    }).catch((e: Error) => {
      if (t !== FlowAudio.tok || FlowAudio.job !== j) {
        return;
      }
      clearTimeout(FlowAudio.waitTimer);
      FlowAudio.noVoice(j, k, t, e instanceof Failure ? e as Failure : new Failure('net', ''));
    });
  }

  /** The server could not give sentence k: paused with `fail` (the page says why, SV.why); 继续 asks again. */
  private static noVoice(j: Job, k: number, t: number, f: Failure): void {
    if (t !== FlowAudio.tok || FlowAudio.job !== j) {
      return;
    }
    FlowAudio.fail = { 'code': f.code, 'server': f.server };
    FlowAudio.tok++;
    FlowAudio.clearTimers();
    FlowAudio.state = 'paused';
    FlowAudio.i = k;
    FlowAudio.save();
    FlowAudio.stopTicks();
    FlowAudio.changed('error');
  }

  /** One sentence said: again (复读), or the next one after its pause, or the end. */
  private static sentenceDone(): void {
    const j = FlowAudio.job;
    if (!j) {
      return;
    }
    const justSaid = FlowAudio.i;
    const a = Sentences.after(FlowAudio.i, FlowAudio.said + 1, j.rep);
    FlowAudio.said = a.said;
    if (a.next >= j.n()) {
      FlowAudio.finish();
      return;
    }
    if (a.next !== FlowAudio.i) {
      FlowAudio.i = a.next;
      FlowAudio.save();
      FlowAudio.changed('');
    }
    const g = j.gapAfter(justSaid);
    const t = FlowAudio.tok;
    if (g > 0) {
      if (j.mode === Mode.REC && FlowAudio.player) {
        FlowAudio.player.pause().catch(() => {});
      }
      FlowAudio.gapTimer = setTimeout(() => {
        if (t === FlowAudio.tok && FlowAudio.state === 'playing') {
          FlowAudio.go();
        }
      }, g);
    } else {
      FlowAudio.go();
    }
  }

  private static altUrl(src: string): string {
    const j = FlowAudio.job;
    if (j && j.alt.startsWith('https://')) {
      return j.alt;
    }
    // as mediaAlt() on the page: the media domain keeps the recordings (not the server voice, not own articles)
    if (!src.startsWith('/audio/') || src.startsWith('/audio/tts/') || src.startsWith('/audio/own/')) {
      return '';
    }
    const m = FlowAudio.media;
    const base = m && typeof m['base'] === 'string' ? m['base'] as string : '';
    if (!base) {
      return '';
    }
    const name = src.split('?')[0].replace(new RegExp('^/audio/'), '').replace(new RegExp('\\.mp4$'), '') + '.m4a';
    return base + '/' + name + '?v=' + encodeURIComponent(m && m['version'] !== undefined ? String(m['version']) : '');
  }

  private static learnMedia(): void {
    AppState.request('/api/session').then((a) => {
      const m = a.json()['media'];
      if (m !== undefined && m !== null && typeof m === 'object') {
        FlowAudio.media = m as Record<string, Object>;
      }
    }).catch(() => {});
  }

  // ---- the end, and stopping
  private static finish(): void {
    const j = FlowAudio.job;
    if (!j) {
      return;
    }
    FlowAudio.progressEnded(j.key);  // both sides clear theirs; the mark is for a page that missed the event
    FlowAudio.release();
    FlowAudio.changed('ended');
  }

  /** Stop the sound and forget the text; where it was is kept. */
  private static async halt(): Promise<void> {
    const j = FlowAudio.job;
    if (!j) {
      return;
    }
    if (j.mode === Mode.REC && !j.loop && FlowAudio.player) {
      const si = Sentences.locate(j.spans, FlowAudio.player.currentTime / 1000);
      if (si >= 0) {
        FlowAudio.i = si;
      }
    }
    FlowAudio.save();
    await FlowAudio.release();
  }

  private static async release(): Promise<void> {
    FlowAudio.tok++;
    FlowAudio.clearTimers();
    const p = FlowAudio.player;
    FlowAudio.player = undefined;
    FlowAudio.job = null;
    FlowAudio.state = 'idle';
    FlowAudio.resumeOnGain = false;
    FlowAudio.reload = false;
    FlowAudio.fail = null;
    FlowAudio.stopTicks();
    if (p) {
      try {
        await p.release();
      } catch (e) {
        // released already
      }
    }
    await FlowAudio.endSession();
  }

  private static save(): void {
    const j = FlowAudio.job;
    if (j) {
      FlowAudio.progressSet(j.key, FlowAudio.i, FlowAudio.seconds());
    }
  }

  private static seconds(): number {
    return FlowAudio.player && FlowAudio.job && FlowAudio.job.mode === Mode.REC ? FlowAudio.player.currentTime / 1000 : 0;
  }

  private static applyRate(): void {
    const j = FlowAudio.job;
    const p = FlowAudio.player;
    if (!j || !p || (p.state !== 'prepared' && p.state !== 'playing' && p.state !== 'paused')) {
      return;
    }
    p.setSpeed(FlowAudio.speedOf(j.rate));
  }

  /** AVPlayer has fixed speeds: the nearest one to the page's 0.5–2. */
  private static speedOf(r: number): media.PlaybackSpeed {
    const table: number[] = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
    const speeds: media.PlaybackSpeed[] = [
      media.PlaybackSpeed.SPEED_FORWARD_0_50_X, media.PlaybackSpeed.SPEED_FORWARD_0_75_X,
      media.PlaybackSpeed.SPEED_FORWARD_1_00_X, media.PlaybackSpeed.SPEED_FORWARD_1_25_X,
      media.PlaybackSpeed.SPEED_FORWARD_1_50_X, media.PlaybackSpeed.SPEED_FORWARD_1_75_X,
      media.PlaybackSpeed.SPEED_FORWARD_2_00_X,
    ];
    let best = 2;
    for (let k = 0; k < table.length; k++) {
      if (Math.abs(table[k] - r) < Math.abs(table[best] - r)) {
        best = k;
      }
    }
    return speeds[best];
  }

  // ------------------------------------------------------------------ the page and the lock screen hear of it

  private static changed(why: string): void {
    const j = FlowAudio.job;
    if (j && FlowAudio.media === null) {
      FlowAudio.learnMedia();
    }
    FlowAudio.refreshSession();
    const d = FlowAudio.stateJson();
    d['key'] = j ? j.key : FlowAudio.lastKey;
    d['why'] = why;
    if (FlowAudio.fail) {
      d['fail'] = FlowAudio.fail;
      FlowAudio.fail = null;
    }
    AppState.emit('audio', d);
    if (j) {
      FlowAudio.lastKey = j.key;
    }
  }

  private static startTicks(): void {
    FlowAudio.stopTicks();
    FlowAudio.tickTimer = setInterval(() => FlowAudio.tick(), 50);
  }

  private static stopTicks(): void {
    if (FlowAudio.tickTimer >= 0) {
      clearInterval(FlowAudio.tickTimer);
      FlowAudio.tickTimer = -1;
    }
  }

  private static tick(): void {
    const j = FlowAudio.job;
    const p = FlowAudio.player;
    if (!j) {
      return;
    }
    if (p && j.mode === Mode.REC && FlowAudio.state === 'playing') {
      const t = p.currentTime / 1000;
      if (j.bySentence()) {
        if (p.state === 'playing' && FlowAudio.stopAtEnd >= 0 && t >= FlowAudio.stopAtEnd) {
          FlowAudio.stopAtEnd = -1;
          p.pause().catch(() => {});
          FlowAudio.sentenceDone();
        }
      } else {
        const si = Sentences.locate(j.spans, t);
        if (si >= 0 && si !== FlowAudio.i) {
          FlowAudio.i = si;
          FlowAudio.save();
          FlowAudio.changed('');
        }
      }
    }
    FlowAudio.tickN++;
    // at: when t was read (the page moves the word on between ticks: t + (now − at) × rate)
    if (FlowAudio.visible && FlowAudio.tickN % 5 === 0) {
      AppState.emit('audio-tick', {
        'key': j.key, 'i': FlowAudio.i, 't': FlowAudio.seconds(), 'at': Date.now(),
        'rate': p && p.state === 'playing' ? j.rate : 0,
      } as Record<string, Object>);
    }
  }

  private static clearTimers(): void {
    clearTimeout(FlowAudio.gapTimer);
    clearTimeout(FlowAudio.waitTimer);
  }

  // ------------------------------------------------------------------ the lock screen (AVSession) and the background

  private static async wantAgent(): Promise<WantAgent> {
    const bundle = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_DEFAULT).name;
    return wantAgent.getWantAgent({
      wants: [{ bundleName: bundle, abilityName: 'EntryAbility' }],
      actionType: wantAgent.OperationType.START_ABILITY,
      requestCode: 0,
      actionFlags: [wantAgent.WantAgentFlags.UPDATE_PRESENT_FLAG],
    });
  }

  private static async startSession(): Promise<void> {
    const ctx = AppState.context;
    if (!ctx) {
      return;
    }
    try {
      if (!FlowAudio.session) {
        const s = await avSession.createAVSession(ctx, 'flow-long', 'audio');
        s.on('play', () => {
          FlowAudio.resume();
        });
        s.on('pause', () => {
          FlowAudio.pause('remote');
        });
        s.on('stop', () => {
          FlowAudio.pause('remote');
        });
        s.on('playNext', () => {
          FlowAudio.step(1);
        });
        s.on('playPrevious', () => {
          FlowAudio.step(-1);
        });
        await s.setLaunchAbility(await FlowAudio.wantAgent());
        FlowAudio.session = s;
      }
      await FlowAudio.session.activate();
      if (!FlowAudio.running) {
        await backgroundTaskManager.startBackgroundRunning(ctx, backgroundTaskManager.BackgroundMode.AUDIO_PLAYBACK,
          await FlowAudio.wantAgent());
        FlowAudio.running = true;
      }
    } catch (e) {
      AppState.warn('session: ' + JSON.stringify(e));
    }
  }

  private static refreshSession(): void {
    const s = FlowAudio.session;
    const j = FlowAudio.job;
    if (!s || !j) {
      return;
    }
    // 「AI 朗读」 on the second line: the sound is synthesised (人工智能生成合成内容标识办法), as Android's
    const meta: avSession.AVMetadata = {
      assetId: j.key || 'flow',
      title: j.title,
      artist: 'AI 朗读 · 第 ' + (FlowAudio.i + 1) + ' / ' + j.n() + ' 句',
    };
    // a recording has a length: the lock screen's bar shows where it is (the server voice goes sentence by sentence)
    const p = FlowAudio.player;
    if (j.mode === Mode.REC && !j.loop && p && p.duration > 0) {
      meta.duration = p.duration;
    }
    s.setAVMetadata(meta).catch(() => {});
    const playing = FlowAudio.state === 'playing' || FlowAudio.state === 'waiting';
    const ps: avSession.AVPlaybackState = {
      state: playing ? avSession.PlaybackState.PLAYBACK_STATE_PLAY : avSession.PlaybackState.PLAYBACK_STATE_PAUSE,
      speed: j.rate,
      position: { elapsedTime: Math.round(FlowAudio.seconds() * 1000), updateTime: Date.now() },
    };
    s.setAVPlaybackState(ps).catch(() => {});
  }

  private static async endSession(): Promise<void> {
    const ctx = AppState.context;
    // the lock screen's card goes away too: stopped, then the session itself (one is made again for the next text)
    const s = FlowAudio.session;
    FlowAudio.session = undefined;
    if (s) {
      try {
        const stopped: avSession.AVPlaybackState = { state: avSession.PlaybackState.PLAYBACK_STATE_STOP };
        await s.setAVPlaybackState(stopped);
        await s.deactivate();
        await s.destroy();
      } catch (e) {
        AppState.warn('session end: ' + JSON.stringify(e));
      }
    }
    try {
      if (FlowAudio.running && ctx) {
        await backgroundTaskManager.stopBackgroundRunning(ctx);
      }
    } catch (e) {
      // stopped already
    }
    FlowAudio.running = false;
  }

  // ------------------------------------------------------------------ where a text was left (30 days, at most 100)

  private static store(): preferences.Preferences | undefined {
    const ctx = AppState.context;
    return ctx ? preferences.getPreferencesSync(ctx, { name: 'flow-progress' }) : undefined;
  }

  private static progressAll(): Map<string, Record<string, Object>> {
    const s = FlowAudio.store();
    const out = new Map<string, Record<string, Object>>();
    let o: Record<string, Record<string, Object>> = {};
    try {
      o = JSON.parse(s ? s.getSync('all', '{}') as string : '{}') as Record<string, Record<string, Object>>;
    } catch (e) {
      o = {};
    }
    const cut = Date.now() - 30 * 86400000;
    Object.keys(o).forEach((k: string) => {
      const at = o[k]['at'];
      if (typeof at === 'number' && (at as number) >= cut) {
        out.set(k, o[k]);
      }
    });
    return out;
  }

  private static progressWrite(all: Map<string, Record<string, Object>>): void {
    const keys = Array.from(all.keys()).sort((a: string, b: string) => Number(all.get(a)!['at']) - Number(all.get(b)!['at']));
    const o: Record<string, Record<string, Object>> = {};
    keys.slice(Math.max(0, keys.length - 100)).forEach((k: string) => {
      o[k] = all.get(k)!;
    });
    const s = FlowAudio.store();
    if (s) {
      s.putSync('all', JSON.stringify(o));
      s.flush();
    }
  }

  private static progressSet(key: string, i: number, t: number): void {
    if (!key) {
      return;
    }
    const all = FlowAudio.progressAll();
    if (i > 0 || t > 1) {
      const v: Record<string, Object> = { 'i': i, 't': t, 'at': Date.now() };
      all.set(key, v);
    } else {
      all.delete(key);
    }
    FlowAudio.progressWrite(all);
  }

  private static progressEnded(key: string): void {
    if (!key) {
      return;
    }
    const all = FlowAudio.progressAll();
    const v: Record<string, Object> = { 'ended': true, 'at': Date.now() };
    all.set(key, v);
    FlowAudio.progressWrite(all);
  }

  // ------------------------------------------------------------------ small helpers

  private static str(v: Object | undefined | null): string {
    return typeof v === 'string' ? v as string : '';
  }

  private static num(v: Object | undefined | null, def: number): number {
    return typeof v === 'number' && !isNaN(v as number) ? v as number : def;
  }

  private static clampRate(r: number): number {
    return Math.min(2, Math.max(0.5, r));
  }

  private static failed(why: string, message: string): Record<string, Object> {
    const o: Record<string, Object> = { 'ok': false, 'why': why, 'message': message };
    return o;
  }
}
