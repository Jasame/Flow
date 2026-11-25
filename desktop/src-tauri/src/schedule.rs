//! Which review reminders to give the system, worked out from what the site says (GET /api/next/vocab).
//! The same rules as the iOS app (ios/Flow/Remind/ReminderPlan.swift) and the shared contract
//! (docs/native-bridge.md §5), which follow the server's reminder mail (vocab_service.send_reminders):
//!  - Hours are China time (UTC+8), as the mail and the site's .ics are.
//!  - Every day at the reminder hour, only on a day with words to review: today, what is left now (beyond the day's
//!    share too); a later day, the server's forecast up to that day (words not reviewed stay due) plus the book's
//!    new words while the book is not finished; after the forecast, every day while there are words or a book.
//!    The app plans again whenever it opens or comes back to the front, so a day done is taken off.
//!  - 这次什么时候复习 (once): while it is ahead, no daily one before it; at that time it comes if that day has
//!    words; then no daily one that day; after it, every day again.
//!  - The day's plan (我的 → 每天提醒 in an app): every day at its hour; a word reminder at the same time is left out.
//!    (Desktop keeps the field for the contract; its .ics link still goes to the system calendar.)

use chrono::{DateTime, Duration, FixedOffset, NaiveDate, TimeZone, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const DAYS: i64 = 14;
const HOURS: std::ops::RangeInclusive<u32> = 6..=23; // vocab_service.REMIND_HOURS

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct Input {
    pub hour: u32,
    /// seconds since 1970, ahead (the server forgets it once past)
    pub once: Option<f64>,
    /// the latest once the app knew of, kept after it passed (that day's daily is skipped)
    pub once_seen: Option<f64>,
    /// today, still to review now / new words still to learn / due beyond the day's share
    pub due: i64,
    pub new: i64,
    pub later: i64,
    pub minutes: i64,
    /// reviews due on each of the next days (0 = today, overdue in it)
    pub forecast: Vec<i64>,
    /// the book's new words a day, while the book is not finished
    pub daily_new: i64,
    /// any word cards at all
    pub has_words: bool,
    pub plan_hour: Option<u32>,
    pub plan_minutes: u32,
    /// the learner wants the app's reminders (FlowApp.notify.sync({app: false}) / sync(null) turn them off)
    pub app: bool,
}

impl Default for Input {
    fn default() -> Self {
        Input {
            hour: 20,
            once: None,
            once_seen: None,
            due: 0,
            new: 0,
            later: 0,
            minutes: 0,
            forecast: vec![],
            daily_new: 0,
            has_words: false,
            plan_hour: None,
            plan_minutes: 10,
            app: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Planned {
    /// review-2026-11-27, review-once, plan-2026-11-27 (stable, so a new plan replaces the old one)
    pub id: String,
    /// epoch seconds
    pub at: i64,
    pub title: String,
    pub body: String,
    /// the page a click opens: "/review" or "/"
    pub route: &'static str,
}

pub fn china() -> FixedOffset {
    FixedOffset::east_opt(8 * 3600).expect("UTC+8")
}

fn at_hour(day: NaiveDate, hour: u32) -> Option<i64> {
    china()
        .from_local_datetime(&day.and_hms_opt(hour, 0, 0)?)
        .single()
        .map(|t| t.timestamp())
}

pub fn slots(x: &Input, now: DateTime<Utc>) -> Vec<Planned> {
    if !x.app {
        return vec![];
    }
    let cn = china();
    let now_s = now.timestamp();
    let today = now.with_timezone(&cn).date_naive();
    let day = |t: i64| {
        cn.timestamp_opt(t, 0)
            .single()
            .map(|d| d.date_naive())
            .unwrap_or(today)
    };
    let day_of = |t: i64| (day(t) - today).num_days();
    // words to review on day k (0: today, what is left now); -1: not known, but there are words
    let count = |k: i64| -> i64 {
        if k <= 0 {
            return x.due + x.new + x.later;
        }
        if (k as usize) < x.forecast.len() {
            return x.forecast[..=k as usize].iter().sum::<i64>() + x.daily_new;
        }
        if x.has_words || x.daily_new > 0 {
            -1
        } else {
            0
        }
    };
    let once = x.once.map(|o| o as i64).filter(|&o| o > now_s);
    let once_counts = once.map(|o| count(day_of(o)) != 0).unwrap_or(false);
    // the day of a once that already came (or will, with words): its daily one does not
    let once_day = once
        .filter(|_| once_counts)
        .or_else(|| x.once_seen.map(|o| o as i64).filter(|&o| o <= now_s))
        .map(day);

    let mut out = Vec::new();
    for k in 0..DAYS {
        let d = today + Duration::days(k);
        let tag = d.format("%Y-%m-%d");
        let mut plan_at = None;
        if let Some(t) = x
            .plan_hour
            .and_then(|ph| at_hour(d, ph))
            .filter(|&t| t > now_s + 60)
        {
            plan_at = Some(t);
            out.push(Planned {
                id: format!("plan-{tag}"),
                at: t,
                title: "今天的学习".into(),
                body: format!(
                    "打开今天的计划：到期的单词、今天这篇材料、该复习的语法点，大约 {} 分钟。",
                    x.plan_minutes
                ),
                route: "/",
            });
        }
        let Some(t) = at_hour(d, x.hour).filter(|&t| t > now_s + 60) else {
            continue;
        };
        if once.is_some_and(|o| t < o) {
            continue; // waiting for the chosen time
        }
        if once_day == Some(d) {
            continue; // that day's reminder was the chosen one
        }
        if plan_at == Some(t) {
            continue;
        }
        let n = count(k);
        if n == 0 {
            continue;
        }
        let due = x.forecast.get(k as usize).copied().unwrap_or(0);
        let body = if k == 0 {
            format!(
                "今天还有 {n} 个词等你复习{}记忆曲线到点了，现在复习效果最好。",
                if x.minutes > 0 {
                    format!("，大约 {} 分钟。", x.minutes)
                } else {
                    "。".into()
                }
            )
        } else if due > 0 {
            format!("今天大约有 {due} 个词到期。记忆曲线到点了，现在复习效果最好。")
        } else if n > x.daily_new {
            "还有没复习完的词在等你，几分钟就好。".into()
        } else if x.daily_new > 0 {
            "今天的新词准备好了，复习加新词几分钟就好。".into()
        } else {
            "到期的单词在等你，记忆曲线到点了，现在复习效果最好。".into()
        };
        out.push(Planned {
            id: format!("review-{tag}"),
            at: t,
            title: "该复习单词了".into(),
            body,
            route: "/review",
        });
    }
    if let (Some(o), true) = (once, once_counts) {
        let n = count(day_of(o));
        let body = if n > 0 {
            format!("你选的复习时间到了：{n} 个词等你，现在复习记得最牢。")
        } else {
            "你选的复习时间到了，现在复习记得最牢。".into()
        };
        out.push(Planned {
            id: "review-once".into(),
            at: o,
            title: "到你选的复习时间了".into(),
            body,
            route: "/review",
        });
    }
    out.sort_by_key(|p| p.at);
    out
}

fn int(v: Option<&Value>) -> Option<i64> {
    match v? {
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f as i64)),
        Value::String(s) => s.trim().parse().ok(),
        _ => None,
    }
}

fn num(v: Option<&Value>) -> Option<f64> {
    match v? {
        Value::Number(n) => n.as_f64(),
        Value::String(s) => s.trim().parse().ok(),
        _ => None,
    }
}

/// From GET /api/next/vocab (reminder, forecast, counts, plan, book, total); keeps what only the app knows.
pub fn input_from(j: &Value, old: &Input) -> Input {
    let mut x = old.clone();
    if let Some(r) = j.get("reminder").and_then(Value::as_object) {
        if let Some(h) = int(r.get("hour"))
            .and_then(|h| u32::try_from(h).ok())
            .filter(|h| HOURS.contains(h))
        {
            x.hour = h;
        }
        if r.contains_key("once") {
            // an older server does not know it: what the app had stays. once_seen is not touched here:
            // only a once that was really scheduled is remembered (remember())
            x.once = num(r.get("once"));
        }
    }
    x.due = int(j.get("due")).unwrap_or(0);
    x.new = int(j.get("new")).unwrap_or(0);
    x.later = int(j.get("later")).unwrap_or(0);
    x.minutes = int(j.get("minutes")).unwrap_or(0);
    x.forecast = j
        .get("forecast")
        .and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|v| int(Some(v))).collect())
        .unwrap_or_default();
    let plan = j.get("plan").filter(|p| p.is_object());
    let book = j.get("book").filter(|b| b.is_object());
    let book_on = match book {
        Some(b) => !b.get("done").and_then(Value::as_bool).unwrap_or(false),
        None => plan.is_some(),
    };
    let paused = j
        .get("new_paused")
        .and_then(Value::as_bool)
        .unwrap_or(false);
    x.daily_new = if book_on && !paused {
        int(plan.and_then(|p| p.get("daily_new")))
            .unwrap_or(0)
            .max(0)
    } else {
        0
    };
    x.has_words = int(j.get("total")).unwrap_or(0) > 0;
    x
}

/// After scheduling: a once that went to the system (its day had words) is remembered, so that day gets no daily
/// one after it came; a once on a day without words is forgotten (that day's hour stays as usual).
pub fn remember(x: &Input, scheduled: &[Planned]) -> Input {
    let mut y = x.clone();
    if let Some(o) = x
        .once
        .filter(|_| scheduled.iter().any(|p| p.id == "review-once"))
    {
        y.once_seen = Some(o.max(x.once_seen.unwrap_or(0.0)));
    }
    y
}

/// Signed out: no word reminders for an account that is not here (the day's plan needs none).
pub fn signed_out(old: &Input) -> Input {
    Input {
        plan_hour: old.plan_hour,
        plan_minutes: old.plan_minutes,
        app: old.app,
        ..Input::default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Timelike;

    fn t(y: i32, m: u32, d: u32, h: u32, mi: u32) -> DateTime<Utc> {
        china()
            .with_ymd_and_hms(y, m, d, h, mi, 0)
            .unwrap()
            .with_timezone(&Utc)
    }
    fn ids(p: &[Planned]) -> Vec<&str> {
        p.iter().map(|x| x.id.as_str()).collect()
    }
    fn now() -> DateTime<Utc> {
        t(2026, 11, 25, 9, 0)
    }

    #[test]
    fn today_counts_what_is_left_including_later() {
        let x = Input {
            due: 0,
            new: 0,
            later: 5,
            ..Default::default()
        };
        let p = slots(&x, now());
        assert_eq!(p[0].id, "review-2026-11-25");
        assert!(p[0].body.starts_with("今天还有 5 个词等你复习。"));
        let x = Input {
            due: 3,
            minutes: 4,
            ..Default::default()
        };
        assert!(slots(&x, now())[0]
            .body
            .contains("今天还有 3 个词等你复习，大约 4 分钟。"));
        // nothing today, nothing known after: no reminders at all
        assert!(slots(&Input::default(), now()).is_empty());
    }

    #[test]
    fn later_days_add_up_the_forecast_and_new_words() {
        // 12 due today and not reviewed: still there tomorrow (cumulative), so tomorrow is reminded too
        let x = Input {
            due: 12,
            forecast: vec![12, 0, 0, 0, 0, 0, 0],
            ..Default::default()
        };
        let p = slots(&x, now());
        assert_eq!(
            &ids(&p)[..3],
            [
                "review-2026-11-25",
                "review-2026-11-26",
                "review-2026-11-27"
            ]
        );
        assert_eq!(p[1].body, "还有没复习完的词在等你，几分钟就好。");
        // past the forecast nothing is known and there are no cards: stop after day 6
        assert_eq!(p.len(), 7);
        // with cards (or a book), every day of the two weeks
        let x = Input {
            has_words: true,
            ..x
        };
        assert_eq!(slots(&x, now()).len(), DAYS as usize);
        // a day with words due says how many
        let x = Input {
            forecast: vec![0, 7, 0],
            ..Default::default()
        };
        let p = slots(&x, now());
        assert_eq!(p[0].id, "review-2026-11-26");
        assert_eq!(
            p[0].body,
            "今天大约有 7 个词到期。记忆曲线到点了，现在复习效果最好。"
        );
        // only the book's new words
        let x = Input {
            forecast: vec![0, 0],
            daily_new: 10,
            ..Default::default()
        };
        let p = slots(&x, now());
        assert_eq!(p[0].id, "review-2026-11-26");
        assert_eq!(p[0].body, "今天的新词准备好了，复习加新词几分钟就好。");
    }

    #[test]
    fn china_time_at_the_hour_and_not_in_the_past() {
        let x = Input {
            hour: 8,
            due: 1,
            has_words: true,
            ..Default::default()
        };
        let p = slots(&x, now()); // 09:00: today's 08:00 is gone
        assert_eq!(p[0].id, "review-2026-11-26");
        let at = china().timestamp_opt(p[0].at, 0).unwrap();
        assert_eq!((at.hour(), at.minute()), (8, 0));
        // a computer in another time zone still gets 08:00 China time (00:00 UTC)
        assert_eq!(DateTime::from_timestamp(p[0].at, 0).unwrap().hour(), 0);
        // less than a minute ahead counts as past
        let x = Input {
            hour: 9,
            due: 1,
            ..Default::default()
        };
        assert!(slots(&x, t(2026, 11, 25, 8, 59) + Duration::seconds(30))
            .iter()
            .all(|p| p.id != "review-2026-11-25"));
    }

    #[test]
    fn once_replaces_the_daily_ones_before_it_and_its_day() {
        let once = t(2026, 11, 26, 15, 0).timestamp() as f64;
        let x = Input {
            once: Some(once),
            forecast: vec![2, 0, 3],
            due: 2,
            has_words: true,
            ..Default::default()
        };
        let p = slots(&x, now());
        assert_eq!(&ids(&p)[..2], ["review-once", "review-2026-11-27"]);
        assert_eq!(p[0].title, "到你选的复习时间了");
        assert_eq!(
            p[0].body,
            "你选的复习时间到了：2 个词等你，现在复习记得最牢。"
        );
    }

    #[test]
    fn once_on_a_day_without_words_does_not_come() {
        let once = t(2026, 11, 25, 21, 0).timestamp() as f64;
        let x = Input {
            once: Some(once),
            forecast: vec![0, 4],
            ..Default::default()
        };
        let p = slots(&x, now());
        assert!(!ids(&p).contains(&"review-once"));
        assert_eq!(p[0].id, "review-2026-11-26");
    }

    #[test]
    fn a_once_that_came_keeps_its_day_quiet() {
        // 15:00 today came and went; today's 20:00 must not come again (the server's last_sent)
        let seen = t(2026, 11, 25, 15, 0).timestamp() as f64;
        let x = Input {
            once: None,
            once_seen: Some(seen),
            due: 3,
            has_words: true,
            ..Default::default()
        };
        let p = slots(&x, t(2026, 11, 25, 16, 0));
        assert_eq!(p[0].id, "review-2026-11-26");
    }

    #[test]
    fn only_a_once_that_was_scheduled_is_remembered() {
        let once = t(2026, 11, 25, 15, 0).timestamp() as f64;
        // 15:00 with words: scheduled and remembered; after it, today's 20:00 does not come
        let x = Input {
            once: Some(once),
            due: 3,
            has_words: true,
            ..Default::default()
        };
        let y = remember(&x, &slots(&x, now()));
        assert_eq!(y.once_seen, Some(once));
        let after = Input { once: None, ..y };
        assert_eq!(
            slots(&after, t(2026, 11, 25, 16, 0))[0].id,
            "review-2026-11-26"
        );
        // 15:00 without words: neither scheduled nor remembered; new words due by 20:00 are reminded as usual
        let x = Input {
            once: Some(once),
            forecast: vec![0, 0],
            ..Default::default()
        };
        let y = remember(&x, &slots(&x, now()));
        assert_eq!(y.once_seen, None);
        let later = Input {
            once: None,
            due: 4,
            ..y
        };
        assert_eq!(
            slots(&later, t(2026, 11, 25, 16, 0))[0].id,
            "review-2026-11-25"
        );
    }

    #[test]
    fn the_days_plan_comes_first_and_takes_the_hour() {
        let x = Input {
            plan_hour: Some(20),
            plan_minutes: 15,
            due: 1,
            has_words: true,
            ..Default::default()
        };
        let p = slots(&x, now());
        assert_eq!(p[0].id, "plan-2026-11-25");
        assert_eq!(p[0].route, "/");
        assert!(p[0].body.contains("大约 15 分钟"));
        assert!(ids(&p).iter().all(|i| !i.starts_with("review-")));
    }

    #[test]
    fn off_means_none() {
        let x = Input {
            app: false,
            due: 9,
            has_words: true,
            ..Default::default()
        };
        assert!(slots(&x, now()).is_empty());
    }

    #[test]
    fn reads_the_vocab_response() {
        let j: Value = serde_json::from_str(
            r#"{"reminder":{"enabled":false,"hour":21,"has_email":false,"once":1764140400},
                "due":3,"new":2,"later":1,"minutes":6,"forecast":[3,1,0,2,0,0,5],
                "plan":{"daily_new":15},"book":{"done":false},"new_paused":false,"total":120}"#,
        )
        .unwrap();
        let x = input_from(&j, &Input::default());
        assert_eq!(
            (x.hour, x.due, x.new, x.later, x.minutes, x.daily_new),
            (21, 3, 2, 1, 6, 15)
        );
        assert_eq!(x.forecast, vec![3, 1, 0, 2, 0, 0, 5]);
        assert_eq!((x.once, x.once_seen), (Some(1764140400.0), None));
        assert!(x.has_words);
        // the book done or new words paused: no new words a day
        let j2: Value =
            serde_json::from_str(r#"{"plan":{"daily_new":15},"book":{"done":true}}"#).unwrap();
        assert_eq!(input_from(&j2, &x).daily_new, 0);
        let j3: Value =
            serde_json::from_str(r#"{"plan":{"daily_new":15},"new_paused":true}"#).unwrap();
        assert_eq!(input_from(&j3, &x).daily_new, 0);
        // once cleared (null): gone, and what was remembered stays; no reminder key: kept
        let j4: Value = serde_json::from_str(r#"{"reminder":{"hour":20,"once":null}}"#).unwrap();
        let y = input_from(
            &j4,
            &Input {
                once_seen: Some(5.0),
                ..x.clone()
            },
        );
        assert_eq!((y.once, y.once_seen), (None, Some(5.0)));
        let j5: Value = serde_json::from_str(r#"{"reminder":{"hour":99}}"#).unwrap();
        assert_eq!(input_from(&j5, &x).once, x.once);
        assert_eq!(input_from(&j5, &x).hour, 21);
        // signed out keeps only the app's own choices
        let s = signed_out(&Input {
            plan_hour: Some(7),
            app: false,
            ..x
        });
        assert_eq!(
            (s.plan_hour, s.app, s.due, s.once),
            (Some(7), false, 0, None)
        );
    }
}
