import {useRef,useState,useEffect} from 'react';
import {initialVoiceDiagnostics,maskVoiceText} from '../services/voiceDiagnostics';
import {PcmCapture} from '../services/pcmCapture';

// Recognition and playback are turn resources. Only endSession ends the call loop.
export function useCallAudio({onFinal,onAudio,onState,onError,config={}}){
 const refs=useRef({active:false,autoListen:false,generation:0,processing:false,blocked:false,restarts:0,forceBrowser:false,forceBackend:false,networkErrors:0});
 const r=refs.current;r.callbacks={onFinal,onAudio,onState,onError};r.config=config;
 const [listening,setListening]=useState(false),[speaking,setSpeaking]=useState(false),[interim,setInterim]=useState('');
 const supported=!!(window.SpeechRecognition||window.webkitSpeechRecognition||(config.audio_available&&navigator.mediaDevices?.getUserMedia&&window.AudioWorkletNode));
 const [speechCapabilities,setSpeechCapabilities]=useState({recognitionSupported:!!(window.SpeechRecognition||window.webkitSpeechRecognition),phraseBiasSupported:false,interimResultsSupported:false,continuousSupported:false});
 const [diagnostics,setDiagnostics]=useState(initialVoiceDiagnostics);
 const debug=(event,values={})=>{setDiagnostics(v=>({...v,...values}));if(import.meta.env.DEV)console.debug('[VOICE] '+event);};
 const [captureState,setCaptureState]=useState('LISTENING');
 function cancel(){
  const r=refs.current;r.generation++;clearTimeout(r.restartTimer);r.restartTimer=null;r.capture?.pause();
  if(r.recognition){const old=r.recognition;r.recognition=null;old.onend=old.onresult=old.onerror=old.onstart=null;try{old.abort();}catch{}}
  const ownedPlayback=!!r.utterance||r.aiSpeaking;
  if(r.utterance){r.utterance.onend=r.utterance.onerror=r.utterance.onstart=null;r.utterance=null;}
  debug('recognition paused',{recognitionActive:false,audioStreamActive:false,interimTranscript:''});
  if(ownedPlayback)window.speechSynthesis?.cancel();r.aiSpeaking=false;setListening(false);setSpeaking(false);setInterim('');
 }
 function endSession(){refs.current.capture?.close();refs.current.capture=null;refs.current.active=false;refs.current.autoListen=false;cancel();}
 function setSession(id,autoListen=false){
  if(refs.current.id===id&&refs.current.active)return;
  cancel();setDiagnostics({...initialVoiceDiagnostics});Object.assign(refs.current,{id,active:!!id,autoListen,processing:false,blocked:false,restarts:0,forceBrowser:false,forceBackend:false,networkErrors:0});
 }
 function schedule(){
  const r=refs.current;
  if(!r.active||!r.autoListen||r.processing||r.aiSpeaking||r.blocked||r.recognition||r.capture?.enabled||r.restartTimer)return;
  const generation=r.generation;
  // Back off repeated empty/error sessions; never spin on recognition.onend.
  r.restartTimer=setTimeout(()=>{r.restartTimer=null;if(r.active&&r.generation===generation&&!r.processing&&!r.aiSpeaking)listen(false);},Math.min(300*2**Math.min(r.restarts,4),4800));
 }
 function resume(){refs.current.processing=false;schedule();}
 function processing(){cancel();refs.current.processing=true;}
 async function listen(manual=true,continuous){
  const r=refs.current;if(!r.active)return;
  if(manual)cancel();r.processing=false;if(continuous!==undefined)r.autoListen=continuous;if(manual){r.blocked=false;r.restarts=0;}
  const generation=r.generation;
  const BrowserRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  const canUseBackend=r.config.audio_available&&!r.forceBrowser&&navigator.mediaDevices?.getUserMedia&&window.AudioWorkletNode;
  if((r.config.browser_mode==='backend'||!BrowserRecognition||r.forceBackend)&&canUseBackend){
   r.capture??=new PcmCapture(r.config.capture||{});
   try{await r.capture.start({
    onState:state=>{if(!r.active||r.generation!==generation)return;debug('PCM capture state',{provider:r.config.provider,microphonePermission:'GRANTED',audioStreamActive:true});setCaptureState(state);setListening(true);if(['LISTENING','CUSTOMER_SPEAKING','FINALIZING_UTTERANCE'].includes(state))r.callbacks.onState(state);},
    onAudio:blob=>{if(!r.active||r.generation!==generation)return;processing();Promise.resolve(r.callbacks.onAudio(blob)).catch(()=>resume());},
    onTooLong:()=>{if(r.active&&r.generation===generation)speak('Please repeat in shorter parts.');}
   });return;}catch(error){if(!r.active||r.generation!==generation)return;r.capture=null;
    if(['NotAllowedError','NotFoundError'].includes(error.name)){r.blocked=true;r.callbacks.onError('Microphone permission or device unavailable. You can still type.');return;}
    r.forceBrowser=true;r.callbacks.onError('Audio capture unavailable; using browser speech fallback.');
   }
  }
  const R=BrowserRecognition;
  if(!R){r.blocked=true;debug('recognition unavailable',{lastRecognitionError:'recognition-unavailable'});r.callbacks.onError('Browser speech recognition is unavailable and backend speech is not ready. You can still type.');return;}
  let rec;
  try{rec=new R();}catch{r.blocked=true;r.callbacks.onError('Browser speech recognition could not initialize. Please retry.');return;}
  r.recognition=rec;rec.lang=r.config.language||'en-IN';rec.interimResults=true;rec.continuous=false;rec.maxAlternatives=3;
  const capabilities={recognitionSupported:true,phraseBiasSupported:false,interimResultsSupported:'interimResults' in rec,continuousSupported:'continuous' in rec};
  try{capabilities.phraseBiasSupported=!r.phraseBiasDisabled&&typeof window.SpeechRecognitionPhrase==='function'&&'phrases' in rec;}catch{}
  setSpeechCapabilities(capabilities);
  // Compatibility default: no experimental phrases, even if Chrome exposes the property.
  if(r.config.browser_phrase_bias===true&&capabilities.phraseBiasSupported){try{rec.phrases=(r.config.phrases||[]).map(p=>new window.SpeechRecognitionPhrase(p,3));}catch{
   r.phraseBiasDisabled=true;setSpeechCapabilities(v=>({...v,phraseBiasSupported:false}));r.recognition=null;try{rec.abort();}catch{};listen(false);return;
  }}
  const start=performance.now();let delivered=false;
  const valid=()=>r.active&&r.generation===generation&&r.recognition===rec;
  const release=()=>{r.recognition=null;rec.onend=rec.onerror=rec.onresult=rec.onstart=rec.onspeechstart=rec.onspeechend=rec.onaudiostart=rec.onaudioend=null;try{rec.abort();}catch{};setListening(false);debug('recognition ended',{recognitionActive:false,audioStreamActive:false});};
  const failure=error=>{
   if(!valid())return;
   debug('recognition error: '+error,{lastRecognitionError:error});
   if(error==='phrases-not-supported'){
    r.phraseBiasDisabled=true;setSpeechCapabilities(v=>({...v,phraseBiasSupported:false}));release();r.restarts=0;
    console.warn('[VOICE] Phrase bias unsupported; continuing with standard SpeechRecognition.');
    r.restartTimer=setTimeout(()=>{r.restartTimer=null;if(r.active&&r.generation===generation&&!r.processing&&!r.aiSpeaking)listen(false);},300);return;
   }
   if(error==='not-allowed'){r.blocked=true;debug('microphone permission denied',{microphonePermission:'DENIED'});r.callbacks.onError('Microphone permission is required for voice mode.');}
   else if(error==='audio-capture'){r.blocked=true;r.callbacks.onError('Microphone device is unavailable. Check its connection and permissions.');}
   else if(error==='service-not-allowed'){
    if(canUseBackend){r.forceBackend=true;r.callbacks.onError('Browser speech service unavailable; switching to configured backend speech.');}
    else{r.blocked=true;r.callbacks.onError('Browser speech service is unavailable. Check browser settings and retry.');}
   }else if(error==='network'){
    r.networkErrors=(r.networkErrors||0)+1;
    if(r.networkErrors>=2&&canUseBackend)r.forceBackend=true;
    r.callbacks.onError('Speech connection interrupted. Retrying recognition.');
   }
   release();r.restarts++;schedule();
  };
  rec.onstart=()=>{if(!valid())return;setListening(true);setCaptureState('LISTENING');debug('recognition started',{recognitionActive:true,speechDetected:false,interimTranscript:'',provider:'browser-web-speech'});r.callbacks.onState('LISTENING');};
  rec.onaudiostart=()=>{if(valid())debug('microphone audio started',{microphonePermission:'GRANTED',audioStreamActive:true});};
  rec.onaudioend=()=>{if(valid())debug('microphone audio ended',{audioStreamActive:false});};
  rec.onspeechstart=()=>{if(valid()){setCaptureState('CUSTOMER_SPEAKING');debug('speech detected',{speechDetected:true});r.callbacks.onState('CUSTOMER_SPEAKING');}};
  rec.onspeechend=()=>{if(valid()){setCaptureState('FINALIZING_UTTERANCE');r.callbacks.onState('FINALIZING_UTTERANCE');}};
  rec.onresult=e=>{
   if(!valid()||r.processing||r.aiSpeaking||delivered)return;
   const results=Array.from(e.results),finals=results.filter(x=>x.isFinal),text=results.map(x=>x[0].transcript).join(' ').trim();
   setInterim(text);debug('transcript received',{interimTranscript:maskVoiceText(text),speechDetected:!!text});
   const final=finals.map(x=>x[0].transcript).join(' ').trim();
   if(!final)return;
   delivered=true;r.restarts=0;r.networkErrors=0;
   // Browser compatibility: an exact zero on a final is not a usable confidence signal.
   // Preserve the reported value in diagnostics; never invent a positive score.
   const reportedConfidence=finals.every(x=>Number.isFinite(x[0].confidence))?Math.min(...finals.map(x=>x[0].confidence)):null;
   const confidence=reportedConfidence>0&&reportedConfidence<=1?reportedConfidence:null;
   const alternatives=finals.length===1?Array.from(finals[0]).slice(1,4).map(x=>({text:x.transcript,confidence:Number.isFinite(x.confidence)&&x.confidence>0&&x.confidence<=1?x.confidence:null})):[];
   debug('final transcript submitted',{finalTranscript:maskVoiceText(final),reportedConfidence,confidenceUsed:confidence,confidenceStatus:confidence===null?'UNAVAILABLE':'REPORTED',lastRecognitionError:null});
   processing();Promise.resolve(r.callbacks.onFinal(final,'voice',performance.now()-start,{confidence,alternatives})).catch(()=>resume());
  };
  rec.onerror=e=>failure(e.error);
  rec.onend=()=>{if(!valid())return;release();r.restarts++;schedule();};
  debug('SpeechRecognition initialized');
  try{rec.start();}catch(error){failure(['NotAllowedError','SecurityError'].includes(error.name)?'not-allowed':error.name==='NotFoundError'?'audio-capture':'network');}
 }

 function useBrowserFallback(){refs.current.forceBrowser=true;refs.current.capture?.close();refs.current.capture=null;}
 function speak(text,{autolisten,onStart=()=>{},enabled=true}={}){
  const r=refs.current;if(!r.active)return;
  cancel();r.processing=false;if(autolisten!==undefined)r.autoListen=autolisten;
  const generation=r.generation;
  const valid=()=>r.active&&r.generation===generation;
  const finish=()=>{if(!valid())return;r.utterance=null;r.aiSpeaking=false;setSpeaking(false);r.callbacks.onState('WAITING');schedule();};
  if(!enabled||!window.speechSynthesis){finish();return;}
  const u=new SpeechSynthesisUtterance(text);r.utterance=u;r.aiSpeaking=true;u.lang='en-IN';u.rate=1;const start=performance.now();
  u.onstart=()=>{if(!valid())return;setSpeaking(true);r.callbacks.onState('SPEAKING');onStart(performance.now()-start);};
  u.onend=finish;
  u.onerror=()=>{if(valid()){r.callbacks.onError('Speech playback failed. The call remains active.');finish();}};
  try{window.speechSynthesis.speak(u);}catch{finish();}
 }
 useEffect(()=>()=>endSession(),[]);
 return {listen,speak,cancel,setSession,endSession,processing,resume,useBrowserFallback,diagnostics,speechCapabilities,captureState,listening,speaking,interim,supported};
}
