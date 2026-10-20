"""Source-backed suggestions derived locally from active, AI-organized memories."""
import hashlib
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MONTHS = {name: i for i, name in enumerate(
    ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
     'september', 'october', 'november', 'december'], 1)}
MONTH_PATTERN = '|'.join(MONTHS) + '|' + '|'.join(m[:3] for m in MONTHS)
TOPICS = {
    'a shopping outing': {'mall', 'shopping', 'shops', 'shoes', 'clothes', 'bookstore'},
    'time outdoors': {'hiking', 'hike', 'trail', 'trails', 'camping', 'garden', 'gardens', 'park'},
    'food or coffee': {'coffee', 'cafe', 'brunch', 'dinner', 'lunch', 'cooking', 'baking'},
    'music': {'music', 'jazz', 'concert', 'piano', 'guitar'},
    'sports': {'soccer', 'football', 'basketball', 'tennis', 'running', 'marathon'},
    'a creative activity': {'photography', 'ceramics', 'painting', 'museum', 'crafts'},
}


def key_for(*parts):
    return hashlib.sha256('\x1f'.join(map(str, parts)).encode()).hexdigest()[:32]


def normalized(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


def stamp_date(stamp, timezone):
    return datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(timezone).date()


def date_window(text, anchor, today, birthday=False):
    """Resolve explicit dates and bounded relative phrases, never guess a day.

    Relative expressions are anchored to the source note, never today's read time.
    Ambiguous numeric dates and unsupported phrases deliberately return None.
    """
    text = text.casefold()
    if re.search(r'\b(?:maybe|perhaps|possibly|probably|not sure|unsure|might|sometime|around|approximately|i think)\b', text):
        return None
    # Use the first date: extraction is responsible for retaining the corrected
    # date before any historical/negated date in the value.
    iso = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', text)
    named = re.search(rf'\b({MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b', text)
    day_first = re.search(rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH_PATTERN})\.?(?:\s+(\d{{4}}))?\b', text)
    if iso or named or day_first:
        first_match = iso or named or day_first
        if re.search(r'\b(?:not|no longer)\s*(?:on\s*)?$', text[:first_match.start()]):
            return None
        if iso:
            year, month, day = map(int, iso.groups())
        else:
            match = named or day_first
            month_name, day_str = (match[1], match[2]) if named else (match[2], match[1])
            month = next(i for name, i in MONTHS.items() if name.startswith(month_name.rstrip('.')))
            day = int(day_str)
            year = int(match[3]) if match[3] else None
        if birthday:
            for year_candidate in range(today.year, today.year + 9):
                try:
                    result = date(year_candidate, month, day)
                except ValueError:
                    continue
                if result >= today:
                    return result, result
            return None
        try:
            if year is None:
                # Choose the nearest calendar occurrence to the source note,
                # so an overdue date is not silently rolled into next year.
                possibilities = []
                for candidate_year in (anchor.year - 1, anchor.year, anchor.year + 1):
                    try:
                        possibilities.append(date(candidate_year, month, day))
                    except ValueError:
                        pass
                if not possibilities:
                    return None
                result = min(possibilities, key=lambda value: abs((value - anchor).days))
            else:
                result = date(year, month, day)
            return result, result
        except ValueError:
            return None
    weekday_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    weekday = re.search(r'\b(' + '|'.join(weekday_names) + r')\b', text)
    if weekday:
        prefix = text[:weekday.start()]
        if re.search(r'\b(?:next|not(?: on)?)\s*$', prefix):
            # "Next Friday" can mean either of two weeks. Avoid guessing.
            return None
        index = weekday_names.index(weekday[1])
        if re.search(r'\bnext week\b', text):
            result = anchor + timedelta(days=7 - anchor.weekday() + index)
        elif re.search(r'\bthis\s*$', prefix):
            result = anchor + timedelta(days=index - anchor.weekday())
        elif re.search(r'\blast\s*$', prefix):
            result = anchor + timedelta(days=index - anchor.weekday() - 7)
        else:
            result = anchor + timedelta(days=(index - anchor.weekday()) % 7)
        return result, result
    if re.search(r'\bnext week\b', text):
        start = anchor + timedelta(days=7 - anchor.weekday())
        return start, start + timedelta(days=6)
    if re.search(r'\bthis week\b', text):
        return anchor, anchor + timedelta(days=6 - anchor.weekday())
    if re.search(r'\btomorrow\b', text):
        result = anchor + timedelta(days=1)
        return result, result
    if re.search(r'\btoday\b', text):
        return anchor, anchor
    relative = re.search(r'\bin (\d{1,3}) days?\b', text)
    if relative:
        result = anchor + timedelta(days=int(relative[1]))
        return result, result
    return None


def entry_anchor(row, zone):
    return date.fromisoformat(row['entry_date']) if row['entry_date'] else stamp_date(row['noted_at'], zone)


def source(memory):
    return {field: memory[field] for field in
            ('id', 'person_id', 'person', 'note_id', 'note_revision', 'category', 'value', 'evidence', 'edited')}


def build_suggestions(db, today=None, timezone='America/New_York', include_all_plans=False):
    zone = ZoneInfo(timezone)
    today = today or datetime.now(zone).date()
    memories = [dict(row) for row in db.execute('''
        SELECT m.*, p.name AS person, n.created_at AS noted_at,
               CASE WHEN v.note_id IS NOT NULL THEN v.entry_date ELSE n.entry_date END AS entry_date
        FROM memories m JOIN people p ON p.id = m.person_id
        JOIN notes n ON n.id = m.note_id
        LEFT JOIN note_versions v ON v.note_id = m.note_id AND v.revision = m.note_revision
        WHERE m.active = 1
        ORDER BY m.id DESC
    ''')]
    items = []
    plans = []
    birthdays = {}
    for memory in memories:
        if memory['category'] == 'birthday':
            birthdays.setdefault(memory['person_id'], set()).add(normalized(memory['value']))
    for memory in memories:
        category = memory['category']
        anchor = entry_anchor(memory, zone)
        window = date_window(memory['value'], anchor, today, birthday=category == 'birthday')
        identity = (memory['person_id'], category, normalized(memory['value']))
        item = None
        if category == 'birthday':
            if len(birthdays[memory['person_id']]) > 1:
                continue
            if window and window[1] >= today and window[0] <= today + timedelta(days=30):
                item = {'id': key_for('birthday', memory['person_id'], window[0], window[1]),
                        'kind': 'date', 'title': f"Make room for {memory['person']}’s birthday",
                        'why': 'Their birthday is coming up in the next 30 days.', 'rank': 0}
        elif category == 'commitment':
            # Do not present a third party's already completed promise as an
            # outstanding task. The application itself never completes a task.
            if not re.search(r'\b(?:already sent|already done|fulfilled|completed|kept my promise|no longer need|cancelled|canceled)\b', memory['value'], re.I):
                if not window or window[0] <= today + timedelta(days=30):
                    item = {'id': key_for('commitment', *identity), 'kind': 'follow_up',
                            'title': f"Revisit a commitment with {memory['person']}",
                            'why': 'Your note includes a promise or commitment worth checking on.', 'rank': 1}
        elif category == 'plan':
            if include_all_plans and re.search(r'\b(?:already done|completed|no longer|cancelled|canceled)\b', memory['value'], re.I):
                continue
            # Some older extractions classified completed life updates as plans.
            if include_all_plans and re.search(r'\b(?:started|graduated(?: from)?)\s+(?:college|school|university|a new job)\b|^moved\b', memory['value'], re.I):
                continue
            if include_all_plans or window and today <= window[1] and window[0] <= today + timedelta(days=14):
                item = {'id': key_for('plan', *identity), 'kind': 'date',
                        'title': f"Check in on plans with {memory['person']}",
                        'why': 'This plan has a date or date range coming up.', 'rank': 2}
                if not window:
                    item['kind'] = 'follow_up'
                    item['why'] = 'Your writing includes an open plan or intention.'
            if (not window and (today - anchor).days <= 30) or (window and window[1] >= today):
                plans.append(memory)
        if item:
            item.update({'sources': [source(memory)], 'due_start': window[0].isoformat() if window else None,
                         'due_end': window[1].isoformat() if window else None,
                         'overdue': bool(window and window[1] < today)})
            if item['overdue']:
                item['why'] = 'The date in this commitment has passed. It may be worth checking whether it is done.'
            items.append(item)

    # A connection needs two different people's explicit plan/interest facts.
    # Shared topics are cues for a tentative suggestion, not proof of friendship.
    def positive(memory):
        return not re.search(r'\b(?:not|dislikes?|hates?|avoids?|no longer|cancelled|canceled)\b', memory['value'], re.I)

    plans = [m for m in plans if positive(m)]
    related_memories = [m for m in memories if m['category'] == 'interest' and positive(m)] + plans
    connections = set()
    distinct = {tuple(row) for row in db.execute('SELECT first_id,second_id FROM distinct_people')}
    for plan in plans:
        words = set(re.findall(r'\w+', plan['value'].casefold()))
        for other in related_memories:
            if other['person_id'] == plan['person_id']:
                continue
            # Suppress obvious unresolved short-name aliases (Josh/Joshua).
            left, right = normalized(plan['person']), normalized(other['person'])
            if tuple(sorted((plan['person_id'], other['person_id']))) not in distinct and min(len(left), len(right)) >= 3 and (left.startswith(right) or right.startswith(left)):
                continue
            other_words = set(re.findall(r'\w+', other['value'].casefold()))
            for topic, vocabulary in TOPICS.items():
                if not words & vocabulary or not other_words & vocabulary:
                    continue
                pair = tuple(sorted((plan['person_id'], other['person_id'])))
                connection = (*pair, topic)
                if connection in connections:
                    continue
                connections.add(connection)
                # The factual inputs determine identity, so unrelated note
                # additions do not make dismissed suggestions reappear.
                facts = sorted([normalized(plan['value']), normalized(other['value'])])
                items.append({'id': key_for('connection', *pair, topic, *facts), 'kind': 'connection',
                              'title': f"A possible connection: {plan['person']} & {other['person']}",
                              'why': f"Their notes both touch on {topic}. This could be a reason to check in or suggest something together.",
                              'sources': [source(plan), source(other)], 'due_start': None, 'due_end': None,
                              'overdue': False, 'rank': 3})
                break
    personal_items = {}
    for row in db.execute('''SELECT r.*, n.created_at AS noted_at, v.entry_date
                          FROM personal_reminders r JOIN notes n ON n.id = r.note_id
                          JOIN note_versions v ON v.note_id = r.note_id AND v.revision = r.note_revision
                          WHERE r.active = 1 AND r.note_revision = n.revision ORDER BY r.id DESC'''):
        reminder = dict(row)
        anchor = entry_anchor(reminder, zone)
        window = date_window(reminder['value'], anchor, today)
        key = key_for('personal', reminder['category'], normalized(reminder['value']),
                      window[0] if window else '', window[1] if window else '')
        source_item = {field: reminder[field] for field in ('id', 'note_id', 'note_revision', 'category', 'value', 'evidence')}
        source_item.update({'person_id': None, 'person': 'You', 'edited': 0})
        if key in personal_items:
            personal_items[key]['sources'].append(source_item)
            continue
        titles = {'task': 'A task for you', 'plan': 'A plan for you', 'reminder': 'Something to remember', 'goal': 'A personal goal'}
        personal_items[key] = {'id': key, 'scope': 'personal', 'category': reminder['category'],
            'kind': 'date' if window else 'follow_up', 'title': titles[reminder['category']],
            'why': 'You mentioned this in your writing.', 'sources': [source_item],
            'due_start': window[0].isoformat() if window else None,
            'due_end': window[1].isoformat() if window else None,
            'overdue': bool(window and window[1] < today), 'rank': 1 if not window else 2}
    items.extend(personal_items.values())
    completions = {}
    for row in db.execute('''SELECT c.* FROM personal_completions c
                          JOIN notes n ON n.id = c.note_id
                          WHERE c.note_revision = n.revision AND n.status IN ('organized','reviewed')
                          ORDER BY c.id DESC'''):
        completions.setdefault(row['reminder_id'], dict(row))
    actions = {row['suggestion_id']: row['status'] for row in db.execute('SELECT suggestion_id, status FROM suggestion_actions')}
    unique = {item['id']: item for item in items}
    result = sorted(unique.values(), key=lambda item: (item['rank'], item['due_start'] or '9999', item['id']))
    for item in result:
        item.setdefault('scope', 'others')
        automatic = item['scope'] == 'personal' and all(source['id'] in completions for source in item['sources'])
        item['status'] = actions.get(item['id'], 'done' if automatic else 'open')
        if automatic and item['id'] not in actions:
            event = max((completions[source['id']] for source in item['sources']), key=lambda event: event['id'])
            item['completion'] = {field: event[field] for field in ('note_id', 'note_revision', 'evidence')}
        item.pop('rank')
    return {'suggestions': result, 'today': today.isoformat(), 'timezone': timezone}
