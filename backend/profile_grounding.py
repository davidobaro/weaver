"""Source passages that should not disappear from otherwise extracted profiles."""
import re

PRONOUNS = {'he', 'she', 'they'}
FACT = re.compile(r"\b(?P<subject>[^\W\d_][\w’'\-]*?)(?:['’](?:s|re)|\s+(?:is|are))\s+(?P<verb>learning|studying)\s+(?P<topic>[^.!?;\n]+?)(?=\s+(?:and|but)\s+|[.!?;\n]|$)", re.I)
UNCERTAIN = re.compile(r"\b(?:maybe|perhaps|probably|possibly|might|could|would|if|unless|not|never|used to|doubt)\b|\b(?:don|doesn|didn)['’]t\b", re.I)
UNNAMED_ACTOR = re.compile(r"\b(?:his|her|their|my|our)\s+(?:brother|sister|friend|partner|colleague|roommate|son|daughter|parent|teacher)\b", re.I)
UNNAMED_SUBJECTS = {'i','we','it','this','that','someone','somebody','everyone','nobody',
                    'brother','sister','friend','partner','colleague','roommate','son','daughter',
                    'parent','teacher','mother','father','mom','dad','husband','wife','boss','manager','child','cousin'}


def fact_hints(note):
    result = []
    for match in FACT.finditer(note):
        subject = match['subject']
        # Preserve a directly written multiword name instead of reducing
        # "Mary Jane is studying" to a new person called Jane.
        if subject[:1].isupper() and subject.casefold() not in PRONOUNS:
            before = re.search(r"((?:[^\W\d_][\w’'\-]*\s+){1,2})$", note[:match.start()])
            if before:
                preceding = []
                for word in reversed(before[1].split()):
                    if not word[:1].isupper() or word.casefold() in {'i','we','he','she','they','today','yesterday'}:
                        break
                    preceding.insert(0, word)
                subject = ' '.join([*preceding, subject])
        if subject.casefold() in UNNAMED_SUBJECTS:
            continue
        begin = max(note.rfind(mark, 0, match.start()) for mark in '.!?;\n') + 1
        end = re.search(r'[.!?;\n]', note[match.start():])
        if (end and end[0] == '?') or UNCERTAIN.search(note[begin:match.end()]):
            continue
        result.append({'subject': subject, 'quote': match[0], 'topic': match['topic'].strip(),
                       'category': 'context' if match['verb'].lower() == 'studying' else 'interest'})
        hobby = re.match(r'\s+and\s+(?P<quote>(?:loves|likes|enjoys)\s+(?P<topic>[^.!?;\n]+))', note[match.end():], re.I)
        if hobby and not UNCERTAIN.search(hobby['quote']):
            result.append({'subject': subject, 'quote': hobby['quote'],
                           'topic': hobby['topic'].strip(), 'category': 'interest'})
    return result


def paragraph_at(note, start):
    separators = list(re.finditer(r'\n\s*\n', note))
    left = max((m.end() for m in separators if m.end() <= start), default=0)
    right = min((m.start() for m in separators if m.start() > start), default=len(note))
    return left, right


def missing_facts(result, note, identity_context=''):
    """Check explicit subjects or a single supported paragraph actor; never guess gender."""
    missing = []
    words = lambda text: set(re.findall(r'\w+', text.casefold())) - {'a', 'an', 'the', 'to', 'is', 'are', 'in', 'of', 'making', 'playing', 'doing'}
    for hint in fact_hints(note):
        start = note.find(hint['quote'])
        left, right = paragraph_at(note, start)
        paragraph = note[left:right]
        if hint['subject'].casefold() not in PRONOUNS:
            actor = hint['subject']
        else:
            source = (identity_context + '\n' if left == 0 else '') + paragraph
            if UNNAMED_ACTOR.search(source):
                continue
            actors = {item.person.casefold(): item.person for item in result.memories
                      if re.search(r'(?<!\w)' + re.escape(item.person) + r'(?!\w)', source, re.I)}
            if len(actors) != 1:
                continue  # Multiple/unnamed actors need model interpretation, not forced attribution.
            names = {name.split()[-1] for name in actors}
            coordinated = re.findall(r"\b([^\W\d_][\w’'\-]*)\s+(and|with)\s+([^\W\d_][\w’'\-]*)\b", source, re.I)
            if any(first.casefold() in names or (join.lower() == 'and' and second.casefold() in names)
                   for first, join, second in coordinated):
                continue  # A second named actor may itself have been omitted.
            actor = next(iter(actors.values()))
        topic = words(hint['topic'])
        covered = any(item.person.casefold() == actor.casefold() and item.category == hint['category']
                      and topic <= words(item.value)
                      and max(start, note.find(item.evidence)) < min(start + len(hint['quote']), note.find(item.evidence) + len(item.evidence))
                      for item in result.memories)
        if topic and not covered:
            missing.append({**hint, 'person': actor, 'paragraph_start': left, 'paragraph_end': right})
    return missing
