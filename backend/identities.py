"""Confirmed aliases resolve identities; nickname similarity only suggests a match."""
import hashlib
import json
import re
import uuid

from .utils import name_key

GROUPS = [set(words.split()) for words in (
    'josh joshua', 'joe joseph joey', 'bob robert rob bobby', 'mike michael mikey',
    'liz elizabeth beth lizzy', 'will william bill billy', 'sam samuel samantha',
    'alex alexander alexandra', 'steve steven stephen', 'dan daniel danny',
    'dave david', 'nick nicholas', 'chris christopher christina', 'jen jennifer jenny',
    'kate katherine catherine katie', 'tom thomas tommy', 'ben benjamin',
)]


class IdentityError(Exception):
    pass


def find_person(db, name):
    return db.execute('''SELECT p.id, p.name FROM people p WHERE p.name_key = ?
                       OR p.id IN (SELECT person_id FROM person_aliases WHERE name_key = ?)''',
                      (name_key(name), name_key(name))).fetchone()


def get_or_create_person(db, name):
    person = find_person(db, name)
    return person['id'] if person else db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',
                                                 (name, name_key(name))).lastrowid


def aliases_for(db, person_id):
    return [dict(row) for row in db.execute('SELECT name, name_key FROM person_aliases WHERE person_id = ? ORDER BY name_key', (person_id,))]


def add_alias(db, person_id, name):
    person = db.execute('SELECT * FROM people WHERE id = ?', (person_id,)).fetchone()
    if not person:
        raise IdentityError('This profile no longer exists.')
    existing = find_person(db, name)
    if existing and existing['id'] != person_id:
        raise IdentityError(f'That name belongs to {existing["name"]}. Use Merge profiles if they are the same person.')
    if name_key(name) == person['name_key']:
        return
    db.execute('INSERT OR IGNORE INTO person_aliases(name_key,name,person_id) VALUES (?,?,?)',
               (name_key(name), name, person_id))


def similar_names(left, right):
    a, b = name_key(left).split(), name_key(right).split()
    if not a or not b or (len(a) > 1 and len(b) > 1 and a[1:] != b[1:]):
        return False
    return (a[0] == b[0] and a != b) or (a[0] != b[0] and any(a[0] in group and b[0] in group for group in GROUPS))


def possible_matches(db, people):
    rejected = {tuple(row) for row in db.execute('SELECT first_id, second_id FROM distinct_people')}
    result = []
    for index, person in enumerate(people):
        for other in people[index + 1:]:
            pair = tuple(sorted((person['id'], other['id'])))
            if pair in rejected:
                continue
            left_names = [person['name']] + [a['name'] for a in person.get('aliases', [])]
            right_names = [other['name']] + [a['name'] for a in other.get('aliases', [])]
            if any(similar_names(a, b) for a in left_names for b in right_names):
                # Keep the fuller name by default; the UI still asks explicitly.
                target, source = sorted((person, other), key=lambda p: (-len(p['name']), p['id']))
                result.append({'source_id': source['id'], 'source_name': source['name'],
                               'target_id': target['id'], 'target_name': target['name']})
    return result


def mentioned(db, person, text):
    names = [person['name']] + [alias['name'] for alias in aliases_for(db, person['id'])]
    for name in names:
        for word in name.split():
            if re.search(r'(?<!\w)' + re.escape(word) + r'(?!\w)', text, re.I):
                return True
    return False


def fingerprint(db, person_id):
    snapshot = {'person': dict(db.execute('SELECT * FROM people WHERE id = ?', (person_id,)).fetchone()),
                'aliases': aliases_for(db, person_id),
                'memories': [dict(row) for row in db.execute('''SELECT id,person_id,note_id,category,value,evidence,
                            edited,active,replaces_id,created_at FROM memories WHERE person_id = ? ORDER BY id''', (person_id,))]}
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


def carry_actions(db, before, after):
    def signature(item):
        return item['kind'], tuple(sorted(source['id'] for source in item['sources']))
    previous = {signature(item): item for item in before['suggestions']}
    for item in after['suggestions']:
        old = previous.get(signature(item))
        if old and old['status'] != 'open' and item['status'] == 'open':
            db.execute('INSERT OR IGNORE INTO suggestion_actions(suggestion_id,status) VALUES (?,?)',
                       (item['id'], old['status']))


def merge_people(db, source_id, target_id):
    from .for_you import build_suggestions
    if source_id == target_id:
        raise IdentityError('Choose two different profiles.')
    source = db.execute('SELECT * FROM people WHERE id = ?', (source_id,)).fetchone()
    target = db.execute('SELECT * FROM people WHERE id = ?', (target_id,)).fetchone()
    if not source or not target:
        raise IdentityError('A profile changed. Refresh before merging.')
    suggestions_before = build_suggestions(db)
    snapshot = {'source': dict(source), 'source_aliases': aliases_for(db, source_id),
                'target_aliases': aliases_for(db, target_id),
                'memory_ids': [row['id'] for row in db.execute('SELECT id FROM memories WHERE person_id = ?', (source_id,))],
                'distinct': [list(row) for row in db.execute('SELECT first_id,second_id FROM distinct_people WHERE first_id = ? OR second_id = ?', (source_id, source_id))]}
    db.execute('UPDATE memories SET person_id = ? WHERE person_id = ?', (target_id, source_id))
    db.execute('UPDATE person_aliases SET person_id = ? WHERE person_id = ?', (target_id, source_id))
    db.execute('DELETE FROM people WHERE id = ?', (source_id,))
    add_alias(db, target_id, source['name'])
    carry_actions(db, suggestions_before, build_suggestions(db))
    merge_id = uuid.uuid4().hex
    db.execute('INSERT INTO people_merges(id,target_id,source_name,snapshot,fingerprint) VALUES (?,?,?,?,?)',
               (merge_id, target_id, source['name'], json.dumps(snapshot), fingerprint(db, target_id)))
    return {'id': merge_id, 'person_id': target_id}


def undo_merge(db, merge_id):
    from .for_you import build_suggestions
    event = db.execute('SELECT * FROM people_merges WHERE id = ? AND undone = 0', (merge_id,)).fetchone()
    if not event or not db.execute('SELECT id FROM people WHERE id = ?', (event['target_id'],)).fetchone():
        raise IdentityError('This merge is no longer available.')
    if fingerprint(db, event['target_id']) != event['fingerprint']:
        raise IdentityError('This profile has changed since the merge. Move individual memories with Edit instead.')
    before = json.loads(event['snapshot'])
    suggestions_before = build_suggestions(db)
    db.execute('DELETE FROM person_aliases WHERE person_id = ?', (event['target_id'],))
    for alias in before['target_aliases']:
        add_alias(db, event['target_id'], alias['name'])
    restored_id = db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',
                             (before['source']['name'], before['source']['name_key'])).lastrowid
    for memory_id in before['memory_ids']:
        db.execute('UPDATE memories SET person_id = ? WHERE id = ?', (restored_id, memory_id))
    for alias in before['source_aliases']:
        add_alias(db, restored_id, alias['name'])
    for first, second in before['distinct']:
        other = second if first == before['source']['id'] else first
        if db.execute('SELECT id FROM people WHERE id = ?', (other,)).fetchone():
            left, right = sorted((restored_id, other))
            if left != right:
                db.execute('INSERT OR IGNORE INTO distinct_people VALUES (?,?)', (left, right))
    db.execute('UPDATE people_merges SET undone = 1 WHERE id = ?', (merge_id,))
    carry_actions(db, suggestions_before, build_suggestions(db))
    return {'person_id': restored_id}
