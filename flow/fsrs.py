"""FSRS-6 spaced-repetition scheduler, a small dependency-free port of the published formulas.

Default weights are those of open-spaced-repetition/py-fsrs (MIT License, Copyright (c) 2022
Open Spaced Repetition). Each item keeps three numbers:
  difficulty D   1..10, how hard this item is for this learner
  stability  S   days until the chance of recalling it falls to 90%
  retrievability R   the chance of recalling it right now, from S and the time since the last review
A review is scheduled for when R would fall to the learner's desired retention (90% by default).
New and lapsed items first go through short same-day steps (1 and 10 minutes, then 10 minutes).
"""
import math
import random

W = (0.212, 1.2931, 2.3065, 8.2956, 6.4133, 0.8334, 3.0194, 0.001, 1.8722, 0.1666,
     0.796, 1.4835, 0.0614, 0.2629, 1.6483, 0.6014, 1.8729, 0.5425, 0.0912, 0.0658, 0.1542)
DECAY = -W[20]
FACTOR = 0.9 ** (1 / DECAY) - 1
S_MIN = 0.001
MAX_INTERVAL = 36500
LEARNING_STEPS = (60, 600)  # seconds
RELEARNING_STEPS = (600,)
DAY = 86400
GRADES = {'again': 1, 'hard': 2, 'good': 3, 'easy': 4}
STATES = ('new', 'learning', 'review', 'relearning')


def retrievability(stability, elapsed_days):
    """Chance of recalling an item now (0..1)."""
    if not stability:
        return 0.0
    return (1 + FACTOR * max(0.0, elapsed_days) / stability) ** DECAY


def interval_days(stability, retention=0.9):
    days = round(stability / FACTOR * (retention ** (1 / DECAY) - 1))
    return min(max(days, 1), MAX_INTERVAL)


def _clamp_d(d):
    return min(max(d, 1.0), 10.0)


def _init_s(g):
    return max(W[g - 1], S_MIN)


def _init_d(g, clamp=True):
    d = W[4] - math.exp(W[5] * (g - 1)) + 1
    return _clamp_d(d) if clamp else d


def _next_d(d, g):
    damped = d + (10.0 - d) * (-W[6] * (g - 3)) / 9.0  # linear damping: changes shrink near the top
    return _clamp_d(W[7] * _init_d(4, clamp=False) + (1 - W[7]) * damped)  # mean reversion


def _recall_s(d, s, r, g):
    hard = W[15] if g == 2 else 1
    easy = W[16] if g == 4 else 1
    return s * (1 + math.exp(W[8]) * (11 - d) * s ** -W[9] * (math.exp((1 - r) * W[10]) - 1) * hard * easy)


def _forget_s(d, s, r):
    long_term = W[11] * d ** -W[12] * ((s + 1) ** W[13] - 1) * math.exp((1 - r) * W[14])
    return min(long_term, s / math.exp(W[17] * W[18]))


def _short_s(s, g):
    inc = math.exp(W[17] * (g - 3 + W[18])) * s ** -W[19]
    if g >= 2:
        inc = max(inc, 1.0)
    return max(s * inc, S_MIN)


def fuzz(days, rnd=random.random):
    """Spread due dates a little so items learned together don't stay bunched together."""
    if days < 2.5:
        return days
    delta = 1.0
    for start, end, factor in ((2.5, 7.0, .15), (7.0, 20.0, .1), (20.0, math.inf, .05)):
        delta += factor * max(min(float(days), end) - start, 0.0)
    hi = min(round(days + delta), MAX_INTERVAL)
    lo = min(max(2, round(days - delta)), hi)
    return min(math.floor(rnd() * (hi - lo + 1) + lo), MAX_INTERVAL)


def review(card, rating, now, retention=0.9, rnd=random.random):
    """Apply one rating ('again'|'hard'|'good'|'easy') at time `now` (epoch seconds).

    card: mapping with state, step, stability, difficulty, last, lapses (missing = new item).
    rnd: random source for spreading due dates (None = exact intervals, for tests).
    Returns the new values: state, step, stability, difficulty, last, due, lapses, interval (days, 0 while in steps).
    """
    g = GRADES[rating]
    state = card.get('state') or 'new'
    step = card.get('step') or 0
    s, d, last = card.get('stability'), card.get('difficulty'), card.get('last')
    lapses = card.get('lapses') or 0
    elapsed = (now - last) // DAY if last else None  # whole days, as the model was fitted on
    if state == 'new' or s is None or d is None:
        s, d, state, step = _init_s(g), _init_d(g), 'learning', 0
    else:
        if elapsed is not None and elapsed < 1:
            s = _short_s(s, g)
        else:
            r = retrievability(s, elapsed or 0)
            s = max(_forget_s(d, s, r) if g == 1 else _recall_s(d, s, r, g), S_MIN)
        d = _next_d(d, g)

    wait = None  # seconds, while still in same-day steps
    if state == 'review':
        if g == 1:
            lapses += 1
            if RELEARNING_STEPS:
                state, step, wait = 'relearning', 0, RELEARNING_STEPS[0]
    else:
        steps = LEARNING_STEPS if state == 'learning' else RELEARNING_STEPS
        if steps and not (step >= len(steps) and g >= 2):
            if g == 1:
                step, wait = 0, steps[0]
            elif g == 2:
                wait = (steps[0] * 1.5 if len(steps) == 1 else (steps[0] + steps[1]) / 2) if step == 0 else steps[step]
            elif g == 3 and step + 1 < len(steps):
                step += 1
                wait = steps[step]
    if wait is None:
        days = interval_days(s, retention)
        days = fuzz(days, rnd) if rnd else days
        return {'state': 'review', 'step': 0, 'stability': s, 'difficulty': d, 'last': now, 'due': now + days * DAY,
                'lapses': lapses, 'interval': days}
    return {'state': state, 'step': step, 'stability': s, 'difficulty': d, 'last': now, 'due': now + wait,
            'lapses': lapses, 'interval': 0}


def from_sm2(interval, ease, reps):
    """Starting FSRS state for an item reviewed under the old SM-2 scheduler, so no progress is lost."""
    if not reps:
        return {'state': 'new', 'step': 0, 'stability': None, 'difficulty': None}
    return {'state': 'review', 'step': 0, 'stability': max(float(interval or 0), 0.5),
            'difficulty': _clamp_d(5 + (2.5 - float(ease or 2.5)) * 4)}
