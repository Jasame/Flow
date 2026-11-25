//! `--smoke-test=<file>`: open the site, check the bridge from inside the page, write a JSON report and quit
//! (exit 0 = report written; 2 = no report within 90 s). CI runs it on windows-latest and macOS; it is also the
//! quickest check on a new computer. The page can call smoke_report at any time; without the flag it does nothing.

use crate::AppState;
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

pub fn path_from_args(args: impl Iterator<Item = String>) -> Option<PathBuf> {
    args.filter_map(|a| a.strip_prefix("--smoke-test=").map(PathBuf::from))
        .next()
}

/// Runs in the page once it has loaded.
pub const PAGE_CHECK: &str = r#"(async () => {
  const F = window.FlowApp, r = { url: location.href, title: document.title, ua: navigator.userAgent,
    flowapp: !!F, v: F && F.v, app: F && F.app, platform: F && F.platform,
    notify: !!(F && F.has('notify')), media: !!(F && F.has('media')), audio: !!(F && F.has('audio')),
    frozen: !!F && Object.isFrozen(F), mediaSession: !!navigator.mediaSession };
  // muted (every smoke test is): an <audio> started by the page comes out muted
  try { const a = new Audio(); a.play().catch(() => {}); r.muted = a.muted; a.pause(); } catch (e) { r.mutedError = String(e); }
  try { r.permission = await F.notify.permission(); } catch (e) { r.permissionError = String(e); }
  try {
    let played = 0;
    navigator.mediaSession.metadata = new MediaMetadata({ title: '语流 · 冒烟测试', artist: '语流 Flow' });
    navigator.mediaSession.setActionHandler('play', () => { played++; });
    navigator.mediaSession.setActionHandler('nexttrack', () => { played += 10; });
    navigator.mediaSession.playbackState = 'paused';
    F._media('play'); F._media('nexttrack');
    r.mediaHandlers = played;
    await new Promise(ok => setTimeout(ok, 300));  // media_update is sent after 40 ms
  } catch (e) { r.mediaError = String(e); }
  // plans the reminders only where 复习提醒用系统通知 is on (never on a fresh install, so not in CI)
  try {
    const now = Math.floor(Date.now() / 1000);
    r.synced = await F.notify.sync({ enabled: false, hour: 20, has_email: false, once: now + 75, forecast: [2, 0, 3, 1, 0, 0, 4] });
  } catch (e) { r.syncError = String(e); }
  await window.__TAURI_INTERNALS__.invoke('smoke_report', { r });
})().catch(e => window.__TAURI_INTERNALS__.invoke('smoke_report', { r: { error: String(e) } }));"#;

#[tauri::command]
pub async fn smoke_report(app: AppHandle, r: serde_json::Value) {
    let st = app.state::<AppState>();
    let Some(path) = st.smoke.clone() else { return };
    let pending = tauri::async_runtime::spawn_blocking(crate::notify::pending)
        .await
        .unwrap_or_default();
    let delivered = tauri::async_runtime::spawn_blocking(crate::notify::delivered)
        .await
        .unwrap_or_default();
    let out = serde_json::json!({
        "page": r,
        "native": {
            "channel": st.channel.name(),
            "identifier": app.config().identifier,
            "version": app.package_info().version.to_string(),
            "webview": tauri::webview_version().ok(),
            "media_controls": st.media_ok.load(std::sync::atomic::Ordering::Relaxed),
            "media_last_title": st.media_title.lock().unwrap().clone(),
            "mute": st.mute,
            "notify_setting": st.settings().notify,
            "pending": pending.iter().map(|(id, at)| serde_json::json!({ "id": id, "at": at.map(|t| chrono::DateTime::from_timestamp(t, 0).map(|d| d.with_timezone(&chrono::Local).to_rfc3339())) })).collect::<Vec<_>>(),
            "delivered": delivered,
            "os": std::env::consts::OS,
            "arch": std::env::consts::ARCH,
        }
    });
    let _ = std::fs::write(&path, serde_json::to_vec_pretty(&out).unwrap_or_default());
    println!("smoke test report: {}", path.display());
    app.exit(0);
}

/// No report in time: write what is known and quit with 2.
pub fn watchdog(app: AppHandle, path: PathBuf) {
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_secs(90));
        let url = app
            .get_webview_window(crate::MAIN)
            .and_then(|w| w.url().ok())
            .map(|u| u.to_string());
        let _ = std::fs::write(
            &path,
            serde_json::to_vec_pretty(
                &serde_json::json!({ "error": "no report in 90 s", "url": url }),
            )
            .unwrap_or_default(),
        );
        std::process::exit(2);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flag() {
        let a = |v: &[&str]| path_from_args(v.iter().map(|s| s.to_string()));
        assert_eq!(
            a(&["flow", "--smoke-test=C:\\t\\smoke.json"]),
            Some(PathBuf::from("C:\\t\\smoke.json"))
        );
        assert_eq!(a(&["flow", "--autostart"]), None);
    }
}
