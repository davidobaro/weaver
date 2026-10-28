"""Fictional, isolated save-to-organized benchmark; never reads the personal DB."""
import sys, json, time, tempfile, statistics, argparse
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import httpx
from fastapi.testclient import TestClient
from backend import main, inference

CASES = [
 {'id':'mixed_names', 'text':"Coffee with stewy and Zoë today. stewy moved into a new apartment. Zoë loves ceramics. I need to renew my passport tomorrow. Look into that running plan.", 'people':['stewy','Zoë'], 'personal':['passport','running'], 'facts':[('stewy','context','apartment'),('Zoë','interest','ceramics')]},
 {'id':'correction', 'text':"Maya corrected me: her birthday is April 18, not April 8. Maya enjoys jazz. I need to book a dentist appointment. I promised Maya I would send her the trail guide.", 'birthday':True,'personal':['dentist'],'facts':[('Maya','birthday','18'),('Maya','interest','jazz'),('Maya','commitment','guide')]},
 {'id':'recurring_mixed', 'text':"I need to water the plants every Saturday. I should stretch daily. I need to pay rent on the first of each month. Noor is learning guitar. Look into a photography course.", 'repeats':['weekly','daily','monthly'],'personal':['plants','stretch','rent','photography'],'facts':[('Noor','interest','guitar')]},
 {'id':'roles_and_completion', 'text':"Maya renewed her passport. I paid the electricity bill. I still need to renew my passport. Maybe I will go hiking sometime. I felt tired and wanted room to breathe.", 'completed':True,'personal':['passport'],'facts':[('Maya','context','passport')], 'forbid_personal':['breathing','room to breathe','electricity']},
 {'id':'uncertain_repeat', 'text':"I might water the plants every Saturday. I used to run daily. I want to run twice a week. Remind me to look into a new desk. rory started college. I don't need to renew the gym membership.", 'no_repeats':True,'personal':['run','desk'],'facts':[('rory','context','college')],'forbid_personal':['gym']},
 {'id':'aliases', 'text':"stewy enjoys photography. I need to call stewy every Friday. Need to get peppers from Marc. I need to pay the phone bill tomorrow.", 'aliases':True,'repeats':['weekly'],'personal':['phone'],'facts':[('Stephen','interest','photography'),('Stephen','plan','call'),('Marc','plan','peppers')]},
 {'id':'context_heavy', 'text':"Maya corrected her birthday: April 18, not April 8. Maya still loves hiking. I promised Maya a trail guide. eli moved in today. I need to submit the application tomorrow.", 'heavy':True,'birthday':True,'personal':['application'],'facts':[('Maya','interest','hiking'),('Maya','commitment','guide'),('eli','context','moved')]},
 {'id':'long_journal', 'text':("I spent the afternoon walking and enjoying the quiet. Nothing to organize in this reflection.\n\n"*13)+"Amara enjoys painting. I need to refill my prescription tomorrow. I need to water the plants every Saturday. Look into a ceramics class.", 'personal':['refill','plants','ceramics'],'facts':[('Amara','interest','painting')],'repeats':['weekly']},
]

def seed(db, case):
 def remember(person, category, value):
  row=db.execute('SELECT id FROM people WHERE name_key=?',(person.casefold(),)).fetchone()
  pid=row['id'] if row else db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',(person,person.casefold())).lastrowid
  note=db.execute("INSERT INTO notes(text,status,entry_date) VALUES (?,'organized','2026-10-20')",(value,)).lastrowid
  main.archive_entry(db,main.note_or_404(db,note))
  db.execute('INSERT INTO memories(person_id,note_id,category,value,evidence) VALUES (?,?,?,?,?)',(pid,note,category,value,value))
  return pid
 remember('Maya','birthday','Birthday April 8')
 remember('Maya','interest','Loves hiking')
 if case.get('heavy'):
  for i in range(75): remember('Maya','context',f'Attended workshop number {i} about a different craft')
 if case.get('aliases'):
  pid=remember('Stephen','context','Moved in')
  db.execute("INSERT INTO person_aliases(person_id,name,name_key) VALUES (?,'stewy','stewy')",(pid,))
 if case.get('completed'):
  note=db.execute("INSERT INTO notes(text,status,entry_date) VALUES ('Pay the electricity bill','organized','2026-10-20')").lastrowid
  main.archive_entry(db,main.note_or_404(db,note))
  db.execute("INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,'task','Pay the electricity bill','Pay the electricity bill')",(note,))

def assess(case, state, personal, suggestions):
 issues=[]
 active=[(p['name'],m) for p in state['people'] for m in p['memories'] if m['active']]
 for name in case.get('people',[]):
  if not any(p['name'].casefold()==name.casefold() for p in state['people']): issues.append('Missing person: '+name)
 for person,category,word in case.get('facts',[]):
  if not any(name.casefold()==person.casefold() and m['category']==category and word.casefold() in m['value'].casefold() for name,m in active): issues.append(f'Missing fact: {person}/{category}/{word}')
 values=' '.join(row['value'].casefold() for row in personal)
 for word in case.get('personal',[]):
  if word.casefold() not in values: issues.append('Missing personal intention: '+word)
 for word in case.get('forbid_personal',[]):
  if word.casefold() in values: issues.append('Incorrect personal intention: '+word)
 repeats=[s['repeat'] for s in suggestions if s['repeat'] and not s['past_occurrence']]
 for frequency in case.get('repeats',[]):
  if frequency not in repeats: issues.append('Missing repeat: '+frequency)
 if case.get('no_repeats') and repeats: issues.append('Unsupported repeat created')
 if case.get('birthday'):
  births=[m['value'] for name,m in active if name=='Maya' and m['category']=='birthday']
  if len(births)!=1 or '18' not in births[0]: issues.append('Birthday correction did not replace old date')
 if case.get('completed') and not any(s['status']=='done' and any('electricity' in x['value'].lower() for x in s['sources']) for s in suggestions): issues.append('Authored completion did not close existing bill task')
 if case.get('aliases') and any(p['name'].casefold()=='stewy' for p in state['people']): issues.append('Confirmed alias split into a new profile')
 return issues

def run(label, selected=None):
 output=[]
 for case in CASES:
  if selected and case['id'] not in selected: continue
  requests=[]
  original=httpx.Client.post
  def timed_post(client,url,*args,**kwargs):
   if not str(url).endswith('/chat/completions'): return original(client,url,*args,**kwargs)
   payload=kwargs.get('json',{}); start=time.perf_counter()
   response=original(client,url,*args,**kwargs)
   try: usage=response.json().get('usage',{})
   except ValueError: usage={}
   requests.append({'seconds':round(time.perf_counter()-start,3),'prompt_characters':sum(len(m['content']) for m in payload.get('messages',[])), 'context_characters':len(json.loads(payload['messages'][1]['content']).get('known_people',[]).__str__()),'status':response.status_code,'usage':usage,'response_content':response.json().get('choices',[{}])[0].get('message',{}).get('content')})
   return response
  with tempfile.TemporaryDirectory(prefix='weaver-benchmark-') as directory, patch.object(main,'DB_PATH',Path(directory)/'benchmark.sqlite3'):
   with TestClient(main.app) as client:
    with main.database() as db: seed(db,case)
    with patch.object(httpx.Client,'post',timed_post):
     started=time.perf_counter()
     response=client.post('/api/notes',json={'text':case['text'],'kind':'journal','entry_date':'2026-10-27'})
     saved=time.perf_counter(); note_id=response.json()['id']
     main.app.state.worker.submit(lambda:None).result(timeout=600)
     organized=time.perf_counter()
    state=client.get('/api/state').json(); note=next(n for n in state['notes'] if n['id']==note_id)
    suggestions=client.get('/api/for-you?include_all_plans=true').json()['suggestions']
    with main.database() as db: personal=[dict(row) for row in db.execute('SELECT * FROM personal_reminders WHERE active=1 AND note_id=?',(note_id,))]
    issues=assess(case,state,personal,suggestions) if note['status']=='organized' else ['Organization failed: '+str(note['error'])]
    row={'case':case['id'],'text':case['text'],'status':note['status'],'issues':issues,'save_seconds':round(saved-started,3),'organized_seconds':round(organized-started,3),'requests':requests,'completion_candidates':note.get('completion_candidates'),'personal':personal,'people':state['people'],'suggestions':suggestions}
    output.append(row)
    print(f"{label} {case['id']}: {'PASS' if not issues else 'CHECK'} {row['organized_seconds']}s, {len(requests)} requests; {'; '.join(issues)}",flush=True)
    Path(__file__).with_name(label+'.json').write_text(json.dumps(output,indent=2))
 summary={'cases':len(output),'passed':sum(not row['issues'] for row in output),'median_organized_seconds':round(statistics.median(row['organized_seconds'] for row in output),3),'requests':sum(len(row['requests']) for row in output),'prompt_characters':sum(r['prompt_characters'] for row in output for r in row['requests'])}
 print(json.dumps(summary),flush=True)
 Path(__file__).with_name(label+'-summary.json').write_text(json.dumps(summary,indent=2))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('label');parser.add_argument('--cases',nargs='*');args=parser.parse_args();run(args.label,args.cases)
