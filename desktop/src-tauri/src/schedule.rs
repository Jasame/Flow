//! The review reminders the system shows when 语流 is not open — the same rules as the iOS app (shared notes
//! ios-app.md, FlowApp.notify.sync) and the server's reminder mail (vocab_service.send_reminders):
//!  - one a day for the next 7 days at the learner's hour (hour:00, this computer's time);
//!    a day the forecast says has no words due gets none;
//!  - 「这次什么时候复习」 (remindOnce, `once`, epoch seconds): that one reminder replaces the daily ones before it,
//!    and its day gets no daily one; after it, back to every day.

use chrono::{DateTime, Duration, NaiveTime, TimeZone};
use serde::Deserialize;

/// What the page passes to FlowApp.notify.sync: /api/next/vocab's `reminder`, with `forecast` added
/// (words due today, tomorrow, … — 7 numbers).
#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
pub struct Reminder {
    #[serde(default = "default_hour")]
    pub hour: u32,
    #[serde(default)]
    pub once: Option<f64>,
    #[serde(default)]
    pub forecast: Option<Vec<u32>>,
}

fn default_hour() -> u32 {
    20
}

/// The server's BATCH: more than this many words due → 「先复习最要紧的 40 个」, as in the reminder mail.
const BATCH: u32 = 40;
pub const DAYS: i64 = 7;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Planned {
    /// stable per day, so a new sync replaces the old ones
    pub id: String,
    /// epoch seconds
    pub at: i64,
    pub title: String,
    pub body: String,
    /// the page a click opens (fragment of the site)
    pub route: &'static str,
}

fn due_text(n: Option<u32>) -> String {
    match n {
        Some(n) if n > BATCH => format!("今天有 {n} 个单词到期。先复习最要紧的 {BATCH} 个，最容易忘的排在前面，做完这些今天就可以停。"),
        Some(n) if n > 0 => format!("今天有 {n} 个单词该复习了。记忆曲线到点了，现在复习效果最好。"),
        _ => "记忆曲线到点了，今天到期的单词现在复习效果最好。".to_string(),
    }
}

pub fn plan<Tz: TimeZone>(r: &Reminder, now: DateTime<Tz>) -> Vec<Planned> {
    let tz = now.timezone();
    let hour = if r.hour <= 23 { r.hour } else { default_hour() };
    let today = now.date_naive();
    let now_s = now.timestamp();
    let once = r.once.map(|x| x as i64).filter(|&o| o > now_s);
    let once_day = once
        .and_then(|o| tz.timestamp_opt(o, 0).single())
        .map(|d| d.date_naive());

    let mut out = Vec::new();
    for d in 0..DAYS {
        let date = today + Duration::days(d);
        let due = r.forecast.as_ref().and_then(|f| f.get(d as usize).copied());
        if r.forecast.is_some() && due == Some(0) {
            continue; // no words due that day
        }
        let Some(at) = tz
            .from_local_datetime(&date.and_time(NaiveTime::from_hms_opt(hour, 0, 0).unwrap()))
            .earliest()
        else {
            continue; // the hour does not exist that day (a daylight-saving jump)
        };
        let at = at.timestamp();
        if at <= now_s {
            continue;
        }
        if let Some(o) = once {
            if at < o || once_day == Some(date) {
                continue; // replaced by the one-off reminder
            }
        }
        out.push(Planned {
            id: format!("flow-daily-{}", date.format("%Y%m%d")),
            at,
            title: "语流 · 该复习单词了".into(),
            body: due_text(due),
            route: "/review",
        });
    }
    if let (Some(o), Some(day)) = (once, once_day) {
        let d = (day - today).num_days();
        let due = r
            .forecast
            .as_ref()
            .and_then(|f| f.get(d.max(0) as usize).copied());
        out.push(Planned {
            id: "flow-once".into(),
            at: o,
            title: "语流 · 到你约好的复习时间了".into(),
            body: due_text(due),
            route: "/review",
        });
    }
    out.sort_by_key(|p| p.at);
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{FixedOffset, Timelike};

    fn cn() -> FixedOffset {
        FixedOffset::east_opt(8 * 3600).unwrap()
    }
    fn at(y: i32, m: u32, d: u32, h: u32, mi: u32) -> DateTime<FixedOffset> {
        cn().with_ymd_and_hms(y, m, d, h, mi, 0).unwrap()
    }

    #[test]
    fn seven_days_at_the_hour() {
        let r = Reminder {
            hour: 20,
            once: None,
            forecast: None,
        };
        let p = plan(&r, at(2026, 11, 25, 9, 0));
        assert_eq!(p.len(), 7);
        assert_eq!(p[0].id, "flow-daily-20261125");
        assert_eq!(p[6].id, "flow-daily-20261201");
        for x in &p {
            let t = cn().timestamp_opt(x.at, 0).unwrap();
            assert_eq!((t.hour(), t.minute()), (20, 0));
        }
    }

    #[test]
    fn past_hour_today_starts_tomorrow() {
        let r = Reminder {
            hour: 8,
            once: None,
            forecast: None,
        };
        let p = plan(&r, at(2026, 11, 25, 9, 0));
        assert_eq!(p.len(), 6);
        assert_eq!(p[0].id, "flow-daily-20261126");
    }

    #[test]
    fn days_without_words_get_none_and_counts_go_in_the_text() {
        let r = Reminder {
            hour: 20,
            once: None,
            forecast: Some(vec![12, 0, 3, 0, 0, 80, 1]),
        };
        let p = plan(&r, at(2026, 11, 25, 9, 0));
        let ids: Vec<_> = p.iter().map(|x| x.id.as_str()).collect();
        assert_eq!(
            ids,
            [
                "flow-daily-20261125",
                "flow-daily-20261127",
                "flow-daily-20261130",
                "flow-daily-20261201"
            ]
        );
        assert!(p[0].body.contains("12 个单词"));
        assert!(p[2].body.contains("先复习最要紧的 40 个"));
    }

    #[test]
    fn once_replaces_the_daily_ones_before_it_and_its_day() {
        // 「明天下午 3 点」: today's 20:00 and tomorrow's 20:00 are replaced, then daily again
        let once = at(2026, 11, 26, 15, 0).timestamp() as f64;
        let r = Reminder {
            hour: 20,
            once: Some(once),
            forecast: None,
        };
        let p = plan(&r, at(2026, 11, 25, 9, 0));
        assert_eq!(p[0].id, "flow-once");
        assert_eq!(p[0].at, once as i64);
        assert_eq!(p[1].id, "flow-daily-20261127");
        assert_eq!(p.len(), 1 + 5);
    }

    #[test]
    fn once_later_today_drops_only_today() {
        let once = at(2026, 11, 25, 21, 30).timestamp() as f64;
        let r = Reminder {
            hour: 20,
            once: Some(once),
            forecast: Some(vec![5; 7]),
        };
        let p = plan(&r, at(2026, 11, 25, 9, 0));
        assert_eq!(p[0].id, "flow-once");
        assert!(p[0].body.contains("5 个单词"));
        assert_eq!(p[1].id, "flow-daily-20261126");
    }

    #[test]
    fn a_past_once_is_ignored() {
        let once = at(2026, 11, 25, 8, 0).timestamp() as f64;
        let r = Reminder {
            hour: 20,
            once: Some(once),
            forecast: None,
        };
        let p = plan(&r, at(2026, 11, 25, 9, 0));
        assert!(p.iter().all(|x| x.id != "flow-once"));
        assert_eq!(p.len(), 7);
    }

    #[test]
    fn parses_what_the_page_sends() {
        // /api/next/vocab's reminder plus forecast, as #139's appNotify({...x, forecast}) passes it
        let r: Reminder = serde_json::from_str(r#"{"enabled":false,"hour":21,"has_email":false,"once":null,"forecast":[1,2,3,4,5,6,7]}"#).unwrap();
        assert_eq!(r.hour, 21);
        assert_eq!(r.once, None);
        assert_eq!(r.forecast.as_ref().map(|f| f.len()), Some(7));
        let r: Reminder = serde_json::from_str(r#"{"once":1764140400}"#).unwrap();
        assert_eq!((r.hour, r.once), (20, Some(1764140400.0)));
        // a bad hour falls back to 20:00 instead of panicking
        let p = plan(
            &Reminder {
                hour: 99,
                once: None,
                forecast: None,
            },
            at(2026, 11, 25, 9, 0),
        );
        assert_eq!(cn().timestamp_opt(p[0].at, 0).unwrap().hour(), 20);
    }
}
