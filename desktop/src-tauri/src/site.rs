//! Which 语流 the app opens: the Beta build opens 内测版 (flow.jasa.hk), the Release build 正式版 (flowlang.cn).
//! The bundle identifier decides it (tauri.beta.conf.json sets `cn.flowlang.desktop.beta`), so one binary
//! cannot open the wrong site.

use url::Url;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Channel {
    Beta,
    Release,
}

impl Channel {
    pub fn from_identifier(identifier: &str) -> Self {
        if identifier.ends_with(".beta") {
            Channel::Beta
        } else {
            Channel::Release
        }
    }

    pub fn site(self) -> &'static str {
        match self {
            Channel::Beta => "https://flow.jasa.hk/",
            Channel::Release => "https://flowlang.cn/",
        }
    }

    /// The URL scheme a notification click (Windows) or another program uses to open this build: flowlang://review
    pub fn scheme(self) -> &'static str {
        match self {
            Channel::Beta => "flowlang-beta",
            Channel::Release => "flowlang",
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Channel::Beta => "语流内测",
            Channel::Release => "语流",
        }
    }
}

/// The site this run opens. Debug builds may point at a local server for testing:
/// `FLOW_DESKTOP_SITE=http://127.0.0.1:8090/ npm run dev`. Release builds ignore the variable.
pub fn site_url(channel: Channel) -> Url {
    #[cfg(debug_assertions)]
    if let Ok(v) = std::env::var("FLOW_DESKTOP_SITE") {
        if let Ok(u) = Url::parse(&v) {
            return u;
        }
    }
    Url::parse(channel.site()).expect("site URL")
}

/// flowlang://review, flowlang://open/#/cards, flowlang:///#/vocab/plan → the page of the site to show.
/// Anything else (another scheme, a different host smuggled in) → the site's home page.
pub fn deep_link_target(site: &Url, scheme: &str, link: &str) -> Url {
    let home = site.clone();
    let Ok(u) = Url::parse(link) else { return home };
    if u.scheme() != scheme {
        return home;
    }
    // the route is the fragment when there is one (#/review), else the host + path (flowlang://review → #/review)
    let route = match u.fragment() {
        Some(f) if !f.is_empty() => f.trim_start_matches('/').to_string(),
        _ => {
            let mut r = u.host_str().unwrap_or("").to_string();
            let p = u.path().trim_matches('/');
            if r == "open" {
                r.clear();
            }
            if !p.is_empty() {
                if !r.is_empty() {
                    r.push('/');
                }
                r.push_str(p);
            }
            r
        }
    };
    let route: String = route
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || "/-_=&?.".contains(*c))
        .collect();
    let mut out = home;
    let frag = format!("/{route}");
    out.set_fragment(if route.is_empty() { None } else { Some(&frag) });
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn channel_from_identifier() {
        assert_eq!(
            Channel::from_identifier("cn.flowlang.desktop.beta"),
            Channel::Beta
        );
        assert_eq!(
            Channel::from_identifier("cn.flowlang.desktop"),
            Channel::Release
        );
        assert_eq!(Channel::Beta.site(), "https://flow.jasa.hk/");
        assert_eq!(Channel::Release.site(), "https://flowlang.cn/");
        assert_eq!(Channel::Beta.scheme(), "flowlang-beta");
    }

    #[test]
    fn deep_links() {
        let site = Url::parse("https://flowlang.cn/").unwrap();
        let t = |l: &str| deep_link_target(&site, "flowlang", l).to_string();
        assert_eq!(t("flowlang://review"), "https://flowlang.cn/#/review");
        assert_eq!(
            t("flowlang://vocab/plan"),
            "https://flowlang.cn/#/vocab/plan"
        );
        assert_eq!(t("flowlang://open/#/cards"), "https://flowlang.cn/#/cards");
        assert_eq!(t("flowlang://open"), "https://flowlang.cn/");
        assert_eq!(t("flowlang:"), "https://flowlang.cn/");
        // another scheme or garbage: just the home page, never another site
        assert_eq!(t("https://evil.example/#/x"), "https://flowlang.cn/");
        assert_eq!(t("not a url"), "https://flowlang.cn/");
        // quotes and markup never reach the page: the link is refused or cleaned
        for bad in [
            "flowlang://review\"><script>",
            "flowlang://open/#/x'\"<b>",
            "flowlang://open/#/../../etc",
        ] {
            let u = t(bad);
            assert!(
                u.starts_with("https://flowlang.cn/") && !u.contains(['"', '\'', '<', '>']),
                "{u}"
            );
        }
    }
}
