//! Menus. macOS: the menu bar (语流 / 编辑 / 显示 / 窗口 / 帮助), with the app's switches in the 语流 menu.
//! Windows: an icon in the tray (like most Windows apps) with the same switches; the page itself has no menu bar.

use crate::{AppState, Wry};
use std::sync::Mutex;
use tauri::menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem};
use tauri::{AppHandle, Manager};
use tauri_plugin_autostart::ManagerExt;

pub struct Handles {
    notify: CheckMenuItem<Wry>,
    autostart: CheckMenuItem<Wry>,
    #[allow(dead_code)]
    tray: Option<CheckMenuItem<Wry>>,
}

#[derive(Default)]
pub struct MenuState(pub Mutex<Option<Handles>>);

/// Tick marks follow the settings (after the page turned reminders on, or the system changed autostart).
pub fn refresh(app: &AppHandle) {
    let st = app.state::<AppState>().settings();
    let auto = app.autolaunch().is_enabled().unwrap_or(false);
    if let Some(h) = app.state::<MenuState>().0.lock().unwrap().as_ref() {
        let _ = h.notify.set_checked(st.notify);
        let _ = h.autostart.set_checked(auto);
        if let Some(t) = &h.tray {
            let _ = t.set_checked(st.close_to_tray);
        }
    }
}

fn switches(
    app: &AppHandle,
) -> tauri::Result<(CheckMenuItem<Wry>, CheckMenuItem<Wry>, MenuItem<Wry>)> {
    let st = app.state::<AppState>().settings();
    let notify = CheckMenuItem::with_id(
        app,
        "notify",
        "复习提醒用系统通知",
        true,
        st.notify,
        None::<&str>,
    )?;
    let autostart = CheckMenuItem::with_id(
        app,
        "autostart",
        "开机时启动",
        true,
        app.autolaunch().is_enabled().unwrap_or(false),
        None::<&str>,
    )?;
    let test = MenuItem::with_id(app, "test-notify", "发一条测试通知", true, None::<&str>)?;
    Ok((notify, autostart, test))
}

#[cfg(target_os = "macos")]
pub fn build(app: &AppHandle) -> tauri::Result<()> {
    use tauri::menu::{AboutMetadata, Submenu};
    let name = app.state::<AppState>().channel.name();
    let (notify, autostart, test) = switches(app)?;
    let about = AboutMetadata {
        name: Some(name.into()),
        version: Some(app.package_info().version.to_string()),
        copyright: Some("语流 Flow · flowlang.cn".into()),
        ..Default::default()
    };
    let sep = || PredefinedMenuItem::separator(app);
    let mut app_items: Vec<Box<dyn tauri::menu::IsMenuItem<Wry>>> = vec![
        Box::new(PredefinedMenuItem::about(
            app,
            Some(&format!("关于{name}")),
            Some(about),
        )?),
        Box::new(sep()?),
        Box::new(notify.clone()),
        Box::new(autostart.clone()),
        Box::new(test),
    ];
    if cfg!(feature = "updater") {
        app_items.push(Box::new(MenuItem::with_id(
            app,
            "update",
            "检查更新…",
            true,
            None::<&str>,
        )?));
    }
    app_items.extend::<Vec<Box<dyn tauri::menu::IsMenuItem<Wry>>>>(vec![
        Box::new(sep()?),
        Box::new(PredefinedMenuItem::services(app, Some("服务"))?),
        Box::new(sep()?),
        Box::new(PredefinedMenuItem::hide(app, Some(&format!("隐藏{name}")))?),
        Box::new(PredefinedMenuItem::hide_others(app, Some("隐藏其他"))?),
        Box::new(PredefinedMenuItem::show_all(app, Some("全部显示"))?),
        Box::new(sep()?),
        Box::new(PredefinedMenuItem::quit(app, Some(&format!("退出{name}")))?),
    ]);
    let refs: Vec<&dyn tauri::menu::IsMenuItem<Wry>> =
        app_items.iter().map(|b| b.as_ref()).collect();
    let app_menu = Submenu::with_items(app, name, true, &refs)?;
    let edit = Submenu::with_items(
        app,
        "编辑",
        true,
        &[
            &PredefinedMenuItem::undo(app, Some("撤销"))?,
            &PredefinedMenuItem::redo(app, Some("重做"))?,
            &sep()?,
            &PredefinedMenuItem::cut(app, Some("剪切"))?,
            &PredefinedMenuItem::copy(app, Some("拷贝"))?,
            &PredefinedMenuItem::paste(app, Some("粘贴"))?,
            &PredefinedMenuItem::select_all(app, Some("全选"))?,
        ],
    )?;
    let view = Submenu::with_items(
        app,
        "显示",
        true,
        &[
            &MenuItem::with_id(app, "back", "后退", true, Some("CmdOrCtrl+["))?,
            &MenuItem::with_id(app, "forward", "前进", true, Some("CmdOrCtrl+]"))?,
            &MenuItem::with_id(app, "home", "回到今日", true, Some("CmdOrCtrl+Shift+H"))?,
            &MenuItem::with_id(app, "reload", "重新载入", true, Some("CmdOrCtrl+R"))?,
            &sep()?,
            &MenuItem::with_id(app, "zoom-reset", "实际大小", true, Some("CmdOrCtrl+0"))?,
            &MenuItem::with_id(app, "zoom-in", "放大", true, Some("CmdOrCtrl+="))?,
            &MenuItem::with_id(app, "zoom-out", "缩小", true, Some("CmdOrCtrl+-"))?,
            &sep()?,
            &PredefinedMenuItem::fullscreen(app, Some("进入全屏幕"))?,
        ],
    )?;
    let window = Submenu::with_items(
        app,
        "窗口",
        true,
        &[
            &PredefinedMenuItem::minimize(app, Some("最小化"))?,
            &PredefinedMenuItem::maximize(app, Some("缩放"))?,
            &sep()?,
            &PredefinedMenuItem::close_window(app, Some("关闭窗口"))?,
        ],
    )?;
    let help = Submenu::with_items(
        app,
        "帮助",
        true,
        &[
            &MenuItem::with_id(app, "guide", "操作指南", true, None::<&str>)?,
            &MenuItem::with_id(app, "privacy", "隐私和数据", true, None::<&str>)?,
        ],
    )?;
    app.set_menu(Menu::with_items(
        app,
        &[&app_menu, &edit, &view, &window, &help],
    )?)?;
    *app.state::<MenuState>().0.lock().unwrap() = Some(Handles {
        notify,
        autostart,
        tray: None,
    });
    Ok(())
}

#[cfg(not(target_os = "macos"))]
pub fn build(app: &AppHandle) -> tauri::Result<()> {
    use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
    let st = app.state::<AppState>();
    let name = st.channel.name();
    let (notify, autostart, test) = switches(app)?;
    let tray = CheckMenuItem::with_id(
        app,
        "tray",
        "关窗口后留在托盘",
        true,
        st.settings().close_to_tray,
        None::<&str>,
    )?;
    let sep = || PredefinedMenuItem::separator(app);
    let mut items: Vec<Box<dyn tauri::menu::IsMenuItem<Wry>>> = vec![
        Box::new(MenuItem::with_id(
            app,
            "show",
            format!("打开{name}"),
            true,
            None::<&str>,
        )?),
        Box::new(sep()?),
        Box::new(notify.clone()),
        Box::new(autostart.clone()),
        Box::new(tray.clone()),
        Box::new(test),
    ];
    if cfg!(feature = "updater") {
        items.push(Box::new(MenuItem::with_id(
            app,
            "update",
            "检查更新…",
            true,
            None::<&str>,
        )?));
    }
    items.push(Box::new(sep()?));
    items.push(Box::new(MenuItem::with_id(
        app,
        "guide",
        "操作指南",
        true,
        None::<&str>,
    )?));
    items.push(Box::new(MenuItem::with_id(
        app,
        "privacy",
        "隐私和数据",
        true,
        None::<&str>,
    )?));
    items.push(Box::new(sep()?));
    items.push(Box::new(MenuItem::with_id(
        app,
        "quit",
        "退出",
        true,
        None::<&str>,
    )?));
    let refs: Vec<&dyn tauri::menu::IsMenuItem<Wry>> = items.iter().map(|b| b.as_ref()).collect();
    let menu = Menu::with_items(app, &refs)?;
    TrayIconBuilder::with_id("main")
        .icon(
            app.default_window_icon()
                .cloned()
                .ok_or(tauri::Error::InvalidIcon(std::io::Error::other("no icon")))?,
        )
        .tooltip(name)
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|t, e| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = e
            {
                crate::show_main(t.app_handle());
            }
        })
        .build(app)?;
    *app.state::<MenuState>().0.lock().unwrap() = Some(Handles {
        notify,
        autostart,
        tray: Some(tray),
    });
    Ok(())
}
