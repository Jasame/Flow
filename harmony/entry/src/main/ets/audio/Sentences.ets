/** One sentence of a recording: where it starts and ends, in seconds (the Kokoro timeline's s and e). */
export class Span {
  s: number;
  e: number;

  constructor(s: number, e: number) {
    this.s = s;
    this.e = e;
  }
}

/** Where to go after a sentence was said: the next index and how many times that one has been said. */
export class After {
  next: number;
  said: number;

  constructor(next: number, said: number) {
    this.next = next;
    this.said = said;
  }
}

/**
 * The page's rules for a whole text (01-audio-offline.js NAR.locate / NAR.step / LONG.after), as Android's
 * audio/Sentences.kt, kept without any system calls so the local tests can check them.
 */
export class Sentences {
  /** The sentence playing at t: from 0.02 s before its start to 0.25 s after its end; -1 between or before them. */
  static locate(spans: Span[], t: number): number {
    for (let i = 0; i < spans.length; i++) {
      const x = spans[i];
      if (t >= x.s - 0.02 && t < x.e + 0.25) {
        return i;
      }
      if (t < x.s) {
        break;
      }
    }
    return -1;
  }

  /** The sentence a previous / next press counts from: the one at t, else the last one that started before t. */
  static current(spans: Span[], t: number): number {
    let i = spans.findIndex((x: Span) => t < x.e + 0.25);
    if (i < 0) {
      i = spans.length - 1;
    }
    return Math.max(0, i);
  }

  /** Previous / next of a recording played straight through: well into a sentence (over 1.5 s), previous = its start. */
  static stepTarget(spans: Span[], t: number, d: number): number {
    if (spans.length === 0) {
      return 0;
    }
    const i = Sentences.current(spans, t);
    const dd = d < 0 && t - spans[i].s > 1.5 ? 0 : d;
    return Math.min(spans.length - 1, Math.max(0, i + dd));
  }

  /** After sentence i was said for the said-th time: again (复读: rep times, 0 = until stopped), or the next one. */
  static after(i: number, said: number, rep: number): After {
    return rep === 0 || said < rep ? new After(i, said) : new After(i + 1, 0);
  }
}
