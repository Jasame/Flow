//! Automatic updates (from 0.1.1; the owner chose them on 2026-11-25).
//!
//! The Release app asks https://flowlang.cn/desktop/latest.json about 20 seconds after it opens (the server sees the
//! network address only, no account). A newer version is downloaded in the background and installed when 语流 is
//! quit, so the next start is the new version; 「检查更新…」 in the menu installs at once and restarts.
//! Only updates signed with the owner's key are accepted (the public half is in tauri.conf.json; the private key
//! stays on the owner's Mac — desktop/README.md「自动更新」). The 内测版 (Beta) and smoke tests never check.

use crate::site::Channel;
use crate::AppState;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Manager};
use tauri_plugin_updater::{Update, UpdaterExt};

/// A downloaded update waiting for the app to quit.
#[derive(Default)]
pub struct Pending(pub Mutex<Option<(Update, Vec<u8>)>>);

fn wanted(app: &AppHandle) -> bool {
    let st = app.state::<AppState>();
    st.channel == Channel::Release && st.smoke.is_none()
}

/// Can this install update itself? Windows and macOS: yes. Linux: only the AppImage (a deb or rpm would need the
/// system's admin password for every update, so those say where to download instead).
fn self_updating() -> bool {
    !cfg!(target_os = "linux") || std::env::var_os("APPIMAGE").is_some()
}

fn say(app: &AppHandle, title: &str, body: &str) {
    let launch = format!("{}://open", app.state::<AppState>().channel.scheme());
    if let Err(e) = crate::notify::show_now(title, body, &launch) {
        log::info!("update note not shown: {e}");
    }
}

/// At start: check, download in the background, keep it for the quit.
pub fn check_on_start(app: AppHandle) {
    if !wanted(&app) {
        return;
    }
    tauri::async_runtime::spawn(async move {
        tokio_sleep(Duration::from_secs(20)).await; // the page first
        log::info!("checking for an update");
        let updater = match app.updater() {
            Ok(u) => u,
            Err(e) => return log::warn!("updater unavailable: {e}"),
        };
        match updater.check().await {
            Ok(Some(u)) if !self_updating() => {
                say(
                    &app,
                    "语流 · 有新版本",
                    &format!(
                        "{} 可以更新了：到 flowlang.cn 的下载页下载安装。",
                        u.version
                    ),
                );
            }
            Ok(Some(u)) => match u.download(|_, _| {}, || {}).await {
                Ok(bytes) => {
                    log::info!("update {} downloaded ({} bytes)", u.version, bytes.len());
                    let v = u.version.clone();
                    *app.state::<Pending>().0.lock().unwrap() = Some((u, bytes));
                    say(
                        &app,
                        "语流 · 新版本已下好",
                        &format!("{v} 已经下好，关掉语流时会装上，下次打开就是新版。"),
                    );
                }
                Err(e) => log::warn!("update download failed: {e}"),
            },
            Ok(None) => log::info!("no update"),
            Err(e) => log::warn!("update check failed: {e}"),
        }
    });
}

/// When 语流 quits: install what was downloaded (macOS replaces the app; Windows runs the installer and exits).
pub fn install_pending(app: &AppHandle) {
    let pending = app
        .try_state::<Pending>()
        .and_then(|p| p.0.lock().unwrap().take());
    if let Some((u, bytes)) = pending {
        log::info!("installing {}", u.version);
        if let Err(e) = u.install(&bytes) {
            log::warn!("update install failed: {e}");
        }
    }
}

/// 「检查更新…」: install now and restart.
pub fn check_now(app: AppHandle) {
    if !wanted(&app) {
        return;
    }
    tauri::async_runtime::spawn(async move {
        let ready = app.state::<Pending>().0.lock().unwrap().take();
        if let Some((u, bytes)) = ready {
            if u.install(&bytes).is_ok() {
                app.restart();
            }
            return;
        }
        let Ok(updater) = app.updater() else { return };
        match updater.check().await {
            Ok(Some(u)) if !self_updating() => {
                say(
                    &app,
                    "语流 · 有新版本",
                    &format!(
                        "{} 可以更新了：到 flowlang.cn 的下载页下载安装。",
                        u.version
                    ),
                );
            }
            Ok(Some(u)) => {
                say(
                    &app,
                    "语流 · 正在更新",
                    &format!("正在下载 {}，装好后语流会自己重新打开。", u.version),
                );
                match u.download_and_install(|_, _| {}, || {}).await {
                    Ok(()) => app.restart(),
                    Err(e) => say(
                        &app,
                        "语流 · 更新没装上",
                        &format!("这次没装上（{e}），可以到 flowlang.cn 下载新版。"),
                    ),
                }
            }
            Ok(None) => say(
                &app,
                "语流 · 已经是最新版",
                &format!("现在的 {} 就是最新版。", app.package_info().version),
            ),
            Err(_) => say(&app, "语流 · 没查到", "这次没连上更新服务器，稍后再试。"),
        }
    });
}

async fn tokio_sleep(d: Duration) {
    // tauri's async runtime is tokio; a blocking sleep on a worker thread would hold it
    let _ = tauri::async_runtime::spawn_blocking(move || std::thread::sleep(d)).await;
}
