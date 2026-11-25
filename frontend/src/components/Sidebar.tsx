import {useEffect,useRef,useState} from 'react'
import {Link,NavLink,useLocation} from 'react-router-dom'
import {BrandMark,Icon} from './Icon'
import {groups,modules} from '../navigation'
type Props={user:string;displayName:string;open:boolean;collapsed:boolean;onClose:()=>void;onToggle:()=>void;onLogout:()=>void}
export default function Sidebar({user,displayName,open,collapsed,onClose,onToggle,onLogout}:Props){
 const [account,setAccount]=useState(false)
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
   {groups.map(g=><section className="nav-group" key={g.id}><div className="nav-label">{g.label}</div>{modules.filter(m=>m.group===g.id).map(m=><NavLink key={m.path} to={m.path} end={m.path==='/'} onClick={onClose} title={m.name+(m.ready?'':'（待迁移）')} aria-label={m.name+(m.ready?'':'，待迁移')} className={({isActive})=>(isActive?'active ':'')+(m.ready?'':'future-link')}><Icon name={m.icon} size={18}/><span className="nav-text">{m.name}</span>{!m.ready&&<small className="nav-pending">待迁移</small>}</NavLink>)}</section>)}
  </nav>
  <div className="side-foot" ref={dock}>
   {account&&<div className="account-popover"><div className="account-popover-heading"><strong>{user}</strong><small>个人教研空间</small></div><Link to="/qoder" onClick={()=>{setAccount(false);onClose()}}><Icon name="spark" size={17}/> AI 账号与模型</Link><Link to="/settings" onClick={()=>{setAccount(false);onClose()}}><Icon name="settings" size={17}/> 系统设置</Link><button onClick={()=>{setAccount(false);onLogout()}}><Icon name="logout" size={17}/> 退出登录</button></div>}
   <button className="account-trigger" aria-expanded={account} aria-label="账号菜单" title={user} onClick={()=>setAccount(a=>!a)}><span className="avatar">{user.slice(0,1).toUpperCase()}</span><span className="account"><strong>{user}</strong><small>个人教研空间</small></span><Icon name="chevron" size={16}/></button>
  </div>
 </aside>
}
