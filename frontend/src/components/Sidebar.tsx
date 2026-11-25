import {useEffect,useRef,useState} from 'react'
import {Link,useLocation} from 'react-router-dom'
import {BrandMark,Icon} from './Icon'
import {MathText} from './MathText'
import {api} from '../auth'
import {modules,mainSections,sectionFor} from '../navigation'
type Props={user:string;displayName:string;open:boolean;collapsed:boolean;onClose:()=>void;onToggle:()=>void;onLogout:()=>void}
type Session={id:string;title:string;pinned:boolean;archived:boolean}
type Doc={id:string;title:string}
export default function Sidebar({user,displayName,open,collapsed,onClose,onToggle,onLogout}:Props){
 const [account,setAccount]=useState(false),[sessions,setSessions]=useState<Session[]>([]),[docs,setDocs]=useState<Doc[]>([]),[refresh,setRefresh]=useState(0),[expanded,setExpanded]=useState<string[]>([])
 const dock=useRef<HTMLDivElement>(null)
 const location=useLocation(),section=sectionFor(location.pathname)
 const chat=location.pathname==='/'||location.pathname==='/chat'
 const activeSession=new URLSearchParams(location.search).get('session')
 const docId=new URLSearchParams(location.search).get('doc')
 useEffect(()=>{setAccount(false)},[location.pathname,open,collapsed])
 useEffect(()=>{const c=new AbortController();api<Session[]>('/chat/sessions?archived=false',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setSessions(r.filter(x=>!x.archived).slice(0,12))}).catch(()=>{});api<{items:Doc[]}>('/documents?kind=intake&limit=5',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setDocs(r.items.slice(0,5))}).catch(()=>{});return()=>c.abort()},[location.pathname,location.search,refresh])
 useEffect(()=>{const sync=()=>setRefresh(v=>v+1);window.addEventListener('wg-recent-changed',sync);return()=>window.removeEventListener('wg-recent-changed',sync)},[])
 useEffect(()=>{if(section&&['/library','/create','/products','/operations'].includes(section.path))setExpanded(old=>old.includes(section.path)?old:[...old,section.path])},[section?.path])
 useEffect(()=>{if(!account)return;function outside(e:PointerEvent){if(!dock.current?.contains(e.target as Node))setAccount(false)}function escape(e:KeyboardEvent){if(e.key==='Escape')setAccount(false)}document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[account])
 function link(m:{path:string;name:string;icon:string},active=false,child=false){return <Link key={m.path} to={m.path} onClick={onClose} title={m.name} aria-current={active?'page':undefined} className={(active?'active ':'')+(child?'nav-child':'')}><Icon name={m.icon} size={18}/><span className="nav-text">{m.name}</span></Link>}
 const main=[{path:'/chat?new=1',name:'新建对话',icon:'plus'},{path:'/resources',name:'搜索资源',icon:'search'},{path:'/intake',name:'资料录入',icon:'intake'}]
 return <aside id="workspace-navigation" className={'nav'+(open?' open':'')} aria-label="工作空间侧栏">
 <div className="side-head"><Link className="brand" to="/" aria-label="微光数学首页" onClick={onClose}><BrandMark/>{displayName!=='微光数学'&&<span className="custom-brand-name">{displayName}</span>}</Link><button className="side-toggle icon-button" onClick={onToggle} aria-label={collapsed?'展开侧边栏':'收起侧边栏'} title={collapsed?'展开侧边栏':'收起侧边栏'}><Icon name="sidebar" size={19}/></button><button className="side-mobile-close icon-button" onClick={onClose} aria-label="关闭导航"><Icon name="close"/></button></div>
 <nav className="nav-scroll clean-nav-scroll" aria-label="主导航"><section className="nav-group main-section-links">{main.map(m=>m.path==='/chat?new=1'?<Link key={m.path} to={m.path} title={m.name} onClick={e=>{onClose();if(location.pathname==='/chat'&&location.search==='?new=1'){e.preventDefault();window.dispatchEvent(new Event('wg-chat-new'))}}}><Icon name="plus" size={19}/><span className="nav-text">{m.name}</span></Link>:link(m,m.path==='/intake'?['/intake','/intelligence','/intake-single'].includes(location.pathname):location.pathname===m.path))}
 {mainSections.filter(s=>['/library','/create','/products','/operations'].includes(s.path)).map(s=><div className="clean-nav-group" key={s.path}><div className="clean-nav-group-head">{link(s,section?.path===s.path&&location.pathname!=='/resources')}<button type="button" className="nav-expander" aria-label={(expanded.includes(s.path)?'收起':'展开')+s.name} aria-expanded={expanded.includes(s.path)} onClick={()=>setExpanded(old=>old.includes(s.path)?old.filter(x=>x!==s.path):[...old,s.path])}><Icon name="chevron" size={13}/></button></div>{expanded.includes(s.path)&&<div className="clean-nav-children">{s.children.map(path=>{const m=modules.find(x=>x.path===path);return m?link(m,location.pathname===path,true):null})}</div>}</div>)}</section>
 <section className="nav-group clean-recent"><div className="clean-recent-heading"><span>最近对话</span><Link to="/chat?history=1" onClick={onClose} title="查看全部会话">全部</Link></div>{sessions.map(s=><Link key={s.id} to={'/chat?session='+encodeURIComponent(s.id)} className={chat&&activeSession===s.id?'active':''} onClick={onClose} title={s.title}><span className="nav-text">{s.pinned?'★ ':''}<MathText compact content={s.title}/></span></Link>)}{!sessions.length&&<small>暂无最近对话</small>}</section>
 <section className="nav-group clean-recent"><div className="clean-recent-heading"><span>最近录入</span><Link to="/intake?mode=document" onClick={onClose}>全部</Link></div>{docs.map(d=><Link key={d.id} to={'/intake?doc='+encodeURIComponent(d.id)} className={docId===d.id?'active':''} onClick={onClose} title={d.title}><span className="nav-text"><MathText compact content={d.title}/></span></Link>)}{!docs.length&&<small>暂无最近文档</small>}</section></nav>
 <div className="side-foot" ref={dock}><nav className="nav-scroll utility-links" aria-label="系统工具">{link({path:'/tasks',name:'任务中心',icon:'clock'},location.pathname==='/tasks')}</nav>
 {account&&<div className="account-popover"><div className="account-popover-heading"><strong>{user}</strong><small>个人教研空间</small></div>{[{path:'/overview',name:'工作总览',icon:'home'},{path:'/qoder',name:'AI 账号与模型',icon:'spark'},{path:'/checkin',name:'签到助手',icon:'calendar'},{path:'/settings',name:'系统设置',icon:'settings'},{path:'/files',name:'文件管理',icon:'files'}].map(m=><Link key={m.path} to={m.path} onClick={()=>{setAccount(false);onClose()}}><Icon name={m.icon} size={17}/> {m.name}</Link>)}<button onClick={()=>{setAccount(false);onLogout()}}><Icon name="logout" size={17}/> 退出登录</button></div>}
 <button className="account-trigger" aria-expanded={account} aria-label="账号菜单" title={user} onClick={()=>setAccount(v=>!v)}><span className="avatar">{user.slice(0,1).toUpperCase()}</span><span className="account"><strong>{user}</strong><small>个人工作空间</small></span><Icon name="chevron" size={16}/></button></div>
 </aside>
}
