import UIKit

/// The site's 主题色 (我的 → 外观: 松绿, the default, or 靛蓝; the page's html data-accent, PR #282): what the app draws
/// itself follows it (an alert's buttons, pull-to-refresh, the error view's 再试一次). The logo, the launch screen and
/// the 「AI 朗读」 marks keep their colours. Values as flow/public/src/next/00-base.css and 99-accent.css.
enum Accent {
    static let key = "flow.accent"

    static func color(_ name: String?) -> UIColor {
        let indigo = name == "indigo"
        return UIColor { t in
            switch (indigo, t.userInterfaceStyle == .dark) {
            case (true, false): return UIColor(rgb: 0x3461D1)
            case (true, true): return UIColor(rgb: 0x8EAEFC)
            case (false, false): return UIColor(rgb: 0x1F9D55)
            case (false, true): return UIColor(rgb: 0x3CCF7C)
            }
        }
    }

    /// The page's names: 'indigo', anything else is the default green
    static func name(_ s: String?) -> String { s == "indigo" ? "indigo" : "green" }

    /// The last one the page showed, for the next launch (before the page is there)
    static var saved: String? { UserDefaults.standard.string(forKey: key) }
    static func save(_ name: String) { UserDefaults.standard.set(name, forKey: key) }

    /// In the page's own world, main frame: html[data-accent] now and whenever 外观 changes it → app.accent
    static let script = """
    (() => {
      const h = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.flow;
      if (!h || !document.documentElement) return;
      let last = null;
      const send = () => {
        const a = document.documentElement.dataset.accent || 'green';
        if (a === last) return;
        last = a;
        try { Promise.resolve(h.postMessage({ cmd: 'app.accent', args: { accent: a } })).catch(() => {}); } catch (e) { /* ignore */ }
      };
      send();
      new MutationObserver(send).observe(document.documentElement, { attributes: true, attributeFilter: ['data-accent'] });
    })();
    """
}

extension UIColor {
    convenience init(rgb: Int) {
        self.init(red: CGFloat((rgb >> 16) & 0xFF) / 255, green: CGFloat((rgb >> 8) & 0xFF) / 255, blue: CGFloat(rgb & 0xFF) / 255, alpha: 1)
    }
}
