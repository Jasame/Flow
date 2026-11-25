import { describe, it, expect } from '@ohos/hypium';
import { Planner, PlanInput, Slot } from '../main/ets/notify/Planner';
import { Sentences, Span } from '../main/ets/audio/Sentences';
import { Wav } from '../main/ets/rec/Wav';
import { Ics } from '../main/ets/common/Ics';

/** 2026-11-<day> <hour>:<minute> China time, as milliseconds. */
function at(day: number, hour: number, minute: number = 0): number {
  return Date.UTC(2026, 10, day, hour - 8, minute);
}

/** The same input as the iOS app's ReminderPlanTests and Android's PlannerTest, so the platforms agree. */
function input(): PlanInput {
  const x = new PlanInput();
  x.hour = 20;
  x.due = 12;
  x.fresh = 0;
  x.minutes = 6;
  x.forecast = [12, 5, 0, 7, 3, 0, 2];
  x.hasWords = true;
  x.app = true;
  return x;
}

function ids(s: Slot[]): string[] {
  return s.map((x: Slot) => x.id);
}

export default function plannerTest() {
  describe('Planner', () => {
    it('every day at the hour, only with words', 0, () => {
      const s = Planner.slots(input(), at(25, 9));
      const i = ids(s);
      expect(i[0]).assertEqual('review-2026-11-25');
      expect(i.indexOf('review-2026-11-26') >= 0).assertTrue();
      expect(i.indexOf('review-2026-11-27') >= 0).assertTrue();  // words not reviewed stay due
      expect(i.indexOf('review-2026-12-08') >= 0).assertTrue();  // after the forecast: while there are words
      expect(s[0].at).assertEqual(at(25, 20));
      expect(s[0].body.indexOf('12 个词') >= 0).assertTrue();
      expect(s.every((x: Slot) => x.path === '#/review')).assertTrue();
    });

    it('no words at all, no reminders', 0, () => {
      const x = input();
      x.due = 0;
      x.forecast = [0, 0, 0, 0, 0, 0, 0];
      x.hasWords = false;
      expect(Planner.slots(x, at(25, 9)).length).assertEqual(0);
    });

    it('nothing left today means no reminder today; beyond the share counts', 0, () => {
      const x = input();
      x.due = 0;
      expect(ids(Planner.slots(x, at(25, 9))).indexOf('review-2026-11-25')).assertEqual(-1);
      x.later = 30;
      expect(ids(Planner.slots(x, at(25, 9))).indexOf('review-2026-11-25') >= 0).assertTrue();
    });

    it('past the hour today starts tomorrow', 0, () => {
      expect(Planner.slots(input(), at(25, 21))[0].id).assertEqual('review-2026-11-26');
    });

    it('once replaces the daily ones until then and that day', 0, () => {
      const x = input();
      x.once = at(26, 12, 30) / 1000;
      const s = Planner.slots(x, at(25, 9));
      const i = ids(s);
      expect(i[0]).assertEqual('review-once');
      expect(s[0].at).assertEqual(at(26, 12, 30));
      expect(i.indexOf('review-2026-11-25')).assertEqual(-1);
      expect(i.indexOf('review-2026-11-26')).assertEqual(-1);
      expect(i.indexOf('review-2026-11-28') >= 0).assertTrue();
    });

    it('a once that came takes that day', 0, () => {
      const x = input();
      x.onceSeen = at(25, 12, 30) / 1000;
      const s = Planner.slots(x, at(25, 13));
      expect(ids(s).indexOf('review-once')).assertEqual(-1);
      expect(ids(s).indexOf('review-2026-11-25')).assertEqual(-1);
      expect(s[0].id).assertEqual('review-2026-11-26');
    });

    it('only a once that was scheduled takes its day', 0, () => {
      let x = input();
      x.once = at(25, 15) / 1000;
      x = Planner.remember(x, Planner.slots(x, at(25, 9)));
      expect(x.onceSeen).assertEqual(at(25, 15) / 1000);
      x.once = null;
      expect(ids(Planner.slots(x, at(25, 16))).indexOf('review-2026-11-25')).assertEqual(-1);
      let y = input();
      y.once = at(25, 15) / 1000;
      y.due = 0;
      y = Planner.remember(y, Planner.slots(y, at(25, 9)));
      expect(y.onceSeen === null).assertTrue();
      y.once = null;
      y.due = 4;
      expect(ids(Planner.slots(y, at(25, 16))).indexOf('review-2026-11-25') >= 0).assertTrue();
    });

    it('the plan reminder, and no double at the same hour', 0, () => {
      const x = input();
      x.planHour = 20;
      x.planMinutes = 15;
      const today = Planner.slots(x, at(25, 9)).filter((s: Slot) => s.id.endsWith('2026-11-25'));
      expect(today.length).assertEqual(1);
      expect(today[0].id).assertEqual('plan-2026-11-25');
      expect(today[0].body.indexOf('15 分钟') >= 0).assertTrue();
      expect(today[0].path).assertEqual('#/');
    });

    it('off until the learner turns it on; paused takes all', 0, () => {
      expect(new PlanInput().app).assertFalse();
      const x = input();
      x.app = false;
      expect(Planner.slots(x, at(25, 9)).length).assertEqual(0);
      expect(Planner.slots(Planner.paused(input()), at(25, 9)).length).assertEqual(0);
    });

    it('never more than HarmonyOS keeps for an app', 0, () => {
      const x = input();
      x.planHour = 8;
      x.once = at(26, 12) / 1000;
      expect(Planner.slots(x, at(25, 7)).length <= Planner.LIMIT).assertTrue();
    });

    it('input from the site', 0, () => {
      const old = new PlanInput();
      old.planHour = 8;
      const j: Record<string, Object> = {
        'reminder': { 'hour': 21, 'once': 1795600000, 'enabled': false } as Record<string, Object>,
        'due': 4, 'new': 10, 'minutes': 7, 'forecast': [4, 3, 2, 1, 0, 0, 5],
        'plan': { 'daily_new': 10, 'book': 'cet4' } as Record<string, Object>, 'total': 120,
      };
      const x = Planner.input(j, old);
      expect(x.hour).assertEqual(21);
      expect(x.once).assertEqual(1795600000);
      expect(x.fresh).assertEqual(10);
      expect(x.dailyNew).assertEqual(10);
      expect(x.hasWords).assertTrue();
      expect(x.planHour).assertEqual(8);  // the app's own setting is kept
      const done: Record<string, Object> = {
        'plan': { 'daily_new': 10 } as Record<string, Object>, 'book': { 'done': true } as Record<string, Object>,
      };
      expect(Planner.input(done, x).dailyNew).assertEqual(0);
      const early: Record<string, Object> = { 'reminder': { 'hour': 3 } as Record<string, Object> };
      expect(Planner.input(early, x).hour).assertEqual(21);  // hours outside REMIND_HOURS are not taken
    });

    it('the line says which consent is missing', 0, () => {
      expect(Planner.pausedLine('storage').indexOf('数据存放在香港') >= 0).assertTrue();
      expect(Planner.pausedLine('terms').indexOf('《用户协议》') >= 0).assertTrue();
      expect(Planner.pausedLine('something-new').indexOf('页面上的提示') >= 0).assertTrue();
      const a: Record<string, Object> = { 'code': 'storage', 'need': 'terms' };
      expect(Planner.consentNeeded(a)).assertEqual('terms');
    });
  });

  describe('Sentences', () => {
    const spans: Span[] = [new Span(0, 2), new Span(2.5, 5), new Span(5.5, 9)];
    it('locate, step and after, as the page', 0, () => {
      expect(Sentences.locate(spans, 1)).assertEqual(0);
      expect(Sentences.locate(spans, 2.2)).assertEqual(0);   // 0.25 s after its end still counts
      expect(Sentences.locate(spans, 2.4)).assertEqual(-1);
      expect(Sentences.stepTarget(spans, 7.5, -1)).assertEqual(2);  // well into it: its start first
      expect(Sentences.stepTarget(spans, 5.8, -1)).assertEqual(1);
      expect(Sentences.after(1, 1, 2).next).assertEqual(1);
      expect(Sentences.after(1, 2, 2).next).assertEqual(2);
      expect(Sentences.after(1, 5, 0).next).assertEqual(1);  // 0 = until stopped
    });
  });

  describe('Wav', () => {
    it('a 44-byte header, 16 kHz mono 16-bit', 0, () => {
      const f = Wav.file([new ArrayBuffer(32000)]);
      expect(f.length).assertEqual(32044);
      const v = new DataView(f.buffer);
      expect(v.getUint32(24, true)).assertEqual(16000);
      expect(v.getUint16(22, true)).assertEqual(1);
      expect(v.getUint32(40, true)).assertEqual(32000);
    });
  });

  describe('Ics', () => {
    it('the site\'s 加到手机日历 file: daily, UTC, folded lines', 0, () => {
      const text = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'BEGIN:VEVENT', 'UID:flow-vocab-20@flow', 'DTSTART:20261126T120000Z',
        'DURATION:PT10M', 'RRULE:FREQ=DAILY', 'SUMMARY:语流：背单词（约 10 分钟）',
        'DESCRIPTION:按遗忘曲线复习今天到期的单词：https://flowlang.cn/#/rev', ' iew',
        'BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:语流：该复习单词了', 'TRIGGER:PT0M', 'END:VALARM', 'END:VEVENT',
        'END:VCALENDAR'].join('\r\n');
      const e = Ics.first(text);
      expect(e !== null).assertTrue();
      if (e) {
        expect(e.start).assertEqual(Date.UTC(2026, 10, 26, 12, 0, 0));  // 20:00 China time
        expect(e.end - e.start).assertEqual(10 * 60000);
        expect(e.daily).assertTrue();
        expect(e.title).assertEqual('语流：背单词（约 10 分钟）');
        expect(e.description).assertEqual('按遗忘曲线复习今天到期的单词：https://flowlang.cn/#/review');
      }
    });

    it('one time (这次什么时候复习), no repeat; nothing readable is null', 0, () => {
      const e = Ics.first('BEGIN:VEVENT\nDTSTART:20261127T043000Z\nDURATION:PT1H30M\nSUMMARY:语流\\, 复习\nEND:VEVENT');
      expect(e !== null && !e.daily && e.end - e.start === 90 * 60000 && e.title === '语流, 复习').assertTrue();
      expect(Ics.first('BEGIN:VEVENT\nSUMMARY:x\nEND:VEVENT') === null).assertTrue();
      expect(Ics.first('not a calendar') === null).assertTrue();
    });
  });
}
