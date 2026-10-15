import {test,expect} from '@playwright/test';
async function openCall(page){
 await page.goto('/');await page.locator('nav').getByRole('button',{name:'Live Calls',exact:true}).click();
 await page.getByLabel('Operating mode').selectOption('BROWSER_VOICE_DEMO');
 const created=page.waitForResponse(r=>r.url().endsWith('/api/calls')&&r.request().method()==='POST');
 await page.getByRole('button',{name:'Start call',exact:true}).click();
 return (await (await created).json()).id;
}
async function ttsStub(page){
 await page.addInitScript(()=>{
  Object.defineProperty(window,'speechSynthesis',{value:{cancel(){},speak(u){u.onstart?.();setTimeout(()=>u.onend?.(),20);}},configurable:true});
 });
}
test('browser displays interim speech but delivers only the complete final sentence',async({page})=>{
 await ttsStub(page);
 await page.addInitScript(()=>{
  class Recognition{start(){window.rec=this;this.onstart?.();}abort(){if(window.rec===this)window.rec=null;this.onend?.();}}
  window.SpeechRecognition=Recognition;
  window.emit=(text,final)=>{const r=[{transcript:text,confidence:.95}];r.isFinal=final;window.rec.onresult({resultIndex:0,results:[r]});};
 });
 const id=await openCall(page);await expect.poll(()=>page.evaluate(()=>!!window.rec)).toBe(true);
 await page.evaluate(()=>window.emit('My card is blocked',false));
 await page.waitForTimeout(700);
 expect((await (await page.request.get('/api/calls/'+id)).json()).turns).toHaveLength(0);
 await page.evaluate(()=>window.emit('My card is blocked and I need a replacement.',true));
 await expect(page.locator('.assistant-message')).toHaveCount(1);
 const call=await (await page.request.get('/api/calls/'+id)).json();
 expect(call.turns[0].raw_transcript).toBe('My card is blocked and I need a replacement.');
 expect(call.turns[0].prediction.intent).toBe('card_blocked');expect(call.ended_at).toBeNull();
 await page.getByRole('button',{name:'End call',exact:true}).click();
});

test('PCM worklet retains a natural pause, uploads one WAV turn, and releases microphone on End',async({page})=>{
 await ttsStub(page);
 await page.route('**/api/config',async route=>{
  const response=await route.fetch(),body=await response.json();
  body.speech={...body.speech,audio_available:true,provider:'faster_whisper',browser_mode:'backend'};
  await route.fulfill({response,json:body});
 });
 await page.addInitScript(()=>{
  window.stoppedTracks=0;
  Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{getUserMedia:async()=>({getTracks:()=>[{stop(){window.stoppedTracks++;}}]})}});
  window.AudioContext=class{constructor(){this.sampleRate=16000;this.state='running';this.destination={};this.audioWorklet={addModule:async()=>{}};}createMediaStreamSource(){return {connect(){},disconnect(){}};}async resume(){}async close(){this.state='closed';}};
  window.AudioWorkletNode=class{constructor(){this.port={onmessage:null,close(){}};window.pcmNode=this;}connect(){}disconnect(){}};
  window.frames=(count,value)=>{for(let i=0;i<count;i++)window.pcmNode.port.onmessage?.({data:new Float32Array(320).fill(value)});};
 });
 let uploads=0;
 await page.route('**/api/calls/*/audio-turn?*',async route=>{
  uploads++;const wav=route.request().postDataBuffer();
  expect(wav.subarray(0,4).toString()).toBe('RIFF');expect(wav.readUInt32LE(24)).toBe(16000);
  expect(wav.length).toBeGreaterThan(64000);
  const id=route.request().url().split('/calls/')[1].split('/')[0];
  // Controlled STT fixture: this checks transport/UI, not acoustic accuracy.
  const response=await page.request.post('/api/calls/'+id+'/turns',{data:{text:'My card is blocked and I need a replacement.',source:'voice',stt_confidence:.95}});
  await route.fulfill({status:response.status(),json:await response.json()});
 });
 const id=await openCall(page);await expect.poll(()=>page.evaluate(()=>!!window.pcmNode?.port.onmessage)).toBe(true);
 await page.evaluate(()=>{window.frames(15,0);window.frames(20,.2);window.frames(35,0);});expect(uploads).toBe(0);
 await page.evaluate(()=>{window.frames(30,.2);window.frames(60,0);});
 await expect(page.locator('.assistant-message')).toHaveCount(1);expect(uploads).toBe(1);
 expect((await (await page.request.get('/api/calls/'+id)).json()).ended_at).toBeNull();
 await page.getByRole('button',{name:'End call',exact:true}).click();await expect(page.locator('.call-state')).toHaveText('COMPLETED');
 expect(await page.evaluate(()=>window.stoppedTracks)).toBe(1);
});

for(const scenario of ['supported','absent','constructor-absent','setter-failure','async-error']){
 test('optional phrase bias: '+scenario,async({page})=>{
  await ttsStub(page);
  await page.route('**/api/config',async route=>{const response=await route.fetch(),body=await response.json();body.speech.audio_available=false;body.speech.browser_phrase_bias=true;await route.fulfill({response,json:body});});
  await page.addInitScript(({scenario})=>{
   window.instances=[];
   class Recognition{
    constructor(){this.continuous=false;this.interimResults=false;window.instances.push(this);if(scenario!=='absent')Object.defineProperty(this,'phrases',{get:()=>this.configuredPhrases,set:v=>{if(scenario==='setter-failure')throw Error('unsupported');this.configuredPhrases=v;}});}
    start(){window.rec=this;this.onstart?.();if(scenario==='async-error'&&this.configuredPhrases?.length)setTimeout(()=>this.onerror?.({error:'phrases-not-supported'}),10);}
    abort(){if(window.rec===this)window.rec=null;this.onend?.();}
   }
   window.SpeechRecognition=Recognition;
   if(scenario==='constructor-absent')Object.defineProperty(window,'SpeechRecognitionPhrase',{value:undefined,configurable:true,writable:true});
   if(scenario!=='constructor-absent')window.SpeechRecognitionPhrase=class{constructor(phrase,boost){this.phrase=phrase;this.boost=boost;}};
   window.emit=text=>{const result=[{transcript:text,confidence:.95}];result.isFinal=true;window.rec.onresult({resultIndex:0,results:[result]});};
  },{scenario});
  const id=await openCall(page);
  await expect.poll(()=>page.evaluate(()=>!!window.rec)).toBe(true);
  if(['setter-failure','async-error'].includes(scenario))await expect.poll(()=>page.evaluate(()=>window.instances.length)).toBe(2);
  expect(await page.evaluate(()=>!!window.rec?.configuredPhrases?.length)).toBe(scenario==='supported');
  await page.evaluate(()=>window.emit('My card is blocked.'));
  await expect(page.locator('.assistant-message')).toHaveCount(1);
  const call=await (await page.request.get('/api/calls/'+id)).json();
  expect(call.turns[0].prediction.intent).toBe('card_blocked');expect(call.ended_at).toBeNull();
  await expect(page.locator('body')).not.toContainText('phrases-not-supported');
  // Capability failure must remain disabled on subsequent recognition instances.
  await expect.poll(()=>page.evaluate(()=>!!window.rec)).toBe(true);
  expect(await page.evaluate(()=>!!window.rec?.configuredPhrases?.length)).toBe(scenario==='supported');
  await page.getByRole('button',{name:'End call',exact:true}).click();
  await expect(page.locator('.call-state')).toHaveText('COMPLETED');
 });
}

test('spoken human request queues a normal handoff without ending the call',async({page})=>{
 await ttsStub(page);
 await page.route('**/api/config',async route=>{const response=await route.fetch(),body=await response.json();body.speech.audio_available=false;body.speech.browser_phrase_bias=true;await route.fulfill({response,json:body});});
 await page.addInitScript(()=>{
  window.SpeechRecognition=class{start(){window.rec=this;this.onstart?.();}abort(){window.rec=null;this.onend?.();}};
 });
 const id=await openCall(page);await expect.poll(()=>page.evaluate(()=>!!window.rec)).toBe(true);
 await page.evaluate(()=>{const result=[{transcript:'Transfer the call to a human agent.',confidence:.95}];result.isFinal=true;window.rec.onresult({resultIndex:0,results:[result]});});
 await expect(page.locator('.assistant-message')).toContainText('support queue');
 await expect(page.locator('.assistant-message')).not.toContainText(/suspicious|fraud/i);
 await expect(page.locator('.call-state')).toHaveText('ESCALATING');
 await page.waitForTimeout(1500);
 expect(await page.evaluate(()=>!!window.rec)).toBe(false);
 const call=await (await page.request.get('/api/calls/'+id)).json();
 expect(call.ended_at).toBeNull();expect(call.turns[0].handoff.customer_requested_human).toBe(true);
 await page.getByRole('button',{name:'End call',exact:true}).click();
});
