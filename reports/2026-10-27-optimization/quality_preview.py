"""Isolated fictional feed for a visual check and before/after card metrics."""
import sys, os, tempfile, json, importlib.util
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
os.environ['WEAVER_DB_PATH']=str(Path(tempfile.mkdtemp(prefix='weaver-quality-preview-'))/'quality.sqlite3')
from backend import main
from backend.models import Extraction
from backend.for_you import build_suggestions
from backend.suggestion_quality import coalesce_suggestions
main.initialize()
main.extract_memories=lambda *args:Extraction(memories=[])
main.build_suggestions=lambda db,timezone='America/New_York',include_all_plans=False:build_suggestions(db,today=date(2026,10,27),timezone=timezone,include_all_plans=include_all_plans)
with main.database() as db:
 for text,category,person in [
  ('Renew my passport','task',None),('I need to renew my passport','reminder',None),
  ('Pay the electricity bill on 2026-10-25','task',None),('Call the dentist today','task',None),
  ('Submit the application on 2026-10-30','task',None),('Send Mira the trail guide','commitment','Mira'),
  ('Wants to go to the mall','plan','Maya'),('Enjoys shopping','interest','Noor')]:
  note=db.execute("INSERT INTO notes(text,status,entry_date) VALUES (?,'organized','2026-10-27')",(text,)).lastrowid
  main.archive_entry(db,main.note_or_404(db,note))
  if person:
   found=db.execute('SELECT id FROM people WHERE name_key=?',(person.casefold(),)).fetchone()
   pid=found['id'] if found else db.execute('INSERT INTO people(name,name_key) VALUES (?,?)',(person,person.casefold())).lastrowid
   db.execute('INSERT INTO memories(person_id,note_id,category,value,evidence) VALUES (?,?,?,?,?)',(pid,note,category,text,text))
  else: db.execute('INSERT INTO personal_reminders(note_id,note_revision,category,value,evidence) VALUES (?,1,?,?,?)',(note,category,text,text))
 spec=importlib.util.spec_from_file_location('backend.baseline_quality',Path(__file__).with_name('baseline-for_you.py'))
 before=importlib.util.module_from_spec(spec);spec.loader.exec_module(before)
 old=before.build_suggestions(db,today=date(2026,10,27))
 new=coalesce_suggestions(build_suggestions(db,today=date(2026,10,27)))
 metrics={'before_cards':len(old['suggestions']),'after_cards':len(new['suggestions']),
          'before_order':[item['sources'][0]['value'] for item in old['suggestions']],
          'after_order':[item['sources'][0]['value'] for item in new['suggestions']],
          'group_sources':[len(item['sources']) for item in new['suggestions']]}
 Path(__file__).with_name('quality-results.json').write_text(json.dumps(metrics,indent=2))
 print(json.dumps(metrics),flush=True)
if __name__=='__main__':
 import uvicorn
 uvicorn.run(main.app,host='127.0.0.1',port=8001)
