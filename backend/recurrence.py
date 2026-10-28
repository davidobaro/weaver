"""Explicit calendar recurrence; missed periods never create a backlog of tasks."""
import calendar
from datetime import date, timedelta
from uuid import uuid4


def occurrence_id(base_id, occurrence_key):
    # Import lazily: for_you applies recurrence after gathering source-backed facts.
    from .for_you import key_for
    return key_for('occurrence', base_id, occurrence_key)


def next_due(current, anchor, frequency, today):
    current, anchor, today = map(date.fromisoformat, (current, anchor, today))
    if frequency in {'daily', 'weekly'}:
        step = 1 if frequency == 'daily' else 7
        periods = max(1, (today - current).days // step + 1)
        return (current + timedelta(days=step * periods)).isoformat()
    # Keep the original day: Jan 31 -> Feb 28 -> Mar 31, including leap years.
    month = max(current.year * 12 + current.month, today.year * 12 + today.month - 1)
    while True:
        year, index = divmod(month, 12)
        value = date(year, index + 1, min(anchor.day, calendar.monthrange(year, index + 1)[1]))
        if value > current and value > today:
            return value.isoformat()
        month += 1


def apply_recurrence(db, items, today):
    rules = {row['suggestion_id']: dict(row) for row in db.execute('SELECT * FROM reminder_recurrence')}
    histories = {}
    for row in db.execute('SELECT * FROM reminder_occurrences ORDER BY due_date DESC, rowid DESC'):
        histories.setdefault(row['suggestion_id'], []).append(dict(row))
    result = []
    for original in items:
        base_id = original['id']
        original.update(base_id=base_id, repeat=None, repeat_origin=None, repeat_anchor_day=None, past_occurrence=False)
        rule = rules.get(base_id)
        if rule and original['can_schedule']:
            original.update(id=occurrence_id(base_id, rule['occurrence_key']), repeat=rule['frequency'], repeat_origin=rule['origin'], repeat_anchor_day=int(rule['anchor_date'][-2:]),
                            due_start=rule['next_due'], due_end=rule['next_due'], status='open',
                            due_date_overridden=True, kind='date', rank=2,
                            overdue=rule['next_due'] < today.isoformat(),
                            why=('Your writing sets a ' + rule['frequency'] + ' repeat.' if rule['origin'] == 'writing' else 'Repeats ' + rule['frequency'] + '.') + ' Mark done or skip to schedule the next occurrence.')
            original.pop('completion', None)
            original['snoozed'] = bool(original['snoozed_until'] and original['snoozed_until'] > today.isoformat())
        result.append(original)
        for past in histories.get(base_id, []):
            historical = dict(original)
            historical.update(id=occurrence_id(base_id, past['occurrence_key']), repeat=past['frequency'],
                              past_occurrence=True, due_start=past['due_date'], due_end=past['due_date'],
                              overdue=past['due_date'] < today.isoformat(), status=past['status'],
                              can_schedule=False, snoozed=False, snoozed_until=None,
                              why='A previous occurrence. Restoring it does not change the current repeat schedule.')
            historical.pop('completion', None)
            result.append(historical)
    return result


def act_on_occurrence(db, item, status, today):
    """Return False for a one-off item; the caller owns the transaction."""
    if item['past_occurrence']:
        rows = db.execute('SELECT occurrence_key FROM reminder_occurrences WHERE suggestion_id = ?', (item['base_id'],)).fetchall()
        key = next(row['occurrence_key'] for row in rows if occurrence_id(item['base_id'], row['occurrence_key']) == item['id'])
        db.execute('UPDATE reminder_occurrences SET status = ? WHERE suggestion_id = ? AND occurrence_key = ?',
                   (status, item['base_id'], key))
        return True
    if not item['repeat']:
        return False
    if status == 'open':
        return True
    rule = db.execute('SELECT * FROM reminder_recurrence WHERE suggestion_id = ?', (item['base_id'],)).fetchone()
    due = next_due(rule['next_due'], rule['anchor_date'], rule['frequency'], today)
    db.execute('INSERT INTO reminder_occurrences(suggestion_id,occurrence_key,due_date,frequency,status) VALUES (?,?,?,?,?)',
               (item['base_id'], rule['occurrence_key'], rule['next_due'], rule['frequency'], status))
    db.execute('UPDATE reminder_recurrence SET next_due = ?, occurrence_key = ? WHERE suggestion_id = ?',
               (due, uuid4().hex, item['base_id']))
    db.execute('UPDATE suggestion_timing SET snoozed_until = NULL WHERE suggestion_id = ?', (item['base_id'],))
    return True
