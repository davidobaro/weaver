"""An inspectable account of what was extracted from an entry's current version."""
import hashlib
import json
import re
from collections import defaultdict
from .completions import completed_action
from .suggestion_quality import canonical_action
from .utils import entry_text


def entry_notices(db, notes, note_id=None):
    wanted = {n['id']: n for n in notes if n['status'] in {'organized','reviewed'}}
    items = defaultdict(list)
    clause, params = (' AND n.id = ?', (note_id,)) if note_id is not None else ('', ())
    for row in db.execute('''SELECT m.*,p.name FROM memories m JOIN people p ON p.id=m.person_id
                            JOIN notes n ON n.id=m.note_id WHERE m.note_revision=n.revision''' + clause + ' ORDER BY m.active DESC,m.id DESC',params):
        if row['note_id'] not in wanted:
            continue
        items[row['note_id']].append({'kind':'task' if row['category'] in {'plan','commitment'} else 'fact',
            'person_id':row['person_id'],'person':row['name'],'category':row['category'],
            'value':row['value'],'evidence':row['evidence'],'active':bool(row['active'])})
    for row in db.execute('''SELECT r.* FROM personal_reminders r JOIN notes n ON n.id=r.note_id
                            WHERE r.note_revision=n.revision''' + clause + ' ORDER BY r.active DESC,r.id DESC',params):
        if row['note_id'] not in wanted:
            continue
        items[row['note_id']].append({'kind':'task','person_id':None,'person':'You','category':row['category'],
            'value':row['value'],'evidence':row['evidence'],'active':bool(row['active'])})
    result = {}
    for id, note in wanted.items():
        distinct = {}
        for item in items[id]:
            normalized = canonical_action(item['value']) if item['kind']=='task' else ' '.join(re.findall(r'\w+',item['value'].casefold()))
            category = ('goal' if item['category']=='goal' else 'action') if item['kind']=='task' else item['category']
            distinct.setdefault((item['person_id'],item['kind'],category,normalized),item)
        rows = list(distinct.values())
        completed = {}
        for candidate in note.get('completion_candidates') or []:
            if isinstance(candidate,dict) and all(isinstance(candidate.get(key),str) for key in ('value','evidence')) and completed_action(entry_text(note),candidate):
                completed.setdefault((canonical_action(candidate['value']),candidate['evidence']),{
                    'kind':'completed','person_id':None,'person':'You','category':'completed',
                    'value':candidate['value'],'evidence':candidate['evidence'],'active':True})
        rows.extend(completed.values())
        people = sorted({item['person_id']:item['person'] for item in rows if item['person_id'] is not None}.items(),key=lambda item:item[1].casefold())
        counts = {'people':len(people),'facts':sum(item['kind']=='fact' for item in rows),
                  'tasks':sum(item['kind']=='task' for item in rows),'completed':len(completed)}
        version = hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest()[:16]
        result[id] = {'counts':counts,'version':version,'people':[{'id':pid,'name':name} for pid,name in people],'items':rows}
    return result
