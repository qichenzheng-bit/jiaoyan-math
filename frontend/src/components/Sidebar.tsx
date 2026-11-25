import {useEffect,useRef,useState} from 'react'
import {Link,useLocation} from 'react-router-dom'
import {BrandMark,Icon} from './Icon'
import {MathText} from './MathText'
import {api} from '../auth'
import {modules,mainSections,sectionFor} from '../navigation'
type Props={user:string;displayName:string;open:boolean;collapsed:boolean;onClose:()=>void;onToggle:()=>void;onLogout:()=>void}
type Session={id:string;title:string;project?:string;pinned:boolean;archived:boolean}
type Doc={id:string;title:string}
type Entry={path:string;name:string;icon:string}
const intakeEntries:Entry[]=[
 {path:'/intake',name:'录入工作台',icon:'intake'},
 {path:'/intelligence',name:'AI 智能录入',icon:'spark'},
 {path:'/intake?mode=document',name:'整套资料录入',icon:'files'},
 {path:'/intake-single?kind=question',name:'单道题目录入',icon:'resources'},
 {path:'/intake-single?kind=knowledge',name:'知识单元录入',icon:'book'},
 {path:'/intake-single?kind=source',name:'登记来源资料',icon:'files'},
]
export default function Sidebar({user,displayName,open,collapsed,onClose,onToggle,onLogout}:Props){
 const [account,setAccount]=useState(false),[sessions,setSessions]=useState<Session[]>([]),[docs,setDocs]=useState<Doc[]>([]),[refresh,setRefresh]=useState(0),[expanded,setExpanded]=useState<string[]>([])
 const [allHistory,setAllHistory]=useState(false),[historyQuery,setHistoryQuery]=useState(''),[archived,setArchived]=useState(false),[historyError,setHistoryError]=useState(false)
 const dock=useRef<HTMLDivElement>(null)
 const location=useLocation(),section=sectionFor(location.pathname),params=new URLSearchParams(location.search)
 const chat=location.pathname==='/'||location.pathname==='/chat',activeSession=params.get('session'),docId=params.get('doc')
 const isIntake=['/intake','/intelligence','/intake-single'].includes(location.pathname)
 const compact=collapsed&&!open
 useEffect(()=>{setAccount(false)},[location.pathname,open,collapsed])
 useEffect(()=>{if(params.has('history')&&chat)setAllHistory(true)},[location.pathname,location.search])
 useEffect(()=>{const c=new AbortController();setHistoryError(false);const timer=window.setTimeout(()=>{api<Session[]>('/chat/sessions?'+new URLSearchParams({archived:String(allHistory&&archived),q:allHistory?historyQuery:''}),{signal:c.signal}).then(r=>{if(!c.signal.aborted)setSessions(r.filter(x=>x.archived===Boolean(allHistory&&archived)))}).catch(()=>{if(!c.signal.aborted){setSessions([]);setHistoryError(true)}})},allHistory?180:0);return()=>{clearTimeout(timer);c.abort()}},[location.pathname,location.search,refresh,allHistory,historyQuery,archived])
 useEffect(()=>{const c=new AbortController();api<{items:Doc[]}>('/documents?kind=intake&limit=5',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setDocs(r.items.slice(0,5))}).catch(()=>{});return()=>c.abort()},[location.pathname,location.search,refresh])
 useEffect(()=>{const sync=()=>setRefresh(v=>v+1);window.addEventListener('wg-recent-changed',sync);return()=>window.removeEventListener('wg-recent-changed',sync)},[])
 const group=isIntake?'/intake':section?.path
 useEffect(()=>{if(group&&['/intake','/library','/create','/products','/operations'].includes(group))setExpanded(old=>old.includes(group)?old:[...old,group])},[group])
 useEffect(()=>{if(!account)return;function outside(e:PointerEvent){if(!dock.current?.contains(e.target as Node))setAccount(false)}function escape(e:KeyboardEvent){if(e.key==='Escape')setAccount(false)}document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[account])
 function allowNavigation(path:string){return !chat||window.dispatchEvent(new CustomEvent('wg-chat-navigation',{cancelable:true,detail:{path}}))}
 function link(m:Entry,active=false,child=false){return <Link key={m.path} to={m.path} onClick={e=>{if(!allowNavigation(m.path)){e.preventDefault();return}onClose()}} title={m.name} aria-current={active?'page':undefined} className={(active?'active ':'')+(child?'nav-child':'')}><Icon name={m.icon} size={18}/><span className="nav-text">{m.name}</span></Link>}
 function toggle(path:string){if(compact){onToggle();setExpanded(old=>old.includes(path)?old:[...old,path])}else setExpanded(old=>old.includes(path)?old.filter(x=>x!==path):[...old,path])}
 function matches(path:string){const [pathname,search]=path.split('?');if(pathname!==location.pathname)return false;if(!search)return pathname!=='/intake'||(!params.has('mode')&&!docId);return new URLSearchParams(search).toString()===params.toString()}
 function groupMenu(path:string,name:string,icon:string,children:Entry[]){const unfolded=expanded.includes(path);return <div className="clean-nav-group" key={path}><button type="button" className={'clean-group-toggle'+(group===path?' current':'')} title={name} aria-expanded={unfolded&&!compact} aria-label={name} onClick={()=>toggle(path)}><Icon name={icon} size={18}/><span className="nav-text">{name}</span><span className="clean-group-chevron"><Icon name="chevron" size={13}/></span></button>{unfolded&&<div className="clean-nav-children">{children.map(m=>link(m,matches(m.path),true))}</div>}</div>}
 const recent=allHistory?sessions:sessions.slice(0,12)
 return <aside id="workspace-navigation" className={'nav'+(open?' open':'')} aria-label="工作空间侧栏">
 <div className="side-head"><Link className="brand" to="/" aria-label="微光数学首页" onClick={e=>{if(!allowNavigation('/')){e.preventDefault();return}onClose()}}><BrandMark/>{displayName!=='微光数学'&&<span className="custom-brand-name">{displayName}</span>}</Link><button className="side-toggle icon-button" onClick={onToggle} aria-label={collapsed?'展开侧边栏':'收起侧边栏'} title={collapsed?'展开侧边栏':'收起侧边栏'}><Icon name="sidebar" size={19}/></button><button className="side-mobile-close icon-button" onClick={onClose} aria-label="关闭导航"><Icon name="close"/></button></div>
 <nav className="nav-scroll clean-nav-scroll" aria-label="主导航"><section className="nav-group main-section-links">
 {link({path:'/',name:'首页',icon:'home'},location.pathname==='/')}
 <Link to="/chat?new=1" title="新建对话" onClick={e=>{if(chat){e.preventDefault();window.dispatchEvent(new Event('wg-chat-new'))}onClose()}}><Icon name="plus" size={19}/><span className="nav-text">新建对话</span></Link>
 {link({path:'/resources',name:'搜索资源',icon:'search'},location.pathname==='/resources')}
 {groupMenu('/intake','资料录入','intake',intakeEntries)}
 {mainSections.filter(s=>['/library','/create','/products','/operations'].includes(s.path)).map(s=>groupMenu(s.path,s.name,s.icon,[{path:s.path,name:s.name+'总览',icon:s.icon},...s.children.flatMap(path=>{const m=modules.find(x=>x.path===path);return m?[m]:[]})]))}
 </section>
 <section className="nav-group clean-recent"><div className="clean-recent-heading"><span>{allHistory?'全部对话':'最近对话'}</span><button type="button" className="clean-history-switch" onClick={()=>{setAllHistory(v=>!v);setHistoryQuery('');setArchived(false)}}>{allHistory?'收起':'全部'}</button></div>
 {allHistory&&<div className="clean-history-filter"><input aria-label="搜索会话" placeholder="搜索会话" value={historyQuery} onChange={e=>setHistoryQuery(e.target.value)}/><select aria-label="会话范围" value={archived?'archived':'active'} onChange={e=>setArchived(e.target.value==='archived')}><option value="active">未归档</option><option value="archived">已归档</option></select></div>}
 {recent.map(s=>{const path='/chat?session='+encodeURIComponent(s.id);return <Link key={s.id} to={path} className={chat&&activeSession===s.id?'active':''} aria-current={chat&&activeSession===s.id?'page':undefined} onClick={e=>{if(!allowNavigation(path)){e.preventDefault();return}onClose()}} title={s.title}><span className="nav-text">{s.pinned?'★ ':''}<MathText compact content={s.title}/></span></Link>})}{!recent.length&&<small>{historyError?'会话读取失败':historyQuery?'暂无匹配会话':archived?'暂无已归档会话':'暂无最近对话'}</small>}</section>
 <section className="nav-group clean-recent"><div className="clean-recent-heading"><span>最近录入</span><Link to="/intake?mode=document" onClick={e=>{if(!allowNavigation('/intake?mode=document'))e.preventDefault();else onClose()}}>全部</Link></div>{docs.map(d=>{const path='/intake?doc='+encodeURIComponent(d.id);return <Link key={d.id} to={path} className={docId===d.id?'active':''} onClick={e=>{if(!allowNavigation(path))e.preventDefault();else onClose()}} title={d.title}><span className="nav-text"><MathText compact content={d.title}/></span></Link>})}{!docs.length&&<small>暂无最近文档</small>}</section></nav>
 <div className="side-foot" ref={dock}><nav className="nav-scroll utility-links" aria-label="系统工具">{link({path:'/tasks',name:'任务中心',icon:'clock'},location.pathname==='/tasks')}</nav>
 {account&&<div className="account-popover"><div className="account-popover-heading"><strong>{user}</strong><small>个人教研空间</small></div>{[{path:'/overview',name:'工作总览',icon:'home'},{path:'/qoder',name:'AI 账号与模型',icon:'spark'},{path:'/checkin',name:'签到助手',icon:'calendar'},{path:'/settings',name:'系统设置',icon:'settings'},{path:'/files',name:'文件管理',icon:'files'}].map(m=><Link key={m.path} to={m.path} onClick={e=>{if(!allowNavigation(m.path)){e.preventDefault();return}setAccount(false);onClose()}}><Icon name={m.icon} size={17}/> {m.name}</Link>)}<button onClick={()=>{if(!allowNavigation('/logout'))return;setAccount(false);onLogout()}}><Icon name="logout" size={17}/> 退出登录</button></div>}
 <button className="account-trigger" aria-expanded={account} aria-label="账号菜单" title={user} onClick={()=>setAccount(v=>!v)}><span className="avatar">{user.slice(0,1).toUpperCase()}</span><span className="account"><strong>{user}</strong><small>个人工作空间</small></span><Icon name="chevron" size={16}/></button></div>
 </aside>
}
