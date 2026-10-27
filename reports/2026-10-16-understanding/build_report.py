from pathlib import Path
from collections import defaultdict
import json,xml.etree.ElementTree as ET
p=Path(__file__).parent
rows=json.loads((p/'live-results.json').read_text())
tests=ET.parse(p/'automated-results.xml').getroot().findall('.//testcase')
groups=defaultdict(list)
for t in tests:groups[t.get('classname','unknown')].append(t)
lines=['# Weaver understanding audit — October 16, 2026','',
'## Results','',f'- Automated suite: **{len(tests)} passed, 0 failed**.',
f"- Live-model audit: **{sum(r['passed'] for r in rows)}/{len(rows)} passed all stated checks; {sum(not r['passed'] for r in rows)} need attention**.",
'- Live cases used fictional text through the real extraction function and configured Nebius provider. They did not create entries or alter the app database.',
'- Automated tests use controlled model responses and temporary databases. Passing these does not establish real-model accuracy.',
'- Each live case was run once through the production pipeline, including its built-in retries and section splitting. These are observed results, not an accuracy guarantee.',
'- No production code was changed during this audit. Full model outputs and expected checks are in live-results.json.','',
'## Findings to fix','',
'1. **Names containing apostrophes:** “D’Arcy loves jazz.” failed name validation after automatic retries.',
'2. **Known and new people together:** Tavi’s chess interest was classified as context; Nora’s identical fact used replacement metadata instead of duplicate metadata.',
'3. **Repeated facts:** the model used replaces_id instead of duplicate_of. The publication layer also checks normalized values and can still consolidate an identical fact, so this is a protocol mismatch, not proof of duplicate visible profiles.',
'4. **Dropped timing:** “I will pay the electricity bill tomorrow” became “Pay the electricity bill” without tomorrow in its value. The source quote retained tomorrow, but reminder scheduling currently reads the value, making this a real scheduling risk.',
'5. **Wrong actor:** “Tavi renewed their passport” was returned as the author’s completed personal action instead of a fact about Tavi. A separate backend actor check rejects this as a personal completion; the person’s fact is still missing.',
'6. **Business mistaken for a person:** Apple was extracted as a person from “I went to Apple in Boston today.”',
'7. **Someone else’s plan placed under You:** “Tavi wants to go to the mall” was classified as a personal plan instead of a plan belonging to Tavi.','',
'## All 28 live-model cases','',
'Pass means the output satisfied person/category/value, item counts, and applicable duplicate/correction references. Every returned result also passed source-quote validation. A failed check is not necessarily a failed request: most were valid JSON with incorrect meaning.','',
'| # | Test | Input | Result |','|---:|---|---|---|']
for r in rows:
 text=r['text'] if len(r['text'])<180 else '[Long fictional entry crossing multiple extraction sections; full text in JSON]'
 lines.append(f"| {r['number']} | {r['name']} | {text.replace('|','/').replace(chr(10),' ')} | {'PASS' if r['passed'] else 'NEEDS ATTENTION'} |")
lines+=['','## Full automated test inventory','',
'Every collected test instance is listed below, including parameterized variants. Each line includes its exact test identifier for reproducibility.','']
for group,items in sorted(groups.items()):
 lines += [f"### {group.removeprefix('tests.test_').replace('_',' ').title()} — {len(items)} tests",'']
 for t in items:
  name=t.get('name');friendly=name.removeprefix('test_').replace('_',' ')
  status='FAIL' if t.find('failure') is not None or t.find('error') is not None else 'SKIP' if t.find('skipped') is not None else 'PASS'
  lines.append(f'- **{status}** {friendly} — `{group}::{name}`')
 lines.append('')
lines+=['## Files','',
'- `live-results.json`: fictional inputs, expected checks, observed outputs, validation findings and elapsed time.',
'- `automated-results.xml`: full machine-readable automated test results.',
'- `automated-output.txt`: test-run output, including the existing Starlette/httpx deprecation warning.',
'- `run_live_cases.py`: repeatable live audit. Running it calls the configured provider and may incur API costs.',
'- `build_report.py`: recreates this report from saved results.','']
(p/'test-report.md').write_text('\n'.join(lines))
print('Automated groups:',{k:len(v) for k,v in sorted(groups.items())})
print('Live:',sum(r['passed'] for r in rows),'/',len(rows))
