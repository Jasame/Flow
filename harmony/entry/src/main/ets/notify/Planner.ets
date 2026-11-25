/**
 * Which reminders to put on the phone, from what the site says (GET /api/next/vocab): docs/native-bridge.md §5, the same
 * rules and words as the iOS app's ReminderPlan and Android's notify/Planner.kt (and the server's mail):
 * - Hours are China time, as the mail and the site's .ics are (UTC+8, no summer time): a day is counted in China time.
 * - Every day at the reminder hour, only on a day with words to review: today, what is left now (beyond the day's share
 *   too); a later day, the forecast up to that day (words not reviewed stay due) plus the book's new words while the book
 *   is not finished; after the forecast, every day while there are words or a book. Refreshed whenever the app opens or
 *   goes to the background, so a day done is taken off.
 * - 这次什么时候复习 (once): while it is ahead, no daily one before it; at that time it comes if that day has words; then no
 *   daily one that day; after it, every day again. A once with nothing to review lapses.
 * - The day's plan (我的 → 每天提醒, chosen in the app): every day at its hour; a word reminder at the same time is left out.
 * - An account that has not given a consent the site needs (any 403): no reminders at all, the plan's neither.
 * HarmonyOS keeps at most 30 reminders an app (reminderAgentManager): the first LIMIT by time go on the phone, and the app
 * puts the rest on when it next opens or goes to the background. No system calls here, so the local tests can check it.
 */
const HOUR_MS = 3600000;
const DAY_MS = 86400000;
const CHINA_MS = 8 * HOUR_MS;

export class PlanInput {
  hour: number = 20;
  once: number | null = null;       // seconds since 1970, ahead (the server forgets it once past)
  onceSeen: number | null = null;   // the latest once that went on the phone, kept after it passed
  due: number = 0;                  // today, still to review now
  fresh: number = 0;                // today's new words still to learn ('new' in the site's answer)
  later: number = 0;                // due today beyond the day's share
  minutes: number = 0;
  forecast: number[] = [];          // reviews due on each of the next days (0 = today, overdue in it)
  dailyNew: number = 0;             // the book's new words a day, while the book is not finished
  hasWords: boolean = false;        // any word cards at all
  planHour: number | null = null;   // the day's plan reminder (from the app; null = off)
  planMinutes: number = 10;
  app: boolean = false;             // the learner turned the app's reminders on (notify.ask / 「到点用 App 通知提醒」)
  paused: boolean = false;          // a consent the site needs is not given (403): no reminders at all

  copy(): PlanInput {
    const x = new PlanInput();
    x.hour = this.hour; x.once = this.once; x.onceSeen = this.onceSeen; x.due = this.due; x.fresh = this.fresh;
    x.later = this.later; x.minutes = this.minutes; x.forecast = this.forecast.slice(); x.dailyNew = this.dailyNew;
    x.hasWords = this.hasWords; x.planHour = this.planHour; x.planMinutes = this.planMinutes; x.app = this.app;
    x.paused = this.paused;
    return x;
  }

  toJson(): string {
    return JSON.stringify(this);
  }

  static fromJson(s: string | undefined): PlanInput {
    const x = new PlanInput();
    if (!s) {
      return x;
    }
    try {
      const o = JSON.parse(s) as Record<string, Object>;
      x.hour = Planner.int(o['hour'], 20);
      x.once = Planner.numOrNull(o['once']);
      x.onceSeen = Planner.numOrNull(o['onceSeen']);
      x.due = Planner.int(o['due'], 0);
      x.fresh = Planner.int(o['fresh'], 0);
      x.later = Planner.int(o['later'], 0);
      x.minutes = Planner.int(o['minutes'], 0);
      x.forecast = Planner.ints(o['forecast']);
      x.dailyNew = Planner.int(o['dailyNew'], 0);
      x.hasWords = o['hasWords'] === true;
      x.planHour = Planner.numOrNull(o['planHour']);
      x.planMinutes = Planner.int(o['planMinutes'], 10);
      x.app = o['app'] === true;
      x.paused = o['paused'] === true;
    } catch (e) {
      // what was kept is unreadable: start over
    }
    return x;
  }
}

export class Slot {
  id: string;
  at: number;   // milliseconds since 1970
  title: string;
  body: string;
  path: string;

  constructor(id: string, at: number, title: string, body: string, path: string) {
    this.id = id;
    this.at = at;
    this.title = title;
    this.body = body;
    this.path = path;
  }
}

export class Planner {
  static readonly DAYS: number = 14;
  static readonly LIMIT: number = 28;           // of HarmonyOS's 30 an app, two left for safety
  static readonly HOUR_MIN: number = 6;         // vocab_service.REMIND_HOURS: 6..23
  static readonly HOUR_MAX: number = 23;

  /** The day (counted in China time) of a moment, as a number of days since 1970. */
  static day(ms: number): number {
    return Math.floor((ms + CHINA_MS) / DAY_MS);
  }

  /** A day's hour (China time) as milliseconds since 1970. */
  static at(day: number, hour: number): number {
    return day * DAY_MS + hour * HOUR_MS - CHINA_MS;
  }

  static clampHour(h: number): number {
    return Math.min(23, Math.max(0, Math.floor(h)));
  }

  static slots(x: PlanInput, now: number): Slot[] {
    if (!x.app || x.paused) {
      return [];
    }
    const out: Slot[] = [];
    const today = Planner.day(now);
    // words to review on day k (k = 0: today, what is left now); -1: not known, but there are words
    const count = (k: number): number => {
      if (k <= 0) {
        return x.due + x.fresh + x.later;
      }
      if (k < x.forecast.length) {
        let s = 0;
        for (let i = 0; i <= k; i++) {
          s += x.forecast[i];
        }
        return s + x.dailyNew;
      }
      return (x.hasWords || x.dailyNew > 0) ? -1 : 0;
    };
    const onceMs = x.once !== null && x.once * 1000 > now ? x.once * 1000 : null;
    const onceCounts = onceMs !== null && count(Planner.day(onceMs) - today) !== 0;
    // the day of a once that already came (or will, with words): its daily one does not
    let onceDay: number | null = null;
    if (onceMs !== null && onceCounts) {
      onceDay = Planner.day(onceMs);
    } else if (x.onceSeen !== null && x.onceSeen * 1000 <= now) {
      onceDay = Planner.day(x.onceSeen * 1000);
    }
    const soon = now + 60000;
    for (let k = 0; k < Planner.DAYS; k++) {
      const day = today + k;
      const tag = Planner.dateTag(day);
      let planAt: number | null = null;
      if (x.planHour !== null) {
        const t = Planner.at(day, Planner.clampHour(x.planHour));
        if (t > soon) {
          planAt = t;
          out.push(new Slot('plan-' + tag, t, '今天的学习',
            '打开今天的计划：到期的单词、今天这篇材料、该复习的语法点，大约 ' + x.planMinutes + ' 分钟。', '#/'));
        }
      }
      const t = Planner.at(day, Planner.clampHour(x.hour));
      if (t <= soon) {
        continue;
      }
      if (onceMs !== null && t < onceMs) {
        continue;   // waiting for the chosen time
      }
      if (onceDay !== null && day === onceDay) {
        continue;   // that day's reminder was the chosen one
      }
      if (planAt !== null && planAt === t) {
        continue;
      }
      const n = count(k);
      if (n === 0) {
        continue;
      }
      const due = k < x.forecast.length ? x.forecast[k] : 0;
      let body: string;
      if (k === 0) {
        body = '今天还有 ' + n + ' 个词等你复习' + (x.minutes > 0 ? '，大约 ' + x.minutes + ' 分钟。' : '。') + '记忆曲线到点了，现在复习效果最好。';
      } else if (due > 0) {
        body = '今天大约有 ' + due + ' 个词到期。记忆曲线到点了，现在复习效果最好。';
      } else if (n > x.dailyNew) {
        body = '还有没复习完的词在等你，几分钟就好。';
      } else if (x.dailyNew > 0) {
        body = '今天的新词准备好了，复习加新词几分钟就好。';
      } else {
        body = '到期的单词在等你，记忆曲线到点了，现在复习效果最好。';
      }
      out.push(new Slot('review-' + tag, t, '该复习单词了', body, '#/review'));
    }
    if (onceMs !== null && onceCounts) {
      const n = count(Planner.day(onceMs) - today);
      out.push(new Slot('review-once', onceMs, '到你选的复习时间了',
        n > 0 ? '你选的复习时间到了：' + n + ' 个词等你，现在复习记得最牢。' : '你选的复习时间到了，现在复习记得最牢。', '#/review'));
    }
    out.sort((a: Slot, b: Slot) => a.at - b.at);
    return out.slice(0, Planner.LIMIT);
  }

  /** From GET /api/next/vocab (reminder, forecast, counts, plan, book, total); keeps what only the app knows. */
  static input(j: Record<string, Object>, old: PlanInput): PlanInput {
    const x = old.copy();
    const r = j['reminder'];
    if (r !== undefined && r !== null && typeof r === 'object') {
      const rr = r as Record<string, Object>;
      const h = Planner.numOrNull(rr['hour']);
      if (h !== null && h >= Planner.HOUR_MIN && h <= Planner.HOUR_MAX) {
        x.hour = h;
      }
      if (Object.keys(rr).indexOf('once') >= 0) {
        x.once = Planner.numOrNull(rr['once']);  // an older server does not know it: the app's stays
      }
    }
    x.due = Planner.int(j['due'], 0);
    x.fresh = Planner.int(j['new'], 0);
    x.later = Planner.int(j['later'], 0);
    x.minutes = Planner.int(j['minutes'], 0);
    x.forecast = Planner.ints(j['forecast']);
    const plan = j['plan'] as Record<string, Object> | undefined;
    const book = j['book'] as Record<string, Object> | undefined;
    const bookOn = (book !== undefined && book !== null) ? book['done'] !== true : (plan !== undefined && plan !== null);
    const pausedNew = j['new_paused'] === true;
    x.dailyNew = (bookOn && !pausedNew && plan) ? Math.max(0, Planner.int(plan['daily_new'], 0)) : 0;
    x.hasWords = Planner.int(j['total'], 0) > 0;
    x.paused = false;  // the site answered: the account is in use again
    return x;
  }

  /** After scheduling: a once that went on the phone is remembered, so after it passed that day's daily one stays away. */
  static remember(x: PlanInput, scheduled: Slot[]): PlanInput {
    if (x.once === null) {
      return x;
    }
    if (!scheduled.some((s: Slot) => s.id === 'review-once')) {
      return x;
    }
    const y = x.copy();
    y.onceSeen = Math.max(x.once, x.onceSeen ?? 0);
    return y;
  }

  /** Signed out: no word reminders for an account that is not here (the day's plan needs none). */
  static signedOut(old: PlanInput): PlanInput {
    const x = new PlanInput();
    x.planHour = old.planHour;
    x.planMinutes = old.planMinutes;
    x.app = old.app;
    return x;
  }

  /** A consent the site needs is not given (403): nothing at all until it is; the hours are kept. */
  static paused(old: PlanInput): PlanInput {
    const x = Planner.signedOut(old);
    x.hour = old.hour;
    x.paused = true;
    return x;
  }

  /** Which consent a 403 asks for: `need` ('storage' | 'terms') first, then `code`. */
  static consentNeeded(answer: Record<string, Object>): string | null {
    const need = typeof answer['need'] === 'string' ? answer['need'] as string : '';
    if (need) {
      return need;
    }
    const code = typeof answer['code'] === 'string' ? answer['code'] as string : '';
    return code ? code : null;
  }

  static pausedLine(code: string | null): string {
    if (code === 'storage') {
      return '先在页面上回答「数据存放在香港」那一问：同意以后，提醒会自己排上。';
    }
    if (code === 'terms') {
      return '先在页面上同意《用户协议》和《隐私和数据》：同意以后，提醒会自己排上。';
    }
    return '这个账号现在排不了提醒：先按页面上的提示处理，处理好以后提醒会自己排上。';
  }

  /** 「今天 12:30」「明天 8:00」「11月28日 9:00」 in China time. */
  static label(secs: number, now: number): string {
    const ms = secs * 1000;
    const d = Planner.day(ms) - Planner.day(now);
    const c = new Date(ms + CHINA_MS);  // its UTC fields are China time
    const hm = c.getUTCHours() + ':' + (c.getUTCMinutes() < 10 ? '0' : '') + c.getUTCMinutes();
    if (d === 0) {
      return '今天 ' + hm;
    }
    if (d === 1) {
      return '明天 ' + hm;
    }
    return (c.getUTCMonth() + 1) + '月' + c.getUTCDate() + '日 ' + hm;
  }

  static dateTag(day: number): string {
    const c = new Date(day * DAY_MS);
    const m = c.getUTCMonth() + 1;
    const d = c.getUTCDate();
    return c.getUTCFullYear() + '-' + (m < 10 ? '0' : '') + m + '-' + (d < 10 ? '0' : '') + d;
  }

  static int(v: Object | undefined | null, def: number): number {
    return typeof v === 'number' && !isNaN(v as number) ? Math.floor(v as number) : def;
  }

  static numOrNull(v: Object | undefined | null): number | null {
    return typeof v === 'number' && !isNaN(v as number) ? v as number : null;
  }

  static ints(v: Object | undefined | null): number[] {
    if (!Array.isArray(v)) {
      return [];
    }
    const a = v as Object[];
    return a.map((n: Object) => Planner.int(n, 0));
  }
}
