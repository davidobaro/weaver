"""Personal intentions have source entries, but never create People profiles."""


def publish_personal(db, note, candidates):
    db.execute('UPDATE personal_reminders SET active = 0 WHERE note_id = ?', (note['id'],))
    for item in candidates:
        db.execute('''INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence)
                   VALUES (?,?,?,?,?)''',
                   (note['id'], note['revision'], item['category'], item['value'], item['evidence']))
