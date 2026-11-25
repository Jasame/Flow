//! Automatic updates — built only with `--features updater`, after the owner has made the signing key
//! (desktop/README.md「自动更新」). The app then checks tauri.updater.conf.json's endpoint at start and from
//! the menu, and installs only updates signed with that key.

use tauri::{AppHandle, Manager};
use tauri_plugin_updater::UpdaterExt;

pub fn check(app: AppHandle, from_menu: bool) {
    tauri::async_runtime::spawn(async move {
        let Ok(u) = app.updater() else { return };
        match u.check().await {
            Ok(Some(update)) if from_menu => {
                log::info!("installing {}", update.version);
                if update.download_and_install(|_, _| {}, || {}).await.is_ok() {
                    app.restart();
                }
            }
            Ok(Some(update)) => {
                let launch = format!("{}://open", app.state::<crate::AppState>().channel.scheme());
                let _ = crate::notify::show_now(
                    "语流 · 有新版本",
                    &format!("{} 可以更新了：在菜单里点「检查更新…」。", update.version),
                    &launch,
                );
            }
            Ok(None) => {}
            Err(e) => log::warn!("update check failed: {e}"),
        }
    });
}
