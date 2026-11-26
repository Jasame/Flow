//! `--smoke-test=<file>`: open the site, check the bridge from inside the page, write a JSON report and quit
//! (exit 0 = report written; 2 = no report within 90 s). CI runs it on windows-latest and macOS; it is also the
//! quickest check on a new computer. The page can call smoke_report at any time; without the flag it does nothing.

use crate::AppState;
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

/// FLOW_SMOKE_NOTIFY=1: also plan the reminders and show one test notification, report the system's queue, then
/// do what account.changed does (切换账号) and report that nothing planned or shown is left. For CI's Windows and
/// Linux runners (nothing to approve there); a Mac would ask for permission first.
pub fn notify_wanted() -> bool {
    std::env::var_os("FLOW_SMOKE_NOTIFY").is_some_and(|v| v != "0")
}

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
  // which audio the webview can decode: the long recordings are AAC (mp4), server speech mp3. On Linux this follows
  // the GStreamer plugins installed (B3 falls back to AI 朗读 where AAC is '')
  try { const t = new Audio(); r.aac = t.canPlayType('audio/mp4; codecs="mp4a.40.2"'); r.mp3 = t.canPlayType('audio/mpeg'); } catch (e) { r.codecError = String(e); }
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
  // the contract's shape (docs/native-bridge.md §1–2)
  try {
    r.build = F.build; r.beta = F.beta;
    const off = F.on('smoke', () => {}); r.onReturnsOff = typeof off === 'function'; off();
    r.hello = await F.call('hello');
    r.callUnknownRejects = await F.call('no-such-thing').then(() => false, () => true);
    // 切换账号 (§5): resolves with the new plan (signed out here: no word reminders)
    r.accountChanged = await F.call('account.changed').then(x => x, e => ({ rejected: String(e) }));
  } catch (e) { r.shapeError = String(e); }
  // the reminders: a made-up /api/next/vocab answer, planned only where the reminders are on (FLOW_SMOKE_NOTIFY)
  try {
    const now = Math.floor(Date.now() / 1000);
    const v = { reminder: { enabled: false, hour: 20, has_email: false, once: now + 75 }, due: 3, new: 0, later: 0, minutes: 2,
      forecast: [3, 0, 2, 1, 0, 0, 4], plan: { daily_new: 0 }, book: { done: true }, total: 40 };
    const p = await window.__TAURI_INTERNALS__.invoke('notify_plan', { v });
    r.synced = p.planned; r.syncOk = p.ok; if (p.why) r.syncError = p.why;
    r.pendingFromPage = (await F.notify.pending()).map(x => x.id);
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
    let (test_notification, shown, after_account_changed) = if notify_wanted() {
        let launch = format!("{}://open", st.channel.scheme());
        let r = tauri::async_runtime::spawn_blocking(move || {
            crate::notify::show_now("语流 · 冒烟测试", "测试通知，可以忽略。", &launch)
        })
        .await;
        let r = match r {
            Ok(Ok(())) => "shown".to_string(),
            Ok(Err(e)) => e,
            Err(e) => e.to_string(),
        };
        // the notification centre lists it a moment later (Linux keeps no list: nothing to wait for)
        let shown = tauri::async_runtime::spawn_blocking(|| {
            for _ in 0..25 {
                let d = crate::notify::delivered();
                if !d.is_empty() || cfg!(target_os = "linux") {
                    return d;
                }
                std::thread::sleep(std::time::Duration::from_millis(200));
            }
            vec![]
        })
        .await
        .unwrap_or_default();
        // 切换账号 as account.changed does it: nothing planned or shown is left for the last account, and the
        // runner keeps nothing planned
        crate::bridge::forget_account(&app).await;
        let pending = tauri::async_runtime::spawn_blocking(crate::notify::pending)
            .await
            .unwrap_or_default();
        let still = tauri::async_runtime::spawn_blocking(crate::notify::delivered)
            .await
            .unwrap_or_default();
        let after = serde_json::json!({
            "pending": pending.iter().map(|(id, _)| id).collect::<Vec<_>>(),
            "shown": still,
        });
        (Some(r), Some(shown), Some(after))
    } else {
        (None, None, None)
    };
    let out = serde_json::json!({
        "page": r,
        "native": {
            "channel": st.channel.name(),
            "identifier": app.config().identifier,
            "version": app.package_info().version.to_string(),
            "webview": tauri::webview_version().ok(),
            "media_controls": st.media_ok.load(std::sync::atomic::Ordering::Relaxed),
            "media_last_title": st.media_title.lock().unwrap().clone(),
            "media_last_artist": st.media_artist.lock().unwrap().clone(),
            "mute": st.mute,
            "notify_setting": st.settings().notify,
            "smoke_notify": notify_wanted(),
            "test_notification": test_notification,
            "shown": shown,
            "after_account_changed": after_account_changed,
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
