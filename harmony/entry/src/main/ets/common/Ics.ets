/** One calendar event, from the site's 「加到手机日历」 file (vocab_service.ics): the first VEVENT, its alarm left out. */
export class IcsEvent {
  start: number = 0;      // milliseconds since 1970
  end: number = 0;
  title: string = '语流';
  description: string = '';
  daily: boolean = false; // RRULE:FREQ=DAILY
}

/**
 * Reads the .ics the site hands out (/api/next/vocab/reminder.ics), as Android's MainActivity.firstEvent does: lines
 * unfolded (RFC 5545), the first VEVENT up to its VALARM, DTSTART in UTC (…Z) or local time, DTEND or a DURATION in
 * minutes or hours, SUMMARY and DESCRIPTION unescaped. No system calls, so the local tests can check it.
 */
export class Ics {
  static first(text: string): IcsEvent | null {
    const raw = text.split('\r\n').join('\n').split('\n');
    const lines: string[] = [];
    raw.forEach((l: string) => {
      if (l.startsWith(' ') && lines.length > 0) {
        lines[lines.length - 1] += l.substring(1);
      } else {
        lines.push(l);
      }
    });
    const from = lines.indexOf('BEGIN:VEVENT');
    if (from < 0) {
      return null;
    }
    const ev: string[] = [];
    for (let i = from + 1; i < lines.length; i++) {
      if (lines[i] === 'END:VEVENT' || lines[i] === 'BEGIN:VALARM') {
        break;
      }
      ev.push(lines[i]);
    }
    const prop = (name: string): string | null => {
      const l = ev.find((x: string) => x.startsWith(name + ':') || x.startsWith(name + ';'));
      return l === undefined ? null : l.substring(l.indexOf(':') + 1);
    };
    const startText = prop('DTSTART');
    const start = startText ? Ics.time(startText) : null;
    if (start === null) {
      return null;
    }
    const out = new IcsEvent();
    out.start = start;
    const endText = prop('DTEND');
    const end = endText ? Ics.time(endText) : null;
    const dur = prop('DURATION');
    out.end = end !== null ? end : start + (dur ? Ics.duration(dur) : 10 * 60000);
    out.title = Ics.unescape(prop('SUMMARY') ?? '语流');
    out.description = Ics.unescape(prop('DESCRIPTION') ?? '');
    const rule = prop('RRULE') ?? '';
    out.daily = rule.indexOf('FREQ=DAILY') >= 0;
    return out;
  }

  /** 20261126T120000Z (UTC) or 20261126T200000 (the phone's own time) → milliseconds; null when unreadable. */
  static time(v: string): number | null {
    const m = new RegExp('^(\\d{4})(\\d{2})(\\d{2})T(\\d{2})(\\d{2})(\\d{2})(Z?)$').exec(v.trim());
    if (!m) {
      return null;
    }
    const n = (i: number): number => Number(m[i]);
    return m[7] === 'Z'
      ? Date.UTC(n(1), n(2) - 1, n(3), n(4), n(5), n(6))
      : new Date(n(1), n(2) - 1, n(3), n(4), n(5), n(6)).getTime();
  }

  /** PT10M, PT1H, PT1H30M → milliseconds (10 minutes when unreadable). */
  static duration(v: string): number {
    const m = new RegExp('^PT(?:(\\d+)H)?(?:(\\d+)M)?$').exec(v.trim());
    if (!m || (!m[1] && !m[2])) {
      return 10 * 60000;
    }
    return (Number(m[1] ?? 0) * 60 + Number(m[2] ?? 0)) * 60000;
  }

  static unescape(s: string): string {
    return s.split('\\n').join('\n').split('\\,').join(',').split('\\;').join(';').split('\\\\').join('\\');
  }
}
