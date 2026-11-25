//! Where a link goes: pages of the site stay in the window; other sites, mail and phone links, calendar files
//! and downloads go to the system (default browser, Mail, Calendar).

use url::Url;

#[derive(Debug, PartialEq, Eq)]
pub enum Nav {
    /// Load it in the app's window.
    InApp,
    /// Hand it to the system: the default browser, Mail, Calendar …
    System,
    /// Nothing to do (javascript:, file:, unknown schemes).
    Ignore,
}

pub fn same_site(site: &Url, u: &Url) -> bool {
    u.scheme() == site.scheme()
        && u.host_str() == site.host_str()
        && u.port_or_known_default() == site.port_or_known_default()
}

pub fn classify(site: &Url, u: &Url) -> Nav {
    match u.scheme() {
        "about" | "data" | "blob" => Nav::InApp,
        "mailto" | "tel" | "sms" | "weixin" => Nav::System,
        "http" | "https" => {
            if !same_site(site, u) {
                return Nav::System;
            }
            // the reminder calendar (/api/next/vocab/reminder.ics): the system opens it with Calendar or Outlook
            if u.path().ends_with(".ics") {
                return Nav::System;
            }
            Nav::InApp
        }
        _ => Nav::Ignore,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(s: &str) -> Nav {
        classify(
            &Url::parse("https://flowlang.cn/").unwrap(),
            &Url::parse(s).unwrap(),
        )
    }

    #[test]
    fn site_pages_stay() {
        assert_eq!(c("https://flowlang.cn/#/review"), Nav::InApp);
        assert_eq!(c("https://flowlang.cn/guide"), Nav::InApp);
        assert_eq!(c("about:blank"), Nav::InApp);
    }

    #[test]
    fn everything_else_goes_out() {
        assert_eq!(c("https://jasa.hk/"), Nav::System);
        assert_eq!(c("https://flowlang.cn.evil.example/"), Nav::System);
        assert_eq!(c("http://flowlang.cn/"), Nav::System); // not https: not the app's site
        assert_eq!(c("https://flowlang.cn:8443/"), Nav::System);
        assert_eq!(c("mailto:hi@flowlang.cn"), Nav::System);
        assert_eq!(
            c("https://flowlang.cn/api/next/vocab/reminder.ics?hour=20"),
            Nav::System
        );
        assert_eq!(c("javascript:alert(1)"), Nav::Ignore);
        assert_eq!(c("file:///etc/passwd"), Nav::Ignore);
    }
}
