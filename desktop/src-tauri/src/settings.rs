//! The app's own switches, in settings.json next to the window state (app config folder). Nothing here leaves
//! the computer.

use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(default)]
pub struct Settings {
    /// 复习提醒用系统通知: turned on by 「到点用 App 通知提醒」 in the page (FlowApp.notify.ask), or the menu
    pub notify: bool,
    /// Windows: closing the window keeps 语流 in the tray (the reminders are the system's either way)
    pub close_to_tray: bool,
    /// the latest 「这次什么时候复习」 time the app knew of (schedule::Input::once_seen): its day gets no second reminder
    pub once_seen: Option<f64>,
}

// not derivable on every target: close_to_tray differs on Linux
#[allow(clippy::derivable_impls)]
impl Default for Settings {
    fn default() -> Self {
        Settings {
            notify: false,
            // Linux has no system that shows reminders while 语流 is closed: it stays in the tray unless turned off
            close_to_tray: cfg!(target_os = "linux"),
            once_seen: None,
        }
    }
}

pub fn load(path: &Path) -> Settings {
    std::fs::read_to_string(path)
        .ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_default()
}

pub fn save(path: &Path, s: &Settings) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, serde_json::to_vec_pretty(s).unwrap_or_default())?;
    std::fs::rename(tmp, path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_or_broken_file_gives_defaults() {
        let dir = std::env::temp_dir().join(format!("flow-desktop-test-{}", std::process::id()));
        let p = dir.join("settings.json");
        assert_eq!(load(&p), Settings::default());
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(&p, "{not json").unwrap();
        assert_eq!(load(&p), Settings::default());
        // older files without a field keep the default for it
        std::fs::write(&p, r#"{"notify":true}"#).unwrap();
        assert_eq!(
            load(&p),
            Settings {
                notify: true,
                ..Default::default()
            }
        );
        let s = Settings {
            notify: true,
            close_to_tray: true,
            once_seen: Some(1764140400.0),
        };
        save(&p, &s).unwrap();
        assert_eq!(load(&p), s);
        std::fs::remove_dir_all(dir).ok();
    }
}
