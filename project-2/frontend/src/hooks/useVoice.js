import { useEffect,useRef,useState } from 'react';
import { patch } from '../services/api';
export function useVoice({onTranscript,onError,enabled}) {
  const recognition=useRef(null), start=useRef(0), callback=useRef(onTranscript), errors=useRef(onError);
  callback.current=onTranscript; errors.current=onError;
  const [listening,setListening]=useState(false),[interim,setInterim]=useState(''),[speaking,setSpeaking]=useState(false);
  const supported=!!(window.SpeechRecognition || window.webkitSpeechRecognition);
  function stop(){recognition.current?.abort();setListening(false);window.speechSynthesis?.cancel();setSpeaking(false);setInterim('');}
  function listen(){
    const Recognition=window.SpeechRecognition || window.webkitSpeechRecognition;
    if(!Recognition){errors.current('Voice recognition is unavailable in this browser. Please type your question.');return;}
    if(listening){stop();return;}
    window.speechSynthesis?.cancel();
    const rec=new Recognition();recognition.current=rec;rec.lang='en-IN';rec.interimResults=true;rec.continuous=false;start.current=performance.now();
    rec.onstart=()=>{setListening(true);setInterim('Listening…');};
    rec.onresult=event=>{const result=event.results[event.results.length-1];setInterim(result[0].transcript);if(result.isFinal){callback.current(result[0].transcript,'voice',performance.now()-start.current);setInterim('');}};
    rec.onerror=event=>{if(event.error!=='aborted')errors.current(`Microphone: ${event.error}. You can continue using typed input.`);setListening(false);};
    rec.onend=()=>setListening(false);rec.start();
  }
  function speak(turn,manual=false){
    if((!enabled&&!manual)||!window.speechSynthesis||turn.speech?.enabled===false)return;
    window.speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(turn.answer);utterance.lang='en-IN';utterance.rate=.98;
    const requested=performance.now();
    utterance.onstart=()=>{setSpeaking(true);patch(`/turns/${turn.id}/voice-metric`,{tts_ms:performance.now()-requested}).catch(()=>{});};
    utterance.onend=()=>setSpeaking(false);utterance.onerror=()=>setSpeaking(false);window.speechSynthesis.speak(utterance);
  }
  useEffect(()=>()=>stop(),[]);
  return {listening,interim,speaking,supported,listen,stop,speak};
}
