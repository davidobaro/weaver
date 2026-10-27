import re,subprocess
from pathlib import Path
p=Path(__file__).parent
s=(p/'fonts-google.css').read_text();(p/'fonts').mkdir(exist_ok=True)
for i,u in enumerate(dict.fromkeys(re.findall(r'url\(([^)]+)\)',s))):
 f='fonts/font-'+str(i)+'.ttf';subprocess.run(['curl','-L','--fail','-s',u,'-o',str(p/f)],check=True);s=s.replace(u,'/'+f)
(p/'fonts.css').write_text(s)
p2=p/'src/style.css';old=p2.read_text();old=re.sub(r"@import url\([^;]+;", "@import url('/fonts.css');",old,count=1);p2.write_text(old)
