import { webview } from '@kit.ArkWeb';
import { common } from '@kit.AbilityKit';
import { util } from '@kit.ArkTS';
import { AppState } from '../common/AppState';
import { Site } from '../common/Site';
import { Permissions } from '../common/Permissions';
import { Bridge } from '../bridge/Bridge';
import { CalendarLink } from '../common/CalendarLink';
import { Consent } from '../common/Consent';
import { ConsentGate } from '../common/ConsentGate';

/**
 * The app: the site in an ArkWeb web view (so every change to the site is in the app at once), with the native parts
 * behind window.FlowApp (Bridge). Signed in as on the site (the web view's own cookies, kept on the phone); the back
 * gesture goes back in the page; other sites open in the phone's browser; light and dark follow the phone at once; the
 * page ends at the keyboard (RESIZE_CONTENT), as in Android's app.
 *
 * Before the site, the first start's question (common/Consent.ets, as Android 1.0.4): no web page and nothing on the
 * network until it is answered. 不同意 → 基本模式, with its line on top of the page.
 */
@Entry
@Component
struct Index {
  private controller: webview.WebviewController = new webview.WebviewController();
  private bridge: Bridge = new Bridge(this.controller);
  private scripts: Array<ScriptItem> = [];
  private docCtl: webview.WebviewController = new webview.WebviewController();
  private docAt: string = '';
  private docId: string = 'terms';
  private answer: (yes: boolean) => void = () => {};
  @State failed: boolean = false;
  /** The site's page is there: once the question is answered. */
  @State opened: boolean = false;
  @State basic: boolean = false;
  /** '' | 'question' | 'second' (不同意 on the first start: 进入基本模式 or 再看看). */
  @State asking: string = '';
  @State why: string = '';
  @State first: boolean = true;
  @State docOpen: boolean = false;
  @State docTitle: string = '';

  aboutToAppear(): void {
    webview.WebviewController.setWebDebuggingAccess(Site.debug);
    this.fresh();
    ConsentGate.asker = (why: string, first: boolean) => this.ask(why, first);
    ConsentGate.listener = (state: string) => this.changed(state);
    const s = ConsentGate.current();
    if (s === Consent.ASK) {
      this.firstQuestion();
    } else {
      this.open();
    }
  }

  aboutToDisappear(): void {
    AppState.web = undefined;
    ConsentGate.asker = null;
    ConsentGate.listener = () => {};
  }

  /** A web view of its own for each page (a withdrawn agreement starts again from nothing). */
  private fresh(): void {
    this.controller = new webview.WebviewController();
    this.bridge = new Bridge(this.controller);
    const ctx = getContext(this) as common.UIAbilityContext;
    this.scripts = [{ script: this.bridge.script(ctx.resourceManager), scriptRules: [Site.origin] }];
    AppState.web = this.controller;
  }

  private async firstQuestion(): Promise<void> {
    const yes = await this.ask('', true);
    if (yes) {
      ConsentGate.agree();
    } else {
      await ConsentGate.decline();
    }
    this.open();
  }

  private open(): void {
    this.basic = ConsentGate.current() === Consent.BASIC;
    this.opened = true;
  }

  /** The answer changed elsewhere: 同意 in 基本模式, or 撤回同意 (the page goes, and the first question comes back). */
  private changed(state: string): void {
    this.basic = state === Consent.BASIC;
    if (state === Consent.ASK && this.opened) {
      this.opened = false;
      this.failed = false;
      AppState.startPath = undefined;
      this.fresh();
      this.firstQuestion();
    }
  }

  /** The question (one at a time) → true for 同意. In 基本模式 (not first) 不同意 just answers false. */
  private ask(why: string, first: boolean): Promise<boolean> {
    if (this.asking !== '') {
      return Promise.resolve(false);
    }
    return new Promise<boolean>((resolve) => {
      this.why = why;
      this.first = first;
      this.answer = (yes: boolean) => {
        this.asking = '';
        this.answer = () => {};
        resolve(yes);
      };
      this.asking = 'question';
    });
  }

  private showDoc(link: string): void {
    const d = Consent.docLink(link);
    if (!d) {
      return;
    }
    this.docId = d[0];
    this.docAt = d[1];
    this.docTitle = ConsentGate.docs().titles.get(d[0]) ?? '';
    if (this.docOpen) {
      this.loadDoc();
    } else {
      this.docCtl = new webview.WebviewController();
      this.docOpen = true;
    }
  }

  private docPage(): string {
    return Consent.page(ConsentGate.docs().html.get(this.docId) ?? '');
  }

  /** The doc as the doc layer's first address (a data: URL: no network, and nothing loads over it). */
  private docSrc(): string {
    const bytes = new util.TextEncoder().encodeInto(this.docPage());
    return 'data:text/html;charset=utf-8;base64,' + new util.Base64Helper().encodeToStringSync(bytes);
  }

  /** Another doc in the layer that is open (a link in one text to the other). */
  private loadDoc(): void {
    try {
      this.docCtl.loadData(this.docPage(), 'text/html', 'UTF-8');
    } catch (e) {
      AppState.warn('doc: ' + JSON.stringify(e));
    }
  }

  /** The back gesture: the doc first, then the page (FlowApp._back: a listener, an open sheet), the page before, away. */
  onBackPress(): boolean {
    if (this.docOpen) {
      this.docOpen = false;
      return true;
    }
    if (this.asking !== '' || !this.opened) {
      if (!this.opened) {
        const ctx = getContext(this) as common.UIAbilityContext;
        ctx.moveAbilityToBackground().catch(() => {});
      }
      return true;  // the question stays until it is answered
    }
    const js = '(function(){try{return !!(window.FlowApp&&FlowApp._back&&FlowApp._back())}catch(e){return false}})()';
    this.controller.runJavaScript(js).then((r: string) => {
      if (r === 'true') {
        return;
      }
      if (this.controller.accessBackward()) {
        this.controller.backward();
      } else {
        const ctx = getContext(this) as common.UIAbilityContext;
        ctx.moveAbilityToBackground().catch(() => {});
      }
    }).catch(() => {
      if (this.controller.accessBackward()) {
        this.controller.backward();
      }
    });
    return true;
  }

  build() {
    Stack() {
      Column() {
        if (this.opened && this.basic) {
          this.BasicBar()
        }
        if (this.opened) {
          this.SitePage()
        }
      }
      .width('100%')
      .height('100%')

      if (this.opened && this.failed) {
        this.Failed()
      }
      if (this.asking !== '') {
        this.Question()
      }
      if (this.docOpen) {
        this.Doc()
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.flow_bg'))
  }

  /** 基本模式's line over the page: what it means, and 「同意」 for everything. */
  @Builder
  BasicBar() {
    Column() {
      Row() {
        Text(Consent.BAR).fontSize(13).fontColor($r('app.color.flow_text')).layoutWeight(1).maxLines(2)
        Text('同意')
          .fontSize(14)
          .fontWeight(FontWeight.Bold)
          .fontColor($r('app.color.flow_accent'))
          .padding({ left: 14, right: 10, top: 10, bottom: 10 })
          .onClick(() => {
            ConsentGate.ask('');
          })
      }
      .width('100%')
      .padding({ left: 16, right: 6, top: 4, bottom: 4 })
      Divider().strokeWidth(0.5).color($r('app.color.flow_line'))
    }
    .width('100%')
    .backgroundColor($r('app.color.flow_surface'))
  }

  @Builder
  SitePage() {
    Web({ src: Site.startUrl(AppState.startPath), controller: this.controller })
      .width('100%')
      .layoutWeight(1)
      .backgroundColor($r('app.color.flow_bg'))  // no white flash before the page paints
      .javaScriptAccess(true)
      .domStorageAccess(true)
      .fileAccess(false)
      .geolocationAccess(false)
      .multiWindowAccess(false)
      .mixedMode(MixedMode.None)
      .mediaPlayGestureAccess(false)  // the next sentence may start by itself (the page unlocks audio in a tap anyway)
      .darkMode(WebDarkMode.Auto)     // prefers-color-scheme follows the phone; the site has its own dark colours
      .forceDarkAccess(false)
      .keyboardAvoidMode(WebKeyboardAvoidMode.RESIZE_CONTENT)
      .javaScriptOnDocumentStart(this.scripts)
      .javaScriptProxy({ object: this.bridge.proxy, name: 'flowNative', methodList: ['post'], controller: this.controller })
      .onControllerAttached(() => {
        // UA: ArkWeb's own, then FlowHarmony/<version> (docs/native-bridge.md §1; 04-home-app.js reads it)
        const ua = this.controller.getUserAgent() + ' FlowHarmony/' + Site.version;
        this.controller.setCustomUserAgent(ua);
        Site.userAgent = ua;
        AppState.startPath = undefined;
        if (ConsentGate.cachePending) {
          // 不同意 before there was a page: the cache from an earlier agreement goes now
          try {
            this.controller.removeCache(true);
            ConsentGate.cachePending = false;
          } catch (e) {
            AppState.warn('cache: ' + JSON.stringify(e));
          }
        }
      })
      .onLoadIntercept((event) => {
        const u = event.data.getRequestUrl();
        if (CalendarLink.isLink(u)) {
          CalendarLink.open(u);  // 「加到手机日历」: the system calendar's own new-event page
          return true;
        }
        if (Site.isOwn(u)) {
          return false;
        }
        if (u.startsWith('http://') || u.startsWith('https://') || u.startsWith('mailto:') || u.startsWith('tel:')) {
          AppState.openOutside(u);
        }
        return true;  // anything else (file:, intent:, …): nothing
      })
      .onInterceptRequest((event) => {
        // 基本模式: signing in or up asks first (Consent.SIGN_IN). The page's form gets a 403 that says why (its
        // `error`), and the question comes up; once agreed, the learner taps again.
        const req = event.request;
        const u = req.getRequestUrl();
        if (req.getRequestMethod().toUpperCase() !== 'POST' || !Site.isOwn(u)) {
          return null;
        }
        const p = Site.parse(u);
        if (!p || !Consent.signIn(p.pathname) || ConsentGate.current() === Consent.AGREED) {
          return null;
        }
        setTimeout(() => {
          ConsentGate.ask(Consent.WHY_SIGNIN);
        }, 0);
        const r = new WebResourceResponse();
        r.setResponseData(Consent.SIGN_IN_ANSWER);
        r.setResponseEncoding('utf-8');
        r.setResponseMimeType('application/json');
        r.setResponseCode(403);
        r.setReasonMessage('Forbidden');
        r.setResponseHeader([{ headerKey: 'Cache-Control', headerValue: 'no-store' }]);
        r.setResponseIsReady(true);
        return r;
      })
      .onPageBegin(() => {
        this.failed = false;
        this.bridge.pageStarted();
      })
      .onErrorReceive((event) => {
        if (event.request.isMainFrame()) {
          this.failed = true;
        }
      })
      .onPermissionRequest((event) => {
        // the page's own recorder (getUserMedia), for pages not on the bridge: this site only, once agreed (基本模式
        // asks first) and once the phone allows it
        const req = event.request;
        const wantsMic = req.getAccessibleResource().indexOf(ProtectedResourceType.AUDIO_CAPTURE) >= 0;
        if (!Site.isOwn(req.getOrigin()) || !wantsMic) {
          req.deny();
          return;
        }
        ConsentGate.ask(Consent.WHY_MIC).then((state: string) => {
          return state === Consent.AGREED ? Permissions.askMic() : false;
        }).then((ok: boolean) => {
          if (ok) {
            req.grant([ProtectedResourceType.AUDIO_CAPTURE]);
          } else {
            req.deny();
          }
        });
      })
      .onDownloadStart((event) => {
        AppState.openOutside(event.url);  // the guide's PDF: the browser saves it
      })
      .onRenderExited(() => {
        // the page's process was ended by the system (memory): load it again
        this.controller.refresh();
      })
  }

  @Builder
  Failed() {
    Column({ space: 12 }) {
      Text('网络连不上').fontSize(20).fontColor($r('app.color.flow_text'))
      Text('语流暂时打不开。看看网络，再点一下重试。').fontSize(15).fontColor($r('app.color.flow_muted'))
        .textAlign(TextAlign.Center).padding({ left: 32, right: 32 })
      Button('重试').margin({ top: 8 }).onClick(() => {
        this.failed = false;
        this.controller.refresh();
      })
    }
    .width('100%')
    .height('100%')
    .justifyContent(FlexAlign.Center)
    .backgroundColor($r('app.color.flow_bg'))
  }

  /** The question, or its second look, as a dialog over a dimmed screen (nothing behind it on the first start). */
  @Builder
  Question() {
    Column() {
      Column() {
        Text(this.asking === 'second' ? Consent.BASIC_TITLE : (this.why ? Consent.TITLE_FEATURE : Consent.TITLE))
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor($r('app.color.flow_text'))
          .width('100%')
          .padding({ left: 24, right: 24, top: 24, bottom: 8 })
        Scroll() {
          if (this.asking === 'second') {
            Text(Consent.BASIC_BODY)
              .fontSize(15)
              .lineHeight(23)
              .fontColor($r('app.color.flow_text'))
              .width('100%')
          } else {
            Text() {
              ForEach(Consent.parts(Consent.question(this.why, this.first, ConsentGate.lists()), ConsentGate.lists()),
                (p: string[]) => {
                  if (p[1]) {
                    Span(p[0]).fontColor($r('app.color.flow_accent')).onClick(() => this.showDoc(p[1]))
                  } else {
                    Span(p[0]).fontColor($r('app.color.flow_text'))
                  }
                }, (p: string[], i: number) => i + ':' + p[0])
            }
            .fontSize(15)
            .lineHeight(23)
            .width('100%')
          }
        }
        .padding({ left: 24, right: 24 })
        .scrollBar(BarState.Auto)
        .align(Alignment.Top)
        .layoutWeight(this.asking === 'second' ? 0 : 1)
        Row({ space: 12 }) {
          Button(this.asking === 'second' ? '再看看' : '不同意', { type: ButtonType.Capsule })
            .layoutWeight(1)
            .height(40)
            .fontSize(16)
            .fontColor($r('app.color.flow_text'))
            .backgroundColor($r('app.color.flow_line'))
            .onClick(() => {
              if (this.asking === 'second') {
                this.asking = 'question';          // 再看看: the question again
              } else if (this.first) {
                this.asking = 'second';            // the first start: the second look
              } else {
                this.answer(false);
              }
            })
          Button(this.asking === 'second' ? '进入基本模式' : '同意', { type: ButtonType.Capsule })
            .layoutWeight(1)
            .height(40)
            .fontSize(16)
            .fontColor(Color.White)
            .backgroundColor($r('app.color.flow_accent'))
            .onClick(() => {
              this.answer(this.asking !== 'second');  // 同意 → true; 进入基本模式 → false
            })
        }
        .width('100%')
        .padding({ left: 24, right: 24, top: 16, bottom: 20 })
      }
      .width('88%')
      .height(this.asking === 'second' ? 'auto' : '76%')  // the question's text scrolls inside; its buttons stay
      .constraintSize({ maxWidth: 480 })
      .borderRadius(24)
      .backgroundColor($r('app.color.flow_surface'))
    }
    .width('100%')
    .height('100%')
    .justifyContent(FlexAlign.Center)
    .backgroundColor(this.opened ? $r('app.color.flow_scrim') : $r('app.color.flow_bg'))
  }

  /**
   * One of the two texts over everything (the question too): 「← 返回」 and its title on top, 「返回」 at the end. A link
   * to the other text (or a part of one) opens it here; a link to a site opens the phone's browser. No network.
   */
  @Builder
  Doc() {
    Column() {
      Row() {
        Text('← 返回')
          .fontSize(16)
          .fontColor($r('app.color.flow_accent'))
          .padding({ left: 16, right: 12, top: 14, bottom: 14 })
          .onClick(() => {
            this.docOpen = false;
          })
        Text(this.docTitle).fontSize(17).fontWeight(FontWeight.Bold).fontColor($r('app.color.flow_text'))
          .maxLines(1).layoutWeight(1)
      }
      .width('100%')
      Web({ src: this.docSrc(), controller: this.docCtl })
        .width('100%')
        .layoutWeight(1)
        .backgroundColor($r('app.color.flow_bg'))
        .javaScriptAccess(true)  // only to go to a part of a text (scrollIntoView): the page is this app's own
        .domStorageAccess(false)
        .fileAccess(false)
        .geolocationAccess(false)
        .blockNetwork(true)
        .darkMode(WebDarkMode.Auto)
        .forceDarkAccess(false)
        .onLoadIntercept((event) => {
          const u = event.data.getRequestUrl();
          if (u.startsWith('data:')) {
            return false;
          }
          if (Consent.docLink(u)) {
            this.showDoc(u);
          } else if (u.startsWith('https://')) {
            AppState.openOutside(u);
          }
          return true;
        })
        .onPageEnd(() => {
          if (this.docAt) {
            const at = this.docAt;
            this.docAt = '';
            this.docCtl.runJavaScript("var e=document.getElementById('" + at + "');if(e)e.scrollIntoView()")
              .catch(() => {});
          }
        })
        .onRenderExited(() => {
          this.docOpen = false;  // ended by the system (memory): this layer closes, the question stays
        })
      Row() {
        Button('返回', { type: ButtonType.Capsule })
          .width('100%')
          .height(44)
          .fontSize(16)
          .fontColor(Color.White)
          .backgroundColor($r('app.color.flow_accent'))
          .onClick(() => {
            this.docOpen = false;
          })
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 8, bottom: 12 })
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.flow_bg'))
  }
}
