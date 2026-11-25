//! System media controls (Windows SMTC, macOS 「正在播放」) and the keyboard's media keys.
//!
//! The page keeps playing its own audio, as in any browser. The bridge (bridge.js) watches the page's
//! navigator.mediaSession — the title MS.claim sets, the actions it registers, playing or paused — and sends it
//! here; the system shows it. A media key or a click in the system's controls comes back to the page as the
//! action the page registered (play, pause, previoustrack, nexttrack, stop), so the page stays in charge of
//! the sentence, the progress and what to light up.

use serde::Deserialize;

#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
pub struct MediaState {
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub artist: Option<String>,
    /// navigator.mediaSession.playbackState: "playing" | "paused" | "none"
    #[serde(default)]
    pub state: String,
    /// the actions the page has a handler for
    #[serde(default)]
    pub actions: Vec<String>,
    /// seconds, from the <audio> that is playing (only for long recordings)
    #[serde(default)]
    pub position: Option<f64>,
    #[serde(default)]
    pub duration: Option<f64>,
}

impl MediaState {
    pub fn active(&self) -> bool {
        self.title.is_some() && self.state != "none" && !self.state.is_empty()
    }
    pub fn playing(&self) -> bool {
        self.state == "playing"
    }
    fn has(&self, a: &str) -> bool {
        self.actions.iter().any(|x| x == a)
    }
}

/// A key or button press, whichever system it came from.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Key {
    Play,
    Pause,
    Toggle,
    Next,
    Previous,
    Stop,
}

/// The page's mediaSession action to run for a key, given what is playing now.
pub fn action_for(key: Key, s: &MediaState) -> Option<&'static str> {
    let pick = |a: &'static str| s.has(a).then_some(a);
    match key {
        Key::Play => pick("play"),
        Key::Pause => pick("pause").or_else(|| pick("stop")),
        Key::Toggle => {
            if s.playing() {
                pick("pause").or_else(|| pick("stop"))
            } else {
                pick("play")
            }
        }
        Key::Next => pick("nexttrack"),
        Key::Previous => pick("previoustrack"),
        Key::Stop => pick("stop").or_else(|| pick("pause")),
    }
}

/// Only a finite, sensible timeline goes to the system (a 2-second word clip has none worth showing).
pub fn timeline(s: &MediaState) -> Option<(f64, f64)> {
    match (s.position, s.duration) {
        (Some(p), Some(d)) if d.is_finite() && p.is_finite() && d >= 20.0 && p >= 0.0 => {
            Some((p.min(d), d))
        }
        _ => None,
    }
}

/// The JavaScript that runs an action in the page.
pub fn js_for(action: &str) -> String {
    // action is one of the fixed names above, never page text
    format!("window.FlowApp&&FlowApp._media&&FlowApp._media({action:?})")
}

#[cfg(any(target_os = "macos", target_os = "windows"))]
pub mod system {
    //! souvlaki talks to SMTC / MPNowPlayingInfoCenter. Everything here runs on the main thread.
    use super::*;
    use souvlaki::{
        MediaControlEvent, MediaControls, MediaMetadata, MediaPlayback, MediaPosition,
        PlatformConfig,
    };
    use std::cell::RefCell;
    use std::time::Duration;

    thread_local! {
        static CONTROLS: RefCell<Option<MediaControls>> = const { RefCell::new(None) };
        static LAST: RefCell<MediaState> = RefCell::new(MediaState::default());
    }

    pub fn key_of(e: &MediaControlEvent) -> Option<Key> {
        Some(match e {
            MediaControlEvent::Play => Key::Play,
            MediaControlEvent::Pause => Key::Pause,
            MediaControlEvent::Toggle => Key::Toggle,
            MediaControlEvent::Next => Key::Next,
            MediaControlEvent::Previous => Key::Previous,
            MediaControlEvent::Stop => Key::Stop,
            _ => return None,
        })
    }

    /// `on_key` gets every key press (on whatever thread the system calls back on).
    pub fn init(
        display_name: &str,
        hwnd: Option<*mut std::ffi::c_void>,
        on_key: impl Fn(Key) + Send + 'static,
    ) -> Result<(), String> {
        let config = PlatformConfig {
            display_name,
            dbus_name: "cn.flowlang.desktop",
            hwnd,
        };
        let mut c = MediaControls::new(config).map_err(|e| format!("{e:?}"))?;
        c.attach(move |e| {
            if let Some(k) = key_of(&e) {
                on_key(k)
            }
        })
        .map_err(|e| format!("{e:?}"))?;
        let _ = c.set_playback(MediaPlayback::Stopped);
        CONTROLS.with(|x| *x.borrow_mut() = Some(c));
        Ok(())
    }

    /// The state the page last sent (for the key → action decision).
    pub fn last() -> MediaState {
        LAST.with(|l| l.borrow().clone())
    }

    pub fn update(s: MediaState) {
        CONTROLS.with(|x| {
            let mut x = x.borrow_mut();
            let Some(c) = x.as_mut() else { return };
            let prev = LAST.with(|l| l.borrow().clone());
            let tl = timeline(&s);
            if !s.active() {
                if prev.active() {
                    let _ = c.set_metadata(MediaMetadata::default());
                    let _ = c.set_playback(MediaPlayback::Stopped);
                }
            } else {
                if prev.title != s.title
                    || prev.artist != s.artist
                    || timeline(&prev).map(|t| t.1) != tl.map(|t| t.1)
                    || !prev.active()
                {
                    let _ = c.set_metadata(MediaMetadata {
                        title: s.title.as_deref(),
                        artist: Some(s.artist.as_deref().unwrap_or("语流 Flow")),
                        album: None,
                        cover_url: None,
                        duration: tl.map(|t| Duration::from_secs_f64(t.1)),
                    });
                }
                let progress = tl.map(|t| MediaPosition(Duration::from_secs_f64(t.0)));
                let _ = c.set_playback(if s.playing() {
                    MediaPlayback::Playing { progress }
                } else {
                    MediaPlayback::Paused { progress }
                });
            }
            LAST.with(|l| *l.borrow_mut() = s);
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn st(state: &str, actions: &[&str]) -> MediaState {
        MediaState {
            title: Some("语流 · The Quiet Library".into()),
            state: state.into(),
            actions: actions.iter().map(|s| s.to_string()).collect(),
            ..Default::default()
        }
    }

    #[test]
    fn keys_map_to_the_pages_actions() {
        let all = ["play", "pause", "stop", "previoustrack", "nexttrack"];
        let s = st("playing", &all);
        assert_eq!(action_for(Key::Toggle, &s), Some("pause"));
        assert_eq!(action_for(Key::Next, &s), Some("nexttrack"));
        assert_eq!(action_for(Key::Previous, &s), Some("previoustrack"));
        let s = st("paused", &all);
        assert_eq!(action_for(Key::Toggle, &s), Some("play"));
    }

    #[test]
    fn short_sounds_only_stop() {
        // MS.claim('short', …) registers pause and stop only: no previous / next sentence
        let s = st("playing", &["pause", "stop"]);
        assert_eq!(action_for(Key::Toggle, &s), Some("pause"));
        assert_eq!(action_for(Key::Next, &s), None);
        assert_eq!(action_for(Key::Play, &s), None);
        let s = st("playing", &["stop"]);
        assert_eq!(action_for(Key::Pause, &s), Some("stop"));
    }

    #[test]
    fn nothing_registered_nothing_runs() {
        let s = MediaState::default();
        assert!(!s.active());
        for k in [
            Key::Play,
            Key::Pause,
            Key::Toggle,
            Key::Next,
            Key::Previous,
            Key::Stop,
        ] {
            assert_eq!(action_for(k, &s), None);
        }
    }

    #[test]
    fn timeline_only_for_long_recordings() {
        let mut s = st("playing", &[]);
        s.position = Some(12.0);
        s.duration = Some(180.0);
        assert_eq!(timeline(&s), Some((12.0, 180.0)));
        s.duration = Some(f64::INFINITY);
        assert_eq!(timeline(&s), None);
        s.duration = Some(1.4);
        assert_eq!(timeline(&s), None);
        s.position = Some(200.0);
        s.duration = Some(180.0);
        assert_eq!(timeline(&s), Some((180.0, 180.0)));
    }

    #[test]
    fn js_is_a_fixed_call() {
        assert_eq!(
            js_for("nexttrack"),
            r#"window.FlowApp&&FlowApp._media&&FlowApp._media("nexttrack")"#
        );
    }

    #[test]
    fn parses_what_bridge_js_sends() {
        let s: MediaState = serde_json::from_str(
            r#"{"title":"语流 · 朗读","artist":"语流 Flow","state":"paused","actions":["play","pause"],"position":3.2,"duration":95.5}"#,
        )
        .unwrap();
        assert!(s.active() && !s.playing());
        let s: MediaState =
            serde_json::from_str(r#"{"title":null,"state":"none","actions":[]}"#).unwrap();
        assert!(!s.active());
    }
}
