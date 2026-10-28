"""Conservative completion matching with reversible, source-backed events."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .for_you import date_window, normalized
from .utils import entry_text

PAST_ACTIONS = {
    'renewed': 'renew', 'submitted': 'submit', 'paid': 'pay', 'bought': 'buy',
    'sent': 'send', 'booked': 'book', 'finished': 'finish', 'completed': 'complete',
    'got': 'get', 'called': 'call', 'emailed': 'email', 'checked': 'check',
    'looked': 'look', 'picked': 'pick', 'ordered': 'order', 'collected': 'collect',
    'returned': 'return', 'washed': 'wash', 'cleaned': 'clean', 'filed': 'file',
    'registered': 'register', 'scheduled': 'schedule', 'cancelled': 'cancel',
    'canceled': 'cancel', 'repaired': 'repair', 'fixed': 'fix', 'updated': 'update',
}
STOP = set('i me my a an the to of for in at by into need should must want remember remind please finally already just have had has today tomorrow yesterday this that on'.split())
STOP.update('monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december next week month'.split())
UNFINISHED = re.compile(r"\b(?:not|never|still|yet|maybe|perhaps|possibly|probably|might|think|guess|unsure|apparently|supposedly|will|would|could|should|need|want|hope|plan|if|unless|before|once)\b|\b(?:haven|hasn|hadn|didn|isn|wasn)['’]t\b", re.I)
RECURRING = re.compile(r'\b(?:every|daily|weekly|monthly|yearly|twice|habit)\b|\ba (?:day|week|month|year)\b', re.I)
ACTOR = re.compile(r"^(?:(?:today|yesterday|this morning|this evening|finally|already|just)[,\s]+)*(?:i\s+(?:(?:have|had|finally|already|just|also|successfully)\s+)*|i['’]ve\s+(?:(?:finally|already|just|also|successfully)\s+)*)?(" + '|'.join(PAST_ACTIONS) + r')\b', re.I)


def words(text):
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', text)
    return {PAST_ACTIONS.get(word, word) for word in re.findall(r'\w+', text.casefold()) if word not in STOP}


def logical_date(note):
    if note.get('entry_date'):
        return note['entry_date']
    return datetime.fromisoformat(note['created_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()


def completed_action(text, item):
    evidence = item['evidence']
    start = text.find(evidence)
    if start < 0 or UNFINISHED.search(evidence):
        return None
    boundary = max(text.rfind(mark, 0, start) for mark in ('.', '!', '?', '\n', ';'))
    end_match = re.search(r'[.!?\n;]', text[start:])
    end = start + end_match.end() if end_match else len(text)
    sentence = text[boundary + 1:end].strip()
    actor = ACTOR.match(sentence)
    if not actor or UNFINISHED.search(sentence) or '?' in sentence:
        return None
    action = PAST_ACTIONS[actor[1].casefold()]
    completed_words = words(item['value'])
    if len(completed_words) < 2 or action not in completed_words or not completed_words <= words(evidence):
        return None
    return completed_words


def is_completed_intention(text, intention, completions):
    start = text.find(intention.evidence)
    for completion in completions:
        completed = completed_action(text, completion.model_dump())
        other = text.find(completion.evidence)
        overlap = max(start, other) < min(start + len(intention.evidence), other + len(completion.evidence))
        if completed and overlap and words(intention.value) == completed:
            return True
    return False


def publish_completions(db, note, candidates):
    # Reprocessing a source replaces its old automatic events atomically.
    db.execute('DELETE FROM personal_completions WHERE note_id = ? AND note_revision = ?', (note['id'], note['revision']))
    text = entry_text(note)
    targets = [dict(row) for row in db.execute('''
        SELECT r.*, n.entry_date, n.created_at FROM personal_reminders r
        JOIN notes n ON n.id = r.note_id
        WHERE r.active = 1 AND r.note_revision = n.revision AND r.category != 'goal'
        AND r.note_id != ? AND n.created_at <= ? AND n.status IN ('organized','reviewed')
    ''', (note['id'], note['created_at']))]
    for item in candidates:
        evidence = item['evidence']
        completed_words = completed_action(text, item)
        if not completed_words:
            continue
        matches = []
        signatures = set()
        for target in targets:
            if RECURRING.search(target['value']) or logical_date(target) > logical_date(note):
                continue
            if words(target['value']) != completed_words:
                continue
            anchor = datetime.fromisoformat(logical_date(target)).date()
            window = date_window(target['value'], anchor, anchor)
            signatures.add((target['category'], normalized(target['value']), window))
            matches.append(target)
        # A completion without a distinguishing date must not choose between
        # two separately worded or separately scheduled obligations.
        if len(signatures) != 1:
            continue
        for target in matches:
            db.execute('''INSERT OR IGNORE INTO personal_completions
                       (note_id,note_revision,reminder_id,evidence) VALUES (?,?,?,?)''',
                       (note['id'], note['revision'], target['id'], evidence))
