import React,{useCallback,useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity,LayoutDashboard,PhoneCall,History,Users,BarChart3,BookOpen,FlaskConical,Settings,ShieldCheck,ChevronRight,X,Menu,LibraryBig,ContactRound,ShieldAlert} from 'lucide-react';
import Workspace from './pages/Workspace';
import {History as LegacyHistory} from './pages/Dashboards';
import LiveCalls,{CallHistory} from './pages/Calls';
import {KnowledgeManager,IntentLibrary,Customers,Security} from './pages/Management';
import {OperationsOverview,OperationsAnalytics,AgentQueue,EvaluationLab,OperationsSettings} from './pages/Operations';
import {api} from './services/api';
import './styles.css';
import './operations.css';
const navigation=[['Overview',LayoutDashboard],['Live Calls',PhoneCall],['Call History',History],['Escalations',ShieldAlert],['Agent Queue',Users],['Customers (Demo)',ContactRound],['Knowledge Base',BookOpen],['Intent Library',LibraryBig],['Analytics',BarChart3],['Evaluation',FlaskConical],['Security Events',ShieldCheck],['Settings',Settings]];
class ErrorBoundary extends React.Component{state={error:false};static getDerivedStateFromError(){return {error:true};}render(){return this.state.error?<div className="empty"><h2>This view could not load.</h2><button className="button" onClick={()=>location.reload()}>Reload workspace</button></div>:this.props.children;}}
function App(){
 const [page,setPage]=useState('Overview'),[config,setConfig]=useState(null),[online,setOnline]=useState(false),[toast,setToast]=useState(''),[menu,setMenu]=useState(false),[callsVisited,setCallsVisited]=useState(false);
 const notify=useCallback(message=>setToast(message),[]);
 useEffect(()=>{const load=()=>api('/config').then(c=>{setConfig(c);setOnline(true);}).catch(()=>setOnline(false));load();const timer=setInterval(load,15000);return()=>clearInterval(timer);},[]);
 useEffect(()=>{if(!toast)return;const timer=setTimeout(()=>setToast(''),7000);return()=>clearTimeout(timer);},[toast]);
 function navigate(next){if(next==='Live Calls')setCallsVisited(true);setPage(next);setMenu(false);window.scrollTo({top:0});}
 const views={
 'Overview':<OperationsOverview notify={notify} navigate={navigate} config={config}/>,
 'Call History':<CallHistory notify={notify} onLegacy={()=>navigate('Legacy Conversations')}/>,
 'Escalations':<AgentQueue key="escalations" notify={notify}/>,
 'Agent Queue':<AgentQueue key="queue" queueOnly notify={notify}/>,
 'Customers (Demo)':<Customers notify={notify}/>,
 'Knowledge Base':<KnowledgeManager notify={notify}/>,
 'Intent Library':<IntentLibrary notify={notify}/>,
 'Analytics':<OperationsAnalytics notify={notify} navigate={navigate}/>,
 'Evaluation':<EvaluationLab notify={notify}/>,
 'Security Events':<Security notify={notify}/>,
 'Settings':<OperationsSettings config={config} notify={notify} onTextTools={()=>navigate('Legacy Text Workspace')}/>,
 'Legacy Text Workspace':<Workspace notify={notify} config={config}/>,
 'Legacy Conversations':<LegacyHistory notify={notify}/>
 };
 return <div className="app operations-app"><aside className={`sidebar ${menu?'open':''}`}><a className="brand" href="#" onClick={e=>{e.preventDefault();navigate('Overview');}}><div className="brand-mark"><Activity size={24}/></div><span>call<span>sense</span><small>BANK OPERATIONS</small></span></a><div className="workspace-label">BANK SUPPORT PLATFORM</div><nav>{navigation.map(([name,Icon],i)=><React.Fragment key={name}>{i===6&&<div className="nav-divider">INTELLIGENCE & CONTROLS</div>}<button className={page===name?'active':''} onClick={()=>navigate(name)}><Icon size={17}/><span>{name}</span>{page===name&&<ChevronRight size={13}/>}</button></React.Fragment>)}</nav><div className="sidebar-bottom"><div className="profile"><div className="avatar">CS</div><div><strong>Bank operations team</strong><small>Fictional institution · Demo operator</small></div></div></div></aside><div className="main-shell"><header className="topbar"><button className="icon-button mobile-menu" aria-label="Toggle navigation" onClick={()=>setMenu(v=>!v)}><Menu size={20}/></button><div className="breadcrumb">Operations <ChevronRight size={14}/><b>{page}</b></div><div className="topbar-right"><span className={`connection ${online?'online':''}`}><i/>{online?'Backend connected':'Backend unavailable'}</span><span className="mode-pill">{config?.telephony?.real_phone_configured?'PHONE GATEWAY':'MOCK GATEWAY'}</span><div className="avatar small">CS</div></div></header><main><ErrorBoundary>{!online&&<div className="offline-banner">Backend unavailable or an operations token is required. Start FastAPI on port 8000, or configure your token in Settings.</div>}{callsVisited&&<div hidden={page!=='Live Calls'}><LiveCalls notify={notify} config={config}/></div>}{page!=='Live Calls'&&views[page]}</ErrorBoundary></main><footer>CALL SENSE <span>Customer calls. Bank teams stay in control.</span><span>Research prototype · Synthetic bank data</span></footer></div>{toast&&<div className="toast" role="status"><ShieldCheck size={19}/><span>{toast}</span><button className="icon-button" aria-label="Dismiss notification" onClick={()=>setToast('')}><X size={16}/></button></div>}</div>;
}
createRoot(document.getElementById('root')).render(<App/>);

