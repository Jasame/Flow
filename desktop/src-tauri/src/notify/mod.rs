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

/// FlowApp.notify.permission(): 'granted' | 'denied' | 'undetermined' (the same words as the iOS app)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Permission {
    Granted,
    Denied,
    Undetermined,
}

impl Permission {
    pub fn as_str(self) -> &'static str {
        match self {
            Permission::Granted => "granted",
            Permission::Denied => "denied",
            Permission::Undetermined => "undetermined",
        }
    }
}

#[cfg_attr(not(target_os = "windows"), allow(dead_code))]
/// The toast XML Windows shows (pure, so it is tested everywhere). A click opens `launch` (flowlang://review).
pub fn toast_xml(title: &str, body: &str, launch: &str) -> String {
    format!(
        r#"<toast launch="{}" activationType="protocol"><visual><binding template="ToastGeneric"><text>{}</text><text>{}</text></binding></visual></toast>"#,
        xml_escape(launch),
        xml_escape(title),
        xml_escape(body)
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

/// The click target of a notification id (all reminders open the review).
pub fn route_of(id: &str) -> Option<&'static str> {
    if id.starts_with("flow-daily-") || id == "flow-once" {
        Some("/review")
    } else {
        None
    }
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
    pub fn schedule(_items: &[Planned], _launch: &str) -> Result<usize, String> {
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
        );
        assert!(x.contains("<text>语流 · &lt;复习&gt;</text>"));
        assert!(x.contains("<text>A &amp; B &quot;quoted&quot;</text>"));
        assert!(x.contains(r#"launch="flowlang://review" activationType="protocol""#));
    }

    #[test]
    fn reminder_clicks_open_the_review() {
        assert_eq!(route_of("flow-daily-20261125"), Some("/review"));
        assert_eq!(route_of("flow-once"), Some("/review"));
        assert_eq!(route_of("flow-test"), None);
        assert_eq!(Permission::Undetermined.as_str(), "undetermined");
    }
}
