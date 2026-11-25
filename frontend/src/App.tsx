import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, Link, useLocation } from 'react-router-dom'
import { api, Login } from './auth'
import Settings, {defaults,type Preferences} from './pages/Settings'
import Files from './pages/Files'
import FormulaLab from './pages/FormulaLab'
import { Icon, BrandMark } from './components/Icon'
import { MathFormula } from './components/MathFormula'

const modules = [
 {path:'/',name:'工作台',desc:'教研与创作入口',icon:'home',group:'overview'},
 {path:'/intake',name:'资源录入',desc:'手动录入、AI 辅助录入及批量导入',icon:'intake',group:'research'},
 {path:'/resources',name:'教学资源',desc:'统一教学资源库及关联体系',icon:'resources',group:'research'},
 {path:'/research',name:'教研创作',desc:'资源调用、数学编辑器及教研任务',icon:'research',group:'research'},
 {path:'/media',name:'多媒体制作',desc:'图文、绘图、文档、文章与课件',icon:'media',group:'production'},
 {path:'/works',name:'教学作品',desc:'作品归档及版本管理',icon:'works',group:'production'},
 {path:'/publishing',name:'自媒体运营',desc:'平台适配、发布管理及运营数据',icon:'publishing',group:'production'},
 {path:'/files',name:'文件管理',desc:'上传、预览、下载与归档',icon:'files',group:'tools'},
 {path:'/formulas',name:'公式预览',desc:'LaTeX 公式实时显示',icon:'formulas',group:'tools'},
 {path:'/settings',name:'系统设置',desc:'账号、主题、存储及系统信息',icon:'settings',group:'tools'},
] as const
const groups=[{id:'overview',label:'总览'},{id:'research',label:'教研空间'},{id:'production',label:'创作与运营'},{id:'tools',label:'基础工具'}]
type Module=typeof modules[number]
type Stats={count:number;bytes:number;max_file_bytes:number}
type FileItem={id:string;name:string;size_bytes:number}
type Audit={id:number;action:string;created_at:number}
const bytes=(n:number)=>n<1024?n+' B':n<1048576?(n/1024).toFixed(1)+' KB':(n/1048576).toFixed(1)+' MB'
function Home(){
 const [stats,setStats]=useState<Stats>()
 const [recent,setRecent]=useState<FileItem[]>([])
 const [audit,setAudit]=useState<Audit[]>([])
 const [error,setError]=useState(false)
 useEffect(()=>{const c=new AbortController();Promise.all([api<Stats>('/files/stats',{signal:c.signal}),api<{items:FileItem[]}>('/files?limit=4',{signal:c.signal}),api<Audit[]>('/settings/audit',{signal:c.signal})]).then(([s,f,a])=>{if(!c.signal.aborted){setStats(s);setRecent(f.items);setAudit(a.slice(0,4))}}).catch(()=>{if(!c.signal.aborted)setError(true)});return()=>c.abort()},[])
 return <div className="home">
  <section className="hero">
   <div className="hero-copy"><div className="eyebrow">WEIGUANG · MATH STUDIO</div><h1>让教研更有条理。</h1><p>集中管理数学资料、组织教学内容，<br className="desktop-break"/>从一个想法到一份作品。</p><div className="hero-actions"><Link className="primary button-link" to="/files"><Icon name="upload" size={18}/> 管理教学文件</Link><Link className="secondary button-link" to="/formulas">公式工作台 <Icon name="arrow" size={16}/></Link></div></div>
   <div className="hero-art" aria-hidden="true"><div className="graph-grid"/><svg viewBox="0 0 300 190" fill="none"><path d="M20 145h260M150 16v156" stroke="currentColor" opacity=".32"/><path d="M24 24C75 35 97 145 150 145S225 35 276 24" stroke="currentColor" strokeWidth="2.2"/><path d="M24 145 276 32" stroke="currentColor" strokeDasharray="5 6" opacity=".5"/><circle cx="150" cy="145" r="4" fill="currentColor"/></svg><div className="hero-math"><MathFormula latex="f(x)=x^2" display={false}/></div></div>
  </section>
  <div className="section-heading"><div><h2>工作概览</h2><p>你的教学资料与工作进展</p></div><span className="phase-label"><span className="status-dot"/> 基础工程阶段</span></div>
  <div className="metric-grid">
    <section className="metric"><div className="metric-label"><Icon name="files" size={18}/> 文件总数</div><strong>{stats?stats.count:'—'}</strong><span>包含已归档文件</span></section>
    <section className="metric"><div className="metric-label"><Icon name="resources" size={18}/> 文件占用</div><strong>{stats?bytes(stats.bytes):'—'}</strong><span>已存储的教学资料</span></section>
    <section className="metric"><div className="metric-label"><Icon name="shield" size={18}/> 存储上限</div><strong>{stats?bytes(stats.max_file_bytes):'—'}</strong><span>单个文件大小限制</span></section>
  </div>
  {error&&<p className="inline-error" role="alert">部分概览数据暂时无法读取。</p>}
  <div className="dashboard-grid">
   <section className="panel"><div className="panel-heading"><div><h2>最近文件</h2><p>继续整理最近上传的资料</p></div><Link className="text-link" to="/files">全部 <Icon name="chevron" size={15}/></Link></div>
    {recent.length? <div className="recent-list">{recent.map(f=><Link to="/files" className="recent-row" key={f.id}><span className="soft-icon"><Icon name="files"/></span><span className="recent-name"><strong>{f.name}</strong><small>{bytes(f.size_bytes)}</small></span><Icon name="chevron" size={16}/></Link>)}</div>:<div className="empty-state"><span className="soft-icon"><Icon name="files" size={24}/></span><strong>{stats?'还没有近期文件':'正在读取文件'}</strong><Link className="text-link" to="/files">前往文件管理 <Icon name="arrow" size={15}/></Link></div>}
   </section>
   <section className="panel"><div className="panel-heading"><div><h2>最近操作</h2><p>工作台活动记录</p></div><Link className="text-link" to="/settings">查看 <Icon name="chevron" size={15}/></Link></div>
    {audit.length?<div className="recent-list">{audit.map(a=><div className="recent-row" key={a.id}><span className="soft-icon"><Icon name="clock" size={17}/></span><span className="recent-name"><strong>{({ 'auth.login':'登录系统','auth.logout':'退出登录','auth.password_change':'修改密码','file.upload':'上传文件','file.archive':'归档文件','file.restore':'恢复文件','settings.update':'更新设置','admin.create':'创建管理员'} as Record<string,string>)[a.action]??a.action}</strong><small>{new Date(a.created_at*1000).toLocaleString()}</small></span></div>)}</div>:<div className="empty-state"><span className="soft-icon"><Icon name="clock" size={24}/></span><strong>暂无操作记录</strong></div>}
   </section>
  </div>
  <div className="section-heading"><div><h2>教研与创作</h2><p>完整工作流程，分阶段开放</p></div></div>
  <div className="workspace-grid">{modules.filter(m=>m.group==='research'||m.group==='production').map(m=><Link className="workspace-card" key={m.path} to={m.path}><span className="soft-icon"><Icon name={m.icon}/></span><span className="workspace-copy"><strong>{m.name}</strong><small>{m.desc}</small></span><Icon name="chevron" size={16}/></Link>)}</div>
 </div>
}
function PlannedPage({module}:{module:Module}){return <><div className="page-heading"><div><div className="eyebrow">教研工作台 / {module.name}</div><h1>{module.name}</h1><p className="muted">{module.desc}</p></div></div><section className="panel planned"><span className="soft-icon"><Icon name={module.icon} size={30}/></span><h2>{module.name}正在建设中</h2><p>该业务将在对应开发阶段开放。当前可以使用文件管理与公式预览。</p><Link to="/" className="button-link secondary">返回工作台 <Icon name="arrow" size={16}/></Link></section></>}
export default function App(){
 const [preferences,setPreferences]=useState<Preferences>(defaults)
 const [menu,setMenu]=useState(false),[assistant,setAssistant]=useState(false)
 const [health,setHealth]=useState('检查中')
 const [user,setUser]=useState<string|null|undefined>(undefined)
 const [error,setError]=useState('')
 const location=useLocation()
 const current=modules.find(m=>m.path===location.pathname)
 useEffect(()=>{setMenu(false)},[location.pathname])
 useEffect(()=>{const close=(e:KeyboardEvent)=>{if(e.key==='Escape'){setMenu(false);setAssistant(false)}};window.addEventListener('keydown',close);return()=>window.removeEventListener('keydown',close)},[])
 useEffect(()=>{const c=new AbortController();fetch('/api/auth/me',{signal:c.signal}).then(async r=>{if(r.status===401)return setUser(null);if(!r.ok)throw new Error('认证服务异常');const data=await r.json();setUser(data.username)}).catch(()=>{if(!c.signal.aborted){setError('无法连接认证服务，请检查服务器配置');setUser(null)}});fetch('/api/ready',{signal:c.signal}).then(r=>setHealth(r.ok?'服务已连接':'服务未就绪')).catch(()=>{if(!c.signal.aborted)setHealth('服务未连接')});return()=>c.abort()},[])
 useEffect(()=>{if(!user)return;const c=new AbortController();api<Preferences>('/settings',{signal:c.signal}).then(p=>{if(!c.signal.aborted)setPreferences(p)}).catch(()=>{});return()=>c.abort()},[user])
 useEffect(()=>{const media=window.matchMedia('(prefers-color-scheme: dark)');const apply=()=>{document.documentElement.dataset.theme=preferences.theme==='system'?(media.matches?'dark':'light'):preferences.theme};apply();media.addEventListener('change',apply);return()=>media.removeEventListener('change',apply)},[preferences.theme])
 async function logout(){try{await api('/auth/logout',{method:'POST'});setUser(null);setPreferences(defaults);setAssistant(false);setMenu(false);setError('')}catch(e){setError(e instanceof Error?e.message:'退出失败')}}
 if(user===undefined)return <div className="login-page"><div className="loading-brand"><BrandMark/><p>正在连接教研工作台…</p></div></div>
 if(user===null)return <><Login onLogin={name=>{setUser(name);setError('')}}/>{error&&<p className="auth-error" role="alert">{error}</p>}</>
 return <div className="shell">
  {menu&&<button className="nav-backdrop" aria-label="关闭导航" onClick={()=>setMenu(false)}/>}
  <nav className={menu?'nav open':'nav'} aria-label="主导航">
   <Link className="brand" to="/" onClick={()=>setMenu(false)}><BrandMark/>{preferences.display_name!==defaults.display_name&&<span className="custom-brand-name">{preferences.display_name}</span>}</Link>
   <div className="nav-scroll">{groups.map(g=><section className="nav-group" key={g.id}><div className="nav-label">{g.label}</div>{modules.filter(m=>m.group===g.id).map(m=><NavLink key={m.path} end={m.path==='/'} to={m.path} onClick={()=>setMenu(false)}><Icon name={m.icon} size={19}/><span>{m.name}</span>{m.path===location.pathname&&<span className="active-indicator"/>}</NavLink>)}</section>)}</div>
   <div className="nav-footer"><span className="avatar">{user.slice(0,1).toUpperCase()}</span><div className="account"><strong>{user}</strong><small>个人教研空间</small></div><button className="icon-button" aria-label="退出登录" title="退出登录" onClick={logout}><Icon name="logout" size={19}/></button></div>
  </nav>
  <header className="topbar"><button className="icon-button menu" aria-label="打开导航" aria-expanded={menu} onClick={()=>{setMenu(!menu);setAssistant(false)}}><Icon name="menu"/></button><div className="breadcrumb"><span>教研空间</span><Icon name="chevron" size={15}/><strong>{current?.name??'页面'}</strong></div><div className="topbar-actions"><span className="health" role="status"><span className={'status-dot '+(health==='服务已连接'?'':'offline')}/><span>{health}</span></span><button className="assistant-trigger" aria-expanded={assistant} onClick={()=>{setAssistant(!assistant);setMenu(false)}}><Icon name="spark" size={18}/> AI 助手</button></div></header>
  <main className="main-content">{error&&<p className="inline-error" role="alert">{error}</p>}<Routes><Route path="/" element={<Home/>}/>{modules.slice(1).map(m=><Route key={m.path} path={m.path} element={m.path==='/files'?<Files/>:m.path==='/formulas'?<FormulaLab/>:m.path==='/settings'?<><div className="page-heading"><h1>系统设置</h1><p className="muted">{m.desc}</p></div><Settings preferences={preferences} onChange={setPreferences}/></>:<PlannedPage module={m}/>}/>)}<Route path="*" element={<section className="panel planned"><h1>页面不存在</h1><Link className="text-link" to="/">返回工作台</Link></section>}/></Routes><footer className="main-footer"><span>微光数学 · 教研工作台</span><span>基础工程 · 01</span></footer></main>
  {assistant&&<><button className="assistant-backdrop" aria-label="关闭 AI 助手" onClick={()=>setAssistant(false)}/><aside className="assistant-panel" aria-label="AI 助手"><div className="panel-heading"><h2><Icon name="spark"/> AI 助手</h2><button className="icon-button" aria-label="关闭 AI 助手" onClick={()=>setAssistant(false)}><Icon name="close"/></button></div><div className="empty-state"><span className="soft-icon"><Icon name="spark" size={30}/></span><strong>AI 教研空间</strong><p>模型接入将在后续阶段完成。</p></div></aside></>}
  <div className="mobile-tabs" role="navigation" aria-label="常用入口">{modules.filter(m=>['/','/resources','/research','/files'].includes(m.path)).map(m=><NavLink key={m.path} to={m.path} end={m.path==='/'}><Icon name={m.icon} size={21}/><span>{m.path==='/resources'?'资源':m.path==='/research'?'创作':m.path==='/files'?'文件':'工作台'}</span></NavLink>)}<button onClick={()=>{setMenu(true);setAssistant(false)}}><Icon name="menu" size={21}/><span>更多</span></button></div>
 </div>
}
