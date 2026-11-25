//! The User-Agent: the webview's own, with `FlowDesktop/<版本> (Windows|macOS)` at the end, so the site and its
//! logs can tell the desktop app apart (like `FlowiOS/<版本>` in the iOS app).

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Os {
    MacOs,
    Windows,
}

impl Os {
    pub fn current() -> Self {
        if cfg!(target_os = "windows") {
            Os::Windows
        } else {
            Os::MacOs
        }
    }
    /// FlowApp.platform in the page
    pub fn platform(self) -> &'static str {
        match self {
            Os::MacOs => "macos",
            Os::Windows => "windows",
        }
    }
    fn label(self) -> &'static str {
        match self {
            Os::MacOs => "macOS",
            Os::Windows => "Windows",
        }
    }
}

pub fn suffix(os: Os, app_version: &str) -> String {
    format!("FlowDesktop/{app_version} ({})", os.label())
}

/// `webview` is what the system webview reports (WebView2: "131.0.2903.70"); macOS's WKWebView string is fixed.
pub fn user_agent(os: Os, app_version: &str, webview: Option<&str>) -> String {
    let base = match os {
        // WKWebView's own (frozen) User-Agent on every macOS version
        Os::MacOs => "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko)".to_string(),
        Os::Windows => {
            let full = webview
                .filter(|v| !v.is_empty() && v.chars().all(|c| c.is_ascii_digit() || c == '.'))
                .unwrap_or("140.0.0.0");
            let major = full.split('.').next().unwrap_or("140");
            // Edge's form; Chromium reports only the major version of Chrome
            format!("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36 Edg/{full}")
        }
    };
    format!("{base} {}", suffix(os, app_version))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mac_user_agent_ends_with_flow_desktop() {
        let ua = user_agent(Os::MacOs, "0.1.0", None);
        assert!(ua.starts_with("Mozilla/5.0 (Macintosh;"));
        assert!(ua.ends_with(" FlowDesktop/0.1.0 (macOS)"), "{ua}");
    }

    #[test]
    fn windows_user_agent_uses_webview2_version() {
        let ua = user_agent(Os::Windows, "0.1.0", Some("131.0.2903.70"));
        assert!(
            ua.contains("Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.70"),
            "{ua}"
        );
        assert!(ua.ends_with(" FlowDesktop/0.1.0 (Windows)"), "{ua}");
        // unknown or odd version strings fall back instead of going into the header
        let ua = user_agent(Os::Windows, "0.1.0", Some("x\r\nEvil: 1"));
        assert!(ua.contains("Chrome/140.0.0.0") && !ua.contains('\n'));
    }

    #[test]
    fn page_regex_matches() {
        // what the page would test: /FlowDesktop\/[\d.]+ \((Windows|macOS)\)/
        for os in [Os::MacOs, Os::Windows] {
            let s = suffix(os, "1.2.3");
            assert!(s == "FlowDesktop/1.2.3 (macOS)" || s == "FlowDesktop/1.2.3 (Windows)");
        }
        assert_eq!(Os::MacOs.platform(), "macos");
        assert_eq!(Os::Windows.platform(), "windows");
    }
}
