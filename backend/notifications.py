"""Device-scoped delivery receipts for optional, open-browser reminder alerts."""
import time
import uuid

from .for_you import key_for


def event_keys(feed):
    """One alert per due-date/snooze occurrence, including overdue catch-up."""
    today = feed['today']
    for item in feed['suggestions']:
        if item['status'] != 'open' or item['snoozed'] or item['kind'] == 'connection':
            continue
        snooze = item.get('snoozed_until')
        due = item.get('due_start')
        if due and due <= today and (not snooze or due > snooze):
            yield key_for(item['id'], 'due', due)
        elif snooze and snooze <= today:
            yield key_for(item['id'], 'snooze', snooze)


def claim(db, device, feed, now=None):
    """Called inside BEGIN IMMEDIATE so competing tabs cannot both reserve."""
    now = time.time() if now is None else now
    token = str(uuid.uuid4())
    count = 0
    for key in event_keys(feed):
        row = db.execute('SELECT delivered, claimed_at FROM notification_receipts WHERE device = ? AND event_key = ?', (device, key)).fetchone()
        if row and (row['delivered'] or row['claimed_at'] > now - 120):
            continue
        db.execute('''INSERT INTO notification_receipts(device,event_key,token,claimed_at) VALUES (?,?,?,?)
                      ON CONFLICT(device,event_key) DO UPDATE SET token=excluded.token, claimed_at=excluded.claimed_at''',
                   (device, key, token, now))
        count += 1
    return {'token': token if count else None, 'count': count}
