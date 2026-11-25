import { reminderAgentManager } from '@kit.BackgroundTasksKit';
import { notificationManager } from '@kit.NotificationKit';
import { bundleManager } from '@kit.AbilityKit';
import { preferences } from '@kit.ArkData';
import { AppState } from '../common/AppState';
import { Permissions } from '../common/Permissions';
import { Planner, PlanInput, Slot } from './Planner';

enum Outcome { FRESH, SIGNED_OUT, PAUSED, OFFLINE }

/**
 * FlowApp.notify (docs/native-bridge.md §5): review reminders, and the day's plan, as the phone's own notifications. The
 * site stays the place where the hour and 这次什么时候复习 are set; the app reads them (with the web view's cookies) when
 * it opens and when it goes to the background, and whenever the page says one changed (sync). Planner has the rules (the
 * same as iOS and Android). The system's 后台代理提醒 (reminderAgentManager) shows them at the time, the app running or
 * not, after a restart too; nothing goes through a push server, nothing leaves the phone.
 */
export class Reminders {
  private static lastFetch: number = 0;
  private static generation: number = 0;
  private static pausedCode: string | null = null;

  private static store(): preferences.Preferences | undefined {
    const ctx = AppState.context;
    return ctx ? preferences.getPreferencesSync(ctx, { name: 'flow-remind' }) : undefined;
  }

  static input(): PlanInput {
    const s = Reminders.store();
    return PlanInput.fromJson(s ? s.getSync('input', '') as string : '');
  }

  private static save(x: PlanInput): void {
    const s = Reminders.store();
    if (s) {
      s.putSync('input', x.toJson());
      s.flush();
    }
  }

  /** Opened and back on screen: what the site says now (at most every 10 minutes); to the background: the same. */
  static init(): void {
    AppState.onForeground.push(() => {
      Reminders.refresh(false);
    });
    AppState.onBackground.push(() => {
      Reminders.refresh(false);
    });
  }

  /**
   * 'granted': turned on in the app and allowed by the phone. 'undetermined': not turned on yet, or the system's question
   * can still come. 'denied': switched off in the settings after it was asked.
   */
  static async permission(): Promise<string> {
    const allowed = Permissions.notifyAllowed();
    if (allowed && Reminders.input().app) {
      return 'granted';
    }
    if (allowed || !Permissions.notifyAskedBefore()) {
      return 'undetermined';
    }
    return 'denied';
  }

  /** ask() true = the learner turned the app's reminders on (again, after off()). */
  static async ask(): Promise<boolean> {
    const ok = await Permissions.askNotify();
    if (ok) {
      const x = Reminders.input();
      x.app = true;
      Reminders.save(x);
      await Reminders.refresh(true);
    }
    return ok;
  }

  /**
   * The page's sync(r): r is its `reminder` ({hour, once, …}), maybe with forecast and `app`; null = off.
   * → {ok, permission, scheduled (how many), next (seconds), exact}
   */
  static async sync(r: Record<string, Object> | null): Promise<Object> {
    const x = Reminders.input();
    if (r === null) {
      x.app = false;
    } else {
      if (typeof r['app'] === 'boolean') {
        x.app = r['app'] as boolean;
      }
      const h = Planner.numOrNull(r['hour']);
      if (h !== null && h >= Planner.HOUR_MIN && h <= Planner.HOUR_MAX) {
        x.hour = h;
      }
      if (Object.keys(r).indexOf('once') >= 0) {
        x.once = Planner.numOrNull(r['once']);
      }
      if (Array.isArray(r['forecast'])) {
        x.forecast = Planner.ints(r['forecast']);
      }
    }
    Reminders.save(x);
    await Reminders.refresh(true);
    const list = Reminders.scheduled();
    const out: Record<string, Object | null> = {
      'ok': true, 'permission': await Reminders.permission(), 'scheduled': list.length,
      'next': list.length > 0 ? list[0].at / 1000 : null, 'exact': true,
    };
    return out;
  }

  /** Ask the site for the counts and the reminder (when on), then put the next two weeks on the phone. */
  static async refresh(force: boolean): Promise<Outcome> {
    if (!Reminders.input().app) {
      await Reminders.schedule();
      return Outcome.FRESH;
    }
    if (!force && Date.now() - Reminders.lastFetch < 10 * 60000) {
      await Reminders.schedule();
      return Outcome.FRESH;
    }
    const mine = ++Reminders.generation;
    let outcome = Outcome.FRESH;
    try {
      const a = await AppState.request('/api/next/vocab');
      if (mine !== Reminders.generation) {
        return Outcome.FRESH;  // a newer refresh is under way: its answer counts
      }
      Reminders.lastFetch = Date.now();
      if (a.code === 401) {
        Reminders.save(Planner.signedOut(Reminders.input()));
        outcome = Outcome.SIGNED_OUT;
      } else if (a.code === 403) {
        // a consent not given yet (code 'storage', `need` says which): no reminders at all until it is given
        Reminders.pausedCode = Planner.consentNeeded(a.json());
        Reminders.save(Planner.paused(Reminders.input()));
        outcome = Outcome.PAUSED;
      } else if (a.ok()) {
        Reminders.save(Planner.input(a.json(), Reminders.input()));
      } else {
        outcome = Outcome.OFFLINE;
      }
    } catch (e) {
      outcome = Outcome.OFFLINE;  // what was known last time
    }
    await Reminders.schedule();
    return outcome;
  }

  /** Put the planned reminders on the phone, taking off the old ones first. */
  static async schedule(): Promise<Slot[]> {
    try {
      await reminderAgentManager.cancelAllReminders();
    } catch (e) {
      AppState.warn('cancel reminders: ' + JSON.stringify(e));
    }
    let x = Reminders.input();
    if (!x.app || !Permissions.notifyAllowed()) {
      Reminders.keep([]);
      return [];
    }
    const slots = Planner.slots(x, Date.now());
    x = Planner.remember(x, slots);
    Reminders.save(x);
    const bundle = bundleManager.getBundleInfoForSelfSync(bundleManager.BundleFlag.GET_BUNDLE_INFO_DEFAULT).name;
    const put: Slot[] = [];
    for (let i = 0; i < slots.length; i++) {
      const s = slots[i];
      const d = new Date(s.at);  // the phone's own time zone: what the system's calendar reminder reads
      const req: reminderAgentManager.ReminderRequestCalendar = {
        reminderType: reminderAgentManager.ReminderType.REMINDER_TYPE_CALENDAR,
        dateTime: {
          year: d.getFullYear(), month: d.getMonth() + 1, day: d.getDate(),
          hour: d.getHours(), minute: d.getMinutes(), second: 0,
        },
        title: s.title,
        content: s.body,
        notificationId: 2000 + i,
        slotType: notificationManager.SlotType.SERVICE_INFORMATION,
        tapDismissed: true,
        ringDuration: 0,
        snoozeTimes: 0,
        wantAgent: { pkgName: bundle, abilityName: 'EntryAbility', parameters: { 'flow.path': s.path } },
      };
      try {
        await reminderAgentManager.publishReminder(req);
        put.push(s);
      } catch (e) {
        AppState.warn('publish reminder: ' + JSON.stringify(e));  // over the system's limit, or not allowed after all
        break;
      }
    }
    Reminders.keep(put);
    return put;
  }

  private static keep(slots: Slot[]): void {
    const s = Reminders.store();
    if (s) {
      s.putSync('slots', JSON.stringify(slots));
      s.flush();
    }
  }

  static scheduled(): Slot[] {
    const s = Reminders.store();
    const now = Date.now();
    try {
      const a = JSON.parse(s ? s.getSync('slots', '[]') as string : '[]') as Slot[];
      return a.filter((x: Slot) => x.at > now);
    } catch (e) {
      return [];
    }
  }

  /** FlowApp.notify.pending() → [{id, at (seconds), title, body}] */
  static async pendingJson(): Promise<Object> {
    const out: Record<string, Object>[] = Reminders.scheduled().map((s: Slot) => {
      const o: Record<string, Object> = { 'id': s.id, 'at': s.at / 1000, 'title': s.title, 'body': s.body };
      return o;
    });
    return out;
  }

  /** UI tests (beta builds): schedule from the given counts, without asking the server. */
  static async test(a: Record<string, Object>): Promise<Object> {
    let x = Planner.input(a, Reminders.input());
    if (typeof a['app'] === 'boolean') {
      x = x.copy();
      x.app = a['app'] as boolean;
    }
    if (Object.keys(a).indexOf('planHour') >= 0) {
      x.planHour = Planner.numOrNull(a['planHour']);
    }
    Reminders.save(x);
    await Reminders.schedule();
    const out: Record<string, Object> = { 'ok': true, 'pending': await Reminders.pendingJson() };
    return out;
  }

  /** What 「App 通知」 says while paused (Planner.pausedLine), for the 「加到手机日历」 question. */
  static pausedLine(): string {
    return Planner.pausedLine(Reminders.pausedCode);
  }
}
