def name_key(value):
    return ' '.join(value.split()).casefold()


def entry_text(note):
    return (note.get('title', '') + '\n\n' if note.get('title') else '') + note['text']
