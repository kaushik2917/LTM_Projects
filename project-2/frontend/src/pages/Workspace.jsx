import {useEffect,useRef,useState} from 'react';
import {Mic,MicOff,Send,Plus,Square,Volume2,VolumeX,ShieldCheck,ArrowUpRight,Radio,LoaderCircle} from 'lucide-react';
import {api,post,socket as createSocket} from '../services/api';
import {useVoice} from '../hooks/useVoice';
import {Badge,Inspector,Turn} from '../components/UI';

export default function Workspace({notify,config}){
 const [conversation,setConversation]=useState(null),[turns,setTurns]=useState([]),[selected,setSelected]=useState(null),[input,setInput]=useState(''),[busy,setBusy]=useState(false),[stage,setStage]=useState('Ready when you are'),[autoSpeak,setAutoSpeak]=useState(false),[scenarios,setScenarios]=useState([]),[connected,setConnected]=useState(false),[closed,setClosed]=useState(false);
 const socket=useRef(null),lock=useRef(false),scroll=useRef(null),timeout=useRef(null),alive=useRef(true);
 const voice=useVoice({onTranscript:send,onError:notify,enabled:autoSpeak&&config?.tts_enabled});
 const voiceRef=useRef(voice);voiceRef.current=voice;
 useEffect(()=>{alive.current=true;api('/scenarios').then(setScenarios).catch(e=>notify(e.message));return()=>{alive.current=false;clearTimeout(timeout.current);socket.current?.close();};},[]);
 useEffect(()=>{const container=scroll.current?.parentElement;if(container&&(turns.length||busy))container.scrollTo({top:container.scrollHeight,behavior:'smooth'});},[turns,busy]);
 function complete(turn){clearTimeout(timeout.current);lock.current=false;setBusy(false);setStage(turn.decision==='ESCALATE'?'Handoff prepared':'Ready when you are');setTurns(t=>[...t,turn]);setSelected(turn);voiceRef.current.speak(turn);}
 function fail(message){clearTimeout(timeout.current);lock.current=false;setBusy(false);setStage('Ready when you are');notify(message);}
 async function start(){
   voice.stop();const previous=socket.current;socket.current=null;previous?.close();setConnected(false);
   const c=await post('/conversations');if(!alive.current)return null;
   setConversation(c);setTurns([]);setSelected(null);setClosed(false);setStage('Ready when you are');
   const ws=createSocket(`/ws/${c.id}`);socket.current=ws;
   ws.onopen=()=>{if(socket.current===ws)setConnected(true);};
   ws.onclose=()=>{if(socket.current===ws){setConnected(false);if(lock.current)fail('Connection interrupted. Open conversation history to check whether this turn was saved before retrying.');}};
   ws.onerror=()=>{if(socket.current===ws)setConnected(false);};
   ws.onmessage=event=>{if(socket.current!==ws)return;const data=JSON.parse(event.data);if(data.type==='status')setStage(data.stage);if(data.type==='turn')complete(data.data);if(data.type==='error')fail(data.message);};
   return c;
 }
 async function send(text=input,source='text',stt_ms=null){
   if(!text.trim()||lock.current)return;
   lock.current=true;setBusy(true);
   try{
     const c=conversation&&!closed?conversation:await start();if(!c)return;
     setInput('');setStage('Understanding and retrieving evidence');
     const payload={text,source,stt_ms};
     if(socket.current?.readyState===WebSocket.OPEN){timeout.current=setTimeout(()=>{socket.current?.close();fail('Response timed out. Check conversation history before retrying.');},45000);socket.current.send(JSON.stringify(payload));}
     else complete(await post(`/conversations/${c.id}/messages`,payload));
   }catch(e){fail(e.message);}
 }
 async function stop(){try{voice.stop();if(conversation)await post(`/conversations/${conversation.id}/stop`);socket.current?.close();setClosed(true);setStage('Conversation ended');notify('Conversation saved. Start a new session whenever you are ready.');}catch(e){notify(e.message);}}
 return <><div className="page-heading"><div><div className="eyebrow">CUSTOMER WORKSPACE</div><h1>A better banking conversation.</h1><p>Natural conversations. Verified answers. Human support when it matters.</p></div><button className="button secondary" disabled={busy} onClick={()=>start().catch(e=>notify(e.message))}><Plus size={16}/>New conversation</button></div><div className="workspace"><section className="conversation panel"><div className="conversation-header"><div className="assistant-avatar"><Radio size={20}/></div><div><h3>Voice assistant</h3><span className="muted"><i className={`status-dot ${busy?'working':''}`}/>{voice.listening?'Listening':voice.speaking?'Speaking':stage}</span></div><div className="conversation-controls"><Badge tone="neutral">{connected?'LIVE SESSION':conversation?'REST SESSION':'READY'}</Badge><button className="icon-button" onClick={()=>{setAutoSpeak(v=>!v);voice.stop();}} aria-label={autoSpeak?'Disable automatic speech':'Enable automatic speech'}>{autoSpeak?<Volume2 size={18}/>:<VolumeX size={18}/>}</button>{conversation&&!closed&&<button className="icon-button" onClick={stop} disabled={busy} aria-label="Stop conversation"><Square size={15}/></button>}</div></div><div className="conversation-body">{!turns.length&&!busy?<div className="welcome"><div className="orb"><Radio size={42}/><span/><span/></div><Badge tone="neutral">VOICE-FIRST. TRUST-LED.</Badge><h2>How can I help you today?</h2><p>Ask about cards, transactions, loans, or everyday banking.<br/>I’ll find the evidence before I answer.</p><div className="suggestions">{['What documents are required for KYC?','My card was charged twice.','My card isn’t working.','I don’t recognize a transaction.'].map(s=><button key={s} onClick={()=>send(s.replaceAll('’',"'"))}>{s}<ArrowUpRight size={16}/></button>)}</div></div>:turns.map((t,i)=><Turn key={t.id} turn={t} index={i} active={selected?.id===t.id} onSpeak={voice.speak} onInspect={setSelected}/>)}{busy&&<div className="thinking"><LoaderCircle className="spin" size={17}/>{stage}…</div>}<div ref={scroll}/></div><div className="composer-wrap">{voice.listening&&<div className="voice-live"><div className="wave">{Array.from({length:20},(_,i)=><i key={i} style={{animationDelay:`${i*.08}s`,height:`${8+(i*13)%22}px`}}/>)}</div><span>{voice.interim||'Listening…'}</span></div>}<form className="composer" onSubmit={e=>{e.preventDefault();send();}}><button className={`mic-button ${voice.listening?'recording':''}`} type="button" onClick={voice.listen} disabled={busy} aria-label={voice.listening?'Stop microphone':'Start microphone'}>{voice.listening?<MicOff size={20}/>:<Mic size={20}/>}</button><input value={input} onChange={e=>setInput(e.target.value)} maxLength={2000} placeholder="Type your banking question…" aria-label="Banking question" disabled={busy}/><button className="send-button" aria-label="Send message" disabled={!input.trim()||busy}><Send size={18}/></button></form><div className="composer-note"><ShieldCheck size={12}/>Research prototype · Use fictional details only <span>English · {voice.supported?'Voice available':'Typed input available'}</span></div><p className="voice-notice">Microphone recognition may use your browser vendor’s service. No audio is stored by Call Sense.</p></div></section><Inspector turn={selected}/></div><section className="scenario-strip"><div><span className="eyebrow">PUT THE DECISION LAYER TO THE TEST</span><h3>One click. Six different situations.</h3></div><div className="scenario-buttons">{scenarios.slice(0,6).map((s,i)=><button disabled={busy} key={s.query} onClick={()=>send(s.query)}><span>0{i+1}</span>{['KYC question','Unclear card issue','Suspected fraud','PIN request','Prompt injection','Unknown topic'][i]}</button>)}</div></section></>;
}
