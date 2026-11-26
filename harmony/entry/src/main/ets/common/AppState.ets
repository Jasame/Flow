import { common, Want } from '@kit.AbilityKit';
import { webview } from '@kit.ArkWeb';
import { http } from '@kit.NetworkKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { Site } from './Site';

const TAG = 'FlowApp';

/** What one request to the site answered (with the web view's cookies, so signed in as on the page). */
export class Answer {
  code: number = 0;
  text: string = '';

  ok(): boolean {
    return this.code >= 200 && this.code < 300;
  }

  json(): Record<string, Object> {
    try {
      const o = JSON.parse(this.text) as Record<string, Object>;
      return o ?? {};
    } catch (e) {
      return {};
    }
  }
}

/**
 * The few things the ability, the page and the native parts share: the ability's context, the web view, where to
 * send the page's events, and a reminder's path waiting to be opened.
 */
export class AppState {
  static context: common.UIAbilityContext | undefined = undefined;
  static web: webview.WebviewController | undefined = undefined;
  /** App → page (Bridge.emit), once the page has said hello. */
  static emit: (type: string, detail: Object | null) => void = () => {};
  /** Called when the app comes back on screen and when it goes to the background (Reminders, the recorder). */
  static onForeground: Array<() => void> = [];
  static onBackground: Array<() => void> = [];
  /** A path from a reminder ("#/review") that arrived before the web view was there. */
  static startPath: string | undefined = undefined;

  static log(msg: string): void {
    hilog.info(0x0F10, TAG, '%{public}s', msg);
  }

  static warn(msg: string): void {
    hilog.warn(0x0F10, TAG, '%{public}s', msg);
  }

  static foreground(): void {
    AppState.onForeground.forEach((f) => {
      try {
        f();
      } catch (e) {
        AppState.warn('foreground: ' + JSON.stringify(e));
      }
    });
  }

  static background(): void {
    AppState.onBackground.forEach((f) => {
      try {
        f();
      } catch (e) {
        AppState.warn('background: ' + JSON.stringify(e));
      }
    });
    AppState.saveCookies();
  }

  /**
   * The web view's cookies to disk now: the engine writes them only now and then by itself, so a sign-in or a switch
   * just before the app is swiped away would be lost. Only once a page is there (before, there is no web engine).
   */
  static saveCookies(): void {
    if (!AppState.web) {
      return;
    }
    try {
      webview.WebCookieManager.saveCookieAsync().catch(() => {});
    } catch (e) {
      AppState.warn('save cookies: ' + JSON.stringify(e));
    }
  }

  /** A reminder was tapped: open its page in the web view that is there, or when it comes. */
  static open(path: string): void {
    if (AppState.web) {
      try {
        AppState.web.loadUrl(Site.startUrl(path));
        return;
      } catch (e) {
        AppState.warn('open: ' + JSON.stringify(e));
      }
    }
    AppState.startPath = path;
  }

  /** Another site, a download, mailto: — the phone's browser or mail app, never inside the app. */
  static openOutside(u: string): void {
    const ctx = AppState.context;
    if (!ctx) {
      return;
    }
    const want: Want = u.startsWith('http://') || u.startsWith('https://')
      ? { action: 'ohos.want.action.viewData', entities: ['entity.system.browsable'], uri: u }
      : { uri: u };
    ctx.startAbility(want).catch((e: Error) => AppState.warn('openOutside: ' + e.message));
  }

  /** GET or POST a path on the site, signed in as the page is (its cookies), as Flow's other apps do. */
  static async request(path: string, method: http.RequestMethod = http.RequestMethod.GET, body?: string,
    csrf?: string): Promise<Answer> {
    const target = Site.abs(path);
    const header: Record<string, string> = { 'Accept': 'application/json', 'User-Agent': Site.userAgent };
    try {
      const c = webview.WebCookieManager.fetchCookieSync(Site.origin);
      if (c) {
        header['Cookie'] = c;
      }
    } catch (e) {
      // no cookies yet: a guest
    }
    if (body !== undefined) {
      header['Content-Type'] = 'application/json';
    }
    if (csrf) {
      header['X-CSRF-Token'] = csrf;
    }
    const req = http.createHttp();
    const a = new Answer();
    try {
      const r = await req.request(target, {
        method: method,
        header: header,
        extraData: body,
        expectDataType: http.HttpDataType.STRING,
        connectTimeout: 15000,
        readTimeout: 20000,
      });
      a.code = r.responseCode;
      a.text = typeof r.result === 'string' ? r.result as string : '';
    } finally {
      req.destroy();
    }
    return a;
  }
}
