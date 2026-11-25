//! Linux: freedesktop notifications (GNOME, KDE, 深度, UOS …). Linux has no system service that shows a notification
//! at a set time (Windows and macOS do), so the reminders come while 语流 runs — with 开机时启动 and
//! 关窗口后留在托盘 (on by default here) it always does: one thread sleeps until the next planned time and shows it.
//! The owner chose this over systemd timers on 2026-11-25 (shared notes linux-desktop-plan.md).

use super::{route_of, silent, split_due, Permission};
use crate::schedule::Planned;
use std::sync::{Condvar, Mutex, OnceLock};
use std::time::Duration;

type OnClick = Box<dyn Fn(Option<&'static str>) + Send + Sync>;
static ON_CLICK: OnceLock<OnClick> = OnceLock::new();
static ICON: OnceLock<String> = OnceLock::new();
static QUEUE: OnceLock<(Mutex<Vec<Planned>>, Condvar)> = OnceLock::new();

fn queue() -> &'static (Mutex<Vec<Planned>>, Condvar) {
    QUEUE.get_or_init(|| (Mutex::new(Vec::new()), Condvar::new()))
}

pub fn init(_identifier: &str, on_click: impl Fn(Option<&'static str>) + Send + Sync + 'static) {
    let _ = ON_CLICK.set(Box::new(on_click));
    // the icon the package installed (hicolor theme, named after the binary: flow / flow-beta)
    let icon = std::env::current_exe()
        .ok()
        .and_then(|p| p.file_stem().map(|s| s.to_string_lossy().to_string()))
        .unwrap_or_else(|| "flow".into());
    let _ = ICON.set(icon);
    std::thread::spawn(|| {
        let (m, cv) = queue();
        let mut items = m.lock().unwrap();
        loop {
            let now = chrono::Utc::now().timestamp();
            let (due, ahead) = split_due(std::mem::take(&mut *items), now);
            *items = ahead;
            if !due.is_empty() {
                drop(items);
                for p in due {
                    if let Err(e) = show(&p.title, &p.body, Some(p.id.clone())) {
                        log::warn!("reminder not shown: {e}");
                    }
                }
                items = m.lock().unwrap();
                continue;
            }
            // wake at the next one, or within a minute anyway (the clock may jump after a suspend)
            let next = items
                .iter()
                .map(|p| p.at)
                .min()
                .map(|t| (t - now).clamp(1, 60))
                .unwrap_or(60);
            items = cv
                .wait_timeout(items, Duration::from_secs(next as u64))
                .unwrap()
                .0;
        }
    });
}

fn show(title: &str, body: &str, id: Option<String>) -> Result<(), String> {
    let mut n = notify_rust::Notification::new();
    n.appname("语流")
        .summary(title)
        .body(body)
        .icon(ICON.get().map(String::as_str).unwrap_or("flow"));
    n.action("default", "打开");
    if silent() {
        n.hint(notify_rust::Hint::SuppressSound(true));
    }
    let handle = n.show().map_err(|e| e.to_string())?;
    // a click (the default action) opens the review; the thread ends when the notification is closed
    std::thread::spawn(move || {
        handle.wait_for_action(|action| {
            if action == "default" {
                if let Some(cb) = ON_CLICK.get() {
                    cb(id.as_deref().and_then(route_of));
                }
            }
        })
    });
    Ok(())
}

pub fn permission() -> Permission {
    // no permission to ask for on Linux: notifications work when the desktop runs a notification server
    match notify_rust::get_server_information() {
        Ok(_) => Permission::Granted,
        Err(_) => Permission::Denied,
    }
}

pub fn ask() -> bool {
    permission() == Permission::Granted
}

pub fn schedule(items: &[Planned], _scheme: &str) -> Result<usize, String> {
    let (m, cv) = queue();
    *m.lock().unwrap() = items.to_vec();
    cv.notify_all();
    Ok(items.len())
}

pub fn clear() {
    let (m, cv) = queue();
    m.lock().unwrap().clear();
    cv.notify_all();
}

pub fn pending() -> Vec<(String, Option<i64>)> {
    let mut v: Vec<_> = queue()
        .0
        .lock()
        .unwrap()
        .iter()
        .map(|p| (p.id.clone(), Some(p.at)))
        .collect();
    v.sort_by_key(|x| x.1);
    v
}

/// (not kept: the notification server has no list we can read)
pub fn delivered() -> Vec<String> {
    vec![]
}

pub fn show_now(title: &str, body: &str, _launch: &str) -> Result<(), String> {
    show(title, body, None)
}
