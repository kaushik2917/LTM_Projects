// Frame-level utterance detection. This class has no call termination capability.
export class PcmTurnDetector {
 constructor(rate,config={}){this.rate=rate;this.c={end_silence_ms:1200,pre_roll_ms:300,post_roll_ms:300,start_ms:150,max_seconds:60,threshold:500/32768,...config};this.reset();}
 reset(){this.pre=[];this.frames=[];this.preSize=0;this.size=0;this.voice=0;this.silence=0;this.started=false;this.overflow=false;}
 feed(frame){
  const ms=frame.length/this.rate*1000;const rms=Math.sqrt(frame.reduce((s,x)=>s+x*x,0)/frame.length);const voice=rms>=this.c.threshold;
  let state=voice?'CUSTOMER_SPEAKING':'FINALIZING_UTTERANCE';
  if(!this.started){
   this.pre.push(frame);this.preSize+=frame.length;
   const limit=(this.c.pre_roll_ms+this.c.start_ms)*this.rate/1000;
   while(this.pre.length&&this.preSize-this.pre[0].length>=limit)this.preSize-=this.pre.shift().length;
   this.voice=voice?this.voice+ms:0;
   if(this.voice<this.c.start_ms)return {state:'LISTENING'};
   this.started=true;this.frames=this.pre;this.size=this.preSize;this.pre=[];this.preSize=0;
  }else if(!this.overflow){this.frames.push(frame);this.size+=frame.length;}
  this.silence=voice?0:this.silence+ms;
  if(this.size>this.c.max_seconds*this.rate){this.overflow=true;this.frames=[];this.size=0;}
  if(this.silence<this.c.end_silence_ms)return {state};
  if(this.overflow){this.reset();return {state:'UTTERANCE_TOO_LONG'};}
  const keep=Math.max(0,this.size-Math.floor(Math.max(0,this.silence-this.c.post_roll_ms)*this.rate/1000));
  const audio=new Float32Array(keep);let offset=0;
  for(const part of this.frames){const n=Math.min(part.length,keep-offset);if(n<=0)break;audio.set(part.subarray(0,n),offset);offset+=n;}
  this.reset();return {state:'UTTERANCE_COMPLETE',audio};
 }
}
export function pcmWav(samples,rate){
 const n=Math.floor(samples.length*16000/rate),buffer=new ArrayBuffer(44+n*2),view=new DataView(buffer);
 const text=(offset,s)=>[...s].forEach((c,i)=>view.setUint8(offset+i,c.charCodeAt(0)));
 text(0,'RIFF');view.setUint32(4,36+n*2,true);text(8,'WAVE');text(12,'fmt ');view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,n*2,true);
 for(let i=0;i<n;i++){const from=i*rate/16000,to=(i+1)*rate/16000;let sum=0,weight=0;
  for(let j=Math.floor(from);j<Math.ceil(to)&&j<samples.length;j++){const w=Math.min(j+1,to)-Math.max(j,from);sum+=samples[j]*w;weight+=w;}
  const x=Math.max(-1,Math.min(1,sum/weight));view.setInt16(44+i*2,Math.round(x*(x<0?32768:32767)),true);
 }
 return new Blob([buffer],{type:'audio/wav'});
}

export class PcmCapture {
 constructor(config){this.config=config;this.closed=false;this.enabled=false;this.version=0;}
 async initialize(){
  const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,sampleRate:16000,echoCancellation:this.config.echoCancellation!==false,noiseSuppression:this.config.noiseSuppression!==false,autoGainControl:this.config.autoGainControl!==false}});
  if(this.closed){stream.getTracks().forEach(t=>t.stop());return;}
  this.stream=stream;this.context=new AudioContext({sampleRate:16000});
  await this.context.audioWorklet.addModule('/audio-capture-worklet.js');
  if(this.closed){await this.close();return;}
  this.detector=new PcmTurnDetector(this.context.sampleRate,this.config);
  this.node=new AudioWorkletNode(this.context,'call-sense-capture');this.source=this.context.createMediaStreamSource(stream);
  this.source.connect(this.node);this.node.connect(this.context.destination);
  this.node.port.onmessage=event=>{
   if(!this.enabled||this.closed)return;const result=this.detector.feed(event.data);
   if(result.state!==this.lastState){this.lastState=result.state;this.callbacks?.onState(result.state);}
   if(result.audio){this.pause();this.callbacks?.onAudio(pcmWav(result.audio,this.context.sampleRate));}
   if(result.state==='UTTERANCE_TOO_LONG'){this.pause();this.callbacks?.onTooLong();}
  };
 }
 async start(callbacks){
  const version=++this.version;this.callbacks=callbacks;
  try{if(!this.ready)this.ready=this.initialize();await this.ready;
   if(this.closed||version!==this.version)return;
   await this.context.resume();this.detector.reset();this.enabled=true;this.lastState='LISTENING';callbacks.onState('LISTENING');
  }catch(error){await this.close();throw error;}
 }
 pause(){this.enabled=false;this.version++;this.detector?.reset();}
 async close(){
  this.closed=true;this.pause();this.stream?.getTracks().forEach(t=>t.stop());this.source?.disconnect();this.node?.disconnect();
  if(this.node){this.node.port.onmessage=null;this.node.port.close();}
  if(this.context&&this.context.state!=='closed')await this.context.close().catch(()=>{});
 }
}
