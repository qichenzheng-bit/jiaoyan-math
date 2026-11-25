import {useEffect,useRef,useState} from 'react'
import {NavLink,useLocation} from 'react-router-dom'
import {modules,mainSections} from '../navigation'
import {Icon} from './Icon'
type Section=typeof mainSections[number]
const primary:Record<string,string[]>={
 '/chat':['/chat','/intelligence','/intake'],
 '/library':['/resources','/knowledge-library','/sources'],
 '/create':['/videos','/handouts','/papers','/research'],
 '/products':['/works'],
 '/operations':['/publishing','/analytics'],
 '/settings':['/settings','/qoder','/checkin'],
}
export default function SectionNavigation({section}:{section:Section}){
 const {pathname}=useLocation()
 const [open,setOpen]=useState(false)
 const box=useRef<HTMLDivElement>(null)
 useEffect(()=>setOpen(false),[pathname])
 useEffect(()=>{if(!open)return;const close=(e:PointerEvent)=>{if(!box.current?.contains(e.target as Node))setOpen(false)};const key=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false)};document.addEventListener('pointerdown',close);document.addEventListener('keydown',key);return()=>{document.removeEventListener('pointerdown',close);document.removeEventListener('keydown',key)}},[open])
 const first=primary[section.path]??section.children
 const rest=section.children.filter(p=>!first.includes(p))
 const current=modules.find(m=>m.path===pathname)
 const activeMore=rest.includes(pathname)
 function nav(p:string){const m=modules.find(m=>m.path===p);return m?<NavLink key={p} end to={p} onClick={()=>setOpen(false)}>{m.name}</NavLink>:p==='/intake-single'?<NavLink key={p} end to={p} onClick={()=>setOpen(false)}>单条录入</NavLink>:null}
 return <div className="section-navigation"><nav className="section-tabs" aria-label={section.name+'内部导航'}>{!['/chat','/settings'].includes(section.path)&&<NavLink to={section.path} end>概览</NavLink>}{first.map(nav)}</nav>{rest.length>0&&<div ref={box} className="section-more"><button type="button" className={activeMore?'selected':''} aria-expanded={open} aria-controls="section-extra-links" onClick={()=>setOpen(v=>!v)}><span>{activeMore?(current?.name??'单条录入'):'更多工具'}</span><Icon name="chevron" size={13}/></button>{open&&<nav id="section-extra-links" className="section-popover" aria-label="更多工具">{rest.map(nav)}</nav>}</div>}</div>
}
