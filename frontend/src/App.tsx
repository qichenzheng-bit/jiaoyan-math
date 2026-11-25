import {useEffect,useRef,useState} from 'react'
import {Link,Route,Routes,useLocation} from 'react-router-dom'
import {api,Login} from './auth'
import Settings,{defaults,type Preferences} from './pages/Settings'
import Files from './pages/Files'
import FormulaLab from './pages/FormulaLab'
import Resources from './pages/Resources'
import Qoder from './pages/Qoder'
import Chat from './pages/Chat'
import Graph from './pages/Graph'
import DocWork from './pages/DocWork'
import Intake from './pages/Intake'
import Intelligence from './pages/Intelligence'
import Tasks from './pages/Tasks'
import DocumentPrint from './pages/DocumentPrint'
import Studio from './pages/Studio'
import Analytics from './pages/Analytics'
import Checkin from './pages/Checkin'
import Cover from './pages/Cover'
import Drawing from './pages/Drawing'
import Home from './pages/Home'
import VideoWork from './pages/VideoWork'
import ModuleHub from './pages/ModuleHub'
import Sidebar from './components/Sidebar'
import {Icon,BrandMark} from './components/Icon'
import {modules,sectionFor,type Module} from './navigation'

function Pending({module}:{module:Module}){
 return <><div className="page-heading"><h1>{module.name}</h1><p className="muted">{module.desc}</p></div><section className="panel planned"><span className="soft-icon"><Icon name={module.icon} size={28}/></span><h2>此模块尚未迁移</h2><p>功能将按照旧系统的业务流程逐步接入，目前不可使用。</p><Link className="button-link" to={module.path==='/chat'?'/qoder':'/'}>{module.path==='/chat'?'管理 AI 账号':'返回首页'}</Link></section></>
}
function initialCollapsed(){try{return localStorage.getItem('wg-sidebar-collapsed')==='true'}catch{return false}}
export default function App(){
 const [preferences,setPreferences]=useState<Preferences>(defaults)
 const [menu,setMenu]=useState(false),[collapsed,setCollapsed]=useState(initialCollapsed)
 const [health,setHealth]=useState('检查中')
 const [user,setUser]=useState<string|null|undefined>(undefined)
 const [error,setError]=useState('')
 const location=useLocation(),mainRef=useRef<HTMLElement>(null)
 const current=modules.find(m=>m.path===location.pathname)
 const section=sectionFor(location.pathname)
 const isChat=location.pathname==='/'||location.pathname==='/chat'
 const isDoc=(location.pathname==='/intake'&&new URLSearchParams(location.search).has('doc'))||['/research','/papers','/handouts'].includes(location.pathname)
 useEffect(()=>{setMenu(false);mainRef.current?.scrollTo(0,0)},[location.pathname,location.search])
 useEffect(()=>{const close=(e:KeyboardEvent)=>{if(e.key==='Escape')setMenu(false)};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[])
 useEffect(()=>{try{localStorage.setItem('wg-sidebar-collapsed',String(collapsed))}catch{}},[collapsed])
 useEffect(()=>{const c=new AbortController();fetch('/api/auth/me',{signal:c.signal}).then(async r=>{if(r.status===401)return setUser(null);if(!r.ok)throw new Error('认证服务异常');const data=await r.json();if(!c.signal.aborted)setUser(data.username)}).catch(()=>{if(!c.signal.aborted){setError('无法连接认证服务，请检查服务器配置');setUser(null)}});fetch('/api/ready',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setHealth(r.ok?'服务已连接':'服务未就绪')}).catch(()=>{if(!c.signal.aborted)setHealth('服务未连接')});return()=>c.abort()},[])
 useEffect(()=>{if(!user)return;const c=new AbortController();api<Preferences>('/settings',{signal:c.signal}).then(p=>{if(!c.signal.aborted)setPreferences(p)}).catch(()=>{});return()=>c.abort()},[user])
 useEffect(()=>{const media=window.matchMedia('(prefers-color-scheme: dark)');const apply=()=>{document.documentElement.dataset.theme=preferences.theme==='system'?(media.matches?'dark':'light'):preferences.theme};apply();media.addEventListener('change',apply);return()=>media.removeEventListener('change',apply)},[preferences.theme])
 async function logout(){try{await api('/auth/logout',{method:'POST'});setUser(null);try{for(const k of Object.keys(sessionStorage))if(k.startsWith('wg-doc-recovery:'))sessionStorage.removeItem(k)}catch{}setPreferences(defaults);setMenu(false);setError('')}catch(e){setError(e instanceof Error?e.message:'退出失败')}}
 if(user===undefined)return <div className="login-page"><div className="loading-brand"><BrandMark/><p>正在连接教研工作台…</p></div></div>
 if(user===null)return <><Login onLogin={name=>{setUser(name);setError('')}}/>{error&&<p className="auth-error" role="alert">{error}</p>}</>
 return <div className={'shell legacy-shell'+(collapsed?' is-collapsed':'')+' clean-workspace'+(isChat?' chat-route':'')+(isDoc?' doc-route':'')}>
  {menu&&<button className="nav-backdrop" aria-label="关闭导航" onClick={()=>setMenu(false)}/>}
  <Sidebar user={user} displayName={preferences.display_name} open={menu} collapsed={collapsed} onClose={()=>setMenu(false)} onToggle={()=>setCollapsed(c=>!c)} onLogout={()=>void logout()}/>
  <div className="workspace">
   <header className="topbar clean-topbar"><button className="icon-button menu" aria-label="打开导航" aria-expanded={menu} aria-controls="workspace-navigation" onClick={()=>setMenu(!menu)}><Icon name="menu"/></button>{collapsed&&<button className="icon-button desktop-expand" aria-label="展开主导航" onClick={()=>setCollapsed(false)}><Icon name="sidebar"/></button>}<div className="breadcrumb"><strong>{isChat?'微光数学':current?.name??(location.pathname==='/intake-single'?'单条录入':location.pathname==='/overview'?'工作总览':'工作空间')}</strong></div><div className="topbar-actions">{!isChat&&section&&section.children.length>0&&<details key={location.pathname} className="clean-context-menu"><summary>模块工具 <Icon name="chevron" size={13}/></summary><div>{section.children.map(p=>{const m=modules.find(x=>x.path===p);return m?<Link key={p} to={p} onClick={e=>e.currentTarget.closest('details')?.removeAttribute('open')} aria-current={location.pathname===p?'page':undefined}>{m.name}</Link>:p==='/intake-single'?<Link key={p} to={p}>单条录入</Link>:null})}</div></details>}{health!=='服务已连接'&&<span className="health" role="status" title={health}><span className="status-dot offline"/><span>{health}</span></span>}<Link className="icon-button top-search" title="搜索题库" aria-label="搜索题库" to="/resources"><Icon name="search" size={20}/></Link>{isChat&&<Link className="icon-button" to="/chat?new=1" aria-label="新建对话" title="新建对话" onClick={e=>{e.preventDefault();window.dispatchEvent(new Event('wg-chat-new'))}}><Icon name="plus" size={20}/></Link>}</div></header>
   <main className="main-content" ref={mainRef}><div className="content-inner">{error&&<p className="inline-error" role="alert">{error}</p>}<Routes>
    <Route path="/" element={<Chat key="home"/>}/>
    <Route path="/overview" element={<Home/>}/>
    {modules.slice(1).map(m=><Route key={m.path} path={m.path} element={['/library','/create','/products','/operations'].includes(m.path)?<ModuleHub key={m.path} path={m.path}/>:m.path==='/videos'?<VideoWork/>:m.path==='/knowledge-library'?<Resources key="knowledge-library" initialKind="knowledge"/>:m.path==='/covers'?<Cover/>:m.path==='/drawing'?<Drawing/>:m.path==='/assets'?<Studio key="assets" kind="asset"/>:m.path==='/works'?<Studio key="works" kind="work"/>:m.path==='/media'?<Studio key="media" kind="work" category="article"/>:m.path==='/slides'?<Studio key="slides" kind="work" category="slides"/>:m.path==='/publishing'?<Studio key="publishing" kind="publication"/>:m.path==='/analytics'?<Analytics/>:m.path==='/checkin'?<Checkin/>:m.path==='/papers'?<DocWork key="paper" docKind="paper"/>:m.path==='/handouts'?<DocWork key="handout" docKind="handout"/>:m.path==='/tasks'?<Tasks/>:m.path==='/intelligence'?<Intelligence/>:m.path==='/graph'?<Graph/>:m.path==='/chat'?<Chat/>:m.path==='/research'?<DocWork key="research"/>:m.path==='/intake'?<Intake/>:m.path==='/resources'?<Resources key="library"/>:m.path==='/sources'?<Resources key="sources" initialKind="source"/>:m.path==='/qoder'?<Qoder/>:m.path==='/files'?<Files/>:m.path==='/formulas'?<FormulaLab/>:m.path==='/settings'?<><div className="page-heading"><h1>系统设置</h1><p className="muted">{m.desc}</p></div><Settings preferences={preferences} onChange={setPreferences}/></>:<Pending module={m}/>}/>)}
    <Route path="/print/:id" element={<DocumentPrint/>}/>
    <Route path="/intake-single" element={<Resources key="intake-single" intake/>}/>
    <Route path="*" element={<section className="panel planned"><h1>页面不存在</h1><Link to="/" className="text-link">返回首页</Link></section>}/>
   </Routes></div></main>
  </div>

 </div>
}
