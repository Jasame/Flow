"""每天的时间预算 (r28 第 1 段「按时间打包今日计划」).

The learner's daily minutes (5–60, next_service.MINUTES) are split into parts. Today's plan (skills_service.daily_path)
puts under 必做 only the steps that fit their part; the rest fold under 「还有时间的话」 and do not count towards the
day's completion. The plan's title gives the real total of 必做, not the minutes chosen.

- words is a cap: the words step takes at most that much (vocab_service sizes the day's share, r28 第 3 段).
- read is today's text. Its mode follows the minutes: at 5 one listen or one paragraph ('glance'); with 考试小练 at 10,
  listened to and read only ('listen-read'); otherwise listened to, read and the questions done ('core').
  At 60 it holds two texts.
- exam is 考试小练 (r28 第 4 段), for learners preparing for an exam once it exists: a few minutes a day taken from output
  and 复听 (at 10 minutes, from today's text). The whole timed set is 「本周任务」, outside the daily budget.
- other holds one more thing on long days: a role-play scene, an easy read, a second text, a radar test.
"""
import math

TIERS = (5, 10, 15, 20, 30, 45, 60)
PARTS = ('words', 'read', 'relisten', 'output', 'grammar', 'exam', 'other')

TABLE = {
    5: {'words': 3, 'read': 2},
    10: {'words': 4, 'read': 6},
    15: {'words': 5, 'read': 8, 'output': 2},
    20: {'words': 6, 'read': 9, 'relisten': 3, 'output': 2},
    30: {'words': 9, 'read': 10, 'relisten': 3, 'output': 5, 'grammar': 3},
    45: {'words': 12, 'read': 10, 'relisten': 3, 'output': 8, 'grammar': 4, 'other': 8},
    60: {'words': 15, 'read': 20, 'relisten': 3, 'output': 10, 'grammar': 4, 'other': 8},
}
# With 考试小练: its minutes come out of output and 复听 (3–5 minutes at 10–20, 6–10 from 30 on); at 10 there are
# neither, so they come out of today's text, which is then only listened to and read.
EXAM = {
    10: {'words': 4, 'read': 3, 'exam': 3},
    15: {'words': 5, 'read': 6, 'exam': 4},
    20: {'words': 6, 'read': 9, 'exam': 5},
    30: {'words': 9, 'read': 10, 'output': 2, 'grammar': 3, 'exam': 6},
    45: {'words': 12, 'read': 10, 'output': 3, 'grammar': 4, 'other': 8, 'exam': 8},
    60: {'words': 15, 'read': 20, 'output': 3, 'grammar': 4, 'other': 8, 'exam': 10},
}
OVER = 1.2  # 今天已经学了… once the day's study reaches this share of the minutes chosen


def tier(minutes):
    """The budget row for these minutes: the largest tier not above them (5 at the least)."""
    m = minutes or 10
    return max([t for t in TIERS if t <= m] or [TIERS[0]])


# 5 分钟的日子轮着来 (r29, the user's pick 2026-11-26): a words day is TABLE[5]; a use day gives the words' minutes to
# 听两句、答一句 (output) and keeps today's text heard once.
USE_DAY = {'read': 2, 'output': 3}


def budget(minutes, exam=False, use_day=False):
    """Minutes for each part of a day (0: not in 必做 today), the text's mode and the tier.
    exam: the learner is preparing for an exam and 考试小练 is there to fill its part.
    use_day: at 5 minutes, the day of 听两句、答一句 rather than words (skills_service decides which)."""
    t = tier(minutes)
    row = USE_DAY if use_day and t == 5 else EXAM[t] if exam and t in EXAM else TABLE[t]
    out = {p: row.get(p, 0) for p in PARTS}
    out['tier'] = t
    out['read_mode'] = 'glance' if t == 5 else 'listen-read' if out['exam'] and t == 10 else 'core'
    out['texts'] = 2 if t >= 60 else 1
    out['use_day'] = bool(use_day and t == 5)
    return out


def read_minutes(words, mode='core'):
    """Minutes for today's text in this mode, from its length (a whole text, four steps, is about words / 30 + 4:
    next_service._card): 'core' leaves out its output step (2 minutes), 'listen-read' the questions too,
    'glance' is one listen (about 120 words a minute, read slowly) or one paragraph."""
    words = words or 0
    if mode == 'glance':
        return max(2, round(words / 120))
    if mode == 'listen-read':
        return max(2, round(words / 30))
    return max(3, round(words / 30) + 2)


def over_at(minutes):
    """The minutes studied today from which the plan says the day's time is used up."""
    return math.ceil((minutes or 10) * OVER)
