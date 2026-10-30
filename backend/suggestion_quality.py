"""Conservative duplicate cards and chronological attention ordering."""
import re
from datetime import date

ACTIONS = re.compile(r'^(?:renew|submit|pay|water|clean|wash|refill|return|collect|send|give|show|ask|email|call|book|buy|get|check|review|read|write|walk|run|stretch|practice|study|take|feed|visit|meet|attend|charge|replace|do|look|pick)\b', re.I)


def canonical_action(value):
    value = ' '.join(value.casefold().split())
    value = re.sub(r"^(?:i\s+)?(?:(?:still\s+)?(?:need to|have to|will|should|must|want to)|remember to|remind me to)\s+", '', value)
    return ' '.join(re.findall(r'\w+', value))


def person_action(value, person, require_name=False):
    """Compare direct recipient actions within an already established person scope."""
    action = canonical_action(value)
    recipient = ' '.join(re.findall(r'\w+', person.casefold()))
    if not recipient:
        return None
    verbs = r'(send|give|show|call|ask|email)'
    named = re.match(r'^' + verbs + r'\s+' + re.escape(recipient) + r'(?:\s+|$)', action)
    if require_name and not named:
        return None
    if named:
        action = named[1] + ' ' + action[named.end():]
    else:
        # "Send her sister" is not the same recipient as "Send Maya".
        action = re.sub(r'^' + verbs + r'\s+(?:him|them)\b\s*', r'\1 ', action)
        action = re.sub(r'^' + verbs + r'\s+her\s+(?=(?:a|an|the|this|that|some|about|how)\b)', r'\1 ', action)
    if not re.match(r'^' + verbs + r'\b', action):
        return None
    return re.sub(r'^' + verbs + r'\s+(?:a|an|the|this|that|my)\s+', r'\1 ', action).strip()


def priority_key(item, today):
    due, end = item.get('due_start'), item.get('due_end')
    day = today.isoformat() if isinstance(today, date) else today
    distance = (date.fromisoformat(due) - date.fromisoformat(day)).days if due else None
    categories = {source['category'] for source in item['sources']}
    if item.get('overdue'):
        bucket = 0
    elif due and due <= day <= (end or due):
        bucket = 1
    elif distance is not None and 0 <= distance <= 14:
        bucket = 2
    elif not due and 'commitment' in categories:
        bucket = 3
    elif not due and item.get('scope') == 'personal' and item.get('category') != 'goal':
        bucket = 4
    elif distance is not None and distance <= 30:
        bucket = 5
    elif item['kind'] != 'connection' and not due:
        bucket = 6
    elif item['kind'] != 'connection':
        bucket = 7
    else:
        bucket = 8
    return (item['status'] != 'open', bool(item.get('snoozed')), bucket, due or '9999',
            'commitment' not in categories, min(source['note_id'] for source in item['sources']), item['id'])


def duplicate_key(item):
    if not item.get('can_schedule') and not item.get('past_occurrence'):
        return ('unique', item['id'])
    value = item['sources'][0]['value']
    canonical = canonical_action(value)
    # Don't conflate somebody else's wish/promise with the author's task.
    if item.get('scope') != 'personal' and not ACTIONS.match(canonical):
        return ('unique', item['id'])
    if item.get('scope') == 'others' and len({source['person_id'] for source in item['sources']}) == 1:
        canonical = person_action(value, item['sources'][0]['person']) or canonical
    return (item.get('scope'), tuple(sorted({source['person_id'] for source in item['sources'] if source['person_id'] is not None})),
            'goal' if item.get('category') == 'goal' else 'action', canonical,
            *(item.get(key) for key in ('status','due_start','due_end','original_due_start','original_due_end',
                                      'due_date_overridden','snoozed_until','repeat','repeat_origin','repeat_anchor_day','past_occurrence','can_schedule')))


def coalesce_suggestions(feed):
    # Historical model output can put the same named-recipient task in both
    # Personal and People. Merge only a unique, explicitly named match with
    # identical status/timing; retain every source and action ID.
    people = []
    for item in feed['suggestions']:
        if item.get('scope') == 'others' and item.get('can_schedule') and len({s['person_id'] for s in item['sources']}) == 1:
            person = item['sources'][0]['person']
            action = person_action(item['sources'][0]['value'], person)
            if action:
                key = duplicate_key(item)
                people.append((item, person, action, key))
    groups = {}
    for item in feed['suggestions']:
        key = duplicate_key(item)
        if item.get('scope') == 'personal' and item.get('category') != 'goal' and key[0] != 'unique':
            matches = {other_key for other, person, action, other_key in people
                       if key[4:] == other_key[4:] and
                       person_action(item['sources'][0]['value'], person, require_name=True) == action}
            if len(matches) == 1:
                key = matches.pop()
        groups.setdefault(key, []).append(item)
    result = []
    for members in groups.values():
        members = sorted(members, key=lambda item: (item.get('scope') == 'personal', min(source['note_id'] for source in item['sources']), item['id']))
        item = dict(members[0])
        sources = {}
        for member in members:
            for source in member['sources']:
                sources.setdefault((source['person_id'], source['id'], source['note_id'], source.get('note_revision')), source)
        item['sources'] = list(sources.values())
        item['related_ids'] = [member['id'] for member in members]
        result.append(item)
    result.sort(key=lambda item: priority_key(item, feed['today']))
    return {**feed, 'suggestions': result}


def related_suggestions(feed, suggestion_id):
    group = next((item for item in coalesce_suggestions(feed)['suggestions'] if suggestion_id in item['related_ids']), None)
    ids = set(group['related_ids']) if group else set()
    return [item for item in feed['suggestions'] if item['id'] in ids]
