import {VoiceStatus,MicrophoneSelfTest} from '../components/VoiceDiagnostics';
import {useEffect,useRef,useState} from 'react';
import {Phone,PhoneOff,Mic,MicOff,Volume2,VolumeX,Send,Users,ShieldCheck,Radio,ArrowUpRight,RefreshCw,Play,LockKeyhole} from 'lucide-react';
import {api,post,patch,socket} from '../services/api';
import {useCallAudio} from '../hooks/useCallAudio';
import {Badge,Inspector,Empty,Turn,Bars,human,pct} from '../components/UI';
const TERMINAL=['COMPLETED','TRANSFERRED','FAILED'];
const duration=s=>`${Math.floor((s||0)/60).toString().padStart(2,'0')}:${((s||0)%60).toString().padStart(2,'0')}`;
export function Heading({eyebrow,title,description,children}){return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{children}</div>;}
export default function LiveCalls({notify,config}){
 const [all,setAll]=useState([]),[call,setCall]=useState(null),[mode,setMode]=useState('MOCK_CALL_MODE'),[customers,setCustomers]=useState([]),[customer,setCustomer]=useState(''),[challenge,setChallenge]=useState(''),[input,setInput]=useState(''),[busy,setBusy]=useState(false),[muted,setMuted]=useState(false),[live,setLive]=useState(false),[selectedTurn,setSelectedTurn]=useState(null);
 const transcriptBox=useRef(null),refreshTimer=useRef(null),loadVersion=useRef(0),sessionVersion=useRef(0),manualEnd=useRef(false),stateQueue=useRef(Promise.resolve()),audioRequest=useRef(null);
 const [clock,setClock]=useState(Date.now());
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),1000);return()=>clearInterval(timer);},[]);
 const callRef=useRef(null),pending=useRef(false),audioRef=useRef(null),wsRef=useRef(null),modeRef=useRef(mode),mutedRef=useRef(muted);callRef.current=call;modeRef.current=mode;mutedRef.current=muted;
 const realCall=call?.mode==='REAL_PHONE_CALL';
 const active=call&&!TERMINAL.includes(call.state),profile=customers.find(c=>c.id===(call?.customer_id||customer));
 const audio=useCallAudio({onFinal:send,onAudio:sendAudio,config:config?.speech||{},onError:notify,onState:state=>{
  const c=callRef.current,version=sessionVersion.current;
  if(!c||c.mode==='REAL_PHONE_CALL'||c.state==='ESCALATING'||TERMINAL.includes(c.state)||manualEnd.current)return;
  stateQueue.current=stateQueue.current.catch(()=>{}).then(()=>{
   if(version===sessionVersion.current&&!manualEnd.current&&callRef.current?.id===c.id)
    return post(`/calls/${c.id}/state`,{state,turn_count:c.turn_count});
  }).catch(()=>{});
 }});audioRef.current=audio;
 async function reload(id=callRef.current?.id){
  const version=++loadVersion.current;
  try{const [items,c]=await Promise.all([api('/calls'),id?api(`/calls/${id}`):Promise.resolve(null)]);
   if(version!==loadVersion.current)return;
   setAll(items);if(c){setCall(c);callRef.current=c;if(TERMINAL.includes(c.state)){manualEnd.current=true;audioRef.current.endSession();}}
  }catch(e){notify(e.message);}
 }
 useEffect(()=>{
   api('/demo-customers').then(setCustomers).catch(e=>notify(e.message));reload();
   const ws=socket('/live-calls');wsRef.current=ws;
   ws.onopen=()=>setLive(true);ws.onclose=()=>setLive(false);
   ws.onmessage=e=>{const event=JSON.parse(e.data);if(event.type==='snapshot')setAll(event.data);
     if(event.call_id===callRef.current?.id){if(event.type==='silence'&&event.data.turn_count===callRef.current?.turn_count&&!audioRef.current.interim&&!['CUSTOMER_SPEAKING','FINALIZING_UTTERANCE'].includes(audioRef.current.captureState)&&!pending.current&&!manualEnd.current&&!TERMINAL.includes(callRef.current?.state)&&callRef.current?.mode!=='REAL_PHONE_CALL')audioRef.current.speak(event.data.text,{enabled:!mutedRef.current&&callRef.current?.mode!=='TEXT_TEST_MODE'});if(['state','turn','authentication','demo_card_block','voice_metrics'].includes(event.type)){clearTimeout(refreshTimer.current);refreshTimer.current=setTimeout(()=>reload(event.call_id),150);}}
     else if(event.type==='state'){clearTimeout(refreshTimer.current);refreshTimer.current=setTimeout(()=>reload(),150);}
   };
   const timer=setInterval(()=>reload(),4000);
   return()=>{clearInterval(timer);clearTimeout(refreshTimer.current);loadVersion.current++;sessionVersion.current++;audioRequest.current?.abort();audioRef.current.endSession();ws.close();};
 },[]);
 useEffect(()=>{const el=transcriptBox.current;if(el&&call?.turns?.length)el.scrollTo({top:el.scrollHeight,behavior:'smooth'});},[call?.turns?.length]);
 async function start(){
  if(pending.current)return;pending.current=true;setBusy(true);
  try{audio.endSession();manualEnd.current=false;sessionVersion.current++;const c=await post('/calls',{mode,customer_id:customer||null});setCall(c);callRef.current=c;audio.setSession(c.id,mode==='BROWSER_VOICE_DEMO');setSelectedTurn(null);setChallenge('');await reload(c.id);audio.speak(c.greeting,{autolisten:mode==='BROWSER_VOICE_DEMO',enabled:!muted&&mode!=='TEXT_TEST_MODE'});}
  catch(e){notify(e.message);}finally{pending.current=false;setBusy(false);}
 }
 async function send(text=input,source='text',stt_ms=null,metadata={}){
  const c=callRef.current,version=sessionVersion.current;if(manualEnd.current||!text.trim()||pending.current||!c||c.mode==='REAL_PHONE_CALL'||TERMINAL.includes(c.state))return;
  pending.current=true;setBusy(true);audioRef.current.processing();setInput('');
  try{
   const turn=await post(`/calls/${c.id}/turns`,{text,source,stt_ms,stt_confidence:metadata.confidence??null,stt_alternatives:metadata.alternatives||[],request_id:crypto.randomUUID()});
   if(manualEnd.current||version!==sessionVersion.current)return;
   const updated={...callRef.current,turn_count:c.turn_count+1};callRef.current=updated;setCall(updated);
   setSelectedTurn(turn);await reload(c.id);
   if(manualEnd.current||version!==sessionVersion.current)return;
   audioRef.current.speak(turn.voice_response,{enabled:!mutedRef.current&&c.mode!=='TEXT_TEST_MODE'&&config?.tts_enabled!==false,autolisten:!turn.handoff?.customer_requested_human&&(c.mode==='BROWSER_VOICE_DEMO'||(c.mode==='MOCK_CALL_MODE'&&source==='voice')),
    onStart:ms=>patch(`/turns/${turn.id}/voice-metric`,{tts_ms:ms}).catch(()=>{})});
  }catch(e){notify(e.message);if(!manualEnd.current&&version===sessionVersion.current)audioRef.current.resume();}finally{pending.current=false;setBusy(false);}
 }
 async function sendAudio(blob){
  const c=callRef.current,version=sessionVersion.current;
  if(!c||manualEnd.current||pending.current||TERMINAL.includes(c.state))return;
  pending.current=true;setBusy(true);const controller=new AbortController();audioRequest.current=controller;
  try{
   const response=await fetch('/api/calls/'+c.id+'/audio-turn?request_id='+crypto.randomUUID(),{method:'POST',credentials:'same-origin',headers:{'Content-Type':'audio/wav'},body:blob,signal:controller.signal});
   const data=await response.json();
   if(manualEnd.current||version!==sessionVersion.current)return;
   if(!response.ok){
    if(data.detail?.fallback==='browser')audioRef.current.useBrowserFallback();
    notify(typeof data.detail==='string'?data.detail:data.detail?.message||'Speech processing failed; please repeat.');
    audioRef.current.speak("I'm sorry, I didn't catch that clearly. Could you repeat it?",{enabled:!mutedRef.current,autolisten:true});return;
   }
   const updated={...callRef.current,turn_count:c.turn_count+1};callRef.current=updated;setCall(updated);
   setSelectedTurn(data);await reload(c.id);
   if(manualEnd.current||version!==sessionVersion.current)return;
   audioRef.current.speak(data.voice_response,{enabled:!mutedRef.current&&config?.tts_enabled!==false,autolisten:!data.handoff?.customer_requested_human,
     onStart:ms=>patch('/turns/'+data.id+'/voice-metric',{tts_ms:ms}).catch(()=>{})});
  }catch(error){if(error.name!=='AbortError'&&!manualEnd.current){notify('Audio processing failed. Please repeat.');audioRef.current.resume();}}
  finally{if(audioRequest.current===controller)audioRequest.current=null;pending.current=false;setBusy(false);}
 }
 async function action(name){
  const c=callRef.current;if(!c)return;
  manualEnd.current=true;sessionVersion.current++;audioRequest.current?.abort();audio.endSession();clearTimeout(refreshTimer.current);
  try{const r=await post(`/calls/${c.id}/${name}`);if(r.id===c.id){callRef.current=r;setCall(r);}await reload(c.id);if(r.message)notify(r.message);}
  catch(e){notify(e.message);}
  finally{const current=callRef.current;if(current?.id===c.id&&!TERMINAL.includes(current.state)){manualEnd.current=false;audio.setSession(c.id,c.mode==='BROWSER_VOICE_DEMO');audio.resume();}}
 }
 async function verify(){try{const r=await post(`/calls/${call.id}/verify`,{customer_id:customer||call.customer_id,answer:challenge});await reload();setChallenge('');notify(r.authentication_status==='VERIFIED'?'Fictional demo profile verified.':'The demo answer did not match.');}catch(e){notify(e.message);}}
 async function microphone(){if(!active||busy||realCall)return;try{await post(`/calls/${call.id}/interrupt`);if(!manualEnd.current)audio.listen(true,call.mode!=='TEXT_TEST_MODE');}catch(e){notify(e.message);}}
 const latest=selectedTurn&&call?.turns?.some(t=>t.id===selectedTurn.id)?selectedTurn:call?.turns?.at(-1);
 return <><Heading eyebrow="BANK OPERATIONS / LIVE MONITOR" title="Every call. A clear next step." description="Monitor phone conversations, inspect decisions, and bring in the right support."><Badge tone={live?'respond':'neutral'}>{live?'LIVE EVENT FEED':'POLLING FALLBACK'}</Badge></Heading>
 <div className="call-launch panel"><div className="launch-label"><Phone size={22}/><div><b>Call simulator</b><small>Customers call. Your team monitors here.</small></div></div><select aria-label="Operating mode" value={mode} disabled={active} onChange={e=>setMode(e.target.value)}>{['MOCK_CALL_MODE','BROWSER_VOICE_DEMO','TEXT_TEST_MODE','REAL_PHONE_CALL'].map(m=><option key={m}>{m}</option>)}</select><select aria-label="Demo customer" value={customer} disabled={active} onChange={e=>setCustomer(e.target.value)}><option value="">Unidentified demo caller</option>{customers.map(c=><option key={c.id} value={c.id}>{c.id} · {c.name}</option>)}</select><button className="button" onClick={start} disabled={active||busy||mode==='REAL_PHONE_CALL'}><Phone size={15}/>{busy&&!call?'Connecting?':'Start call'}</button></div>
 {mode==='REAL_PHONE_CALL'&&<div className="info-note"><Phone size={20}/><p>{config?.telephony?.real_phone_configured?`Call the configured support number ${config.telephony.phone_number}. Incoming calls appear below.`:`Real phone mode not ready. Check Settings ? Telephony. Missing or invalid: ${config?.telephony?.missing?.join(', ')||'provider configuration'}.`}</p></div>}
 <div className="call-layout"><section className="panel call-screen"><div className="call-screen-top"><Badge tone="neutral">{call?.mode||'PHONE-FIRST SUPPORT'}</Badge><span>{call?.id?call.id.slice(0,8):'No active session'}</span></div><div className={`call-avatar ${audio.listening?'listening':''}`}><Phone size={32}/></div><h2>{call?.customer_id?customers.find(c=>c.id===call.customer_id)?.name||call.customer_id:'Banking support caller'}</h2><div className="call-timer">{active?duration(Math.max(0,Math.floor((clock-Date.parse(call.created_at))/1000))):call?duration(call.duration_seconds):'00:00'}</div><div className="call-state"><i/>{audio.listening?audio.captureState:audio.speaking?'SPEAKING':call?.state||'READY FOR A CALL'}</div><div className="call-wave">{Array.from({length:27},(_,i)=><i className={audio.listening||audio.speaking?'moving':''} style={{height:`${8+(i*17)%34}px`,animationDelay:`${i*.05}s`}} key={i}/>)}</div><p className="call-utterance">{audio.interim||latest?.voice_response||call?.greeting||'Start a simulated incoming call, or connect a configured telephony provider.'}</p><div className="call-buttons"><button aria-label="Microphone and interrupt" disabled={!active||busy||realCall} onClick={microphone}>{audio.listening?<MicOff size={21}/>:<Mic size={21}/>}</button><button aria-label={muted?'Enable call audio':'Mute call audio'} disabled={realCall} onClick={()=>{setMuted(v=>!v);audio.cancel();audio.resume();if(active)post(`/calls/${call.id}/state`,{state:'WAITING'}).catch(()=>{});}}>{muted?<VolumeX size={21}/>:<Volume2 size={21}/>}</button><button aria-label="Transfer call" disabled={!active||busy} onClick={()=>action('transfer')}><Users size={21}/></button><button className="hangup" aria-label="End call" disabled={!active} onClick={()=>action('end')}><PhoneOff size={21}/></button></div><div className="call-button-labels"><span>Speak / interrupt</span><span>Audio</span><span>Transfer</span><span>End</span></div>
 <div className="call-auth"><div><LockKeyhole size={14}/><b>{call?.authentication_status||'UNVERIFIED'}</b></div>{profile?<><p>Demo profile: {profile.id}. Non-sensitive challenge: favourite colour shown on this fictional profile.</p><small>Demo answer: <b>{profile.demo_answer}</b>. This is a simulation, not real bank authentication.</small>{active&&call.authentication_status!=='VERIFIED'&&<div className="inline-form"><input aria-label="Demo challenge answer" value={challenge} onChange={e=>setChallenge(e.target.value)} placeholder="Demo colour"/><button className="button secondary" onClick={verify} disabled={!challenge.trim()}>Verify demo</button></div>}{active&&call.authentication_status==='VERIFIED'&&<button className="button secondary" onClick={()=>action('demo-block-card')}>Simulate card block</button>}</>:<p>Select a demo customer before starting to try account-specific enquiries. General banking information requires no verification.</p>}</div>
 <details className="voice-diagnostics"><summary>Operator voice diagnostics</summary><VoiceStatus diagnostics={audio.diagnostics}/><MicrophoneSelfTest disabled={!!active}/></details>
 <p className="voice-notice">Speech: {audio.diagnostics.provider}. Call Sense stores masked transcripts, not audio. Microphone interrupts playback; the waveform is a state indicator.</p></section>
 <section className="panel call-transcript"><div className="panel-title"><Radio size={18}/>Live call transcript <Badge tone="neutral">{call?.turns?.length||0} TURNS</Badge></div><div className="call-transcript-body" ref={transcriptBox}>{!call?.turns?.length?<Empty title="Ready to hear the customer">The transcript and approved spoken responses appear here as the call progresses.</Empty>:call.turns.map((t,i)=><Turn key={t.id} turn={t} index={i} onInspect={setSelectedTurn} active={latest?.id===t.id} onSpeak={t=>audio.speak(t.voice_response||t.answer)}/>)}{busy&&<p className="thinking">Processing caller turn and checking evidence…</p>}</div><form className="call-test-input" onSubmit={e=>{e.preventDefault();send();}}><input aria-label="Test utterance" value={input} onChange={e=>setInput(e.target.value)} placeholder={active?'Type a caller utterance to simulate speech…':'Start a call to send a test utterance'} maxLength={2000} disabled={!active||busy||realCall}/><button aria-label="Send test utterance" className="send-button" disabled={!active||busy||realCall||!input.trim()}><Send size={17}/></button></form><div className="call-context"><span>Intent <b>{human(latest?.prediction?.intent)}</b></span><span>Confidence <b>{latest?.prediction?.confidence!=null?pct(latest.prediction.confidence):'?'}</b></span><span>Provider <b>{call?.provider||'?'}</b></span><span>Decision <b>{latest?.decision||'—'}</b></span><span>Risk <b>{latest?.risk||'—'}</b></span><span>Trust <b>{latest?.trust?.score??'—'}</b></span></div></section></div>
 {latest&&<details className="panel decision-drawer"><summary><ShieldCheck size={17}/>Inspect evidence, trust components and safety decision</summary><div className="two-column padded"><Inspector turn={latest}/><section><h3>Call decision timeline</h3><p>{latest.reason}</p><p><b>Answer type:</b> {human(latest.answer_type)}</p><h4>Entities</h4><pre>{JSON.stringify(latest.entities,null,2)}</pre><h4>Observable stages</h4><div className="state-timeline">{call?.events?.filter(e=>e.type==='state').slice(-12).map(e=><Badge key={e.id} tone="neutral">{e.state}</Badge>)}</div><Bars data={latest.latency} suffix=" ms"/></section></div></details>}
 <section className="panel table-wrap recent-calls"><div className="panel-title"><Phone size={16}/>Call monitor <span>{all.filter(c=>!TERMINAL.includes(c.state)).length} active</span></div><table><thead><tr><th>Call</th><th>Caller</th><th>Mode</th><th>State</th><th>Duration</th><th>Auth</th><th/></tr></thead><tbody>{all.slice(0,15).map(c=><tr key={c.id}><td>{c.id.slice(0,8)}</td><td>{c.customer_id||c.caller||'Demo caller'}</td><td>{human(c.mode)}</td><td><Badge tone="neutral">{c.state}</Badge></td><td>{duration(c.duration_seconds)}</td><td>{human(c.authentication_status)}</td><td><button className="text-button" onClick={()=>{audio.endSession();sessionVersion.current++;manualEnd.current=TERMINAL.includes(c.state);callRef.current=c;audio.setSession(manualEnd.current||c.mode==='REAL_PHONE_CALL'?null:c.id,c.mode==='BROWSER_VOICE_DEMO');setSelectedTurn(null);reload(c.id).then(()=>audio.resume());}}>Monitor <ArrowUpRight size={13}/></button></td></tr>)}</tbody></table>{!all.length&&<p className="muted padded">No calls yet. Use the simulator above to begin.</p>}</section></>;
}
export function CallHistory({notify,onLegacy}){
 const [items,setItems]=useState([]),[selected,setSelected]=useState(null),[step,setStep]=useState(0),[playing,setPlaying]=useState(false);
 const load=()=>api('/calls').then(rows=>setItems(rows.filter(c=>TERMINAL.includes(c.state)))).catch(e=>notify(e.message));useEffect(()=>{load();},[]);
 useEffect(()=>{if(!playing||!selected?.turns?.length)return;const timer=setInterval(()=>setStep(s=>{if(s>=selected.turns.length-1){setPlaying(false);return s;}return s+1;}),1600);return()=>clearInterval(timer);},[playing,selected]);
 async function open(id){try{setSelected(await api(`/calls/${id}`));setStep(0);setPlaying(false);}catch(e){notify(e.message);}}
 const current=selected?.turns?.[step];
 return <><Heading eyebrow="CALL AUDIT / REPLAY" title="The full story of every call." description="Follow caller speech through understanding, evidence, safety and the approved spoken answer."><div className="inline-form"><button className="button secondary" onClick={onLegacy}>Legacy conversations</button><button className="button secondary" onClick={load}><RefreshCw size={15}/>Refresh</button></div></Heading><div className="panel table-wrap"><table><thead><tr><th>Call ID</th><th>Started</th><th>Customer</th><th>Duration</th><th>State</th><th>Turns</th><th/></tr></thead><tbody>{items.map(c=><tr key={c.id}><td>{c.id.slice(0,8)}</td><td>{new Date(c.created_at).toLocaleString()}</td><td>{c.customer_id||c.caller||'Unidentified caller'}</td><td>{duration(c.duration_seconds)}</td><td><Badge tone="neutral">{c.state}</Badge></td><td>{c.turn_count}</td><td><button className="text-button" onClick={()=>open(c.id)}>Inspect call <ArrowUpRight size={14}/></button></td></tr>)}</tbody></table>{!items.length&&<Empty title="No calls recorded">Start a mock call from Live Calls.</Empty>}</div>{selected&&<><div className="replay-controls"><h3>Call {selected.id.slice(0,8)}</h3>{selected.turns.length>0&&<><button className="button secondary" onClick={()=>{if(!playing)setStep(0);setPlaying(v=>!v);}}><Play size={14}/>{playing?'Pause':'Replay'}</button><input type="range" aria-label="Call replay turn" min="0" max={selected.turns.length-1} value={step} onChange={e=>{setStep(+e.target.value);setPlaying(false);}}/><span>{step+1}/{selected.turns.length}</span></>}</div><div className="panel padded"><h3>Structured call summary</h3><p>{selected.summary}</p><Badge tone="neutral">{selected.authentication_status}</Badge></div>{current&&<div className="workspace replay-workspace"><section className="panel padded"><Turn turn={current} index={step}/><h4>Entities and rewritten retrieval query</h4><pre>{JSON.stringify(current.entities,null,2)}</pre><p>{current.effective_query}</p><h4>Proposed answer</h4><p>{current.proposed_answer}</p><h4>Safety verification</h4><pre>{JSON.stringify(current.verification,null,2)}</pre><h4>Spoken response</h4><p>{current.voice_response}</p><Bars data={current.latency} suffix=" ms"/></section><Inspector turn={current}/></div>}<details className="panel padded"><summary>All call-state and authentication events</summary><pre>{JSON.stringify(selected.events,null,2)}</pre></details></>}</>;
}

