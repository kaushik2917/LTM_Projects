import {useEffect,useRef,useState} from 'react';
import {useCallAudio} from '../hooks/useCallAudio';
export function VoiceStatus({diagnostics}){
 return <dl>{Object.entries(diagnostics).map(([key,value])=><div className="security-count" key={key}><dt>{key}</dt><dd style={{overflowWrap:'anywhere'}}>{typeof value==='boolean'?(value?'YES':'NO'):value||'—'}</dd></div>)}</dl>;
}
export function MicrophoneSelfTest({disabled=false}){
 const [running,setRunning]=useState(false),[permission,setPermission]=useState('UNKNOWN'),[level,setLevel]=useState(0),[error,setError]=useState('');
 const resource=useRef({version:0}),audioRef=useRef();
 const audio=useCallAudio({config:{language:'en-IN',browser_phrase_bias:false,audio_available:false},onState:()=>{},onError:setError,onFinal:()=>audioRef.current.resume()});audioRef.current=audio;
 function cleanup(){const r=resource.current;r.version++;clearInterval(r.timer);r.stream?.getTracks().forEach(t=>t.stop());r.stream=null;r.source?.disconnect();r.context?.close().catch(()=>{});r.context=null;audioRef.current.endSession();}
 function stop(){cleanup();setRunning(false);setLevel(0);setPermission(v=>v==='REQUESTING'?'UNKNOWN':v);}
 async function start(){
  stop();const r=resource.current,version=r.version;setError('');setPermission('REQUESTING');
  try{
   if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone access requires a supported browser on localhost or HTTPS.');
   const stream=await navigator.mediaDevices.getUserMedia({audio:true});
   if(r.version!==version){stream.getTracks().forEach(t=>t.stop());return;}
   r.stream=stream;setPermission('GRANTED');setRunning(true);
   const Context=window.AudioContext||window.webkitAudioContext;
   if(Context){r.context=new Context();await r.context.resume();if(r.version!==version)return;
    const analyser=r.context.createAnalyser();analyser.fftSize=256;r.source=r.context.createMediaStreamSource(stream);r.source.connect(analyser);
    const data=new Float32Array(analyser.fftSize);r.timer=setInterval(()=>{analyser.getFloatTimeDomainData(data);setLevel(Math.sqrt(data.reduce((sum,x)=>sum+x*x,0)/data.length));},100);
   }
   audioRef.current.setSession('diagnostic-'+crypto.randomUUID(),true);audioRef.current.listen(true,true);
  }catch(e){if(r.version!==version)return;stop();setPermission(e.name==='NotAllowedError'?'DENIED':'UNAVAILABLE');setError(e.name==='NotAllowedError'?'Microphone permission is required for voice mode.':e.message);}
 }
 useEffect(()=>()=>cleanup(),[]);
 useEffect(()=>{if(disabled)stop();},[disabled]);
 return <section><h4>Microphone self-test</h4><p>End the active call first. Say “Hello Call Sense”. This test displays masked transcripts locally and never sends them to the banking pipeline.</p>
 <button className="button secondary" onClick={start} disabled={disabled||running}>Test microphone</button> <button className="button secondary" onClick={stop} disabled={!running&&permission!=='REQUESTING'}>Stop microphone test</button>
 <p>Microphone permission: {permission}. Audio stream: {running?'ACTIVE':'INACTIVE'}. Audio level: {level.toFixed(4)}.</p><meter aria-label="Microphone audio level" min="0" max="0.3" value={level}/>
 <p role="status">{error}</p><VoiceStatus diagnostics={audio.diagnostics}/></section>;
}
