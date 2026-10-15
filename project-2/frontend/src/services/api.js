export async function api(path,options={}){
 const response=await fetch(`/api${path}`,{credentials:'same-origin',...options,headers:{'Content-Type':'application/json',...options.headers}});
 if(!response.ok){let data;try{data=await response.json();}catch{}throw new Error(typeof data?.detail==='string'?data.detail:`Request failed (${response.status}). Check the backend and input.`);}
 return response.json();
}
export const post=(path,body)=>api(path,{method:'POST',body:body===undefined?undefined:JSON.stringify(body)});
export const patch=(path,body)=>api(path,{method:'PATCH',body:JSON.stringify(body)});
export const put=(path,body)=>api(path,{method:'PUT',body:JSON.stringify(body)});
export function socket(path){return new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api${path}`,['callsense']);}

