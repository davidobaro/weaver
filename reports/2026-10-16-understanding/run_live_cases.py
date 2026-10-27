"""Explicit live-model audit. Never writes to the application's database."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from backend.inference import extract_memories

load_dotenv(ROOT / '.env')
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)
known = [{'id': 101, 'name': 'Nora', 'aliases': [], 'memories': [
    {'id': 901, 'category': 'birthday', 'value': 'April 8'},
    {'id': 902, 'category': 'interest', 'value': 'Enjoys ceramics'},
]}]

# m: (person, category, required value fragment); p: (category, fragment).
CASES = [
 {'name':'New name, short life update','text':'Tavi moved in.', 'm':[('Tavi','context','moved')]},
 {'name':'Lowercase unfamiliar name','text':'rory started college', 'm':[('rory','context','college')]},
 {'name':'Lowercase name, errand without I','text':'need to get peppers from ellis', 'm':[('ellis','plan','pepper')]},
 {'name':'Apostrophe in a name','text':"D’Arcy loves jazz.", 'm':[("D’Arcy",'interest','jazz')]},
 {'name':'Accented name','text':'Zoë enjoys ceramics.', 'm':[('Zoë','interest','ceramic')]},
 {'name':'Hyphenated name','text':'Anne-Marie is studying architecture.', 'm':[('Anne-Marie','context','architect')]},
 {'name':'Several new people','text':'Tavi loves chess. Ellis moved to Vermont. Zoë is learning guitar.', 'm':[('Tavi','interest','chess'),('Ellis','context','Vermont'),('Zoë','interest','guitar')]},
 {'name':'Known and new people in one entry','text':'Nora enjoys ceramics. Tavi loves chess.', 'known':known, 'm':[('Nora','interest','ceramic'),('Tavi','interest','chess')], 'refs':{'Nora':('duplicate_of',902)}},
 {'name':'Correction of an existing birthday','text':'Nora corrected her birthday: April 18, not April 8.', 'known':known, 'm':[('Nora','birthday','April 18')], 'refs':{'Nora':('replaces_id',901)}},
 {'name':'Repeated fact','text':'Nora enjoys ceramics.', 'known':known, 'm':[('Nora','interest','ceramic')], 'refs':{'Nora':('duplicate_of',902)}},
 {'name':'Personal task with no person','text':'I need to renew my passport.', 'p':[('task','passport')]},
 {'name':'Everyday imperative','text':'get water', 'p':[('task','water')]},
 {'name':'Vague personal reminder','text':'look into that running plan', 'p':[('reminder','running')]},
 {'name':'Unnamed task after a named person','text':'Nora loves ceramics. Need to book that appointment.', 'm':[('Nora','interest','ceramic')], 'p':[('task','appointment')]},
 {'name':'Relative deadline stays relative','text':'Submit the application by Friday.', 'p':[('task','Friday')]},
 {'name':'Personal recurring goal','text':'I want to run twice a week.', 'p':[('goal','twice a week')]},
 {'name':'Promise involving a named person','text':'I promised Tavi I would send the recipe.', 'm':[('Tavi','commitment','recipe')]},
 {'name':'Completed personal action','text':'I renewed my passport.', 'c':['passport']},
 {'name':'Negated completion','text':"I haven't renewed my passport."},
 {'name':'Uncertain completion','text':'I might have paid the electricity bill.'},
 {'name':'Future action is not a completion','text':'I will pay the electricity bill tomorrow.', 'p':[('task','tomorrow')]},
 {'name':'Another person completed an action','text':'Tavi renewed their passport.', 'm':[('Tavi','context','passport')]},
 {'name':'Reflection without actionable details','text':'Today felt quiet. I was tired and wanted some room to breathe.'},
 {'name':'Bare name does not create a profile','text':'Tavi'},
 {'name':'Business and place do not become people','text':'I went to Apple in Boston today.'},
 {'name':'Co-occurrence does not imply a relationship','text':'Tavi likes chess. Ellis enjoys hiking.', 'm':[('Tavi','interest','chess'),('Ellis','interest','hiking')]},
 {'name':'One-off wish is a plan, not a hobby','text':'Tavi wants to go to the mall.', 'm':[('Tavi','plan','mall')]},
 {'name':'Long entry preserves details across sections','text':('It was a quiet walk, and I noticed the trees along the path. '*26)+'\n\nTavi loves chess.\n\n'+('I spent the evening reflecting on the day. '*26)+'\n\nI need to renew my passport.', 'm':[('Tavi','interest','chess')], 'p':[('task','passport')]},
]

def check(case, result):
    issues=[]
    for key, expected in [('memories',case.get('m',[])),('personal',case.get('p',[])),('completed_personal',case.get('c',[]))]:
        actual=result[key]
        if len(actual)!=len(expected): issues.append(f'{key}: expected {len(expected)}, got {len(actual)}')
        for item in expected:
            if key=='memories':
                person,category,fragment=item
                found=any(x['person'].casefold()==person.casefold() and x['category']==category and fragment.casefold() in x['value'].casefold() for x in actual)
            elif key=='personal':
                category,fragment=item
                found=any(x['category']==category and fragment.casefold() in x['value'].casefold() for x in actual)
            else:
                found=any(item.casefold() in x['value'].casefold() for x in actual)
            if not found: issues.append(f'{key}: missing expected {item!r}')
    for person,(field,value) in case.get('refs',{}).items():
        if not any(x['person']==person and x.get(field)==value for x in result['memories']):issues.append(f'{person}: expected {field}={value}')
    return issues

def run_case(index, case):
    started=time.monotonic()
    try:
        result=extract_memories(case['text'],case.get('known',[])).model_dump()
        issues=check(case,result)
    except Exception as exc:
        result=None;issues=[type(exc).__name__+': '+str(exc)]
    row={'number':index,'name':case['name'],'text':case['text'],'expected':{k:v for k,v in case.items() if k not in ('text','known','name')},'result':result,'passed':not issues,'issues':issues,'seconds':round(time.monotonic()-started,2)}
    print(f"{index:02d} {'PASS' if not issues else 'REVIEW'} {case['name']}"+(' — '+'; '.join(issues) if issues else ''),flush=True)
    return row

results=[]
workers = min(2, max(1, int(sys.argv[2]))) if len(sys.argv) > 2 else 1
selected = {int(value) for value in sys.argv[3].split(',')} if len(sys.argv) > 3 else None
cases = [(index, case) for index, case in enumerate(CASES, 1) if selected is None or index in selected]
with ThreadPoolExecutor(max_workers=workers) as pool:
    pending = [pool.submit(run_case, index, case) for index, case in cases]
    for future in as_completed(pending):
        results.append(future.result())
        results.sort(key=lambda row: row['number'])
        (OUT/'live-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
print(f"{sum(x['passed'] for x in results)}/{len(results)} cases passed",flush=True)
