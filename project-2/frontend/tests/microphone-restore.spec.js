import {test,expect} from '@playwright/test';
async function setup(page,{available=true,backend=false}={}){
 await page.route('**/api/config',async route=>{const response=await route.fetch(),body=await response.json();body.speech={...body.speech,audio_available:backend,browser_mode:'browser',browser_phrase_bias:false};await route.fulfill({response,json:body});});
 await page.addInitScript(({available})=>{
  window.voice={starts:0,errors:[],current:null};
  window.SpeechRecognitionPhrase=class{};
  class Recognition{
   constructor(){Object.defineProperty(this,'phrases',{set(){throw Error('Default path must not assign phrases');}});}
   start(){window.voice.current=this;window.voice.starts++;this.onstart?.();this.onaudiostart?.();}
   abort(){if(window.voice.current===this)window.voice.current=null;this.onend?.();}
  }
  Object.defineProperty(window,'SpeechRecognition',{value:available?Recognition:undefined,configurable:true});
  Object.defineProperty(window,'webkitSpeechRecognition',{value:undefined,configurable:true});
  Object.defineProperty(window,'speechSynthesis',{value:{cancel(){},speak(u){u.onstart?.();setTimeout(()=>u.onend?.(),30);}},configurable:true});
  window.emit=(text,final=true)=>{const rec=window.voice.current,result=[{transcript:text,confidence:.95}];result.isFinal=final;const callback=rec.onresult;callback({resultIndex:0,results:[result]});if(final)callback({resultIndex:0,results:[result]});};
 },{available});
 await page.goto('/');await page.locator('nav').getByRole('button',{name:'Live Calls',exact:true}).click();
}
async function start(page){await page.getByLabel('Operating mode').selectOption('BROWSER_VOICE_DEMO');const response=page.waitForResponse(r=>r.url().endsWith('/api/calls')&&r.request().method()==='POST');await page.getByRole('button',{name:'Start call',exact:true}).click();return (await(await response).json()).id;}
async function listening(page){await expect(page.locator('.thinking')).toHaveCount(0);await expect(page.locator('.call-state')).toHaveText('LISTENING');await expect.poll(()=>page.evaluate(()=>!!window.voice.current)).toBe(true);}

test('browser default bypasses PCM and phrases; final sentences reach the pipeline once',async({page})=>{
 await setup(page,{backend:true});let uploads=0;await page.route('**/audio-turn?*',route=>{uploads++;return route.abort();});
 const id=await start(page);
 const phrases=['Hello.','My card is blocked.',"It's a debit card.",'It stopped working at the ATM.','What is UPI?','What is NEFT?','My debit card is blocked and I tried using it at the ATM this morning but it is still not working.'];
 for(let i=0;i<phrases.length;i++){
  await listening(page);expect(await page.evaluate(()=>window.voice.current.continuous)).toBe(false);
  await page.evaluate(text=>window.emit(text),phrases[i]);await expect(page.locator('.assistant-message')).toHaveCount(i+1);
 }
 await listening(page);const c=await(await page.request.get('/api/calls/'+id)).json();
 expect(c.turns.map(t=>t.raw_transcript)).toEqual(phrases);expect(c.ended_at).toBeNull();expect(uploads).toBe(0);
 await page.getByRole('button',{name:'End call',exact:true}).click();const count=await page.evaluate(()=>window.voice.starts);await page.waitForTimeout(700);expect(await page.evaluate(()=>window.voice.starts)).toBe(count);
});

test('abandoned interim cannot block a final result from the next session',async({page})=>{
 await setup(page);const id=await start(page);await listening(page);
 await page.evaluate(()=>{window.emit('unfinished earlier words',false);window.voice.current.onend();});
 await listening(page);await page.evaluate(()=>window.emit('My card is blocked.'));
 await expect(page.locator('.assistant-message')).toHaveCount(1);
 const c=await(await page.request.get('/api/calls/'+id)).json();expect(c.turns[0].raw_transcript).toBe('My card is blocked.');
 await page.getByRole('button',{name:'End call',exact:true}).click();
});

for(const error of ['no-speech','aborted','network','phrases-not-supported'])test('recover '+error+' without onend',async({page})=>{
 await setup(page);const id=await start(page);await listening(page);
 const starts=await page.evaluate(error=>{const starts=window.voice.starts;window.voice.current.onerror({error});return starts;},error);
 await expect.poll(()=>page.evaluate(()=>window.voice.starts)).toBeGreaterThan(starts);await listening(page);
 await page.evaluate(()=>window.emit('Hello.'));await expect(page.locator('.assistant-message')).toHaveCount(1);
 expect((await(await page.request.get('/api/calls/'+id)).json()).ended_at).toBeNull();
 await page.getByRole('button',{name:'End call',exact:true}).click();
});

test('recognition unavailable does not end the call',async({page})=>{
 await setup(page,{available:false});const id=await start(page);
 await expect(page.getByRole('status').filter({hasText:'Browser speech recognition is unavailable'})).toBeVisible();
 expect((await(await page.request.get('/api/calls/'+id)).json()).ended_at).toBeNull();
 await page.getByRole('button',{name:'End call',exact:true}).click();
});

for(const score of [0,.3])test('browser confidence '+score+' is handled without inventing certainty',async({page})=>{
 await setup(page);const id=await start(page);await listening(page);
 await page.evaluate(score=>{const result=[{transcript:'My credit card is blocked.',confidence:score}];result.isFinal=true;window.voice.current.onresult({results:[result]});},score);
 await expect(page.locator('.assistant-message')).toHaveCount(1);
 const c=await(await page.request.get('/api/calls/'+id)).json(),turn=c.turns[0];
 expect(turn.raw_transcript).toBe('My credit card is blocked.');
 if(score===0){expect(turn.speech_metadata.stt_confidence).toBeNull();expect(turn.awaiting_slot).toBe('card_channel');}
 else{expect(turn.speech_metadata.stt_confidence).toBe(.3);expect(turn.awaiting_slot).toBe('speech_confirmation');}
 expect(c.ended_at).toBeNull();await page.getByRole('button',{name:'End call',exact:true}).click();
});
