//! The commands behind window.FlowApp (bridge.js; the contract is docs/native-bridge.md). Only the app's own site
//! can call them: the capability in capabilities/site.json names its two origins, and the window never shows any
//! other site.

use crate::media::MediaState;
use crate::notify;
use crate::schedule::{self, Input, Planned};
use crate::AppState;
use serde::Serialize;
use std::sync::atomic::Ordering;
use tauri::{AppHandle, Manager, State};

/// What goes into bridge.js for this run (filled in as JSON literals: no quoting surprises).
pub struct ScriptVars<'a> {
    pub origin: &'a str,
    pub version: &'a str,
    pub build: &'a str,
    pub platform: &'a str,
    pub beta: bool,
    pub mute: bool,
}

pub fn script(v: &ScriptVars) -> String {
    let lit = |s: &str| serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into());
    let b = |x: bool| if x { "true" } else { "false" };
    include_str!("bridge.js")
        .replace("__FLOW_ORIGIN__", &lit(v.origin))
        .replace("__FLOW_VERSION__", &lit(v.version))
        .replace("__FLOW_BUILD__", &lit(v.build))
        .replace("__FLOW_PLATFORM__", &lit(v.platform))
        .replace("__FLOW_BETA__", b(v.beta))
        .replace("__FLOW_MUTE__", b(v.mute))
}

/// The commit the app was built from (CI's GITHUB_SHA), or "dev".
pub fn build_id() -> &'static str {
    match option_env!("GITHUB_SHA") {
        Some(s) if s.len() >= 7 => &s[..7],
        _ => "dev",
    }
}

#[tauri::command]
pub fn media_update(app: AppHandle, s: MediaState) {
    *app.state::<AppState>().media_title.lock().unwrap() = s.title.clone();
    *app.state::<AppState>().media_artist.lock().unwrap() =
        s.active().then(|| crate::media::display_artist(&s));
    #[cfg(any(target_os = "macos", target_os = "windows", target_os = "linux"))]
    {
        let _ = app.run_on_main_thread(move || crate::media::system::update(s));
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    {
        let _ = (app, s);
    }
}

/// Whether the app's reminders are on (notify::app_permission), not only the system's answer.
#[tauri::command]
pub async fn notify_permission(app: AppHandle) -> String {
    let on = app.state::<AppState>().settings().notify;
    let sys = tauri::async_runtime::spawn_blocking(notify::permission)
        .await
        .unwrap_or(notify::Permission::Denied);
    notify::app_permission(sys, on, cfg!(target_os = "windows")).to_string()
}

/// 「到点用 App 通知提醒」: asks the system once; yes → the app keeps the reminders planned from now on.
#[tauri::command]
pub async fn notify_ask(app: AppHandle) -> bool {
    let ok = tauri::async_runtime::spawn_blocking(notify::ask)
        .await
        .unwrap_or(false);
    if ok {
        app.state::<AppState>().update_settings(|s| s.notify = true);
        crate::menu::refresh(&app);
    }
    ok
}

/// Whether bridge.js should fetch /api/next/vocab and plan now: the reminders are on, and the last plan is older
/// than 30 minutes (or from before this run).
#[tauri::command]
pub fn notify_due(state: State<'_, AppState>) -> bool {
    state.settings().notify
        && chrono::Utc::now().timestamp() - state.last_sync.load(Ordering::Relaxed) > 30 * 60
}

#[derive(Serialize)]
pub struct PlanResult {
    ok: bool,
    planned: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    why: Option<String>,
}

/// Hand a plan to the system (replacing what was there) and remember it for pending().
async fn put(app: &AppHandle, items: Vec<Planned>) -> PlanResult {
    let st = app.state::<AppState>();
    st.last_sync
        .store(chrono::Utc::now().timestamp(), Ordering::Relaxed);
    let scheme = st.channel.scheme().to_string();
    let n = items.len();
    *st.last_plan.lock().unwrap() = items.clone();
    let r = tauri::async_runtime::spawn_blocking(move || {
        if items.is_empty() {
            notify::clear();
            Ok(0)
        } else {
            notify::schedule(&items, &scheme)
        }
    })
    .await;
    match r {
        Ok(Ok(_)) => PlanResult {
            ok: true,
            planned: n,
            why: None,
        },
        Ok(Err(e)) => PlanResult {
            ok: false,
            planned: 0,
            why: Some(e),
        },
        Err(e) => PlanResult {
            ok: false,
            planned: 0,
            why: Some(e.to_string()),
        },
    }
}

fn input_now(st: &AppState) -> Input {
    let s = st.settings();
    Input {
        once_seen: s.once_seen,
        app: s.notify,
        ..Input::default()
    }
}

/// The page fetched /api/next/vocab (bridge.js): plan the next two weeks from it (schedule.rs), if the learner
/// turned the app's reminders on.
#[tauri::command]
pub async fn notify_plan(app: AppHandle, v: serde_json::Value) -> PlanResult {
    let st = app.state::<AppState>();
    let x = schedule::input_from(&v, &input_now(&st));
    let items = schedule::slots(&x, chrono::Utc::now());
    // a once that went to the system is remembered (its day gets no daily one after it)
    let seen = schedule::remember(&x, &items).once_seen;
    if seen != st.settings().once_seen {
        st.update_settings(|s| s.once_seen = seen);
    }
    put(&app, items).await
}

/// Signed out (/api/next/vocab said 401): no word reminders for an account that is not here.
#[tauri::command]
pub async fn notify_signed_out(app: AppHandle) -> PlanResult {
    let st = app.state::<AppState>();
    let x = schedule::signed_out(&input_now(&st));
    put(&app, schedule::slots(&x, chrono::Utc::now())).await
}

/// 「数据存放在香港」 not agreed to yet (/api/next/vocab said 403 'storage'): no reminders at all, the switch stays
/// on, and the next plan after the learner agrees puts them back.
#[tauri::command]
pub async fn notify_hold(app: AppHandle) -> PlanResult {
    put(&app, vec![]).await
}

/// FlowApp.call('account.changed') (切换账号, 添加账号, 退出登录; docs/native-bridge.md §5): what this computer kept
/// for the last account goes — its planned and shown reminders, the 「这次什么时候复习」 it saw — and the next look plans
/// for the account now in use: the bridge asks at once, and if the page goes away first, opening or coming back to the
/// front does, without the 30 minutes' wait. The switch stays as it is: it belongs to this computer, not the account.
#[tauri::command]
pub async fn notify_account(app: AppHandle) -> PlanResult {
    forget_account(&app).await
}

/// What account.changed does here (also the smoke test's check that the shown reminders go too).
pub(crate) async fn forget_account(app: &AppHandle) -> PlanResult {
    let st = app.state::<AppState>();
    if st.settings().once_seen.is_some() {
        st.update_settings(|s| s.once_seen = None);
    }
    let _ = tauri::async_runtime::spawn_blocking(notify::clear_shown).await;
    let r = put(app, vec![]).await;
    st.last_sync.store(0, Ordering::Relaxed);
    r
}

/// FlowApp.notify.sync(null) or sync({app: false}): the learner turned the app's reminders off.
#[tauri::command]
pub async fn notify_off(app: AppHandle) -> PlanResult {
    app.state::<AppState>()
        .update_settings(|s| s.notify = false);
    crate::menu::refresh(&app);
    put(&app, vec![]).await
}

#[derive(Serialize)]
pub struct Pending {
    id: String,
    at: Option<i64>,
    title: String,
    body: String,
}

/// FlowApp.notify.pending(): what the system has queued, with the texts of the last plan.
#[tauri::command]
pub async fn notify_pending(app: AppHandle) -> Vec<Pending> {
    let queued = tauri::async_runtime::spawn_blocking(notify::pending)
        .await
        .unwrap_or_default();
    let plan = app.state::<AppState>().last_plan.lock().unwrap().clone();
    queued
        .into_iter()
        .map(|(key, at)| {
            let p = plan
                .iter()
                .find(|p| p.id == key || notify::tag_of(&p.id) == key);
            Pending {
                id: p.map(|p| p.id.clone()).unwrap_or(key),
                at: at.or(p.map(|p| p.at)),
                title: p.map(|p| p.title.clone()).unwrap_or_default(),
                body: p.map(|p| p.body.clone()).unwrap_or_default(),
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn vars(origin: &str, mute: bool) -> ScriptVars<'_> {
        ScriptVars {
            origin,
            version: "0.1.0",
            build: "abc1234",
            platform: "macos",
            beta: true,
            mute,
        }
    }

    #[test]
    fn script_fills_in_literals() {
        let s = script(&vars("https://flowlang.cn", false));
        assert!(s.contains(r#"location.origin !== "https://flowlang.cn""#));
        assert!(
            s.contains(r#"app: "0.1.0""#)
                && s.contains(r#"build: "abc1234""#)
                && s.contains("beta: true")
        );
        assert!(s.contains(r#"platform: "macos""#));
        assert!(s.contains("const MUTE = false;"));
        assert!(script(&vars("https://flowlang.cn", true)).contains("const MUTE = true;"));
        assert!(!s.contains("__FLOW_"));
        // a quote in a value cannot break out of the string
        assert!(script(&vars("https://x\"y", false)).contains(r#""https://x\"y""#));
    }

    #[test]
    fn script_matches_the_contract() {
        let s = script(&vars("https://flowlang.cn", false));
        // docs/native-bridge.md §2: has(), call('hello'), on() returning an unsubscribe function, notify.pending()
        assert!(s.contains("CAPS = ['notify', 'media']"));
        for c in [
            "notify_hold",
            "notify_permission",
            "notify_ask",
            "notify_plan",
            "notify_off",
            "notify_signed_out",
            "notify_due",
            "notify_pending",
            "media_update",
        ] {
            assert!(s.contains(&format!("'{c}'")), "{c}");
        }
        assert!(s.contains("'hello'") && s.contains("'app.visible'"));
        assert!(s.contains("return () => FlowApp.off(type, fn)"));
    }

    #[test]
    fn build_id_is_short() {
        let b = build_id();
        assert!(b == "dev" || b.len() == 7);
    }
}
