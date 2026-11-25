import {useEffect,useRef,useState} from 'react'
import {Link,useLocation} from 'react-router-dom'
import {BrandMark,Icon} from './Icon'
import {mainSections,sectionFor} from '../navigation'
type Props={user:string;displayName:string;open:boolean;collapsed:boolean;onClose:()=>void;onToggle:()=>void;onLogout:()=>void}
export default function Sidebar({user,displayName,open,collapsed,onClose,onToggle,onLogout}:Props){
 const [account,setAccount]=useState(false)
 const dock=useRef<HTMLDivElement>(null)
 const location=useLocation()
 const section=sectionFor(location.pathname)
 const link=(m:{path:string;name:string;icon:string})=><Link key={m.path} to={m.path} onClick={onClose} title={m.name} aria-label={m.name} aria-current={(section?.path===m.path||location.pathname===m.path)?'page':undefined} className={(section?.path===m.path||location.pathname===m.path)?'active':''}><Icon name={m.icon} size={19}/><span className="nav-text">{m.name}</span></Link>
 useEffect(()=>{setAccount(false)},[location.pathname,open,collapsed])
 useEffect(()=>{if(!account)return;function outside(e:PointerEvent){if(!dock.current?.contains(e.target as Node))setAccount(false)}function escape(e:KeyboardEvent){if(e.key==='Escape')setAccount(false)}document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[account])
 return <aside id="workspace-navigation" className={'nav'+(open?' open':'')} aria-label="工作空间侧栏">
  <div className="side-head">
   <Link className="brand" to="/" aria-label="微光数学首页" onClick={onClose}><BrandMark/>{displayName!=='微光数学'&&<span className="custom-brand-name">{displayName}</span>}</Link>
   <button className="side-toggle icon-button" onClick={onToggle} aria-label={collapsed?'展开侧边栏':'收起侧边栏'} title={collapsed?'展开侧边栏':'收起侧边栏'}><Icon name="sidebar" size={19}/></button>
   <button className="side-mobile-close icon-button" onClick={onClose} aria-label="关闭导航"><Icon name="close"/></button>
  </div>
  <nav className="nav-scroll" aria-label="主导航">
   <section className="nav-group main-section-links">{mainSections.map(link)}</section>
  </nav>
  <div className="side-foot" ref={dock}>
   <nav className="nav-scroll utility-links" aria-label="系统工具">{link({path:"/tasks",name:"后台任务",icon:"clock"})}{link({path:"/settings",name:"系统设置",icon:"settings"})}</nav>
   {account&&<div className="account-popover"><div className="account-popover-heading"><strong>{user}</strong><small>个人教研空间</small></div><Link to="/qoder" onClick={()=>{setAccount(false);onClose()}}><Icon name="spark" size={17}/> AI 账号与模型</Link><Link to="/settings" onClick={()=>{setAccount(false);onClose()}}><Icon name="settings" size={17}/> 系统设置</Link><button onClick={()=>{setAccount(false);onLogout()}}><Icon name="logout" size={17}/> 退出登录</button></div>}
   <button className="account-trigger" aria-expanded={account} aria-label="账号菜单" title={user} onClick={()=>setAccount(a=>!a)}><span className="avatar">{user.slice(0,1).toUpperCase()}</span><span className="account"><strong>{user}</strong><small>个人教研空间</small></span><Icon name="chevron" size={16}/></button>
  </div>
 </aside>
}
