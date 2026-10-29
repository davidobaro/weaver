"""Conservative coverage checks for explicit author follow-up intentions."""
import re

from .profile_grounding import paragraph_at

INTENTION = re.compile(
    r"(?:^|(?<=[.!?;\n]))\s*(?P<quote>I(?:['’]d| would) like to\s+"
    r"(?P<like>ask|check in|follow up|talk|contact)\b[^.!?;\n]*|"
    r"I (?:should|need to|want to|plan to|must|will)\s+"
    r"(?P<direct>ask|check in|follow up|talk|contact)\b[^.!?;\n]*)", re.I)
ACTION = re.compile(r'\b(?:ask|check|follow|talk|contact)\b', re.I)
UNCERTAIN = re.compile(r"\b(?:maybe|perhaps|might|if|unless|not|never)\b|\b(?:don|doesn|didn)['’]t\b", re.I)
TOPICS = re.compile(r'\b(?:book|trip|interview|appointment|project|class|exam|application)\b', re.I)


def followup_hints(note, identity_context=''):
    hints = []
    for match in INTENTION.finditer(note):
        quote = match['quote']
        if UNCERTAIN.search(quote) or note[match.end('quote'):match.end('quote') + 1] == '?':
            continue
        start = match.start('quote')
        left, _ = paragraph_at(note, start)
        preceding = (identity_context + ' ' if left == 0 else '') + note[left:start]
        # Only demand a topic when a pronoun has one clear, explicitly written
        # antecedent in this paragraph. Multiple possible topics need model judgment.
        topics = {m[0].casefold() for m in TOPICS.finditer(preceding)}
        topic = next(iter(topics)) if len(topics) == 1 and re.search(r'\b(?:it|that)\b', quote, re.I) else None
        hints.append({'quote': quote, 'start': start, 'end': match.end('quote'),
                      'action_start': match.start('like') if match['like'] else match.start('direct'),
                      'topic': topic})
    return hints


def followup_failure(result, note, identity_context=''):
    for hint in followup_hints(note, identity_context):
        def covers(item):
            start = note.find(item.evidence)
            return (start <= hint['action_start'] < start + len(item.evidence)
                    and ACTION.search(item.value))
        items = [item for item in [*result.memories, *result.personal]
                 if item.category in {'plan', 'commitment', 'task', 'reminder', 'goal'} and covers(item)]
        if not items:
            return 'An explicit follow-up was omitted: ' + hint['quote'] + '. Extract this intention separately from the event it refers to, with an exact source quote and its timing.'
        if hint['topic'] and not any(re.search(r'\b' + hint['topic'] + r'\b', item.value, re.I) for item in items):
            return 'A follow-up lost its subject: ' + hint['quote'] + '. Include the source topic "' + hint['topic'] + '" in its value; keep evidence an exact quote from new_note.'
    return None
