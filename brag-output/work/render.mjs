import { chromium } from '/Users/davidobaro/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
import fs from 'node:fs/promises';
const out=new URL('./',import.meta.url).pathname;
const browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true,args:['--disable-gpu','--no-sandbox']});
const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
page.on('pageerror',e=>console.error('PAGE ERROR',e.message));
await page.goto('http://127.0.0.1:4317/',{waitUntil:'networkidle'});
await page.evaluate(()=>document.fonts.ready);
await page.waitForFunction(()=>typeof window.renderFrame==='function');
const mode=process.argv[2]||'check';
if(mode==='check'){
 for(const t of [.7,3.18,5.2,8.5,9.38,11,14.18,15,17.5,19.38,20.7]){
  await page.evaluate(t=>window.renderFrame(t),t);await page.screenshot({path:out+'check-'+t+'.png'});
 }
 console.log(await page.evaluate(()=>({fonts:document.fonts.check('400 16px "DM Sans"'),body:document.body.innerText.slice(0,200)})));
}else{
 await fs.mkdir(out+'frames',{recursive:true});
 for(let i=0;i<666;i++){
  await page.evaluate(t=>window.renderFrame(t),i/30);
  await page.screenshot({path:out+'frames/'+String(i).padStart(4,'0')+'.png'});
  if(i%90===0)console.log('Rendered '+i+'/666');
 }
}
await browser.close();
