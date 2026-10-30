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
    'watered': 'water', 'refilled': 'refill', 'charged': 'charge',
}
STOP = set('i me my a an the to of for in at by into need should must want remember remind please finally already just have had has today tomorrow yesterday this that on'.split())
STOP.update('monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december next week month sometime'.split())
UNFINISHED = re.compile(r"\b(?:not|never|still|yet|maybe|perhaps|possibly|probably|might|think|guess|unsure|apparently|supposedly|will|would|could|should|need|want|hope|plan|if|unless|before|once)\b|\b(?:haven|hasn|hadn|didn|isn|wasn)['’]t\b", re.I)
RECURRING = re.compile(r'\b(?:every|daily|weekly|monthly|yearly|twice|habit)\b|\ba (?:day|week|month|year)\b', re.I)
ACTOR = re.compile(r"^(?:(?:today|yesterday|this morning|this evening|finally|already|just)[,\s]+)*(?:i\s+(?:(?:have|had|finally|already|just|also|successfully)\s+)*|i['’]ve\s+(?:(?:finally|already|just|also|successfully)\s+)*)?(" + '|'.join(PAST_ACTIONS) + r')\b', re.I)
PAST_PATTERN = '|'.join(PAST_ACTIONS)
CLAUSE_START = re.compile(r"^(?:then\s+)?(?:" + PAST_PATTERN +
    r"|i|we|he|she|they|still|not|never)\b|^[^\W\d_][\w’'\-]*\s+"
    r"(?:(?:also|still|has|had)\s+)*(?:" + PAST_PATTERN + r"|might|will|could|should|hasn['’]t|hadn['’]t)\b", re.I)


def completion_clauses(text, evidence):
    """Keep actor/certainty local to coordinated actions, retaining source offsets."""
    start = text.find(evidence)
    if start < 0 or text.count(evidence) != 1:
        return []
    boundary = max(text.rfind(mark, 0, start) for mark in ('.', '!', '?', '\n', ';')) + 1
    end_match = re.search(r'[.!?\n;]', text[start:])
    end = start + end_match.end() if end_match else len(text)
    sentence = text[boundary:end]
    if '?' in sentence:
        return []
    parts = []
    left = 0
    for separator in re.finditer(r',\s*(?:(?:and|but|while|then)\s+)?|\s+(?:and|but|while)\s+', sentence, re.I):
        if CLAUSE_START.match(sentence[separator.end():]):
            parts.append((left, separator.start()))
            left = separator.end()
    parts.append((left, len(sentence)))
    inherited = False
    valid = []
    for index, (left, right) in enumerate(parts):
        raw = sentence[left:right]
        clause = raw.lstrip()
        offset = boundary + left + len(raw) - len(clause)
        then = re.match(r'then\s+', clause, re.I)
        if then:
            offset += then.end()
            clause = clause[then.end():]
        actor = ACTOR.match(clause)
        explicit_author = re.match(r"i(?:\s|['’]ve\b)", clause, re.I)
        # Bare coordinated verbs inherit only a definite author action, never
        # a third party, hypothetical or negated first clause.
        safe = bool(actor and not UNFINISHED.search(clause) and
                    (index == 0 or explicit_author or inherited))
        inherited = safe
        if safe:
            action_start = offset + actor.start(1)
            action_end = offset + actor.end(1)
            if max(start, action_start) < min(start + len(evidence), action_end):
                valid.append((PAST_ACTIONS[actor[1].casefold()], clause))
    return valid


def words(text):
    text = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', text)
    return {PAST_ACTIONS.get(word, word) for word in re.findall(r'\w+', text.casefold()) if word not in STOP}


def logical_date(note):
    if note.get('entry_date'):
        return note['entry_date']
    return datetime.fromisoformat(note['created_at'].replace('Z', '+00:00')).astimezone(ZoneInfo('America/New_York')).date().isoformat()


def completed_action(text, item):
    evidence = item['evidence']
    completed_words = words(item['value'])
    if len(completed_words) < 2 or not completed_words <= words(evidence):
        return None
    matches = [clause for action, clause in completion_clauses(text, evidence)
               if action in completed_words and completed_words <= words(clause)]
    return completed_words if len(matches) == 1 else None


def completion_hints(text):
    """Concrete author actions that a mixed journal response must account for."""
    hints = []
    for sentence in re.finditer(r'[^.!?\n;]+[.!?]?', text):
        for action, clause in completion_clauses(text, sentence[0]):
            # Vague "got things done" or "finished up" is not a task identity.
            if action in {'get', 'finish', 'complete', 'look'}:
                continue
            actor = ACTOR.match(clause)
            quote = clause.strip()
            if actor and len(words(quote)) >= 2:
                hints.append({'quote':quote, 'action':action})
    return hints


def missing_completions(result, text):
    missing = []
    for hint in completion_hints(text):
        actor = ACTOR.match(hint['quote'])
        position = text.find(hint['quote']) + actor.start(1)
        def covers(item):
            start = text.find(item.evidence)
            return start <= position < start + len(item.evidence)
        if not any(covers(item) and hint['action'] in words(item.value) and words(item.value) <= words(hint['quote'])
                   and completed_action(text, item.model_dump()) for item in result.completed_personal) and not any(
                covers(item) and item.category == 'context' for item in result.memories):
            # Person-related completed actions remain profile context; they do
            # not need a personal completion that could close somebody else's task.
            names = {item.person for item in result.memories}
            if any(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', hint['quote'], re.I) for name in names):
                continue
            missing.append(hint)
    return missing


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
