import { webview } from '@kit.ArkWeb';
import { util } from '@kit.ArkTS';
import { resourceManager } from '@kit.LocalizationKit';
import { AppState } from '../common/AppState';
import { Site } from '../common/Site';
import { Permissions } from '../common/Permissions';
import { Reminders } from '../notify/Reminders';
import { Recorder } from '../rec/Recorder';
import { FlowAudio } from '../audio/FlowAudio';

/** {id, cmd, args} from the page (flowapp-harmony.js). */
interface Msg {
  id?: number;
  cmd?: string;
  args?: Object;
}

/** The object the page sees as window.flowNative (javaScriptProxy). One method: the page's message, as JSON. */
export class BridgeProxy {
  private bridge: Bridge;

  constructor(bridge: Bridge) {
    this.bridge = bridge;
  }

  post(json: string): void {
    this.bridge.onPost(json);
  }
}

/**
 * The page ↔ app bridge (docs/native-bridge.md, FlowApp v1): window.FlowApp, put in place before the page's scripts on
 * the site's own origin only (rawfile/flowapp-harmony.js + the shared native/flowapp.js), and the `flowNative` proxy
 * behind it. Only the site's own page is answered. Expected failures resolve with {ok: false, why}; only unknown commands
 * and transport errors reject (§2).
 */
export class Bridge {
  /** What this app does natively (FlowApp.has). No 'speech': the system's voice is Core Speech Kit, not used (C4 plan §5). */
  static readonly FEATURES: string[] = ['audio', 'rec', 'notify'];

  readonly proxy: BridgeProxy = new BridgeProxy(this);
  private web: webview.WebviewController;
  /** The receiver's name on the page (flowapp-harmony.js); new for every start of the app. */
  private recv: string = '__flowRecv_' + util.generateRandomUUID(false).replace(new RegExp('-', 'g'), '');
  private connected: boolean = false;

  constructor(web: webview.WebviewController) {
    this.web = web;
    AppState.emit = (type: string, detail: Object | null) => this.emit(type, detail);
  }

  private config(): Record<string, Object> {
    return {
      'v': 1, 'app': Site.version, 'build': Site.build, 'beta': Site.beta, 'platform': 'harmony',
      'features': Bridge.FEATURES, 'mute': Site.mute, 'recv': this.recv,
    };
  }

  /** HarmonyOS's own lines (the transport, _back, the test switch), then the wrapper the apps share (native/flowapp.js). */
  script(rm: resourceManager.ResourceManager): string {
    const text = (name: string): string => {
      const bytes = rm.getRawFileContentSync(name);
      return new util.TextDecoder('utf-8').decodeToString(bytes);
    };
    return text('flowapp-harmony.js').replace('__FLOW_CONFIG__', JSON.stringify(this.config())) + '\n' + text('flowapp.js');
  }

  /** The page's message. Only from the site's own page (the proxy is the web view's, so check what it shows). */
  onPost(json: string): void {
    if (!Site.isOwn(this.web.getUrl())) {
      return;
    }
    let m: Msg;
    try {
      m = JSON.parse(json) as Msg;
    } catch (e) {
      return;
    }
    const id = m.id ?? 0;
    const cmd = m.cmd ?? '';
    const args: Record<string, Object> = (m.args !== undefined && m.args !== null && typeof m.args === 'object')
      ? m.args as Record<string, Object> : {};
    this.handle(cmd, args, m.args).then((result: Object | null) => {
      this.reply({ 'id': id, 'ok': true, 'result': result });
    }).catch((e: Error) => {
      AppState.warn(cmd + ' failed: ' + (e && e.message ? e.message : String(e)));
      this.reply({ 'id': id, 'ok': false, 'error': e && e.message ? e.message : 'error' });
    });
  }

  private async handle(cmd: string, o: Record<string, Object>, raw: Object | undefined): Promise<Object | null> {
    switch (cmd) {
      case 'hello':
        if (!this.connected) {
          AppState.log('page connected (bridge v1)');  // no address or content: only that the bridge is up
        }
        this.connected = true;
        FlowAudio.replay();
        return { 'v': 1, 'app': Site.version, 'build': Site.build, 'platform': 'harmony', 'features': Bridge.FEATURES };
      case 'app.visible':
        FlowAudio.replay();
        return true;

      case 'audio.play':
        return FlowAudio.play(o);
      case 'audio.pause':
        return FlowAudio.pause(o['why'] === 'other' ? 'other' : 'user');
      case 'audio.resume':
        return FlowAudio.resume();
      case 'audio.stop':
        return FlowAudio.stop();
      case 'audio.step':
        return FlowAudio.step(Bridge.num(raw, 'd', 1));
      case 'audio.seek':
        return FlowAudio.seek(Bridge.num(raw, 'i', 0));
      case 'audio.set':
        return FlowAudio.set(o);
      case 'audio.state':
        return FlowAudio.stateJson();
      case 'audio.progress':
        return FlowAudio.progressJson(typeof raw === 'string' ? raw as string : String(o['key'] ?? ''));

      case 'rec.permission':
        return Permissions.mic();
      case 'rec.ask':
        return Permissions.askMic();
      case 'rec.start': {
        const token = Recorder.begin();
        if (!(await Permissions.askMic())) {
          return { 'ok': false, 'why': 'denied', 'message': '没有拿到麦克风权限' };
        }
        if (!Recorder.stillWanted(token)) {
          return { 'ok': false, 'why': 'cancelled' };  // stopped while asking
        }
        const max = typeof o['max'] === 'number' ? o['max'] as number : 60;
        const format = typeof o['format'] === 'string' ? o['format'] as string : '';
        return Recorder.start(max, format);
      }
      case 'rec.stop':
        return Recorder.stop();
      case 'rec.cancel':
        await Recorder.cancel();
        return true;

      case 'notify.permission':
        return Reminders.permission();
      case 'notify.ask':
        return Reminders.ask();
      case 'notify.sync': {
        const off = raw === undefined || raw === null;
        if (!off && o['ask'] === true) {
          await Reminders.ask();
        }
        return Reminders.sync(off ? null : o);
      }
      case 'notify.pending':
        return Reminders.pendingJson();
      case 'notify.off':
        return Reminders.sync({ 'app': false });
      case 'notify.settings':
        Permissions.openNotifySettings();
        return true;
      case 'notify.test':
        // UI tests on the beta: schedule from the given counts without asking the server (as iOS's and Android's)
        if (!Site.beta) {
          throw new Error('unknown command ' + cmd);
        }
        return Reminders.test(o);

      default:
        throw new Error('unknown command ' + cmd);
    }
  }

  private static num(raw: Object | undefined, field: string, def: number): number {
    if (typeof raw === 'number') {
      return raw as number;
    }
    if (raw !== undefined && raw !== null && typeof raw === 'object') {
      const v = (raw as Record<string, Object>)[field];
      if (typeof v === 'number') {
        return v as number;
      }
    }
    return def;
  }

  private reply(m: Record<string, Object | null>): void {
    this.run(JSON.stringify(m));
  }

  /** App → page: FlowApp.on(type) and window 'flowapp:<type>'. */
  emit(type: string, detail: Object | null): void {
    if (!this.connected) {
      return;
    }
    const m: Record<string, Object | null> = { 'ev': type, 'detail': detail };
    this.run(JSON.stringify(m));
  }

  private run(json: string): void {
    if (!Site.isOwn(this.web.getUrl())) {
      return;
    }
    // the JSON is a JavaScript literal as it is; U+2028 and U+2029 are escaped for older parsers anyway
    const lit = json.replace(new RegExp(' ', 'g'), '\\u2028').replace(new RegExp(' ', 'g'), '\\u2029');
    try {
      this.web.runJavaScript('window["' + this.recv + '"] && window["' + this.recv + '"](' + lit + ')').catch(() => {});
    } catch (e) {
      // the page is gone (navigating, or the web view is not attached yet)
    }
  }

  /** A new page is loading: it says hello again before it gets events. */
  pageStarted(): void {
    this.connected = false;
  }
}
