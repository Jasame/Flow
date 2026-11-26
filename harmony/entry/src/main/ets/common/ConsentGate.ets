import { preferences } from '@kit.ArkData';
import { webview } from '@kit.ArkWeb';
import { promptAction } from '@kit.ArkUI';
import { util } from '@kit.ArkTS';
import { AppState } from './AppState';
import { Consent, LegalDocs } from './Consent';

/**
 * Consent on this phone (common/Consent.ets has the rules and the words): the answer and the version it was for, the
 * question asked through the page's UI (pages/Index.ets sets `asker`), and what 基本模式 and 撤回同意 clear.
 */
export class ConsentGate {
  private static docsCache: LegalDocs | null = null;
  /** The question, shown by pages/Index.ets: why ('' on its own), first (the first start: 不同意 has a second look). */
  static asker: ((why: string, first: boolean) => Promise<boolean>) | null = null;
  /** The page is told when the answer changes (to show or hide the 基本模式 line, or to ask again after 撤回). */
  static listener: (state: string) => void = () => {};
  /** Done before the phone is cleared (the recorder, the player): set by the ability, so this file needs none of them. */
  static onClear: Array<() => Promise<void>> = [];
  /** The web cache could not be cleared (no page yet): the next page clears it as it starts (pages/Index.ets). */
  static cachePending: boolean = false;

  private static store(): preferences.Preferences | undefined {
    const ctx = AppState.context;
    return ctx ? preferences.getPreferencesSync(ctx, { name: 'flow-consent' }) : undefined;
  }

  static docs(): LegalDocs {
    if (ConsentGate.docsCache) {
      return ConsentGate.docsCache;
    }
    let d: LegalDocs | null = null;
    try {
      const ctx = AppState.context;
      if (ctx) {
        const bytes = ctx.resourceManager.getRawFileContentSync('legal/legal.json');
        d = Consent.parse(new util.TextDecoder('utf-8').decodeToString(bytes));
      }
    } catch (e) {
      d = null;
    }
    ConsentGate.docsCache = d ?? Consent.missing();
    return ConsentGate.docsCache;
  }

  static lists(): boolean {
    return Consent.hasLists(ConsentGate.docs().html.get('privacy') ?? '');
  }

  static current(): string {
    const s = ConsentGate.store();
    const agreed = s ? s.getSync('version', '') as string : '';
    const basic = s ? s.getSync('basic', false) as boolean : false;
    return Consent.state(agreed, basic, ConsentGate.docs().version);
  }

  static agree(): void {
    const s = ConsentGate.store();
    if (s) {
      s.putSync('version', ConsentGate.docs().version);
      s.putSync('basic', false);
      s.putSync('at', Date.now());
      s.flush();
    }
    ConsentGate.listener(Consent.AGREED);
  }

  /** 进入基本模式: the answer kept, and this phone cleared of a sign-in and what the page kept. */
  static async decline(): Promise<void> {
    await ConsentGate.clearPhone();
    const s = ConsentGate.store();
    if (s) {
      s.deleteSync('version');
      s.putSync('basic', true);
      s.putSync('at', Date.now());
      s.flush();
    }
    ConsentGate.listener(Consent.BASIC);
  }

  /**
   * Asked from 基本模式 (the page's privacy.ask, signing in, recording): 同意 → agreed; else it stays 基本模式.
   * → the state now ('agreed' | 'basic').
   */
  static async ask(why: string): Promise<string> {
    const now = ConsentGate.current();
    if (now === Consent.AGREED || !ConsentGate.asker) {
      return now;
    }
    const ok = await ConsentGate.asker(why, false);
    if (ok) {
      ConsentGate.agree();
    }
    return ConsentGate.current();
  }

  /** 撤回同意 (privacy.withdraw): what it does, then 撤回 → this phone cleared, and the question of the first start. */
  static async withdraw(): Promise<boolean> {
    let go = false;
    try {
      const r = await promptAction.showDialog({
        title: Consent.WITHDRAW_TITLE,
        message: Consent.WITHDRAW_BODY,
        buttons: [{ text: '取消', color: '#5E6662' }, { text: '撤回', color: '#1F9D55' }],
      });
      go = r.index === 1;
    } catch (e) {
      go = false;  // dismissed
    }
    if (!go) {
      return false;
    }
    await ConsentGate.clearPhone();
    const s = ConsentGate.store();
    if (s) {
      s.clearSync();
      s.flush();
    }
    ConsentGate.listener(Consent.ASK);
    return true;
  }

  /** The sign-in, the page's storage and cache, the player's progress and the reminders: gone from this phone. */
  static async clearPhone(): Promise<void> {
    for (let i = 0; i < ConsentGate.onClear.length; i++) {
      try {
        await ConsentGate.onClear[i]();
      } catch (e) {
        AppState.warn('clear: ' + JSON.stringify(e));
      }
    }
    try {
      webview.WebviewController.initializeWebEngine();  // before any page on this start (不同意 on the first question)
      webview.WebCookieManager.clearAllCookiesSync();
      webview.WebCookieManager.saveCookieAsync().catch(() => {});
      webview.WebStorage.deleteAllData();
    } catch (e) {
      AppState.warn('clear web: ' + JSON.stringify(e));
    }
    ConsentGate.cachePending = true;
    try {
      if (AppState.web) {
        AppState.web.removeCache(true);
        ConsentGate.cachePending = false;
      }
    } catch (e) {
      // no page attached: the next one clears it
    }
  }
}
