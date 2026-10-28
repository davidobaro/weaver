"""Local keyword search over writing and its current, source-backed records."""
import re
import unicodedata

KINDS = ('entry', 'person', 'memory', 'task')


def words(text):
    folded = ''.join(char for char in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(char))
    return re.findall(r'[^\W_]+', folded)


def score(query, primary, *context):
    terms = words(query)
    if not terms:
        return None
    main = words(primary)
    tokens = main + words(' '.join(filter(None, context)))
    if not all(any(token.startswith(term) for token in tokens) for term in terms):
        return None
    phrase = ' '.join(terms)
    title = ' '.join(main)
    return (100 if phrase == title else 50 if phrase in title else 0) + sum(
        10 if term in main else 5 if any(token.startswith(term) for token in main) else 0 for term in terms)


def excerpt(text, query, length=240):
    terms = words(query)
    match = next((part for part in re.finditer(r'[^\W_]+', text)
                  if any(token.startswith(term) for token in words(part[0]) for term in terms)), None)
    start = max(0, (match.start() if match else 0) - 65)
    end = min(len(text), start + length)
    return ('…' if start else '') + text[start:end].strip() + ('…' if end < len(text) else '')


def search_workspace(db, query, feed, kind='all', limit=20):
    counts = dict.fromkeys(KINDS, 0)
    results = []
    if not words(query):
        return {'results': [], 'counts': counts, 'total': 0}
    people = {row['id']: dict(row) for row in db.execute('SELECT id,name FROM people')}
    aliases = {}
    for row in db.execute('SELECT person_id,name FROM person_aliases'):
        aliases.setdefault(row['person_id'], []).append(row['name'])
    memories = [dict(row) for row in db.execute('''SELECT m.*, n.entry_date, n.created_at
                 FROM memories m JOIN notes n ON n.id=m.note_id WHERE m.active=1 ORDER BY m.id DESC''')]
    by_person = {}
    for memory in memories:
        by_person.setdefault(memory['person_id'], []).append(memory)
    people[0] = {'id': 0, 'name': 'You'}
    aliases[0] = ['Personal']
    for item in feed['suggestions']:
        if item.get('scope') == 'personal' and not item.get('past_occurrence'):
            by_person.setdefault(0, []).extend(item['sources'])

    def add(result, primary, *context, priority=0):
        rank = score(query, primary, *context)
        if rank is None:
            return
        counts[result['kind']] += 1
        if kind == 'all' or result['kind'] == kind:
            results.append((rank + priority, result))

    for row in db.execute('SELECT id,title,text,kind,entry_date,created_at,revision FROM notes ORDER BY id DESC'):
        note = dict(row)
        add({'id': f"entry:{note['id']}", 'kind': 'entry', 'title': note['title'] or ('Journal entry' if note['kind'] == 'journal' else 'Quick note'),
             'excerpt': excerpt(note['text'], query), 'note_id': note['id'], 'note_revision': note['revision'],
             'entry_date': note['entry_date'] or note['created_at'][:10], 'category': note['kind']},
            note['title'] or '', note['text'])

    for person in people.values():
        facts = by_person.get(person['id'], [])
        names = aliases.get(person['id'], [])
        matching = next((fact for fact in facts if score(query, person['name'], ' '.join(names), fact['value'], fact['evidence']) is not None), None)
        fact = matching or (facts[0] if facts else None)
        add({'id': f"person:{person['id']}", 'kind': 'person', 'title': person['name'], 'person_id': person['id'],
             'excerpt': excerpt(fact['value'], query) if fact else 'Also known as ' + ', '.join(names) if names else 'Open this profile.',
             'note_id': fact['note_id'] if fact else None, 'note_revision': fact['note_revision'] if fact else None},
            person['name'], ' '.join(names), ' '.join(fact['value'] + ' ' + fact['evidence'] for fact in facts))

    for memory in memories:
        person = people.get(memory['person_id'])
        if not person:
            continue
        add({'id': f"memory:{memory['id']}", 'kind': 'memory', 'title': memory['value'],
             'excerpt': excerpt(memory['evidence'], query), 'person': person['name'], 'person_id': person['id'],
             'note_id': memory['note_id'], 'note_revision': memory['note_revision'], 'category': memory['category']},
            memory['value'], person['name'], ' '.join(aliases.get(person['id'], [])), memory['evidence'])

    for item in feed['suggestions']:
        if item['kind'] == 'connection' or not (item['can_schedule'] or item.get('past_occurrence')):
            continue
        sources = item['sources']
        text = ' '.join(source['value'] for source in sources)
        add({'id': 'task:' + item['id'], 'kind': 'task', 'title': sources[0]['value'],
             'excerpt': excerpt(' '.join(source['evidence'] for source in sources), query),
             'person': sources[0]['person'], 'person_id': sources[0]['person_id'],
             'note_id': sources[0]['note_id'], 'note_revision': sources[0]['note_revision'],
             'status': item['status'], 'snoozed': item['snoozed'], 'due_start': item['due_start'],
             'repeat': item.get('repeat'), 'past_occurrence': item.get('past_occurrence', False)},
            text, ' '.join(source['person'] + ' ' + ' '.join(aliases.get(source['person_id'], [])) + ' ' + source['evidence'] for source in sources),
            priority=5 if item['status'] == 'open' else 0)
    # Stable insertion order breaks ties: newest entries/facts first.
    results.sort(key=lambda pair: -pair[0])
    return {'results': [item for _, item in results[:limit]], 'counts': counts,
            'total': sum(counts.values()) if kind == 'all' else counts[kind]}
