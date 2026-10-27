import numpy as np, wave
from pathlib import Path
sr=48000; duration=22.2
out=np.zeros((int(sr*duration),2),dtype=np.float64)
def note(start,midi,length,amp=.1,pan=0,pad=False):
 n=int(sr*length);t=np.arange(n)/sr;f=440*2**((midi-69)/12)
 if pad:
  env=np.minimum(t/.65,1)*np.minimum((length-t)/.9,1); tone=(np.sin(2*np.pi*f*t)+.16*np.sin(2*np.pi*f*2*t))*.65
 else:
  env=(1-np.exp(-t*100))*np.exp(-t*2.4)*np.minimum((length-t)/.3,1)
  tone=np.sin(2*np.pi*f*t)+.24*np.sin(2*np.pi*f*2*t)*np.exp(-t*4)+.08*np.sin(2*np.pi*f*3*t)*np.exp(-t*7)
 v=tone*env*amp
 # Small diffuse echoes form the same space for bed and UI notes.
 for delay,gain in [(0,1),(.143,.15),(.287,.08)]:
  i=int((start+delay)*sr); k=min(len(v),len(out)-i)
  if k>0:out[i:i+k,0]+=v[:k]*gain*(.75-pan*.2);out[i:i+k,1]+=v[:k]*gain*(.75+pan*.2)
chords=[[50,57,61,66],[47,54,57,62],[43,50,57,59],[45,52,57,61]]
for j,start in enumerate([0,4.8,9.6,14.4,19.2]):
 chord=chords[j%4]
 for k,m in enumerate(chord):note(start,m, min(5.8,duration-start),.035,(-1)**k*.5,True)
 for b in range(8):
  st=start+b*.6
  if st<21:note(st,chord[(b+1)%4]+12,1.5,.07,(-1)**b*.45)
for st,m in [(3.15,78),(8.15,81),(9.3,78),(14.1,74),(16.4,78),(16.52,81),(19.35,86)]:note(st,m,.85,.045,.15)
x=np.arange(len(out))/sr
out*=np.minimum(x/.5,1)[:,None]*np.minimum((duration-x)/1.2,1)[:,None]
out=np.tanh(out*1.5)*.75
with wave.open(str(Path(__file__).parent/'score.wav'),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((out*32767).astype('<i2').tobytes())
print('Audio peak',float(np.max(np.abs(out))),'RMS',float(np.sqrt(np.mean(out*out))))
