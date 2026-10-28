"""Grounded repeat detection from explicit, authored intentions, at publication time."""
import calendar
import re
from datetime import date, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from .for_you import build_suggestions, date_window, stamp_date
from .utils import entry_text

WEEKDAYS = 'monday tuesday wednesday thursday friday saturday sunday'.split()
DAY_WORDS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
             'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
             'fifteenth': 15, 'twentieth': 20, 'thirtieth': 30, 'thirty-first': 31, 'last day': 31}
DAY = r'(?:\d{1,2}(?:st|nd|rd|th)?|' + '|'.join(DAY_WORDS) + ')'
WEEKLY = re.compile(r'\b(?:every|each)\s+(' + '|'.join(WEEKDAYS) + r')s?\b|\b(' + '|'.join(day + 's' for day in WEEKDAYS) + r')\b', re.I)
MONTHLY = [re.compile(pattern, re.I) for pattern in (
    rf'\b(?:on\s+)?(?:the\s+)?({DAY})\s+(?:day\s+)?of\s+(?:each|every|the)\s+month\b',
    rf'\b(?:each|every)\s+month\s+on\s+(?:the\s+)?({DAY})\b',
    rf'\bmonthly\s+on\s+(?:the\s+)?({DAY})\b',
)]
DAILY = re.compile(r'\b(?:every day|each day|daily|everyday)\b(?=\s*(?:$|[.!?,;]|starting\b|beginning\b|from\b|at\b))', re.I)
UNSAFE = re.compile(r"\b(?:not|never|no longer|no need|maybe|perhaps|possibly|probably|might|could|would|if|unless|unsure|uncertain|used to|stopped|quit|cancelled|canceled|until|through|between|except|only|other|alternat\w*|twice|biweekly|bimonthly|yearly|annually|weekdays|weekends|or|either)\b|\b(?:don|doesn|didn|won|can|shouldn|wouldn)['’]t\b|\bfor\s+(?:the\s+next\s+)?(?:\d+|a|one|two|three|few)\s+(?:days?|weeks?|months?|years?)\b|\b(?:at|by)\s+\d|\b\d(?::\d\d)?\s*(?:am|pm)\b|\b(?:noon|midnight)\b", re.I)
INTENTION = re.compile(r"^(?:i\s+(?:need to|have to|must|will|should|want to|plan to|intend to|am going to|promised(?: to)?)\b|remind me\b|remember to\b|need to\b|(?:water|pay|check|call|send|clean|exercise|run|stretch|walk|practice|study|read|write|take|refill|review|update|back up|feed|visit|meet|attend|book|charge|replace|wash|do|meditate|schedule|renew|submit|buy|pick up|bring)\b)", re.I)


def source_context(text, evidence):
    if not evidence or text.count(evidence) != 1:
        return None
    start = text.index(evidence)
    left = max(text.rfind(mark, 0, start) for mark in '.!?\n;') + 1
    tail = start + len(evidence)
    end = re.search(r'[.!?\n;]', text[tail:])
    return text[left:tail + end.start() if end else len(text)].strip()


def detect_repeat(value, evidence, text, anchor):
    """Return a calendar rule only when the source clearly supports one cadence."""
    context = source_context(text, evidence)
    if not context or '?' in context or UNSAFE.search(context) or UNSAFE.search(value):
        return None
    markers = []
    markers.extend(('daily', None, match) for match in DAILY.finditer(evidence))
    markers.extend(('weekly', WEEKDAYS.index((match[1] or match[2].rstrip('s')).lower()), match) for match in WEEKLY.finditer(evidence))
    for pattern in MONTHLY:
        for match in pattern.finditer(evidence):
            raw = match[1].lower()
            day = DAY_WORDS.get(raw) if raw in DAY_WORDS else int(re.match(r'\d+', raw)[0])
            if not 1 <= day <= 31:
                return None
            markers.append(('monthly', day, match))
    # Bare weekly/monthly needs a concrete start date, rather than guessing a day.
    start_match = re.search(r'\b(?:starting|beginning|from)\s+(?:on\s+)?(.+)', evidence, re.I)
    start = anchor
    if start_match:
        window = date_window(start_match[1], anchor, anchor)
        if not window or window[0] != window[1]:
            return None
        start = window[0]
    if not markers and start_match:
        match = re.search(r'\b(?:weekly|every week|each week|monthly|every month|each month)\b', evidence, re.I)
        if match:
            markers.append(('weekly' if 'week' in match[0].lower() else 'monthly', None, match))
    if len(markers) != 1:
        return None
    frequency, day, marker = markers[0]
    # A front-loaded cadence is fine: "Every Saturday, water the plants."
    authored = context
    offset = context.lower().find(marker[0].lower())
    if offset == 0:
        authored = context[len(marker[0]):].lstrip(' ,:')
    if not INTENTION.match(authored):
        return None
    # Additional cadence words or multiple weekdays are unsupported combinations.
    remainder = evidence[:marker.start()] + evidence[marker.end():]
    if re.search(r'\b(?:every|each|daily|weekly|monthly)\b', remainder, re.I):
        return None
    if frequency == 'weekly':
        if day is not None:
            start += timedelta(days=(day - start.weekday()) % 7)
        anchor_date = start
    elif frequency == 'monthly':
        day = day or start.day
        year, month = start.year, start.month
        due = date(year, month, min(day, calendar.monthrange(year, month)[1]))
        if due < start:
            year, index = divmod(year * 12 + month, 12)
            due = date(year, index + 1, min(day, calendar.monthrange(year, index + 1)[1]))
        anchor_date = date(start.year, 1, day)
        start = due
    else:
        anchor_date = start
    if start.year > 9998:
        return None
    return {'frequency': frequency, 'anchor_date': anchor_date.isoformat(), 'next_due': start.isoformat()}


def discover_repeats(db, note):
    """Publish only newly organized source facts; never mutate schedules on reads."""
    anchor = date.fromisoformat(note['entry_date']) if note.get('entry_date') else stamp_date(note['created_at'], ZoneInfo('America/New_York'))
    feed = build_suggestions(db, include_all_plans=True)
    text = entry_text(note)
    for item in feed['suggestions']:
        if not item['can_schedule'] or item['status'] != 'open' or item['repeat']:
            continue
        base = item['base_id']
        if any(db.execute(f'SELECT 1 FROM {table} WHERE suggestion_id = ?', (base,)).fetchone()
               for table in ('reminder_repeat_choices', 'suggestion_timing', 'suggestion_actions')):
            continue
        for source in item['sources']:
            if source['note_id'] != note['id'] or source['note_revision'] != note['revision'] or source.get('edited'):
                continue
            rule = detect_repeat(source['value'], source['evidence'], text, anchor)
            if rule:
                db.execute('''INSERT OR IGNORE INTO reminder_recurrence(suggestion_id,frequency,anchor_date,next_due,occurrence_key,origin)
                              VALUES (?,?,?,?,?,'writing')''', (base, rule['frequency'], rule['anchor_date'], rule['next_due'], uuid4().hex))
                break
