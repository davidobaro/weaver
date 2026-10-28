from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,json,os,tarfile,io
root=Path(__file__).resolve().parents[2]; out=Path(__file__).parent
config=json.loads((out/'check-path.json').read_text()); checkout=Path(config['temporary_checkout'])
archive=subprocess.check_output(['git','archive','HEAD','.env.example'],cwd=root)
with tarfile.open(fileobj=io.BytesIO(archive)) as t:t.extractall(checkout,filter='data')
def run(name,args,cwd):
 result=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 (out/(name+'.log')).write_text(result.stdout)
 print(name+': '+str(result.returncode),flush=True)
 if result.returncode:raise RuntimeError(name+' failed; see log')
def backend():
 run('venv',['python3','-m','venv',str(checkout/'.venv')],checkout)
 py=str(checkout/'.venv/bin/python')
 run('python-install',[py,'-m','pip','install','-r','backend/requirements.lock'],checkout)
 run('pytest',[py,'-m','pytest','tests','-q'],checkout)
def frontend():
 run('npm-install',['npm','ci','--no-audit','--no-fund'],checkout/'frontend')
 run('frontend-build',['npm','run','build'],checkout/'frontend')
results={}
with ThreadPoolExecutor(max_workers=2) as pool:
 pending={pool.submit(fn):name for name,fn in [('backend',backend),('frontend',frontend)]}
 for future,name in pending.items():
  try:future.result();results[name]='passed'
  except Exception as exc:results[name]=str(exc)
(out/'fresh-results.json').write_text(json.dumps(results,indent=2))
print(results,flush=True)
