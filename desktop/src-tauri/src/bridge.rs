//! The commands behind window.FlowApp (bridge.js). Only the app's own site can call them: the capability in
//! capabilities/site.json names its two origins, and the window never shows any other site.

use crate::media::MediaState;
use crate::notify;
use crate::schedule::{self, Reminder};
use crate::AppState;
use std::sync::atomic::Ordering;
use tauri::{AppHandle, Manager, State};

/// bridge.js with this run's origin, version and platform filled in (as JSON literals: no quoting surprises).
pub fn script(origin: &str, version: &str, platform: &str) -> String {
    let lit = |s: &str| serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into());
    include_str!("bridge.js")
        .replace("__FLOW_ORIGIN__", &lit(origin))
        .replace("__FLOW_VERSION__", &lit(version))
        .replace("__FLOW_PLATFORM__", &lit(platform))
}

#[tauri::command]
pub fn media_update(app: AppHandle, s: MediaState) {
    *app.state::<AppState>().media_title.lock().unwrap() = s.title.clone();
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    {
        let _ = app.run_on_main_thread(move || crate::media::system::update(s));
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = (app, s);
    }
}

#[tauri::command]
pub async fn notify_permission() -> String {
    tauri::async_runtime::spawn_blocking(|| notify::permission().as_str().to_string())
        .await
        .unwrap_or_else(|_| "denied".into())
}

/// 「到点用 App 通知提醒」: asks the system once, and from then on the app keeps the reminders planned.
#[tauri::command]
pub async fn notify_ask(app: AppHandle) -> bool {
    let ok = tauri::async_runtime::spawn_blocking(notify::ask)
        .await
        .unwrap_or(false);
    if ok {
        let st = app.state::<AppState>();
        st.update_settings(|s| s.notify = true);
        crate::menu::refresh(&app);
    }
    ok
}

/// Whether bridge.js should fetch the reminder and sync now: the reminders are on, and the last plan is
/// older than 30 minutes (or from before this run).
#[tauri::command]
pub fn notify_due(state: State<'_, AppState>) -> bool {
    if !state.settings().notify {
        return false;
    }
    let now = chrono::Utc::now().timestamp();
    now - state.last_sync.load(Ordering::Relaxed) > 30 * 60
}

/// FlowApp.notify.sync(r): plan the next 7 days from the page's reminder; r = null clears them (signed out).
#[tauri::command]
pub async fn notify_sync(app: AppHandle, r: Option<Reminder>) -> Result<usize, String> {
    let state = app.state::<AppState>();
    let launch = format!("{}://review", state.channel.scheme());
    let on = state.settings().notify;
    state
        .last_sync
        .store(chrono::Utc::now().timestamp(), Ordering::Relaxed);
    tauri::async_runtime::spawn_blocking(move || match r {
        Some(r) if on => notify::schedule(&schedule::plan(&r, chrono::Local::now()), &launch),
        _ => {
            notify::clear();
            Ok(0)
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn script_fills_in_literals() {
        let s = script("https://flowlang.cn", "0.1.0", "macos");
        assert!(s.contains(r#"location.origin !== "https://flowlang.cn""#));
        assert!(s.contains(r#"app: "0.1.0""#));
        assert!(s.contains(r#"platform: "macos""#));
        assert!(!s.contains("__FLOW_"));
        // a quote in a value cannot break out of the string
        let s = script("https://x\"y", "0", "windows");
        assert!(s.contains(r#""https://x\"y""#));
    }

    #[test]
    fn capabilities_match_the_page() {
        let s = script("https://flowlang.cn", "0.1.0", "macos");
        // the three things the page tests for (#139 uses has('notify'), notify.ask and notify.sync)
        assert!(s.contains("CAPS = ['notify', 'media']"));
        for c in [
            "notify_permission",
            "notify_ask",
            "notify_sync",
            "notify_due",
            "media_update",
        ] {
            assert!(s.contains(&format!("'{c}'")), "{c}");
        }
    }
}
