import {test,expect} from '@playwright/test';

async function fakeSpeech(page){
 await page.addInitScript(()=>{
  window.voice={starts:0,aborts:0,cancels:0,current:null,utterance:null,stale:[],hold:false,failTTS:false};
  class Recognition{
   start(){window.voice.starts++;window.voice.current=this;this.onstart?.();}
   abort(){window.voice.aborts++;if(window.voice.current===this)window.voice.current=null;this.onend?.();}
  }
  window.SpeechRecognition=Recognition;
  Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{
   cancel(){window.voice.cancels++;window.voice.utterance=null;},
   speak(u){window.voice.utterance=u;window.voice.stale.push(u.onend);u.onstart?.();if(!window.voice.hold)setTimeout(()=>{if(window.voice.failTTS){window.voice.failTTS=false;u.onerror?.({error:'synthesis-failed'});}else u.onend?.();},30);}
  }});
  window.say=text=>{const rec=window.voice.current;if(!rec)throw Error('Microphone is not listening');const result=[{transcript:text}];result.isFinal=true;rec.onresult?.({results:[result]});rec.onend?.();};
 });
}
async function start(page,mode){
 await page.goto('/');await page.locator('nav').getByRole('button',{name:'Live Calls',exact:true}).click();
 await page.getByLabel('Operating mode').selectOption(mode);
 const created=page.waitForResponse(r=>r.url().endsWith('/api/calls')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Start call',exact:true}).click();
 const call=await (await created).json();
 await expect(page.getByLabel('Test utterance',{exact:true})).toBeEnabled();return call;
}
async function detail(page,id){return (await page.request.get(`/api/calls/${id}`)).json();}
async function say(page,text,count){
 await expect.poll(()=>page.evaluate(()=>!!window.voice.current)).toBe(true);
 await page.evaluate(text=>window.say(text),text);
 await expect(page.locator('.assistant-message')).toHaveCount(count);
 await expect(page.locator('.thinking')).toHaveCount(0);
 await expect(page.locator('.call-state')).toHaveText('LISTENING');
 await expect.poll(()=>page.evaluate(()=>!!window.voice.current)).toBe(true);
}

test('requested five-turn conversation with actual 5/10/4/20 second pauses stays one mock call',async({page})=>{
 await fakeSpeech(page);const c=await start(page,'MOCK_CALL_MODE');
 const queries=['What is UPI?','What is NEFT?',"My debit card isn't working.",'Online.','What documents are needed for KYC?'];
 for(let i=0;i<queries.length;i++){
  await page.getByLabel('Test utterance',{exact:true}).fill(queries[i]);await page.getByRole('button',{name:'Send test utterance'}).click();
  await expect(page.locator('.assistant-message')).toHaveCount(i+1);
  if(i<4)await page.waitForTimeout([5000,10000,4000,20000][i]);
  const current=await detail(page,c.id);expect(current.ended_at).toBeNull();expect(current.id).toBe(c.id);
 }
 const current=await detail(page,c.id);expect(current.turns[3].context_used).toBe(true);expect(current.duration_seconds).toBeGreaterThanOrEqual(39);
 await page.getByRole('button',{name:'End call',exact:true}).click();await expect(page.locator('.call-state')).toHaveText('COMPLETED');
 const ended=await detail(page,c.id);expect(ended.turns).toHaveLength(5);expect(ended.summary).toBeTruthy();expect(ended.ended_at).toBeTruthy();
});

test('browser onend, TTS completion/error and long silence resume listening until explicit End',async({page})=>{
 await fakeSpeech(page);const c=await start(page,'BROWSER_VOICE_DEMO');
 await say(page,'What is an FD?',1);
 const starts=await page.evaluate(()=>{const rec=window.voice.current;window.voice.current=null;rec.onend();return window.voice.starts;});
 await expect.poll(()=>page.evaluate(()=>window.voice.starts)).toBeGreaterThan(starts);
 await page.waitForTimeout(31000);
 expect((await detail(page,c.id)).ended_at).toBeNull();
 await page.waitForTimeout(5000);
 await say(page,'What about recurring deposits?',2);
 await page.evaluate(()=>window.voice.failTTS=true);
 await say(page,'What is NEFT?',3);
 expect((await detail(page,c.id)).ended_at).toBeNull();
 await page.getByRole('button',{name:'End call',exact:true}).click();await expect(page.locator('.call-state')).toHaveText('COMPLETED');
 const stopped=await page.evaluate(()=>window.voice.starts);
 // Invoke callbacks captured before abort; generation guards must ignore them.
 await page.evaluate(()=>window.voice.stale.forEach(fn=>fn?.()));await page.waitForTimeout(1500);
 expect(await page.evaluate(()=>window.voice.starts)).toBe(stopped);
 expect(await page.evaluate(()=>window.voice.current)).toBeNull();
 expect((await detail(page,c.id)).termination_reason).toBe('manual_end');
});

test('interrupt cancels playback and End during a pending turn prevents late restart',async({page})=>{
 await fakeSpeech(page);const c=await start(page,'BROWSER_VOICE_DEMO');
 await expect.poll(()=>page.evaluate(()=>!!window.voice.current)).toBe(true);
 await page.evaluate(()=>window.voice.hold=true);
 await page.evaluate(()=>window.say('What is NEFT?'));
 await expect(page.locator('.assistant-message')).toHaveCount(1);await expect(page.locator('.call-state')).toHaveText('SPEAKING');
 await page.getByRole('button',{name:'Microphone and interrupt'}).click();
 await expect.poll(()=>page.evaluate(()=>!!window.voice.current)).toBe(true);
 await page.evaluate(()=>{window.voice.stale.forEach(fn=>fn?.());window.voice.hold=false;});
 let release;const wait=new Promise(r=>release=r);
 await page.route(`**/api/calls/${c.id}/turns`,async route=>{const response=await route.fetch();await wait;await route.fulfill({response});});
 await page.evaluate(()=>window.say('What is UPI?'));
 await expect(page.locator('.thinking')).toBeVisible();
 await page.getByRole('button',{name:'End call',exact:true}).click();
 await expect(page.locator('.call-state')).toHaveText('COMPLETED');
 const stopped=await page.evaluate(()=>window.voice.starts);release();await expect(page.locator('.thinking')).toHaveCount(0);
 await page.waitForTimeout(1000);expect(await page.evaluate(()=>window.voice.starts)).toBe(stopped);
 expect((await detail(page,c.id)).turns).toHaveLength(2);
});

test('permission denial pauses restarts without ending the call; escalation waits for transfer',async({page})=>{
 await fakeSpeech(page);const c=await start(page,'BROWSER_VOICE_DEMO');
 await expect.poll(()=>page.evaluate(()=>!!window.voice.current)).toBe(true);
 const starts=await page.evaluate(()=>{const rec=window.voice.current;window.voice.current=null;rec.onerror({error:'not-allowed'});rec.onend?.();return window.voice.starts;});
 await page.waitForTimeout(1200);expect(await page.evaluate(()=>window.voice.starts)).toBe(starts);
 expect((await detail(page,c.id)).ended_at).toBeNull();
 await page.getByRole('button',{name:'Microphone and interrupt'}).click();
 await say(page,'My card was stolen.',1);
 expect((await detail(page,c.id)).ended_at).toBeNull();
 // Active calls belong in the live monitor, not finalized Call History.
 await page.locator('nav').getByRole('button',{name:'Call History',exact:true}).click();
 await expect(page.locator('tbody:visible').getByText(c.id.slice(0,8),{exact:true})).toHaveCount(0);
 await page.locator('nav').getByRole('button',{name:'Live Calls',exact:true}).click();
 await page.getByRole('button',{name:'Transfer call',exact:true}).click();await expect(page.locator('.call-state')).toHaveText('TRANSFERRED');
 const ended=await detail(page,c.id);expect(ended.termination_reason).toBe('transfer');
 expect(ended.events.some(e=>e.state==='COMPLETED')).toBe(false);
 expect(await page.evaluate(()=>window.voice.current)).toBeNull();
});
