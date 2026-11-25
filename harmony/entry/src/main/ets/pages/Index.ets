import { webview } from '@kit.ArkWeb';
import { common } from '@kit.AbilityKit';
import { AppState } from '../common/AppState';
import { Site } from '../common/Site';
import { Permissions } from '../common/Permissions';
import { Bridge } from '../bridge/Bridge';

/**
 * The app: the site in an ArkWeb web view (so every change to the site is in the app at once), with the native parts
 * behind window.FlowApp (Bridge). Signed in as on the site (the web view's own cookies, kept on the phone); the back
 * gesture goes back in the page; other sites open in the phone's browser; light and dark follow the phone at once; the
 * page ends at the keyboard (RESIZE_CONTENT), as in Android's app.
 */
@Entry
@Component
struct Index {
  private controller: webview.WebviewController = new webview.WebviewController();
  private bridge: Bridge = new Bridge(this.controller);
  private scripts: Array<ScriptItem> = [];
  @State failed: boolean = false;

  aboutToAppear(): void {
    webview.WebviewController.setWebDebuggingAccess(Site.debug);
    const ctx = getContext(this) as common.UIAbilityContext;
    this.scripts = [{ script: this.bridge.script(ctx.resourceManager), scriptRules: [Site.origin] }];
    AppState.web = this.controller;
  }

  aboutToDisappear(): void {
    AppState.web = undefined;
  }

  /** The back gesture: the page first (FlowApp._back: a listener, an open sheet), then the page before, then away. */
  onBackPress(): boolean {
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
      Web({ src: Site.startUrl(AppState.startPath), controller: this.controller })
        .width('100%')
        .height('100%')
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
        })
        .onLoadIntercept((event) => {
          const u = event.data.getRequestUrl();
          if (Site.isOwn(u)) {
            return false;
          }
          if (u.startsWith('http://') || u.startsWith('https://') || u.startsWith('mailto:') || u.startsWith('tel:')) {
            AppState.openOutside(u);
          }
          return true;  // anything else (file:, intent:, …): nothing
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
          // the page's own recorder (getUserMedia), for pages not on the bridge: this site only, once the phone allows it
          const req = event.request;
          const wantsMic = req.getAccessibleResource().indexOf(ProtectedResourceType.MicStream) >= 0;
          if (!Site.isOwn(req.getOrigin()) || !wantsMic) {
            req.deny();
            return;
          }
          Permissions.askMic().then((ok: boolean) => {
            if (ok) {
              req.grant([ProtectedResourceType.MicStream]);
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

      if (this.failed) {
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
    }
    .width('100%')
    .height('100%')
    .backgroundColor($r('app.color.flow_bg'))
  }
}
