import UIKit
import WebKit

/// The site, edge to edge. The page lays itself out under the status bar and the home indicator (viewport-fit=cover,
/// env(safe-area-inset-*)); its bottom edge rides on the keyboard, so what the page sees is the part above it.
final class WebViewController: UIViewController, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    let webView: WKWebView
    private let bridge: Bridge
    private let reminders: Reminders
    private let site: SiteClient
    private let refresh = UIRefreshControl()
    private var errorView: UIView?
    private var downloads: [ObjectIdentifier: URL] = [:]
    private var started = false
    private var pendingPath: String?  // a page asked for (a reminder tapped) before the site had finished loading

    init(bridge: Bridge, reminders: Reminders, site: SiteClient) {
        self.bridge = bridge
        self.reminders = reminders
        self.site = site
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .default()
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = []
        cfg.allowsAirPlayForMediaPlayback = true
        // the site's own domains only (Info.plist WKAppBoundDomains): its service worker works, nothing else can be
        // navigated to in here (other sites open in the system browser)
        cfg.limitsNavigationsToAppBoundDomains = true
        cfg.applicationNameForUserAgent = AppConfig.userAgentSuffix
        cfg.preferences.javaScriptCanOpenWindowsAutomatically = false
        bridge.install(in: cfg.userContentController)
        webView = WKWebView(frame: .zero, configuration: cfg)
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("not used") }

    override func viewDidLoad() {
        super.viewDidLoad()
        let bg = UIColor(named: "LaunchBackground") ?? .systemBackground
        view.backgroundColor = bg
        webView.isOpaque = false  // no white flash before the page paints (dark mode)
        webView.backgroundColor = bg
        webView.scrollView.backgroundColor = bg
        webView.underPageBackgroundColor = bg
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.allowsLinkPreview = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.accessibilityIdentifier = "flow.web"
        #if BETA
        webView.isInspectable = true  // Safari → 开发 → Simulator / iPhone (tools/ios_sim_check.py works in the app too)
        #endif
        webView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(webView)
        view.keyboardLayoutGuide.usesBottomSafeArea = false
        view.keyboardLayoutGuide.followsUndockedKeyboard = true
        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: view.topAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            webView.bottomAnchor.constraint(equalTo: view.keyboardLayoutGuide.topAnchor),
        ])
        refresh.addTarget(self, action: #selector(pulled), for: .valueChanged)
        webView.scrollView.refreshControl = refresh
        Task { await start() }
    }

    private func start() async {
        guard !started else { return }
        started = true
        await site.ready?.value  // the saved session is back in WebKit (Shell, CookieKeeper)
        #if BETA
        if ProcessInfo.processInfo.environment["FLOW_BRIDGE_TEST"] == "1" {
            webView.loadHTMLString(BridgeTestPage.html, baseURL: AppConfig.site)
            return
        }
        #endif
        load(AppConfig.start)
    }

    func load(_ url: URL) {
        hideError()
        webView.load(URLRequest(url: url))
    }

    /// A page of the site from outside (a reminder tapped): "#/review" while the site is open; otherwise it waits for
    /// the site to finish loading (a cold launch from the notification) and is opened then (didFinish).
    func open(path: String) {
        guard path.hasPrefix("#") else {
            if let url = URL(string: path, relativeTo: AppConfig.start)?.absoluteURL { load(url) }
            return
        }
        if started, !webView.isLoading, let now = webView.url, AppConfig.isOwn(now), errorView == nil {
            webView.evaluateJavaScript("location.hash = \(Bridge.js(path))", completionHandler: nil)
        } else {
            pendingPath = path
            if started, !webView.isLoading { load(AppConfig.start) }
        }
    }

    @objc private func pulled() {
        if webView.url == nil || errorView != nil { load(AppConfig.start) } else { webView.reload() }
    }

    // MARK: navigation

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction) async -> WKNavigationActionPolicy {
        guard let url = action.request.url else { return .cancel }
        if action.shouldPerformDownload { return .download }
        switch url.scheme?.lowercased() ?? "" {
        case "about", "blob", "data":
            return .allow
        case "http", "https":
            if AppConfig.isOwn(url) {
                if url.path.hasSuffix("/reminder.ics") {  // 「加到手机日历」: in the app, a notification is the better reminder
                    remindChoice(url)
                    return .cancel
                }
                if action.targetFrame == nil {  // target=_blank on the site itself: here
                    webView.load(action.request)
                    return .cancel
                }
                return .allow
            }
            if action.targetFrame?.isMainFrame == false { return .allow }
            await UIApplication.shared.open(url)
            return .cancel
        default:  // mailto:, tel:, the App Store …
            await UIApplication.shared.open(url)
            return .cancel
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse) async -> WKNavigationResponsePolicy {
        if let http = response.response as? HTTPURLResponse,
           let cd = http.value(forHTTPHeaderField: "Content-Disposition"), cd.lowercased().hasPrefix("attachment") {
            return .download
        }
        return response.canShowMIMEType ? .allow : .download
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        refresh.endRefreshing()
        hideError()
        if let p = pendingPath, let now = webView.url, AppConfig.isOwn(now) {
            pendingPath = nil
            webView.evaluateJavaScript("location.hash = \(Bridge.js(p))", completionHandler: nil)
        }
        bridge.resendState()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        refresh.endRefreshing()
        if !Self.ignorable(error) { showError(error) }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        refresh.endRefreshing()
    }

    // The page's process was ended by iOS (memory, a long time in the background): load it again. A whole text
    // playing natively goes on meanwhile; the page asks for its state when it is back.
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        if webView.url != nil { webView.reload() } else { load(AppConfig.start) }
    }

    static func ignorable(_ error: Error) -> Bool {
        let e = error as NSError
        if e.domain == NSURLErrorDomain && e.code == NSURLErrorCancelled { return true }
        if e.domain == "WebKitErrorDomain" && (e.code == 102 || e.code == 204) { return true }  // policy change, plug-in handled
        return false
    }

    // MARK: the page's own dialogs (confirm() before deleting, alert(), prompt()), new windows, the microphone

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo) async {
        await withCheckedContinuation { (done: CheckedContinuation<Void, Never>) in
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "好", style: .default) { _ in done.resume() })
            present(a) { done.resume() }
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo) async -> Bool {
        await withCheckedContinuation { (done: CheckedContinuation<Bool, Never>) in
            let a = UIAlertController(title: nil, message: message, preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in done.resume(returning: false) })
            a.addAction(UIAlertAction(title: "确定", style: .default) { _ in done.resume(returning: true) })
            present(a) { done.resume(returning: false) }
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?, initiatedByFrame frame: WKFrameInfo) async -> String? {
        await withCheckedContinuation { (done: CheckedContinuation<String?, Never>) in
            let a = UIAlertController(title: nil, message: prompt, preferredStyle: .alert)
            a.addTextField { $0.text = defaultText }
            a.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in done.resume(returning: nil) })
            a.addAction(UIAlertAction(title: "确定", style: .default) { [weak a] _ in done.resume(returning: a?.textFields?.first?.text ?? "") })
            present(a) { done.resume(returning: nil) }
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url {
            if AppConfig.isOwn(url) { webView.load(action.request) } else { UIApplication.shared.open(url) }
        }
        return nil
    }

    // getUserMedia on the site (pages not yet on the native recorder): no second question after iOS's own
    func webView(_ webView: WKWebView, decideMediaCapturePermissionsFor origin: WKSecurityOrigin, initiatedBy frame: WKFrameInfo, type: WKMediaCaptureType) async -> WKPermissionDecision {
        AppConfig.isOwnOrigin(host: origin.host, scheme: origin.protocol) && type == .microphone ? .grant : .deny
    }

    // MARK: downloads (导出我的数据 …): saved, then the share sheet (存到「文件」, AirDrop …)

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String) async -> URL? {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("downloads", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let name = suggestedFilename.isEmpty ? "flow-download" : suggestedFilename
        let url = dir.appendingPathComponent(name)
        try? FileManager.default.removeItem(at: url)
        downloads[ObjectIdentifier(download)] = url
        return url
    }

    func downloadDidFinish(_ download: WKDownload) {
        guard let url = downloads.removeValue(forKey: ObjectIdentifier(download)) else { return }
        let share = UIActivityViewController(activityItems: [url], applicationActivities: nil)
        present(share)
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        downloads.removeValue(forKey: ObjectIdentifier(download))
        say("下载没有完成", "网络不太好，稍后再试一次。")
    }

    // MARK: 「加到手机日历」 → a notification, or the calendar

    private func remindChoice(_ url: URL) {
        let q = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        let v = { (k: String) in q.first { $0.name == k }?.value }
        // the same checks as the server's ics(): an hour of REMIND_HOURS, minutes of 5/10/15/20/30
        let hour = v("hour").flatMap(Int.init).flatMap { ReminderPlan.hours.contains($0) ? $0 : nil }
        let minutes = v("minutes").flatMap(Int.init).flatMap { ReminderPlan.planMinutes.contains($0) ? $0 : nil } ?? 10
        let at = v("at").flatMap(Double.init).flatMap { $0 > Date().timeIntervalSince1970 ? Date(timeIntervalSince1970: $0) : nil }
        let ask = ReminderAsk(kind: v("kind") == "plan" ? .plan : .vocab, hour: hour, minutes: minutes, at: at)
        let sheet = UIAlertController(title: "怎么提醒你？", message: ask.when, preferredStyle: .actionSheet)
        sheet.addAction(UIAlertAction(title: "用 App 通知提醒（推荐）", style: .default) { [weak self] _ in
            Task { await self?.notify(ask) }
        })
        sheet.addAction(UIAlertAction(title: "加到系统日历", style: .default) { [weak self] _ in
            guard let self else { return }
            CalendarAdd.present(from: self, ask: ask)
        })
        sheet.addAction(UIAlertAction(title: "取消", style: .cancel))
        present(sheet)
    }

    private func notify(_ ask: ReminderAsk) async {
        switch await reminders.optIn(ask) {
        case .scheduled(let line): say("好", line)
        case .denied:
            let a = UIAlertController(title: "通知没有打开", message: "到 iPhone 的「设置 → \(Bundle.main.displayName) → 通知」打开「允许通知」，再点一次。", preferredStyle: .alert)
            a.addAction(UIAlertAction(title: "去设置", style: .default) { _ in
                if let u = URL(string: UIApplication.openNotificationSettingsURLString) { UIApplication.shared.open(u) }
            })
            a.addAction(UIAlertAction(title: "先不用", style: .cancel))
            present(a)
        case .failed(let why): say("没有排上提醒", why)
        }
    }

    // MARK: helpers

    func say(_ title: String, _ message: String) {
        let a = UIAlertController(title: title, message: message, preferredStyle: .alert)
        a.addAction(UIAlertAction(title: "好", style: .default))
        present(a)
    }

    /// Shows vc from the top view controller (an alert may already be up). When nothing can show it (the app in the
    /// background), `otherwise` runs instead, so a page's alert() / confirm() is always answered. UIKit drops a
    /// presentation asked for while another one is coming or going (an action sheet closing): it waits for that first.
    func present(_ vc: UIViewController, otherwise: (() -> Void)? = nil) {
        guard view.window != nil else { otherwise?(); return }
        var top: UIViewController = self
        while let p = top.presentedViewController, !p.isBeingDismissed { top = p }
        if let moving = top.presentedViewController ?? (top.isBeingPresented ? top : nil), let tc = moving.transitionCoordinator {
            tc.animate(alongsideTransition: nil) { [weak self] _ in
                guard let self else { otherwise?(); return }
                self.present(vc, otherwise: otherwise)
            }
            return
        }
        if let pop = vc.popoverPresentationController {  // iPad: action sheets and the share sheet need an anchor
            pop.sourceView = view
            pop.sourceRect = CGRect(x: view.bounds.midX, y: view.bounds.maxY - 80, width: 1, height: 1)
            pop.permittedArrowDirections = []
        }
        top.present(vc, animated: true)
    }

    private func showError(_ error: Error) {
        hideError()
        let box = UIStackView()
        box.axis = .vertical
        box.alignment = .center
        box.spacing = 14
        box.translatesAutoresizingMaskIntoConstraints = false
        let title = UILabel()
        title.text = "连不上语流"
        title.font = .preferredFont(forTextStyle: .title2)
        let detail = UILabel()
        detail.text = Self.offline(error) ? "手机现在没有网络。连上网以后再试一次。" : "网络不太好，或者服务器正在更新。过一会儿再试一次。"
        detail.font = .preferredFont(forTextStyle: .body)
        detail.textColor = .secondaryLabel
        detail.numberOfLines = 0
        detail.textAlignment = .center
        var conf = UIButton.Configuration.filled()
        conf.title = "再试一次"
        conf.cornerStyle = .capsule
        let again = UIButton(configuration: conf, primaryAction: UIAction { [weak self] _ in self?.load(AppConfig.start) })
        again.accessibilityIdentifier = "flow.retry"
        [title, detail, again].forEach(box.addArrangedSubview)
        let cover = UIView()
        cover.backgroundColor = view.backgroundColor
        cover.translatesAutoresizingMaskIntoConstraints = false
        cover.addSubview(box)
        view.addSubview(cover)
        NSLayoutConstraint.activate([
            cover.topAnchor.constraint(equalTo: view.topAnchor), cover.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            cover.leadingAnchor.constraint(equalTo: view.leadingAnchor), cover.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            box.centerYAnchor.constraint(equalTo: cover.centerYAnchor),
            box.leadingAnchor.constraint(equalTo: cover.layoutMarginsGuide.leadingAnchor, constant: 16),
            box.trailingAnchor.constraint(equalTo: cover.layoutMarginsGuide.trailingAnchor, constant: -16),
        ])
        errorView = cover
    }

    private func hideError() {
        errorView?.removeFromSuperview()
        errorView = nil
    }

    static func offline(_ error: Error) -> Bool {
        let e = error as NSError
        return e.domain == NSURLErrorDomain && [NSURLErrorNotConnectedToInternet, NSURLErrorNetworkConnectionLost, NSURLErrorDataNotAllowed].contains(e.code)
    }
}

extension Bundle {
    var displayName: String { (object(forInfoDictionaryKey: "CFBundleDisplayName") as? String) ?? "语流" }
}
