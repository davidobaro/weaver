"""Compact profile facts from current, source-backed memories."""
import re

LABELS = {
    'background': 'Background',
    'context': 'From your notes',
    'birthday': 'Birthday',
    'interest': 'Interests',
    'relationship': 'Connections',
    'plan': 'Current plans',
}


def overview_category(memory):
    value = memory['value']
    if memory['category'] == 'commitment':
        return None
    # Older extractions sometimes put life updates under plans. Surface the
    # original factual statement as background without changing its wording.
    if re.search(r'\b(?:start(?:ed|ing)|attend(?:s|ing)?|graduated|enrolled)\b.{0,35}\b(?:college|university|school|job)\b|\b(?:moved|moving)\s+(?:to|out|away)|\b(?:works?|working)\s+(?:at|as|for|in)|\b(?:lives|living)\s+(?:in|with)', value, re.I):
        return 'background'
    # A task for the note author is not a quick fact about the other person.
    if memory['category'] == 'plan' and re.match(r"^(?:i (?:will|should|need to|want to) )?(?:ask|send|remind|check in|follow up)\b", value, re.I):
        return None
    return memory['category']


def profile_about(memories, notes):
    """Select a small, diverse overview without turning anecdotes into traits.

    Use the actual memory wording, including uncertainty and negation. Promises
    belong in their own section, not in a person's biographical overview.
    """
    facts = []
    seen = set()
    birthday_conflict = len({m['value'].casefold().strip() for m in memories if m['active'] and m['category'] == 'birthday'}) > 1
    for category, label in LABELS.items():
        chosen = 0
        for memory in sorted(memories, key=lambda item: item['id'], reverse=True):
            if not memory['active'] or overview_category(memory) != category:
                continue
            normalized = ' '.join(re.findall(r'\w+', memory['value'].casefold()))
            if normalized in seen:
                continue
            note = notes.get(memory['note_id'])
            if note is None:
                continue
            seen.add(normalized)
            facts.append({'memory_id': memory['id'], 'note_id': memory['note_id'],
                          'label': 'Birthday · conflicting notes' if category == 'birthday' and birthday_conflict else label, 'value': memory['value'], 'evidence': memory['evidence'],
                          'noted_at': note.get('entry_date') or note['created_at'], 'edited': bool(memory['edited'])})
            chosen += 1
            if chosen >= (2 if category in {'context', 'background'} or category == 'birthday' and birthday_conflict else 1):
                break
        if len(facts) >= 5:
            break
    return {'facts': facts[:5], 'note_count': len({m['note_id'] for m in memories if m['active']})}
