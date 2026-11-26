//! 复习提醒: system notifications scheduled ahead of time, so they come even when 语流 is not open
//! (macOS: UserNotifications; Windows: scheduled toasts). schedule.rs decides when; this sends them to the system.

use crate::schedule::Planned;

#[cfg(target_os = "macos")]
mod macos;
#[cfg(target_os = "macos")]
pub use macos::*;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
pub use linux::*;

#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "windows")]
pub use self::windows::*;

/// Linux keeps the plan itself (no system scheduler): a reminder that comes more than this late (the computer was
/// asleep or off) is skipped, not shown at wake-up.
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
const STALE: i64 = 10 * 60;

/// (due now and not stale, still ahead)
#[cfg_attr(not(target_os = "linux"), allow(dead_code))]
pub fn split_due(items: Vec<Planned>, now: i64) -> (Vec<Planned>, Vec<Planned>) {
    let (due, ahead): (Vec<_>, Vec<_>) = items.into_iter().partition(|p| p.at <= now);
    (
        due.into_iter().filter(|p| now - p.at <= STALE).collect(),
        ahead,
    )
}

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
    /// notifications will be shown
    pub fn ok(self) -> bool {
        matches!(self, Permission::Granted | Permission::Provisional)
    }
}

/// FlowApp.notify.permission() as the contract means it (docs/native-bridge.md §5): whether the app's reminders
/// are on, not only what the system allows. 'granted' = the system allows and the learner turned them on;
/// 'undetermined' = not turned on yet, or turned off; 'denied' = turned off in the system's settings.
/// `lenient`: Windows cannot say before its first toast ('undetermined' there is not a no).
pub fn app_permission(sys: Permission, on: bool, lenient: bool) -> &'static str {
    let allowed = sys.ok() || (lenient && sys == Permission::Undetermined);
    if sys == Permission::Denied {
        "denied"
    } else if on && allowed {
        if sys == Permission::Provisional {
            "provisional"
        } else {
            "granted"
        }
    } else {
        "undetermined"
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
#[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
mod none {
    use super::*;
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
    pub fn clear_shown() {}
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
#[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
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
    fn permission_means_the_apps_reminders() {
        use Permission::*;
        assert_eq!(app_permission(Granted, true, false), "granted");
        assert_eq!(app_permission(Granted, false, false), "undetermined"); // not turned on, or turned off
        assert_eq!(app_permission(Denied, true, false), "denied");
        assert_eq!(app_permission(Undetermined, true, false), "undetermined");
        assert_eq!(app_permission(Undetermined, true, true), "granted"); // Windows before its first toast
        assert_eq!(app_permission(Provisional, true, false), "provisional");
    }

    #[test]
    fn linux_shows_what_is_due_and_skips_what_is_stale() {
        let p = |id: &str, at: i64| Planned {
            id: id.into(),
            at,
            title: String::new(),
            body: String::new(),
            route: "/review",
        };
        let (due, ahead) = split_due(vec![p("a", 100), p("b", 1000), p("c", -5000)], 200);
        assert_eq!(due.iter().map(|x| x.id.as_str()).collect::<Vec<_>>(), ["a"]); // c: missed while asleep
        assert_eq!(
            ahead.iter().map(|x| x.id.as_str()).collect::<Vec<_>>(),
            ["b"]
        );
    }

    #[test]
    fn reminder_clicks_open_the_review() {
        assert_eq!(route_of("review-2026-11-25"), Some("/review"));
        assert_eq!(route_of("review-once"), Some("/review"));
        assert_eq!(route_of("plan-2026-11-25"), Some("/"));
        assert_eq!(route_of("flow-test"), None);
        assert!(Permission::Provisional.ok() && !Permission::Undetermined.ok());
        assert_eq!(tag_of("review-2026-11-27"), "r20261127");
        assert_eq!(tag_of("plan-2026-11-27"), "p20261127");
        assert_eq!(tag_of("review-once"), "once");
        assert!(tag_of("something-much-longer-than-sixteen").chars().count() <= 16);
    }
}
