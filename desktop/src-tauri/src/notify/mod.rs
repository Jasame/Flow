//! 复习提醒: system notifications scheduled ahead of time, so they come even when 语流 is not open
//! (macOS: UserNotifications; Windows: scheduled toasts). schedule.rs decides when; this sends them to the system.

#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "macos")]
pub use macos::*;

#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "windows")]
pub use self::windows::*;

/// Notifications without their sound (FLOW_MUTE=1, smoke tests).
static SILENT: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
pub fn set_silent(on: bool) {
    SILENT.store(on, std::sync::atomic::Ordering::Relaxed);
}
pub fn silent() -> bool {
    SILENT.load(std::sync::atomic::Ordering::Relaxed)
}

/// FlowApp.notify.permission(): 'granted' | 'denied' | 'undetermined' | 'provisional' (docs/native-bridge.md §5)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Permission {
    Granted,
    Denied,
    Undetermined,
    /// macOS: delivered quietly to Notification Centre — still allowed
    #[allow(dead_code)]
    Provisional,
}

impl Permission {
    pub fn as_str(self) -> &'static str {
        match self {
            Permission::Granted => "granted",
            Permission::Denied => "denied",
            Permission::Undetermined => "undetermined",
            Permission::Provisional => "provisional",
        }
    }
    /// notifications will be shown
    pub fn ok(self) -> bool {
        matches!(self, Permission::Granted | Permission::Provisional)
    }
}

#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
/// The toast XML Windows shows (pure, so it is tested everywhere). A click opens `launch` (flowlang://review).
pub fn toast_xml(title: &str, body: &str, launch: &str, silent: bool) -> String {
    format!(
        r#"<toast launch="{}" activationType="protocol"><visual><binding template="ToastGeneric"><text>{}</text><text>{}</text></binding></visual>{}</toast>"#,
        xml_escape(launch),
        xml_escape(title),
        xml_escape(body),
        if silent {
            r#"<audio silent="true"/>"#
        } else {
            ""
        }
    )
}

#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
pub fn xml_escape(s: &str) -> String {
    let mut o = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => o.push_str("&amp;"),
            '<' => o.push_str("&lt;"),
            '>' => o.push_str("&gt;"),
            '"' => o.push_str("&quot;"),
            '\'' => o.push_str("&apos;"),
            c if (c as u32) < 0x20 && c != '\n' && c != '\t' => {}
            c => o.push(c),
        }
    }
    o
}

/// The click target of a notification id: word reminders open the review, the day's plan the home page.
#[cfg_attr(not(target_os = "macos"), allow(dead_code))]
pub fn route_of(id: &str) -> Option<&'static str> {
    if id.starts_with("review-") {
        Some("/review")
    } else if id.starts_with("plan-") {
        Some("/")
    } else {
        None
    }
}

/// Windows tags are at most 16 characters: review-2026-11-27 → r20261127, plan-… → p…, review-once → once.
#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
pub fn tag_of(id: &str) -> String {
    let short = |prefix: &str, rest: &str| format!("{prefix}{}", rest.replace('-', ""));
    let t = if id == "review-once" {
        "once".to_string()
    } else if let Some(r) = id.strip_prefix("review-") {
        short("r", r)
    } else if let Some(r) = id.strip_prefix("plan-") {
        short("p", r)
    } else {
        id.to_string()
    };
    t.chars().take(16).collect()
}

/// A system without a backend (other targets, unit tests): nothing is scheduled.
#[cfg(not(any(target_os = "macos", target_os = "windows")))]
mod none {
    use super::*;
    use crate::schedule::Planned;
    pub fn init(_id: &str, _on_click: impl Fn(Option<&'static str>) + Send + Sync + 'static) {}
    pub fn permission() -> Permission {
        Permission::Denied
    }
    pub fn ask() -> bool {
        false
    }
    pub fn schedule(_items: &[Planned], _scheme: &str) -> Result<usize, String> {
        Ok(0)
    }
    pub fn clear() {}
    pub fn pending() -> Vec<(String, Option<i64>)> {
        vec![]
    }
    pub fn delivered() -> Vec<String> {
        vec![]
    }
    pub fn show_now(_title: &str, _body: &str, _launch: &str) -> Result<(), String> {
        Ok(())
    }
}
#[cfg(not(any(target_os = "macos", target_os = "windows")))]
pub use none::*;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn toast_text_is_escaped() {
        let x = toast_xml(
            "语流 · <复习>",
            "A & B \"quoted\"\u{1}",
            "flowlang://review",
            false,
        );
        assert!(!x.contains("<audio"));
        assert!(toast_xml("t", "b", "flowlang://review", true)
            .contains(r#"<audio silent="true"/></toast>"#));
        assert!(x.contains("<text>语流 · &lt;复习&gt;</text>"));
        assert!(x.contains("<text>A &amp; B &quot;quoted&quot;</text>"));
        assert!(x.contains(r#"launch="flowlang://review" activationType="protocol""#));
    }

    #[test]
    fn reminder_clicks_open_the_review() {
        assert_eq!(route_of("review-2026-11-25"), Some("/review"));
        assert_eq!(route_of("review-once"), Some("/review"));
        assert_eq!(route_of("plan-2026-11-25"), Some("/"));
        assert_eq!(route_of("flow-test"), None);
        assert_eq!(Permission::Undetermined.as_str(), "undetermined");
        assert!(Permission::Provisional.ok() && !Permission::Undetermined.ok());
        assert_eq!(tag_of("review-2026-11-27"), "r20261127");
        assert_eq!(tag_of("plan-2026-11-27"), "p20261127");
        assert_eq!(tag_of("review-once"), "once");
        assert!(tag_of("something-much-longer-than-sixteen").chars().count() <= 16);
    }
}
