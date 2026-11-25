import { calendarManager } from '@kit.CalendarKit';
import { promptAction } from '@kit.ArkUI';
import { AppState } from './AppState';
import { Ics, IcsEvent } from './Ics';
import { Site } from './Site';

/**
 * 「加到手机日历」 tapped in the app (the site's /api/next/vocab/reminder.ics link): the event goes to the system
 * calendar's own 新建日程 page (Calendar Kit editEvent, API 12+), where the learner saves it. No calendar permission is
 * asked, no browser opens, nothing else is read or written. The reminders of this app until Huawei opens its 代理提醒
 * (bridge/Bridge.ts FEATURES); the file needs no account (vocab_service.ics only reads the link's own hour, kind, at).
 */
export class CalendarLink {
  static isLink(u: string): boolean {
    const p = Site.parse(u);
    return !!p && Site.isOwn(u) && p.pathname === '/api/next/vocab/reminder.ics';
  }

  static async open(u: string): Promise<void> {
    const ctx = AppState.context;
    if (!ctx) {
      return;
    }
    let ev: IcsEvent | null = null;
    try {
      const p = Site.parse(u);
      const a = await AppState.request(p ? p.pathname + p.search : u);
      ev = a.ok() ? Ics.first(a.text) : null;
    } catch (e) {
      ev = null;
    }
    if (!ev) {
      CalendarLink.toast('日历提醒没拿到，稍后再试');
      return;
    }
    const event: calendarManager.Event = {
      type: calendarManager.EventType.NORMAL,
      title: ev.title,
      startTime: ev.start,
      endTime: ev.end,
      description: ev.description,
      reminderTime: [0],  // at the time itself, as the file's own alarm (TRIGGER:PT0M)
    };
    if (ev.daily) {
      event.recurrenceRule = { recurrenceFrequency: calendarManager.RecurrenceFrequency.DAILY };
    }
    try {
      await calendarManager.getCalendarManager(ctx).editEvent(event);
    } catch (e) {
      AppState.warn('calendar: ' + JSON.stringify(e));
      CalendarLink.toast('没能打开系统日历');
    }
  }

  private static toast(message: string): void {
    try {
      promptAction.showToast({ message: message, duration: 3000 });
    } catch (e) {
      // no window to show it in
    }
  }
}
