//! Windows: scheduled toasts (ToastNotifier.AddToSchedule). Windows shows them at the time even when 语流 is
//! closed. They belong to the app's AppUserModelID — the bundle identifier, which the installer puts on the
//! Start-menu shortcut — and a click opens flowlang://review, which starts 语流 on the review page.

use super::{toast_xml, Permission};
use crate::schedule::Planned;
use std::sync::OnceLock;
use windows::core::HSTRING;
use windows::Data::Xml::Dom::XmlDocument;
use windows::Foundation::DateTime;
use windows::UI::Notifications::{
    NotificationSetting, ScheduledToastNotification, ToastNotification, ToastNotificationManager,
    ToastNotifier,
};

static AUMID: OnceLock<String> = OnceLock::new();

pub fn init(identifier: &str, _on_click: impl Fn(Option<&'static str>) + Send + Sync + 'static) {
    let _ = AUMID.set(identifier.to_string());
    // the taskbar and the toasts know this process as the installed 语流
    unsafe {
        let _ = windows::Win32::UI::Shell::SetCurrentProcessExplicitAppUserModelID(&HSTRING::from(
            identifier,
        ));
    }
}

fn notifier() -> Result<ToastNotifier, String> {
    let id = AUMID.get().ok_or("not initialised")?;
    ToastNotificationManager::CreateToastNotifierWithId(&HSTRING::from(id.as_str()))
        .map_err(|e| e.message().to_string())
}

pub fn permission() -> Permission {
    match notifier().and_then(|n| n.Setting().map_err(|e| e.message().to_string())) {
        Ok(NotificationSetting::Enabled) => Permission::Granted,
        Ok(_) => Permission::Denied, // off in 设置 → 系统 → 通知, by policy, or not installed
        Err(_) => Permission::Undetermined,
    }
}

/// Windows never asks: notifications are on unless turned off in Settings.
pub fn ask() -> bool {
    permission() == Permission::Granted
}

fn doc(title: &str, body: &str, launch: &str) -> Result<XmlDocument, String> {
    let d = XmlDocument::new().map_err(|e| e.message().to_string())?;
    d.LoadXml(&HSTRING::from(toast_xml(title, body, launch)))
        .map_err(|e| e.message().to_string())?;
    Ok(d)
}

/// epoch seconds → Windows FILETIME ticks (100 ns since 1601)
fn when(at: i64) -> DateTime {
    DateTime {
        UniversalTime: (at + 11_644_473_600) * 10_000_000,
    }
}

/// What Windows has queued: (tag, when it fires, epoch seconds).
pub fn pending() -> Vec<(String, Option<i64>)> {
    let Ok(n) = notifier() else { return vec![] };
    let Ok(list) = n.GetScheduledToastNotifications() else {
        return vec![];
    };
    let mut v: Vec<_> = list
        .into_iter()
        .map(|s| {
            let tag = s.Tag().map(|t| t.to_string()).unwrap_or_default();
            let at = s
                .DeliveryTime()
                .ok()
                .map(|d| d.UniversalTime / 10_000_000 - 11_644_473_600);
            (tag, at)
        })
        .collect();
    v.sort_by_key(|x| x.1);
    v
}

/// (not read on Windows: the Action Center keeps its own history)
pub fn delivered() -> Vec<String> {
    vec![]
}

pub fn clear() {
    if let Ok(n) = notifier() {
        if let Ok(list) = n.GetScheduledToastNotifications() {
            for s in list {
                let _ = n.RemoveFromSchedule(&s);
            }
        }
    }
}

pub fn schedule(items: &[Planned], launch: &str) -> Result<usize, String> {
    let n = notifier()?;
    clear();
    let mut done = 0;
    for p in items {
        let st = ScheduledToastNotification::CreateScheduledToastNotification(
            &doc(&p.title, &p.body, launch)?,
            when(p.at),
        )
        .map_err(|e| e.message().to_string())?;
        // tags are at most 16 characters: d20261125 / once
        let tag = p.id.trim_start_matches("flow-daily-").replace("flow-", "");
        let _ = st.SetTag(&HSTRING::from(if tag.len() == 8 {
            format!("d{tag}")
        } else {
            tag
        }));
        let _ = st.SetGroup(&HSTRING::from("review"));
        n.AddToSchedule(&st).map_err(|e| e.message().to_string())?;
        done += 1;
    }
    Ok(done)
}

pub fn show_now(title: &str, body: &str, launch: &str) -> Result<(), String> {
    let t = ToastNotification::CreateToastNotification(&doc(title, body, launch)?)
        .map_err(|e| e.message().to_string())?;
    notifier()?.Show(&t).map_err(|e| e.message().to_string())
}

#[cfg(test)]
mod tests {
    #[test]
    fn filetime() {
        // 1970-01-01 is 11644473600 s after 1601-01-01
        assert_eq!(super::when(0).UniversalTime, 116_444_736_000_000_000);
    }
}
