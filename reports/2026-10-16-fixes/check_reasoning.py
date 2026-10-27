import sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
load_dotenv('.env')
from backend import inference
import httpx
real=httpx.Client
class ReasoningClient:
 def __init__(self,**kwargs):self.client=real(**kwargs)
 def __enter__(self):self.client.__enter__();return self
 def __exit__(self,*args):return self.client.__exit__(*args)
 def post(self,*args,**kwargs):
  kwargs['json']['chat_template_kwargs']={'enable_thinking':True}
  return self.client.post(*args,**kwargs)
inference.httpx.Client=ReasoningClient
out=[]
for text in ['need to get peppers from ellis','I renewed my passport.',"I haven't renewed my passport.",'Today felt quiet. I was tired and wanted some room to breathe.']:
 start=time.monotonic()
 try:result=inference.extract_memories(text).model_dump()
 except Exception as exc:result={'error':str(exc)}
 row={'text':text,'result':result,'seconds':round(time.monotonic()-start,2)};out.append(row);print(json.dumps(row),flush=True)
 Path('reports/2026-10-16-fixes/reasoning-experiment.json').write_text(json.dumps(out,indent=2))
