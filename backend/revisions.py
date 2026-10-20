"""Entry versions and safe retirement of facts from revised writing."""


def archive_entry(db, note):
    db.execute('''INSERT OR IGNORE INTO note_versions
               (note_id, revision, text, title, kind, entry_date, saved_at)
               VALUES (?,?,?,?,?,?,COALESCE(?,?))''',
               (note['id'], note['revision'], note['text'], note['title'], note['kind'],
                note['entry_date'], note.get('updated_at'), note['created_at']))


def current_predecessor(db, previous, excluded_note_id):
    visited = set()
    while previous and previous not in visited:
        visited.add(previous)
        old = db.execute('''SELECT m.*, n.revision AS current_revision FROM memories m
                         JOIN notes n ON n.id = m.note_id WHERE m.id = ?''', (previous,)).fetchone()
        if not old:
            break
        if old['note_id'] != excluded_note_id and (old['edited'] or old['note_revision'] == old['current_revision']):
            return previous
        previous = old['replaces_id']
    return None


def retire_generated(db, note_id):
    db.execute('UPDATE personal_reminders SET active = 0 WHERE note_id = ?', (note_id,))
    retired = [dict(row) for row in db.execute(
        'SELECT * FROM memories WHERE note_id = ? AND active = 1 AND edited = 0', (note_id,))]
    db.execute('UPDATE memories SET active = 0 WHERE note_id = ? AND edited = 0', (note_id,))
    for memory in retired:
        previous = current_predecessor(db, memory['replaces_id'], note_id)
        if previous:
            db.execute('UPDATE memories SET active = 1 WHERE id = ?', (previous,))


def historical_entry(db, note, revision):
    version = db.execute('SELECT * FROM note_versions WHERE note_id = ? AND revision = ?',
                         (note['id'], revision)).fetchone()
    if version is None:
        return None
    return {**note, 'revision': revision, 'current_revision': note['revision'],
            'text': version['text'], 'title': version['title'], 'kind': version['kind'],
            'entry_date': version['entry_date'], 'updated_at': version['saved_at'],
            'is_history': revision != note['revision'], 'candidates': None, 'personal_candidates': None, 'completion_candidates': None}
