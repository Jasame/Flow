//! 语流 Flow desktop (Windows + macOS): the site in a native window, plus what a browser tab cannot do well —
//! the system's media controls and media keys, review reminders when the app is closed, starting at login,
//! a remembered window, and links to other sites in the default browser.

mod bridge;
mod links;
mod media;
mod menu;
mod notify;
mod schedule;
mod settings;
mod site;
mod smoke;
mod ua;
#[cfg(feature = "updater")]
mod updater;

use settings::Settings;
use site::Channel;
use std::path::PathBuf;
use std::sync::atomic::AtomicI64;
use std::sync::Mutex;
use tauri::webview::{NewWindowResponse, PageLoadEvent, PermissionKind, PermissionResponse};
#[cfg(target_os = "macos")]
use tauri::RunEvent;
use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder, WindowEvent};
use tauri_plugin_autostart::ManagerExt as _;
use tauri_plugin_deep_link::DeepLinkExt;
use tauri_plugin_opener::OpenerExt;
use url::Url;

pub type Wry = tauri::Wry;

/// A few lines on stderr (warnings; everything with FLOW_DESKTOP_LOG=1). No files, nothing sent anywhere.
struct StderrLog(log::LevelFilter);
impl log::Log for StderrLog {
    fn enabled(&self, m: &log::Metadata) -> bool {
        m.level() <= self.0 && m.target().starts_with("flow_desktop")
    }
    fn log(&self, r: &log::Record) {
        if self.enabled(r.metadata()) {
            eprintln!("[语流] {} {}", r.level(), r.args());
        }
    }
    fn flush(&self) {}
}

pub struct AppState {
    pub channel: Channel,
    pub site: Url,
    settings_path: PathBuf,
    settings: Mutex<Settings>,
    /// when the reminders were last planned (epoch seconds; 0 = not yet this run)
    pub last_sync: AtomicI64,
    zoom: Mutex<f64>,
    /// --smoke-test=<file> (smoke.rs)
    pub smoke: Option<PathBuf>,
    pub media_ok: std::sync::atomic::AtomicBool,
    pub media_title: Mutex<Option<String>>,
    /// the reminders last handed to the system (for FlowApp.notify.pending())
    pub last_plan: Mutex<Vec<schedule::Planned>>,
    /// FLOW_MUTE=1 or a smoke test: no sound from the page or the notifications
    pub mute: bool,
}

impl AppState {
    pub fn settings(&self) -> Settings {
        self.settings.lock().unwrap().clone()
    }
    /// A smoke test with FLOW_SMOKE_NOTIFY=1: reminders on for this run only (not saved).
    pub fn force_notify(&self) {
        self.settings.lock().unwrap().notify = true;
    }
    pub fn update_settings(&self, f: impl FnOnce(&mut Settings)) {
        let mut s = self.settings.lock().unwrap();
        f(&mut s);
        if self.smoke.is_some() {
            return; // a smoke test never changes the learner's settings
        }
        if let Err(e) = settings::save(&self.settings_path, &s) {
            log::warn!("settings not saved: {e}");
        }
    }
}

pub(crate) const MAIN: &str = "main";

pub fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window(MAIN) {
        let _ = w.unminimize();
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// Show a page of the site (#/review …) without reloading the app.
fn go(app: &AppHandle, route: &str) {
    let st = app.state::<AppState>();
    let Some(w) = app.get_webview_window(MAIN) else {
        return;
    };
    let on_site = w
        .url()
        .map(|u| links::same_site(&st.site, &u))
        .unwrap_or(false);
    let route: String = route
        .chars()
        .filter(|c| c.is_ascii_alphanumeric() || "/-_".contains(*c))
        .collect();
    if on_site {
        let _ = w.eval(format!("location.hash = {:?}", format!("#{route}")));
    } else {
        let mut u = st.site.clone();
        u.set_fragment(Some(&route));
        let _ = w.navigate(u);
    }
    show_main(app);
}

fn open_link(app: &AppHandle, link: &str) {
    let st = app.state::<AppState>();
    let target = site::deep_link_target(&st.site, st.channel.scheme(), link);
    match target.fragment() {
        Some(f) => go(app, f),
        None => go(app, "/"),
    }
}

fn open_system(app: &AppHandle, u: &Url) {
    if let Err(e) = app.opener().open_url(u.as_str(), None::<&str>) {
        log::warn!("could not open {u}: {e}");
    }
}

fn zoom(app: &AppHandle, how: &str) {
    let st = app.state::<AppState>();
    let mut z = st.zoom.lock().unwrap();
    *z = match how {
        "in" => (*z + 0.1).min(2.0),
        "out" => (*z - 0.1).max(0.6),
        _ => 1.0,
    };
    if let Some(w) = app.get_webview_window(MAIN) {
        let _ = w.set_zoom(*z);
    }
}

fn test_notification(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let st = app.state::<AppState>();
        let launch = format!("{}://open", st.channel.scheme());
        let p = notify::permission();
        log::info!("notification permission before the test: {p:?}");
        if !p.ok() && !notify::ask() {
            log::warn!("notifications are off for this app: opening the system settings");
            open_notification_settings(&app);
            return;
        }
        let _ = notify::show_now(
            "语流 · 通知能用了",
            "到了复习时间，这里会提醒你。点一下就打开语流。",
            &launch,
        );
    });
}

fn open_notification_settings(app: &AppHandle) {
    let url = if cfg!(target_os = "macos") {
        "x-apple.systempreferences:com.apple.Notifications-Settings.extension"
    } else {
        "ms-settings:notifications"
    };
    let _ = app.opener().open_url(url, None::<&str>);
}

fn toggle_notify(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let st = app.state::<AppState>();
        if st.settings().notify {
            st.update_settings(|s| s.notify = false);
            st.last_plan.lock().unwrap().clear();
            notify::clear();
        } else if notify::permission().ok() || notify::ask() {
            st.update_settings(|s| s.notify = true);
            // the page fetches /api/next/vocab with its login and plans (bridge.js)
            if let Some(w) = app.get_webview_window(MAIN) {
                let _ = w.eval("window.FlowApp && FlowApp._replan()");
            }
        } else {
            open_notification_settings(&app);
        }
        menu::refresh(&app);
    });
}

fn on_menu(app: &AppHandle, id: &str) {
    let w = app.get_webview_window(MAIN);
    match id {
        "show" => show_main(app),
        "quit" => app.exit(0),
        "notify" => toggle_notify(app),
        "autostart" => {
            let a = app.autolaunch();
            let _ = if a.is_enabled().unwrap_or(false) {
                a.disable()
            } else {
                a.enable()
            };
            menu::refresh(app);
        }
        "tray" => {
            app.state::<AppState>()
                .update_settings(|s| s.close_to_tray = !s.close_to_tray);
            menu::refresh(app);
        }
        "test-notify" => test_notification(app),
        "back" => {
            if let Some(w) = w {
                let _ = w.eval("history.back()");
            }
        }
        "forward" => {
            if let Some(w) = w {
                let _ = w.eval("history.forward()");
            }
        }
        "reload" => {
            if let Some(w) = w {
                let _ = w.eval("location.reload()");
            }
        }
        "home" => go(app, "/"),
        "guide" => go(app, "/guide"),
        "privacy" => go(app, "/guide/privacy"),
        "zoom-in" => zoom(app, "in"),
        "zoom-out" => zoom(app, "out"),
        "zoom-reset" => zoom(app, "reset"),
        #[cfg(feature = "updater")]
        "update" => updater::check(app.clone(), true),
        _ => {}
    }
}

fn downloads_path(dir: Option<PathBuf>, url: &Url, suggested: &std::path::Path) -> PathBuf {
    let dir = dir.unwrap_or_else(std::env::temp_dir);
    let name = suggested
        .file_name()
        .map(|s| s.to_string_lossy().to_string())
        .filter(|s| !s.is_empty())
        .or_else(|| {
            url.path_segments()
                .and_then(|mut s| s.next_back().map(|x| x.to_string()))
                .filter(|s| !s.is_empty())
        })
        .unwrap_or_else(|| "语流下载".into());
    let mut p = dir.join(&name);
    let (stem, ext) = match name.rsplit_once('.') {
        Some((a, b)) if !a.is_empty() => (a.to_string(), format!(".{b}")),
        _ => (name.clone(), String::new()),
    };
    let mut k = 2;
    while p.exists() {
        p = dir.join(format!("{stem} ({k}){ext}"));
        k += 1;
    }
    p
}

fn build_window(app: &AppHandle, hidden: bool) -> tauri::Result<WebviewWindow> {
    let st = app.state::<AppState>();
    let site = st.site.clone();
    let version = app.package_info().version.to_string();
    let os = ua::Os::current();
    let user_agent = ua::user_agent(os, &version, tauri::webview_version().ok().as_deref());
    let origin = site.origin().ascii_serialization();
    let (s1, s2, s3, a1, a2) = (
        site.clone(),
        site.clone(),
        site.clone(),
        app.clone(),
        app.clone(),
    );
    let builder = WebviewWindowBuilder::new(app, MAIN, WebviewUrl::External(site.clone()))
        .title(st.channel.name())
        .inner_size(1180.0, 820.0)
        .min_inner_size(380.0, 560.0)
        .visible(!hidden)
        .user_agent(&user_agent)
        .initialization_script(bridge::script(&bridge::ScriptVars {
            origin: &origin,
            version: &version,
            build: bridge::build_id(),
            platform: os.platform(),
            beta: st.channel == Channel::Beta,
            mute: st.mute,
        }))
        .zoom_hotkeys_enabled(cfg!(target_os = "windows"))
        .on_navigation(move |u| match links::classify(&s1, u) {
            links::Nav::InApp => true,
            links::Nav::System => {
                open_system(&a1, u);
                false
            }
            links::Nav::Ignore => false,
        })
        .on_new_window(move |u, _features| {
            // target=_blank and window.open: the site's own pages in this window, others in the browser
            match links::classify(&s2, &u) {
                links::Nav::InApp if links::same_site(&s2, &u) => {
                    if let Some(w) = a2.get_webview_window(MAIN) {
                        let _ = w.navigate(u);
                    }
                }
                links::Nav::System | links::Nav::InApp => open_system(&a2, &u),
                links::Nav::Ignore => {}
            }
            NewWindowResponse::Deny
        })
        .on_download(|w, e| {
            if let tauri::webview::DownloadEvent::Requested { url, destination } = e {
                *destination = downloads_path(w.path().download_dir().ok(), &url, destination);
            }
            true
        })
        .on_permission_request(move |w, kind| {
            // the microphone for 跟读、口语、发音 on the site's own pages; nothing else is asked for
            let ours = w.url().map(|u| links::same_site(&s3, &u)).unwrap_or(false);
            match kind {
                PermissionKind::Microphone if ours => PermissionResponse::Allow,
                PermissionKind::Microphone
                | PermissionKind::Camera
                | PermissionKind::Geolocation => PermissionResponse::Deny,
                _ => PermissionResponse::Default,
            }
        })
        .on_page_load(|w, p| {
            if p.event() == PageLoadEvent::Finished {
                log::info!(
                    "loaded {}",
                    w.url().map(|u| u.to_string()).unwrap_or_default()
                );
                if w.app_handle().state::<AppState>().smoke.is_some() {
                    let w = w.clone();
                    std::thread::spawn(move || {
                        std::thread::sleep(std::time::Duration::from_secs(3));
                        let _ = w.eval(smoke::PAGE_CHECK);
                    });
                }
            }
        });
    // WebView2 would answer the media keys itself as well; the app does it (media.rs), once
    #[cfg(target_os = "windows")]
    let builder = builder.additional_browser_args(
        "--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection,HardwareMediaKeyHandling",
    );
    builder.build()
}

fn setup(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let handle = app.handle().clone();
    let channel = Channel::from_identifier(&app.config().identifier);
    let config_dir = app.path().app_config_dir()?;
    let settings_path = config_dir.join("settings.json");
    app.manage(AppState {
        channel,
        site: site::site_url(channel),
        settings: Mutex::new(settings::load(&settings_path)),
        settings_path,
        last_sync: AtomicI64::new(0),
        zoom: Mutex::new(1.0),
        smoke: smoke::path_from_args(std::env::args()),
        media_ok: Default::default(),
        media_title: Mutex::new(None),
        last_plan: Mutex::new(vec![]),
        mute: std::env::var_os("FLOW_MUTE").is_some_and(|v| v != "0")
            || smoke::path_from_args(std::env::args()).is_some(),
    });
    notify::set_silent(app.state::<AppState>().mute);
    if let Some(p) = app.state::<AppState>().smoke.clone() {
        smoke::watchdog(handle.clone(), p);
        if smoke::notify_wanted() {
            app.state::<AppState>().force_notify();
        }
    }
    app.manage(menu::MenuState::default());

    // a click on a reminder (macOS: the delegate; Windows: flowlang://review → the deep link below)
    let h = handle.clone();
    notify::init(&app.config().identifier, move |route| {
        let h2 = h.clone();
        let _ = h.run_on_main_thread(move || match route {
            Some(r) => go(&h2, r),
            None => show_main(&h2),
        });
    });

    let hidden = std::env::args().any(|a| a == "--autostart");
    let window = build_window(&handle, hidden)?;
    menu::build(&handle)?;

    #[cfg(any(target_os = "macos", target_os = "windows"))]
    {
        #[cfg(target_os = "windows")]
        let hwnd = window.hwnd().ok().map(|h| h.0);
        #[cfg(not(target_os = "windows"))]
        let hwnd = None;
        let h = handle.clone();
        if let Err(e) = media::system::init(channel.name(), hwnd, move |key| {
            let h2 = h.clone();
            let _ = h.run_on_main_thread(move || {
                if let Some(a) = media::action_for(key, &media::system::last()) {
                    if let Some(w) = h2.get_webview_window(MAIN) {
                        let _ = w.eval(media::js_for(a));
                    }
                }
            });
        }) {
            log::warn!("media controls unavailable: {e}");
        } else {
            app.state::<AppState>()
                .media_ok
                .store(true, std::sync::atomic::Ordering::Relaxed);
        }
    }
    let _ = &window;

    // flowlang://… : a reminder click on Windows, or a link from elsewhere
    #[cfg(target_os = "windows")]
    let _ = app.deep_link().register_all();
    let h = handle.clone();
    app.deep_link().on_open_url(move |e| {
        if let Some(u) = e.urls().first() {
            open_link(&h, u.as_str());
        }
    });
    if let Ok(Some(urls)) = app.deep_link().get_current() {
        if let Some(u) = urls.first() {
            open_link(&handle, u.as_str());
        }
    }

    #[cfg(feature = "updater")]
    updater::check(handle.clone(), false);
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let level = if std::env::var_os("FLOW_DESKTOP_LOG").is_some() {
        log::LevelFilter::Info
    } else {
        log::LevelFilter::Warn
    };
    if log::set_boxed_logger(Box::new(StderrLog(level))).is_ok() {
        log::set_max_level(level);
    }
    let mut app = tauri::Builder::default();
    if smoke::path_from_args(std::env::args()).is_none() {
        // a second start (a reminder click, the Start menu) brings the running window forward
        app = app.plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main(app)
        }));
    }
    let app = app
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_window_state::Builder::default()
                .with_state_flags(
                    tauri_plugin_window_state::StateFlags::all()
                        & !tauri_plugin_window_state::StateFlags::VISIBLE,
                )
                .build(),
        )
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--autostart"]),
        ));
    #[cfg(feature = "updater")]
    let app = app.plugin(tauri_plugin_updater::Builder::new().build());
    let app = app
        .invoke_handler(tauri::generate_handler![
            bridge::media_update,
            bridge::notify_permission,
            bridge::notify_ask,
            bridge::notify_due,
            bridge::notify_plan,
            bridge::notify_signed_out,
            bridge::notify_off,
            bridge::notify_hold,
            bridge::notify_pending,
            smoke::smoke_report
        ])
        .on_menu_event(|app, e| on_menu(app, e.id().as_ref()))
        .on_window_event(|w, e| {
            if let WindowEvent::CloseRequested { api, .. } = e {
                // macOS: closing the window keeps 语流 in the Dock (⌘Q quits). Windows: quits, unless
                // 「关窗口后留在托盘」 is on. The reminders are the system's either way.
                let keep = cfg!(target_os = "macos")
                    || w.app_handle().state::<AppState>().settings().close_to_tray;
                if keep {
                    api.prevent_close();
                    let _ = w.hide();
                }
            }
        })
        .setup(setup)
        .build(tauri::generate_context!())
        .expect("error while building 语流");
    app.run(|_app, _e| {
        // the Dock icon (macOS only: Windows has the taskbar and the tray)
        #[cfg(target_os = "macos")]
        if let RunEvent::Reopen { .. } = _e {
            show_main(_app);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn downloads_never_overwrite() {
        let dir = std::env::temp_dir().join(format!("flow-dl-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let u = Url::parse("https://flowlang.cn/api/me/export.json").unwrap();
        let p = downloads_path(Some(dir.clone()), &u, std::path::Path::new(""));
        assert_eq!(p, dir.join("export.json"));
        std::fs::write(&p, "x").unwrap();
        assert_eq!(
            downloads_path(Some(dir.clone()), &u, std::path::Path::new("")),
            dir.join("export (2).json")
        );
        assert_eq!(
            downloads_path(
                Some(dir.clone()),
                &u,
                std::path::Path::new("/tmp/语流数据.json")
            ),
            dir.join("语流数据.json")
        );
        std::fs::remove_dir_all(dir).ok();
    }
}
