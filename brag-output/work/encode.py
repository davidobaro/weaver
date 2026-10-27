from pathlib import Path
from PIL import Image
import subprocess,imageio_ffmpeg
p=Path(__file__).parent; out=p.parent
poster=Image.open(p/'frames/0156.png').convert('RGB');poster.save(out/'brag.jpg',quality=95,subsampling=0)
# Replace the first frame with the final JPEG's pixels. Duration stays 666 frames.
Image.open(out/'brag.jpg').convert('RGB').save(p/'frames/0000.png')
ff=imageio_ffmpeg.get_ffmpeg_exe()
cmd=[ff,'-hide_banner','-y','-framerate','30','-i',str(p/'frames/%04d.png'),'-i',str(p/'score.wav'),'-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-af','loudnorm=I=-18:TP=-2:LRA=7','-c:a','aac','-b:a','192k','-ar','48000','-t','22.2','-movflags','+faststart',str(out/'brag.mp4')]
r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True);(p/'encode.log').write_text(r.stderr);r.check_returncode();print('Encoded',out/'brag.mp4')
verify=subprocess.run([ff,'-hide_banner','-i',str(out/'brag.mp4'),'-map','0:v','-f','null','-'],capture_output=True,text=True);(p/'verification.log').write_text(verify.stderr);verify.check_returncode();print(verify.stderr[-1600:])
