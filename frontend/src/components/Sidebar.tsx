import {useEffect,useRef,useState} from 'react'
import {useLocation} from 'react-router-dom'
import {WorkspaceLink as Link,guardNavigation} from './WorkspaceNavigation'
import {BrandMark,Icon} from './Icon'
import {MathText} from './MathText'
import {api} from '../auth'
import {workspaceGroups,type WorkspaceGroup} from '../navigation'
type Props={user:string;displayName:string;open:boolean;collapsed:boolean;onClose:()=>void;onToggle:()=>void;onLogout:()=>void}
type Session={id:string;title:string;project?:string;pinned:boolean;archived:boolean}
type Doc={id:string;title:string}
export default function Sidebar({user,displayName,open,collapsed,onClose,onToggle,onLogout}:Props){
 const [account,setAccount]=useState(false),[sessions,setSessions]=useState<Session[]>([]),[docs,setDocs]=useState<Doc[]>([]),[refresh,setRefresh]=useState(0)
 const [allHistory,setAllHistory]=useState(false),[historyQuery,setHistoryQuery]=useState(''),[archived,setArchived]=useState(false),[historyError,setHistoryError]=useState(false)
 const dock=useRef<HTMLDivElement>(null)
 const location=useLocation(),params=new URLSearchParams(location.search)
 const chat=location.pathname==='/'||location.pathname==='/chat',activeSession=params.get('session'),docId=params.get('doc')
 useEffect(()=>{setAccount(false)},[location.pathname,open,collapsed])
 useEffect(()=>{if(params.has('history')&&chat)setAllHistory(true)},[location.pathname,location.search])
 useEffect(()=>{const c=new AbortController();setHistoryError(false);const timer=window.setTimeout(()=>{api<Session[]>('/chat/sessions?'+new URLSearchParams({archived:String(allHistory&&archived),q:allHistory?historyQuery:''}),{signal:c.signal}).then(r=>{if(!c.signal.aborted)setSessions(r.filter(x=>x.archived===Boolean(allHistory&&archived)))}).catch(()=>{if(!c.signal.aborted){setSessions([]);setHistoryError(true)}})},allHistory?180:0);return()=>{clearTimeout(timer);c.abort()}},[location.pathname,location.search,refresh,allHistory,historyQuery,archived])
 useEffect(()=>{const c=new AbortController();api<{items:Doc[]}>('/documents?kind=intake&limit=5',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setDocs(r.items.slice(0,5))}).catch(()=>{});return()=>c.abort()},[location.pathname,location.search,refresh])
 useEffect(()=>{const sync=()=>setRefresh(v=>v+1);window.addEventListener('wg-recent-changed',sync);return()=>window.removeEventListener('wg-recent-changed',sync)},[])
 const activeGroup=workspaceGroups.find(g=>location.pathname==='/project/'+g.id||g.sections.some(s=>s.entries.some(e=>e.path.split('?')[0]===location.pathname)))
 useEffect(()=>{if(!account)return;function outside(e:PointerEvent){if(!dock.current?.contains(e.target as Node))setAccount(false)}function escape(e:KeyboardEvent){if(e.key==='Escape')setAccount(false)}document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[account])
 function groupMenu(g:WorkspaceGroup){const path=g.id==='intake'?'/intake':'/project/'+g.id;return <div className="clean-nav-group" data-nav-group={g.id} key={g.id}><Link to={path} className={'clean-group-link'+(activeGroup?.id===g.id?' active':'')} title={g.name} aria-current={location.pathname===path?'page':undefined} onApproved={onClose}><Icon name={g.icon} size={18}/><span className="nav-text">{g.name}</span>{g.id!=='intake'&&<span className="clean-group-chevron"><Icon name="chevron" size={13}/></span>}</Link></div>}
 const recent=allHistory?sessions:sessions.slice(0,12)
 return <aside id="workspace-navigation" className={'nav'+(open?' open':'')} aria-label="工作空间侧栏">
 <div className="side-head"><Link className="brand" to="/" aria-label="返回聊天" onApproved={onClose}><BrandMark/>{displayName!=='微光数学'&&<span className="custom-brand-name">{displayName}</span>}</Link><button className="side-toggle icon-button" onClick={onToggle} aria-label={collapsed?'展开侧边栏':'收起侧边栏'} title={collapsed?'展开侧边栏':'收起侧边栏'}><Icon name="sidebar" size={19}/></button><button className="side-mobile-close icon-button" onClick={onClose} aria-label="关闭导航"><Icon name="close"/></button></div>
 <nav className="nav-scroll clean-nav-scroll" aria-label="主导航"><section className="nav-group main-section-links">
 <Link to="/chat?new=1" title="新建对话" onClick={e=>{if(chat){e.preventDefault();window.dispatchEvent(new Event('wg-chat-new'));onClose()}}} onApproved={onClose}><Icon name="plus" size={19}/><span className="nav-text">新建对话</span></Link>
 {workspaceGroups.map(groupMenu)}
 </section>
 <section className="nav-group clean-recent"><div className="clean-recent-heading"><span>{allHistory?'全部对话':'最近对话'}</span><button type="button" className="clean-history-switch" onClick={()=>{setAllHistory(v=>!v);setHistoryQuery('');setArchived(false)}}>{allHistory?'收起':'全部'}</button></div>
 {allHistory&&<div className="clean-history-filter"><input aria-label="搜索会话" placeholder="搜索会话" value={historyQuery} onChange={e=>setHistoryQuery(e.target.value)}/><select aria-label="会话范围" value={archived?'archived':'active'} onChange={e=>setArchived(e.target.value==='archived')}><option value="active">未归档</option><option value="archived">已归档</option></select></div>}
 {recent.map(s=>{const path='/chat?session='+encodeURIComponent(s.id);return <Link key={s.id} to={path} className={chat&&activeSession===s.id?'active':''} aria-current={chat&&activeSession===s.id?'page':undefined} onApproved={onClose} title={s.title}><span className="nav-text">{s.pinned?'★ ':''}<MathText compact content={s.title}/></span></Link>})}{!recent.length&&<small>{historyError?'会话读取失败':historyQuery?'暂无匹配会话':archived?'暂无已归档会话':'暂无最近对话'}</small>}</section>
 <section className="nav-group clean-recent"><div className="clean-recent-heading"><span>最近录入</span><Link to="/intake?mode=document" onApproved={onClose}>全部</Link></div>{docs.map(d=>{const path='/intake?doc='+encodeURIComponent(d.id);return <Link key={d.id} to={path} className={docId===d.id?'active':''} onApproved={onClose} title={d.title}><span className="nav-text"><MathText compact content={d.title}/></span></Link>})}{!docs.length&&<small>暂无最近文档</small>}</section></nav>
 <div className="side-foot" ref={dock}>
 {account&&<div className="account-popover"><div className="account-popover-heading"><strong>{user}</strong><small>个人教研空间</small></div>{[{path:'/qoder',name:'AI 账号与模型',icon:'spark'},{path:'/checkin',name:'签到助手',icon:'calendar'},{path:'/settings',name:'系统设置',icon:'settings'}].map(m=><Link key={m.path} to={m.path} onApproved={()=>{setAccount(false);onClose()}}><Icon name={m.icon} size={17}/> {m.name}</Link>)}<button onClick={async()=>{if(!await guardNavigation('/logout'))return;setAccount(false);onLogout()}}><Icon name="logout" size={17}/> 退出登录</button></div>}
 <button className="account-trigger" aria-expanded={account} aria-label="账号菜单" title={user} onClick={()=>setAccount(v=>!v)}><span className="avatar">{user.slice(0,1).toUpperCase()}</span><span className="account"><strong>{user}</strong><small>个人工作空间</small></span><Icon name="chevron" size={16}/></button></div>
 </aside>
}
