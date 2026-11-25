import {useEffect,useRef,useState} from 'react'
import {Link,Route,Routes,Navigate,useLocation} from 'react-router-dom'
import {api,Login} from './auth'
import Settings,{defaults,type Preferences} from './pages/Settings'
import Resources from './pages/Resources'
import Qoder from './pages/Qoder'
import Chat from './pages/Chat'
import Work from './pages/Work'
import Graph from './pages/Graph'
import DocWork from './pages/DocWork'
import Intake from './pages/Intake'
import Tasks from './pages/Tasks'
import DocumentPrint from './pages/DocumentPrint'
import Studio from './pages/Studio'
import Checkin from './pages/Checkin'
import Cover from './pages/Cover'
import VideoWork from './pages/VideoWork'
import ModuleHub from './pages/ModuleHub'
import ProjectHub from './pages/ProjectHub'
import Sidebar from './components/Sidebar'
import {Icon,BrandMark} from './components/Icon'
import {modules,workspaceGroups,type Module} from './navigation'

function Pending({module}:{module:Module}){
 return <><div className="page-heading"><h1>{module.name}</h1><p className="muted">{module.desc}</p></div><section className="panel planned"><span className="soft-icon"><Icon name={module.icon} size={28}/></span><h2>此模块尚未迁移</h2><p>功能将按照旧系统的业务流程逐步接入，目前不可使用。</p><Link className="button-link" to={module.path==='/chat'?'/qoder':'/'}>{module.path==='/chat'?'管理 AI 账号':'返回首页'}</Link></section></>
}
function initialCollapsed(){try{return localStorage.getItem('wg-sidebar-collapsed')==='true'}catch{return false}}
export default function App(){
 const [preferences,setPreferences]=useState<Preferences>(defaults)
 const [menu,setMenu]=useState(false),[collapsed,setCollapsed]=useState(initialCollapsed),[more,setMore]=useState(false)
 const moreRef=useRef<HTMLDivElement>(null)
 const [health,setHealth]=useState('检查中')
 const [user,setUser]=useState<string|null|undefined>(undefined)
 const [error,setError]=useState('')
 const location=useLocation(),mainRef=useRef<HTMLElement>(null)
 const current=modules.find(m=>m.path===location.pathname)
 const project=workspaceGroups.find(g=>location.pathname==='/project/'+g.id)
 const isChat=location.pathname==='/'||location.pathname==='/chat'
 const isWork=location.pathname==='/work'||location.pathname==='/intelligence', workHome=isWork&&!new URLSearchParams(location.search).has('job')&&!new URLSearchParams(location.search).has('history'), modeHome=isChat||isWork
 const lastChat=useRef('/')
 useEffect(()=>{if(isChat)lastChat.current=location.pathname+location.search},[isChat,location.pathname,location.search])
 function allowMode(path:string){return window.dispatchEvent(new CustomEvent('wg-chat-navigation',{cancelable:true,detail:{path}}))}
 const isDoc=(location.pathname==='/intake'&&new URLSearchParams(location.search).has('doc'))||['/papers','/handouts','/textbooks'].includes(location.pathname)
 useEffect(()=>{const history=location.pathname==='/chat'&&new URLSearchParams(location.search).has('history');setMenu(history&&window.matchMedia('(max-width: 760px)').matches);if(history)setCollapsed(false);mainRef.current?.scrollTo(0,0)},[location.pathname,location.search])
 useEffect(()=>{setMore(false)},[location.pathname,location.search])
 useEffect(()=>{const close=(e:KeyboardEvent)=>{if(e.key==='Escape'){setMenu(false);setMore(false)}};const outside=(e:PointerEvent)=>{if(!moreRef.current?.contains(e.target as Node))setMore(false)};window.addEventListener('keydown',close);document.addEventListener('pointerdown',outside);return()=>{window.removeEventListener('keydown',close);document.removeEventListener('pointerdown',outside)}},[])
 useEffect(()=>{try{localStorage.setItem('wg-sidebar-collapsed',String(collapsed))}catch{}},[collapsed])
 useEffect(()=>{const c=new AbortController();fetch('/api/auth/me',{signal:c.signal}).then(async r=>{if(r.status===401)return setUser(null);if(!r.ok)throw new Error('认证服务异常');const data=await r.json();if(!c.signal.aborted)setUser(data.username)}).catch(()=>{if(!c.signal.aborted){setError('无法连接认证服务，请检查服务器配置');setUser(null)}});fetch('/api/ready',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setHealth(r.ok?'服务已连接':'服务未就绪')}).catch(()=>{if(!c.signal.aborted)setHealth('服务未连接')});return()=>c.abort()},[])
 useEffect(()=>{if(!user)return;const c=new AbortController();api<Preferences>('/settings',{signal:c.signal}).then(p=>{if(!c.signal.aborted)setPreferences(p)}).catch(()=>{});return()=>c.abort()},[user])
 useEffect(()=>{const media=window.matchMedia('(prefers-color-scheme: dark)');const apply=()=>{document.documentElement.dataset.theme=preferences.theme==='system'?(media.matches?'dark':'light'):preferences.theme};apply();media.addEventListener('change',apply);return()=>media.removeEventListener('change',apply)},[preferences.theme])
 async function logout(){try{await api('/auth/logout',{method:'POST'});setUser(null);try{for(const k of Object.keys(sessionStorage))if(k.startsWith('wg-doc-recovery:'))sessionStorage.removeItem(k)}catch{}setPreferences(defaults);setMenu(false);setError('')}catch(e){setError(e instanceof Error?e.message:'退出失败')}}
 if(user===undefined)return <div className="login-page"><div className="loading-brand"><BrandMark/><p>正在连接教研工作台…</p></div></div>
 if(user===null)return <><Login onLogin={name=>{setUser(name);setError('')}}/>{error&&<p className="auth-error" role="alert">{error}</p>}</>
 return <div className={'shell legacy-shell'+(collapsed?' is-collapsed':'')+' clean-workspace'+(isChat||workHome?' chat-route':'')+(modeHome?' mode-home':'')+(isDoc?' doc-route':'')}>
  {menu&&<button className="nav-backdrop" aria-label="关闭导航" onClick={()=>setMenu(false)}/>}
  <Sidebar user={user} displayName={preferences.display_name} open={menu} collapsed={collapsed} onClose={()=>setMenu(false)} onToggle={()=>setCollapsed(c=>!c)} onLogout={()=>void logout()}/>
  <div className="workspace">
   <header className={'topbar clean-topbar'+(modeHome?' mode-topbar':'')}><div className="mode-left"><button className="icon-button menu" aria-label="打开导航" aria-expanded={menu} aria-controls="workspace-navigation" onClick={()=>setMenu(!menu)}><Icon name="menu"/></button>{collapsed&&<button className="icon-button desktop-expand" aria-label="展开主导航" onClick={()=>setCollapsed(false)}><Icon name="sidebar"/></button>}</div>{modeHome?<nav className="mode-switch" aria-label="工作模式"><Link to={isChat?location.pathname+location.search:lastChat.current} aria-current={isChat?'page':undefined}>聊天</Link><Link to="/work" aria-current={isWork?'page':undefined} onClick={e=>{if(isChat&&!allowMode('/work'))e.preventDefault()}}>工作</Link></nav>:<div className="breadcrumb"><strong>{project?.name??current?.name??(location.pathname==='/intake-single'?'单条录入':'工作空间')}</strong></div>}<div className="topbar-actions">{modeHome&&<div className="mode-more" ref={moreRef}><button type="button" className="icon-button mode-more-trigger" aria-label="更多选项" aria-expanded={more} aria-controls="mode-more-panel" onClick={()=>setMore(v=>!v)}><Icon name="more" size={24}/></button><div id="mode-more-panel" className="mode-more-panel" hidden={!more}><Link to="/qoder" onClick={e=>{if(!allowMode('/qoder'))e.preventDefault();else setMore(false)}}><Icon name="spark" size={19}/>AI 登录与模型</Link>{isChat?<><button type="button" onClick={()=>{setMore(false);window.dispatchEvent(new Event('wg-chat-new'))}}><Icon name="plus" size={19}/>新建对话</button><div id="chat-session-actions" className="chat-session-actions" onClick={()=>setMore(false)}/></>:<Link to="/tasks" onClick={e=>{if(!allowMode('/tasks'))e.preventDefault();else setMore(false)}}><Icon name="clock" size={19}/>任务中心</Link>}</div></div>}{health!=='服务已连接'&&<span className="health" role="status" title={health}><span className="status-dot offline"/><span>{health}</span></span>}</div></header>
   <main className="main-content" ref={mainRef}><div className="content-inner">{error&&<p className="inline-error" role="alert">{error}</p>}<Routes>
    <Route path="/" element={<Chat key="home"/>}/>
    <Route path="/overview" element={<Navigate to="/" replace/>}/>
    <Route path="/library" element={<Navigate to="/project/teaching" replace/>}/>
    <Route path="/create" element={<Navigate to="/project/creation" replace/>}/>
    <Route path="/operations" element={<Navigate to="/project/publishing" replace/>}/>
    {["/drawing","/formulas","/files","/assets","/media","/slides"].map(path=><Route key={path} path={path} element={<Navigate to="/project/teaching" replace/>}/>)}
    <Route path="/research" element={<Navigate to="/intake" replace/>}/>
    <Route path="/work" element={<Work/>}/>
    <Route path="/publishing" element={<Navigate to="/project/publishing" replace/>}/>
    <Route path="/analytics" element={<Navigate to="/project/publishing" replace/>}/>
    <Route path="/project/:id" element={<ProjectHub/>}/>
    {modules.slice(1).map(m=><Route key={m.path} path={m.path} element={m.path==='/products'?<ModuleHub key={m.path} path={m.path}/>:m.path==='/videos'?<VideoWork/>:m.path==='/knowledge-library'?<Resources key="knowledge-library" initialKind="knowledge"/>:m.path==='/covers'?<Cover/>:m.path==='/works'?<Studio key="works" kind="work"/>:m.path==='/checkin'?<Checkin/>:m.path==='/papers'?<DocWork key="paper" docKind="paper"/>:m.path==='/handouts'?<DocWork key="handout" docKind="handout"/>:m.path==='/textbooks'?<DocWork key="textbook" docKind="textbook"/>:m.path==='/tasks'?<Tasks/>:m.path==='/intelligence'?<Navigate to={'/work'+location.search} state={location.state} replace/>:m.path==='/graph'?<Graph/>:m.path==='/chat'?<Chat/>:m.path==='/intake'?<Intake/>:m.path==='/resources'?<Resources key="library"/>:m.path==='/sources'?<Resources key="sources" initialKind="source"/>:m.path==='/qoder'?<Qoder/>:m.path==='/settings'?<><div className="page-heading"><h1>系统设置</h1><p className="muted">{m.desc}</p></div><Settings preferences={preferences} onChange={setPreferences}/></>:<Pending module={m}/>}/>)}
    <Route path="/print/:id" element={<DocumentPrint/>}/>
    <Route path="/source-print/:id" element={<DocumentPrint source/>}/>
    <Route path="/intake-single" element={<Resources key="intake-single" intake/>}/>
    <Route path="*" element={<section className="panel planned"><h1>页面不存在</h1><Link to="/" className="text-link">返回首页</Link></section>}/>
   </Routes></div></main>
  </div>

 </div>
}
