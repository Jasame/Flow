//! macOS: UNUserNotificationCenter. Works only from the bundled 语流.app (not `cargo run`): outside a bundle
//! there is no notification center, and every call here quietly does nothing.

use super::{route_of, silent, Permission};
use crate::schedule::Planned;
use block2::RcBlock;
use chrono::{Datelike, Local, TimeZone, Timelike};
use objc2::rc::Retained;
use objc2::runtime::{Bool, NSObject, NSObjectProtocol, ProtocolObject};
use objc2::{define_class, msg_send, AllocAnyThread};
use objc2_foundation::{NSBundle, NSDateComponents, NSError, NSString};
use objc2_user_notifications::{
    UNAuthorizationOptions, UNAuthorizationStatus, UNCalendarNotificationTrigger,
    UNMutableNotificationContent, UNNotification, UNNotificationPresentationOptions,
    UNNotificationRequest, UNNotificationResponse, UNNotificationSettings, UNNotificationSound,
    UNUserNotificationCenter, UNUserNotificationCenterDelegate,
};
use std::ptr::NonNull;
use std::sync::mpsc;
use std::sync::OnceLock;
use std::time::Duration;

type OnClick = Box<dyn Fn(Option<&'static str>) + Send + Sync>;
static ON_CLICK: OnceLock<OnClick> = OnceLock::new();

pub struct Ivars;

define_class!(
    #[unsafe(super(NSObject))]
    #[name = "FlowNotifyDelegate"]
    #[ivars = Ivars]
    struct Delegate;

    unsafe impl NSObjectProtocol for Delegate {}

    unsafe impl UNUserNotificationCenterDelegate for Delegate {
        // 语流 in front: still show the banner (the page does not show its own)
        #[unsafe(method(userNotificationCenter:willPresentNotification:withCompletionHandler:))]
        fn will_present(
            &self,
            _center: &UNUserNotificationCenter,
            _n: &UNNotification,
            handler: &block2::DynBlock<dyn Fn(UNNotificationPresentationOptions)>,
        ) {
            let mut o =
                UNNotificationPresentationOptions::Banner | UNNotificationPresentationOptions::List;
            if !silent() {
                o |= UNNotificationPresentationOptions::Sound;
            }
            handler.call((o,));
        }

        #[unsafe(method(userNotificationCenter:didReceiveNotificationResponse:withCompletionHandler:))]
        fn did_receive(
            &self,
            _center: &UNUserNotificationCenter,
            r: &UNNotificationResponse,
            handler: &block2::DynBlock<dyn Fn()>,
        ) {
            let id = r.notification().request().identifier().to_string();
            if let Some(cb) = ON_CLICK.get() {
                cb(route_of(&id));
            }
            handler.call(());
        }
    }
);

fn center() -> Option<Retained<UNUserNotificationCenter>> {
    // currentNotificationCenter raises an exception outside an app bundle (cargo run, unit tests)
    NSBundle::mainBundle().bundleIdentifier()?;
    if !NSBundle::mainBundle()
        .bundlePath()
        .to_string()
        .ends_with(".app")
    {
        return None;
    }
    Some(UNUserNotificationCenter::currentNotificationCenter())
}

/// Call once, on the main thread, before the app finishes launching (a click that launched the app is
/// delivered to this delegate).
pub fn init(_identifier: &str, on_click: impl Fn(Option<&'static str>) + Send + Sync + 'static) {
    let _ = ON_CLICK.set(Box::new(on_click));
    let Some(c) = center() else { return };
    let d: Retained<Delegate> =
        unsafe { msg_send![super(Delegate::alloc().set_ivars(Ivars)), init] };
    c.setDelegate(Some(ProtocolObject::from_ref(&*d)));
    std::mem::forget(d); // the center holds it weakly; it lives as long as the app
}

pub fn permission() -> Permission {
    let Some(c) = center() else {
        return Permission::Denied;
    };
    let (tx, rx) = mpsc::channel();
    let block = RcBlock::new(move |s: NonNull<UNNotificationSettings>| {
        let st = unsafe { s.as_ref() }.authorizationStatus();
        let _ = tx.send(st);
    });
    c.getNotificationSettingsWithCompletionHandler(&block);
    match rx.recv_timeout(Duration::from_secs(5)) {
        Ok(UNAuthorizationStatus::Authorized) | Ok(UNAuthorizationStatus::Provisional) => {
            Permission::Granted
        }
        Ok(UNAuthorizationStatus::NotDetermined) => Permission::Undetermined,
        _ => Permission::Denied,
    }
}

/// The system asks once; after that it answers from System Settings → Notifications.
pub fn ask() -> bool {
    let Some(c) = center() else { return false };
    let (tx, rx) = mpsc::channel();
    let block = RcBlock::new(move |granted: Bool, e: *mut NSError| {
        if let Some(e) = unsafe { e.as_ref() } {
            log::warn!(
                "notification permission: {} ({} {})",
                e.localizedDescription(),
                e.domain(),
                e.code()
            );
        }
        let _ = tx.send(granted.as_bool());
    });
    c.requestAuthorizationWithOptions_completionHandler(
        UNAuthorizationOptions::Alert | UNAuthorizationOptions::Sound,
        &block,
    );
    // the user may take a while to click 允许
    rx.recv_timeout(Duration::from_secs(120)).unwrap_or(false)
}

fn request(id: &str, title: &str, body: &str, at: Option<i64>) -> Retained<UNNotificationRequest> {
    let content = UNMutableNotificationContent::new();
    content.setTitle(&NSString::from_str(title));
    content.setBody(&NSString::from_str(body));
    if !silent() {
        content.setSound(Some(&UNNotificationSound::defaultSound()));
    }
    content.setThreadIdentifier(&NSString::from_str("flow-review"));
    let trigger = at
        .and_then(|at| Local.timestamp_opt(at, 0).single())
        .map(|t| {
            let dc = NSDateComponents::new();
            dc.setYear(t.year() as isize);
            dc.setMonth(t.month() as isize);
            dc.setDay(t.day() as isize);
            dc.setHour(t.hour() as isize);
            dc.setMinute(t.minute() as isize);
            dc.setSecond(t.second() as isize);
            UNCalendarNotificationTrigger::triggerWithDateMatchingComponents_repeats(&dc, false)
        });
    UNNotificationRequest::requestWithIdentifier_content_trigger(
        &NSString::from_str(id),
        &content,
        trigger.as_deref().map(|t| &**t),
    )
}

/// What the system has queued: (id, when it fires, epoch seconds).
pub fn pending() -> Vec<(String, Option<i64>)> {
    let Some(c) = center() else { return vec![] };
    let (tx, rx) = mpsc::channel();
    let block = RcBlock::new(
        move |list: NonNull<objc2_foundation::NSArray<UNNotificationRequest>>| {
            let list = unsafe { list.as_ref() };
            let out: Vec<(String, Option<i64>)> = list
                .iter()
                .map(|r| {
                    let at = r
                        .trigger()
                        .and_then(|t| t.downcast::<UNCalendarNotificationTrigger>().ok())
                        .and_then(|t| t.nextTriggerDate())
                        .map(|d| d.timeIntervalSince1970() as i64);
                    (r.identifier().to_string(), at)
                })
                .collect();
            let _ = tx.send(out);
        },
    );
    c.getPendingNotificationRequestsWithCompletionHandler(&block);
    let mut v = rx.recv_timeout(Duration::from_secs(5)).unwrap_or_default();
    v.sort_by_key(|x| x.1);
    v
}

/// Ids of the notifications shown and still in Notification Centre.
pub fn delivered() -> Vec<String> {
    let Some(c) = center() else { return vec![] };
    let (tx, rx) = mpsc::channel();
    let block = RcBlock::new(
        move |list: NonNull<objc2_foundation::NSArray<UNNotification>>| {
            let ids = unsafe { list.as_ref() }
                .iter()
                .map(|n| n.request().identifier().to_string())
                .collect::<Vec<_>>();
            let _ = tx.send(ids);
        },
    );
    c.getDeliveredNotificationsWithCompletionHandler(&block);
    rx.recv_timeout(Duration::from_secs(5)).unwrap_or_default()
}

pub fn clear() {
    if let Some(c) = center() {
        c.removeAllPendingNotificationRequests();
    }
}

/// The reminders already shown (Notification Center): an account change takes the last account's away.
pub fn clear_shown() {
    if let Some(c) = center() {
        c.removeAllDeliveredNotifications();
    }
}

pub fn schedule(items: &[Planned], _scheme: &str) -> Result<usize, String> {
    let Some(c) = center() else { return Ok(0) };
    c.removeAllPendingNotificationRequests();
    for p in items {
        let id = p.id.clone();
        let done = RcBlock::new(move |e: *mut NSError| {
            if let Some(e) = unsafe { e.as_ref() } {
                log::warn!("{id} not scheduled: {}", e.localizedDescription());
            }
        });
        c.addNotificationRequest_withCompletionHandler(
            &request(&p.id, &p.title, &p.body, Some(p.at)),
            Some(&done),
        );
    }
    Ok(items.len())
}

pub fn show_now(title: &str, body: &str, _launch: &str) -> Result<(), String> {
    let Some(c) = center() else {
        return Err("not in an app bundle".into());
    };
    let done = RcBlock::new(|e: *mut NSError| match unsafe { e.as_ref() } {
        Some(e) => log::warn!("test notification: {}", e.localizedDescription()),
        None => log::info!("test notification sent"),
    });
    c.addNotificationRequest_withCompletionHandler(
        &request("flow-test", title, body, None),
        Some(&done),
    );
    Ok(())
}
