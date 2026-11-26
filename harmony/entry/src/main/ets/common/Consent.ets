/** The two texts as this build has them (rawfile legal/legal.json, made by android/tools/legal_docs.py). */
export class LegalDocs {
  version: string = '';
  titles: Map<string, string> = new Map<string, string>();
  html: Map<string, string> = new Map<string, string>();
}

interface LegalDoc {
  title: string;
  html: string;
}

interface LegalFile {
  version: string;
  docs: Record<string, LegalDoc>;
}

/**
 * The question on the first start, before the app opens the site or anything else on the network — as Android's
 * privacy/Consent.kt (android/README.md 「第一次打开」), with the same words and the same rules:
 *   同意   → as before.
 *   不同意 → 基本模式: the site without signing in (the page keeps its progress on the phone); no microphone; signing in or
 *           up, or recording, asks again first. Asked once on its own: never again by itself.
 * The answer is kept on this phone with the version of the two texts it was for (their 生效日期, as
 * privacy_service.CONSENT_VERSION writes it); a build with a newer version asks again. 撤回同意 forgets it.
 * No system calls here, so the local tests can check it; ConsentGate keeps the answer and asks.
 */
export class Consent {
  static readonly ASK: string = 'ask';
  static readonly AGREED: string = 'agreed';
  static readonly BASIC: string = 'basic';
  static readonly DOCS: string[] = ['terms', 'privacy'];

  /** From what this phone answered and the version of the texts in this build. */
  static state(agreed: string, basic: boolean, current: string): string {
    if (agreed !== '' && agreed === current) {
      return Consent.AGREED;
    }
    return basic ? Consent.BASIC : Consent.ASK;
  }

  /** The site's sign-in routes (flow/app.py SIGN_IN_ROUTES): in 基本模式 the app answers them itself, and asks first. */
  static readonly SIGN_IN: string[] = ['/api/login', '/api/register', '/api/auth/code', '/api/auth/reset',
    '/api/recovery/request', '/api/recovery/reset', '/api/teacher/check'];

  static signIn(path: string): boolean {
    return Consent.SIGN_IN.indexOf(path.replace(new RegExp('/+$'), '')) >= 0;
  }

  /** What the page's form gets instead (403): its `error` is shown under the form. */
  static readonly SIGN_IN_ANSWER: string =
    '{"error":"要登录或注册，请先在弹出的窗口里同意《用户协议》和《隐私和数据》，然后再点一次。","code":"app-consent"}';

  /** The two lists in 《隐私和数据》 (its sections {#info-list}, {#sharing-list}), named only when this build has both. */
  static readonly LISTS: string[][] = [['《个人信息收集清单》', 'g-info-list'], ['《第三方信息共享清单》', 'g-sharing-list']];

  static hasLists(privacyHtml: string): boolean {
    return Consent.LISTS.every((l: string[]) => privacyHtml.indexOf('id="' + l[1] + '"') >= 0);
  }

  static parse(json: string): LegalDocs | null {
    try {
      const o = JSON.parse(json) as LegalFile;
      if (!o.version || !o.docs) {
        return null;
      }
      const d = new LegalDocs();
      d.version = o.version;
      for (let i = 0; i < Consent.DOCS.length; i++) {
        const id = Consent.DOCS[i];
        const doc = o.docs[id];
        if (!doc || !doc.title || !doc.html) {
          return null;
        }
        d.titles.set(id, doc.title);
        d.html.set(id, doc.html);
      }
      return d;
    } catch (e) {
      return null;
    }
  }

  /** Never in a build (entry/hvigorfile.ts makes the file); only so the app still opens if the file were missing. */
  static missing(): LegalDocs {
    const d = new LegalDocs();
    d.version = 'missing';
    const gone = '<p>这个版本的 App 里少了这一章。请到语流网站的「操作指南」里看。</p>';
    d.titles.set('terms', '语流用户协议');
    d.titles.set('privacy', '隐私和数据');
    d.html.set('terms', gone);
    d.html.set('privacy', gone);
    return d;
  }

  // The words: the same as Android's (android res/values/strings.xml), read by D2 and the user.
  static readonly TITLE: string = '欢迎使用语流';
  static readonly TITLE_FEATURE: string = '先同意，再继续';
  static readonly BODY: string = '语流是一个英语自学工具。开始之前，请读一读《用户协议》和《隐私和数据》。简单说：\n\n' +
    '• 收的都是学英语用得上的信息：账号（用户名、邮箱、年龄段）、学习记录、你写的作文和翻译、你主动发的问题反馈。完整清单见《隐私和数据》。\n' +
    '• 你写的作文、翻译和说的录音，批改时会交给阿里云百炼上的 AI；录音不保存。\n' +
    '• 账号和学习数据存放在香港的服务器上，注册时还会单独问你。\n' +
    '• 不满 14 岁的，要先告诉家长（或监护人）并得到同意。\n' +
    '• App 没有接第三方 SDK，不做跟踪。麦克风和通知都是第一次用到时才问。\n' +
    '• 运营者：语流的运营者（公司注册完成后会写上公司名称）。联系我们：「我的 → 问题反馈」，或写信到 i@jasa.hk。';
  static readonly LISTS_LINE: string = '• 收了哪些信息、交给了谁，分别见《个人信息收集清单》和《第三方信息共享清单》。';
  static readonly CLOSE: string = '点「同意」，表示你已阅读并同意《用户协议》和《隐私和数据》。';
  static readonly TAIL_FIRST: string = '不同意也可以进入基本模式：不登录，进度只存在这台手机上。';
  static readonly TAIL_BASIC: string = '不同意的话，继续用基本模式。';
  static readonly BASIC_TITLE: string = '不同意也能先看看';
  static readonly BASIC_BODY: string = '不同意的话，语流会进入基本模式：不登录，学习进度只存在这台手机上；不开提醒，也不用麦克风。' +
    '这台手机上要是登录过，也会退出登录。\n\n想用全部功能时，点页面顶上的「同意」就行。';
  static readonly WHY_SIGNIN: string = '要登录或注册，请先同意《用户协议》和《隐私和数据》。';
  static readonly WHY_MIC: string = '要用麦克风录音，请先同意《用户协议》和《隐私和数据》。';
  static readonly BAR: string = '基本模式：不登录，进度只存在这台手机上';
  static readonly WITHDRAW_TITLE: string = '撤回同意';
  static readonly WITHDRAW_BODY: string = '撤回以后，这台手机上的语流会：\n• 退出登录，清掉这台手机上的登录信息、缓存、朗读进度和提醒；\n' +
    '• 回到第一次打开时的样子，再问你一次。\n\n账号里的学习记录还在服务器上，再同意、再登录就能接着学。' +
    '账号上的同意（「数据存放在香港」和《用户协议》）在网页的「我的 → 账号和隐私」里管理。';

  /** The question's text: why (a feature asked for it in 基本模式), the body, the lists when there, the close and tail. */
  static question(why: string, first: boolean, lists: boolean): string {
    const body = Consent.BODY + (lists ? '\n' + Consent.LISTS_LINE : '') + '\n\n' + Consent.CLOSE +
      (first ? Consent.TAIL_FIRST : Consent.TAIL_BASIC);
    return why ? why + '\n\n' + body : body;
  }

  /**
   * A link in one of the texts (legal_docs.py writes them): "flow-doc:privacy#g-info-list" → ['privacy', 'g-info-list'];
   * anything else → null.
   */
  static docLink(u: string): string[] | null {
    if (!u.startsWith('flow-doc:')) {
      return null;
    }
    const rest = u.substring('flow-doc:'.length);
    const hash = rest.indexOf('#');
    const id = hash >= 0 ? rest.substring(0, hash) : rest;
    const at = hash >= 0 ? rest.substring(hash + 1) : '';
    return [Consent.DOCS.indexOf(id) >= 0 ? id : Consent.DOCS[0], new RegExp('^g-[a-z0-9-]+$').test(at) ? at : ''];
  }

  /** The chapter as the site's guide shows it (its .guide-body look, as Android's), light or dark as the phone is. */
  static page(body: string): string {
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width,initial-scale=1"><style>' +
      ':root{color-scheme:light dark;--fg:#1B1F1D;--bg:#FBFAF6;--ac:#1F9D55;--line:rgba(27,36,32,.14);--soft:rgba(27,36,32,.045)}' +
      '@media (prefers-color-scheme:dark){:root{--fg:#E8ECEA;--bg:#101412;--ac:#3CCF7C;' +
      '--line:rgba(232,238,234,.18);--soft:rgba(232,238,234,.06)}}' +
      'body{margin:0;padding:2px 20px 28px;font:16px/1.75 sans-serif;color:var(--fg);background:var(--bg);' +
      'overflow-wrap:anywhere}' +
      'h3{font-size:17px;line-height:1.5;margin:24px 0 6px}' +
      'p{margin:10px 0}ul,ol{padding-left:22px;margin:8px 0}li{margin:4px 0}b{font-weight:600}' +
      'a{color:var(--ac);text-decoration:none}.dead{color:inherit}' +
      'table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.6;margin:12px 0}' +
      'th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{background:var(--soft)}' +
      '.tip{border-left:3px solid var(--ac);background:var(--soft);padding:6px 12px;margin:12px 0}' +
      'kbd{font:inherit;border:1px solid var(--line);border-radius:4px;padding:0 4px}pre{white-space:pre-wrap}' +
      '</style></head><body>' + body + '</body></html>';
  }

  /**
   * The question cut where 《用户协议》, 《隐私和数据》 and the two lists are, each part with what it opens as a docLink
   * ('' = plain text).
   */
  static parts(text: string, lists: boolean): string[][] {
    const links: string[][] = [['《用户协议》', 'flow-doc:terms'], ['《隐私和数据》', 'flow-doc:privacy']];
    if (lists) {
      Consent.LISTS.forEach((l: string[]) => {
        links.push([l[0], 'flow-doc:privacy#' + l[1]]);
      });
    }
    const out: string[][] = [];
    let rest = text;
    while (rest.length > 0) {
      let at = -1;
      let hit: string[] = [];
      links.forEach((l: string[]) => {
        const i = rest.indexOf(l[0]);
        if (i >= 0 && (at < 0 || i < at)) {
          at = i;
          hit = l;
        }
      });
      if (at < 0) {
        out.push([rest, '']);
        break;
      }
      if (at > 0) {
        out.push([rest.substring(0, at), '']);
      }
      out.push([hit[0], hit[1]]);
      rest = rest.substring(at + hit[0].length);
    }
    return out;
  }
}
