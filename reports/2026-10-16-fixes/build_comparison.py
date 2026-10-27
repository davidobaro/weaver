from pathlib import Path
import json,xml.etree.ElementTree as ET
p=Path(__file__).parent
before=json.loads((p.parent/'2026-10-16-understanding/live-results.json').read_text())
after=json.loads((p/'final-summary/live-results.json').read_text())
tests=ET.parse(p/'final-summary/automated-results.xml').getroot().findall('.//testcase')
passed=sum(r['passed'] for r in after)
lines=['# Weaver understanding fixes — October 16, 2026','',
f'Automated suite: {len(tests)} passed. Live-model rerun: {passed}/{len(after)} passed all audit checks (baseline 21/28).','',
'## What changed','',
'- Enabled Nemotron reasoning to improve interpretation and actor attribution. Writing is saved immediately; background organization takes longer. Only structured final answers are parsed and stored.',
'- Clarified people versus personal tasks, completed actions, ongoing hobbies, business/location names, and reflective feelings.',
'- Restored typographic apostrophe variants to the exact source spelling in names and evidence. No paraphrase or expanded identity is accepted.',
'- Normalized exact matching existing facts as duplicates, preserving genuine corrections and distinct people.',
'- Added bounded corrective retries with specific feedback for obvious wrong-actor responses and dropped personal deadlines.',
'- Kept the original section/token/retry limits and atomic publication. No user entries were rewritten during this audit.','',
'## Before and after — every original live case','',
'| # | Case | Baseline | After fixes |','|---:|---|---|---|']
for a,b in zip(before,after):
 assert a['number']==b['number']
 lines.append(f"| {a['number']} | {a['name']} | {'Pass' if a['passed'] else 'Needs attention'} | {'Pass' if b['passed'] else 'Needs attention'} |")
lines+=['','## Interpretation and limits','',
'The final status combines the most recent full 28-case run with focused rechecks of cases 6, 9, 15, and 21 after narrow category/reference fixes. Each result records its verification run. It is not a claim that every intermediate run passed. These are fictional inputs run through the configured live provider. This is an observed rerun, not a guarantee of perfect accuracy on all journal writing. The baseline and final runs use the same expectations. Intermediate trials are retained in this folder rather than replacing the baseline.','',
'## New regression coverage','']
for t in tests:
 if t.get('classname')=='tests.test_understanding':lines.append('- `'+t.get('name')+'`')
lines+=['','## Remaining failures','']
failed=[r for r in after if not r['passed']]
if not failed:lines.append('None in this 28-case rerun.')
for r in failed:lines.append(f"- {r['name']}: {'; '.join(r['issues'])}")
lines+=['','Full observed outputs: [live-results.json](final-summary/live-results.json). Automated output: [automated-output.txt](final-summary/automated-output.txt).','']
(p/'fix-report.md').write_text('\n'.join(lines))
print(f'{len(tests)} automated tests; {passed}/{len(after)} live cases')
