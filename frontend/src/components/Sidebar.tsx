import {useEffect,useRef,useState} from 'react'
import {Link,NavLink,useLocation} from 'react-router-dom'
import {BrandMark,Icon} from './Icon'
import {modules} from '../navigation'
type Props={user:string;displayName:string;open:boolean;collapsed:boolean;onClose:()=>void;onToggle:()=>void;onLogout:()=>void}
export default function Sidebar({user,displayName,open,collapsed,onClose,onToggle,onLogout}:Props){
 const [account,setAccount]=useState(false),[more,setMore]=useState(false)
 const primaryGroups=[{label:'工作空间',paths:['/','/chat','/tasks']},{label:'教学资源',paths:['/intake','/resources','/graph']},{label:'教研创作',paths:['/research','/handouts','/papers']},{label:'内容制作',paths:['/works','/publishing']},{label:'',paths:['/checkin','/settings']}]
 const mainPaths=new Set(primaryGroups.flatMap(g=>g.paths))
 const link=(m:typeof modules[number])=><NavLink key={m.path} to={m.path} end={m.path==='/'} onClick={onClose} title={m.name} aria-label={m.name} className={({isActive})=>isActive?'active':''}><Icon name={m.icon} size={17}/><span className="nav-text">{m.name}</span></NavLink>
 const dock=useRef<HTMLDivElement>(null)
 const location=useLocation()
 useEffect(()=>{setAccount(false)},[location.pathname,open,collapsed])
 useEffect(()=>{if(!account)return;function outside(e:PointerEvent){if(!dock.current?.contains(e.target as Node))setAccount(false)}function escape(e:KeyboardEvent){if(e.key==='Escape')setAccount(false)}document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[account])
 return <aside id="workspace-navigation" className={'nav'+(open?' open':'')} aria-label="工作空间侧栏">
  <div className="side-head">
   <Link className="brand" to="/" aria-label="微光数学首页" onClick={onClose}><BrandMark/>{displayName!=='微光数学'&&<span className="custom-brand-name">{displayName}</span>}</Link>
   <button className="side-toggle icon-button" onClick={onToggle} aria-label={collapsed?'展开侧边栏':'收起侧边栏'} title={collapsed?'展开侧边栏':'收起侧边栏'}><Icon name="sidebar" size={19}/></button>
   <button className="side-mobile-close icon-button" onClick={onClose} aria-label="关闭导航"><Icon name="close"/></button>
  </div>
  <nav className="nav-scroll" aria-label="主导航">
   {primaryGroups.map(g=><section className="nav-group" key={g.label}>{g.label&&<div className="nav-label">{g.label}</div>}{modules.filter(m=>g.paths.includes(m.path)).sort((a,b)=>g.paths.indexOf(a.path)-g.paths.indexOf(b.path)).map(link)}</section>)}<section className="nav-group"><button className="nav-more" aria-expanded={more} onClick={()=>setMore(v=>!v)}><Icon name="menu" size={17}/><span className="nav-text">{more?'收起其他工具':'更多工具'}</span></button>{(more||collapsed)&&modules.filter(m=>!mainPaths.has(m.path)).map(link)}{!more&&!collapsed&&modules.filter(m=>!mainPaths.has(m.path)&&m.path===location.pathname).map(link)}</section>
  </nav>
  <div className="side-foot" ref={dock}>
   {account&&<div className="account-popover"><div className="account-popover-heading"><strong>{user}</strong><small>个人教研空间</small></div><Link to="/qoder" onClick={()=>{setAccount(false);onClose()}}><Icon name="spark" size={17}/> AI 账号与模型</Link><Link to="/settings" onClick={()=>{setAccount(false);onClose()}}><Icon name="settings" size={17}/> 系统设置</Link><button onClick={()=>{setAccount(false);onLogout()}}><Icon name="logout" size={17}/> 退出登录</button></div>}
   <button className="account-trigger" aria-expanded={account} aria-label="账号菜单" title={user} onClick={()=>setAccount(a=>!a)}><span className="avatar">{user.slice(0,1).toUpperCase()}</span><span className="account"><strong>{user}</strong><small>个人教研空间</small></span><Icon name="chevron" size={16}/></button><div className="legacy-account-dock"><Link to="/qoder" title="Qoder CN 模型管理" onClick={onClose}>Q</Link><Link to="/settings" title="系统设置" onClick={onClose}><Icon name="settings" size={16}/></Link></div>
  </div>
 </aside>
}
