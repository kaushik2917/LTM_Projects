import {test,expect} from '@playwright/test';
async function open(page,kind){
 await page.addInitScript(({kind})=>{
  window.stops=0;window.audioContextsClosed=0;window.rec=null;
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>{
   if(kind==='denied')throw new DOMException('Denied','NotAllowedError');
   if(kind==='pending')await new Promise(resolve=>window.allow=resolve);
   return {getTracks:()=>[{stop(){window.stops++;}}]};
  }}});
  window.AudioContext=class{async resume(){}async close(){window.audioContextsClosed++;}createAnalyser(){return {fftSize:256,getFloatTimeDomainData(data){data.fill(.1);}};}createMediaStreamSource(){return {connect(){},disconnect(){}};}};
  window.SpeechRecognition=class{start(){window.rec=this;this.onstart?.();this.onaudiostart?.();}abort(){window.rec=null;this.onend?.();}};
 },{kind});
 await page.goto('/');await page.locator('nav').getByRole('button',{name:'Live Calls',exact:true}).click();
 await page.getByText('Operator voice diagnostics',{exact:true}).click();
}
test('microphone self-test measures audio, masks diagnostics and never sends banking turns',async({page})=>{
 const logs=[];page.on('console',message=>logs.push(message.text()));let turns=0;
 page.on('request',r=>{if(r.url().includes('/turns')&&r.method()==='POST')turns++;});
 await open(page,'granted');await page.getByRole('button',{name:'Test microphone',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!window.rec)).toBe(true);
 await expect.poll(async()=>Number(await page.getByRole('meter',{name:'Microphone audio level'}).getAttribute('value'))).toBeGreaterThan(.09);
 await page.evaluate(()=>{const result=[{transcript:'Hello Call Sense',confidence:.95}];result.isFinal=true;window.rec.onresult({results:[result]});});
 const panel=page.locator('.voice-diagnostics section');await expect(panel).toContainText('Hello Call Sense');
 await expect.poll(()=>page.evaluate(()=>!!window.rec)).toBe(true);
 await page.evaluate(()=>{const result=[{transcript:'My PIN is 1234',confidence:.95}];result.isFinal=true;window.rec.onresult({results:[result]});});
 await expect(panel).toContainText('[CREDENTIAL REDACTED]');await expect(panel).not.toContainText('1234');expect(logs.join(' ')).not.toContain('1234');expect(turns).toBe(0);
 await page.getByRole('button',{name:'Stop microphone test',exact:true}).click();
 expect(await page.evaluate(()=>window.stops)).toBe(1);expect(await page.evaluate(()=>window.audioContextsClosed)).toBe(1);expect(await page.evaluate(()=>window.rec)).toBeNull();
});
test('self-test distinguishes microphone permission denial',async({page})=>{
 await open(page,'denied');await page.getByRole('button',{name:'Test microphone',exact:true}).click();
 await expect(page.locator('.voice-diagnostics section')).toContainText('Microphone permission is required for voice mode.');
 expect(await page.evaluate(()=>window.rec)).toBeNull();
});
test('stopping pending permission releases a late stream without starting recognition',async({page})=>{
 await open(page,'pending');await page.getByRole('button',{name:'Test microphone',exact:true}).click();
 await expect.poll(()=>page.evaluate(()=>!!window.allow)).toBe(true);
 await page.getByRole('button',{name:'Stop microphone test',exact:true}).click();await page.evaluate(()=>window.allow());
 await expect.poll(()=>page.evaluate(()=>window.stops)).toBe(1);expect(await page.evaluate(()=>window.rec)).toBeNull();
});
