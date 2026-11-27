import {useEffect,useRef,useState,type PointerEvent as ReactPointerEvent} from 'react'
import {createPortal} from 'react-dom'
import {useLocation,useNavigate} from 'react-router-dom'
import {WorkspaceLink as Link,guardNavigation} from './WorkspaceNavigation'
import {BrandMark,Icon} from './Icon'
import {MathText} from './MathText'
import {confirmAction} from './WorkspaceConfirm'
import {api} from '../auth'
import {workspaceGroups,activeWorkspaceGroup,type WorkspaceGroup} from '../navigation'
type Props={user:string;displayName:string;open:boolean;phone:boolean;collapsed:boolean;onClose:()=>void;onToggle:()=>void;onLogout:()=>void}
type Session={id:string;title:string;project?:string;pinned:boolean;archived:boolean;updated_at?:number;created_at?:number}
type Job={id:string;title:string;state:string;updated_at?:number;created_at?:number;provenance?:{workspace_id?:string;work_batch_id?:string}}
type PersistentSession={id:string;title:string;updated_at:number;intake_job_ids?:string[]}
type Doc={id:string;title:string}
type RecordItem={id:string;title:string;kind:'chat'|'work';path:string;time:number;pinned:boolean;session?:Session}
const tools=[{path:'/checkin',name:'签到助手',icon:'calendar'},{path:'/qoder',name:'AI 账号与模型',icon:'spark'},{path:'/settings',name:'系统设置',icon:'settings'}]
function initialGroups():string[]{try{const value=JSON.parse(localStorage.getItem('wg-nav-groups')??'[]');return Array.isArray(value)?value.filter(x=>typeof x==='string'&&workspaceGroups.some(g=>g.id===x)):[]}catch{return []}}
function dateGroup(t:number){if(!t)return '较早';const date=new Date(t*1000),today=new Date(),yesterday=new Date();yesterday.setDate(today.getDate()-1);return date.toDateString()===today.toDateString()?'今天':date.toDateString()===yesterday.toDateString()?'昨天':'较早'}
export default function Sidebar({user,displayName,open,phone,collapsed,onClose,onToggle,onLogout}:Props){
 const [account,setAccount]=useState(false),[sessions,setSessions]=useState<Session[]>([]),[docs,setDocs]=useState<Doc[]>([]),[jobs,setJobs]=useState<Job[]>([]),[workspaces,setWorkspaces]=useState<PersistentSession[]>([]),[refresh,setRefresh]=useState(0)
 const [allHistory,setAllHistory]=useState(false),[historyQuery,setHistoryQuery]=useState(''),[historyError,setHistoryError]=useState(false),[workError,setWorkError]=useState(false),[historyKind,setHistoryKind]=useState<'all'|'chat'|'work'>('all'),[historyLoading,setHistoryLoading]=useState(false)
 const [expanded,setExpanded]=useState(initialGroups),[recordMenu,setRecordMenu]=useState<string>(),[renaming,setRenaming]=useState<string>(),[newTitle,setNewTitle]=useState(''),[recordError,setRecordError]=useState(''),[historyBusy,setHistoryBusy]=useState(false)
 const dock=useRef<HTMLDivElement>(null),nav=useRef<HTMLElement>(null),inFlight=useRef(false),sheet=useRef<HTMLDialogElement>(null),press=useRef<{timer:number;x:number;y:number}|undefined>(undefined),longPressed=useRef(false)
 const location=useLocation(),navigate=useNavigate(),params=new URLSearchParams(location.search)
 const chat=location.pathname==='/'||location.pathname==='/chat',activeSession=params.get('session'),docId=params.get('doc'),activeJob=location.pathname==='/work'?params.get('job'):null
 const activeGroup=activeWorkspaceGroup(location.pathname)
 useEffect(()=>{setAccount(false);setRecordMenu(undefined);setRenaming(undefined);setRecordError('')},[location.pathname,location.search,open,collapsed])
 useEffect(()=>{try{localStorage.setItem('wg-nav-groups',JSON.stringify(expanded))}catch{}},[expanded])
 useEffect(()=>{if(params.has('history')&&chat)setAllHistory(true)},[location.pathname,location.search])
 useEffect(()=>{const c=new AbortController();setHistoryError(false);setHistoryLoading(true);const timer=window.setTimeout(()=>{api<Session[]>('/chat/sessions?'+new URLSearchParams({q:allHistory?historyQuery:''}),{signal:c.signal}).then(r=>{if(!c.signal.aborted)setSessions(r)}).catch(()=>{if(!c.signal.aborted){setSessions([]);setHistoryError(true)}}).finally(()=>{if(!c.signal.aborted)setHistoryLoading(false)})},allHistory?180:0);return()=>{clearTimeout(timer);c.abort()}},[location.pathname,location.search,refresh,allHistory,historyQuery])
 useEffect(()=>{const c=new AbortController();setWorkError(false);api<Job[]>('/intelligence/jobs',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setJobs(Array.isArray(r)?r:[])}).catch(()=>{if(!c.signal.aborted){setJobs([]);setWorkError(true)}});return()=>c.abort()},[location.pathname,location.search,refresh])
 useEffect(()=>{const c=new AbortController();api<{items:Doc[]}>('/documents?kind=intake&limit=5',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setDocs(r.items.slice(0,5))}).catch(()=>{});return()=>c.abort()},[location.pathname,location.search,refresh])
 useEffect(()=>{const sync=()=>setRefresh(v=>v+1);window.addEventListener('wg-recent-changed',sync);return()=>window.removeEventListener('wg-recent-changed',sync)},[])
 useEffect(()=>{if(!account&&!recordMenu)return;function outside(e:PointerEvent){if(!dock.current?.contains(e.target as Node))setAccount(false);if(!(e.target as HTMLElement).closest('.nav-history-row,.nav-record-sheet,.workspace-confirm'))setRecordMenu(undefined)}function escape(e:KeyboardEvent){if(e.key==='Escape'&&!document.querySelector('.workspace-confirm[open]')){setAccount(false);if(!phone)setRecordMenu(undefined)}}document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[account,recordMenu,phone])
 useEffect(()=>{if(!phone||!open)return;const el=nav.current,previous=document.activeElement as HTMLElement|null
 const focusables=()=>Array.from(el?.querySelectorAll<HTMLElement>('a[href],button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled)')??[]).filter(x=>x.getClientRects().length>0&&getComputedStyle(x).visibility!=='hidden')
 const t=requestAnimationFrame(()=>el?.querySelector<HTMLElement>('.side-mobile-close')?.focus({preventScroll:true}))
 const trap=(e:KeyboardEvent)=>{if(e.key!=='Tab'||document.querySelector('.workspace-confirm[open],.nav-record-sheet[open]'))return;const list=focusables();if(!list.length)return;const first=list[0],last=list[list.length-1];if(e.shiftKey&&(document.activeElement===first||!el?.contains(document.activeElement))){e.preventDefault();last.focus()}else if(!e.shiftKey&&(document.activeElement===last||!el?.contains(document.activeElement))){e.preventDefault();first.focus()}}
 document.addEventListener('keydown',trap);return()=>{cancelAnimationFrame(t);document.removeEventListener('keydown',trap);if(previous?.isConnected&&previous.getClientRects().length&&document.activeElement?.closest('#workspace-navigation'))previous.focus({preventScroll:true})}
 },[phone,open])
 function toggleGroup(g:WorkspaceGroup){setExpanded(v=>v.includes(g.id)?v.filter(x=>x!==g.id):[...v,g.id])}
 function groupMenu(g:WorkspaceGroup){const path=g.id==='intake'?'/intake':'/project/'+g.id,show=!collapsed&&expanded.includes(g.id);return <div className="clean-nav-group" data-nav-group={g.id} key={g.id}><div className="clean-nav-group-head"><Link to={path} className={'clean-group-link'+(activeGroup?.id===g.id?' active':'')} title={g.name} aria-current={location.pathname===path&&!location.search?'page':undefined} onApproved={onClose}><Icon name={g.icon} size={18}/><span className="nav-text">{g.name}</span></Link>{!collapsed&&<button className="nav-expander" type="button" aria-label={(show?'收起':'展开')+g.name} aria-expanded={show} aria-controls={show?'nav-group-'+g.id:undefined} onClick={()=>toggleGroup(g)}><Icon name="chevron" size={15}/></button>}</div>{show&&<div className="clean-nav-children" id={'nav-group-'+g.id}>{g.sections.flatMap(s=>s.entries).map(e=>{const current=location.pathname+location.search===e.path||location.pathname===e.path&&!location.search;return <Link key={e.path} to={e.path} className={'nav-child'+(current?' active':'')} aria-current={current?'page':undefined} title={e.name} onApproved={onClose}><span className="nav-text">{e.name}</span></Link>})}</div>}</div>}
 async function changeSession(s:Session,values:Partial<Session>){
  if(inFlight.current)return
  inFlight.current=true;setHistoryBusy(true);setRecordError('')
  try{
   const updated=await api<Session>('/chat/sessions/'+encodeURIComponent(s.id),{method:'PATCH',body:JSON.stringify(values)})
   setSessions(old=>old.map(x=>x.id===updated.id?updated:x))
   window.dispatchEvent(new CustomEvent('wg-chat-session-updated',{detail:updated}))
   window.dispatchEvent(new Event('wg-recent-changed'));setRenaming(undefined);setRecordMenu(undefined)
  }catch(e){setRecordError(e instanceof Error?e.message:'会话操作失败')}finally{inFlight.current=false;setHistoryBusy(false)}
 }
 async function deleteSession(s:Session){
  if(inFlight.current)return
  inFlight.current=true;setHistoryBusy(true);setRecordError('')
  try{
   if(!await confirmAction('删除此对话及其全部消息？删除后不可恢复，独立资料库附件仍保留。','删除会话','删除'))return
   await api('/chat/sessions/'+encodeURIComponent(s.id),{method:'DELETE'})
   setSessions(old=>old.filter(x=>x.id!==s.id));setRecordMenu(undefined);setRenaming(undefined)
   if(chat&&activeSession===s.id){window.dispatchEvent(new CustomEvent('wg-chat-session-deleted',{detail:s.id}));navigate('/chat?new=1',{replace:true});onClose()}
   window.dispatchEvent(new Event('wg-recent-changed'))
  }catch(e){setRecordError(e instanceof Error?e.message:'删除会话失败')}finally{inFlight.current=false;setHistoryBusy(false)}
 }
 useEffect(()=>{if(phone&&recordMenu&&sheet.current&&!sheet.current.open)sheet.current.showModal()},[phone,recordMenu])
 useEffect(()=>()=>{if(press.current)clearTimeout(press.current.timer)},[])
 useEffect(()=>{const c=new AbortController();api<PersistentSession[]>('/workspaces',{signal:c.signal}).then(r=>{if(!c.signal.aborted&&Array.isArray(r))setWorkspaces(r)}).catch(()=>{});return()=>c.abort()},[location.pathname,location.search,refresh])
 // A recognition/organization job is a child of its conversation, not another history record.
 const jobParents=new Map<string,string>();for(const w of workspaces)for(const id of w.intake_job_ids??[])jobParents.set(id,w.id);for(const j of jobs)if(j.provenance?.workspace_id)jobParents.set(j.id,j.provenance.workspace_id)
 const activeWorkspace=params.get('workspace')||params.get('fromWorkspace')||(activeJob?jobParents.get(activeJob):undefined)
 const records:RecordItem[]=[...((historyKind==='chat')?[]:workspaces.filter(w=>!allHistory||!historyQuery||w.title.toLowerCase().includes(historyQuery.toLowerCase())).map(w=>({id:'workspace:'+w.id,title:w.title,kind:'work' as const,path:'/work?workspace='+encodeURIComponent(w.id),time:Math.max(w.updated_at,...jobs.filter(j=>jobParents.get(j.id)===w.id).map(j=>j.updated_at??j.created_at??0)),pinned:false}))),...((historyKind==='work')?[]:sessions.map(s=>({id:'chat:'+s.id,title:s.title,kind:'chat' as const,path:'/chat?session='+encodeURIComponent(s.id),time:s.updated_at??s.created_at??0,pinned:s.pinned,session:s}))),...((historyKind==='chat')?[]:jobs.filter(j=>!jobParents.has(j.id)&&!j.provenance?.work_batch_id&&(!allHistory||!historyQuery||j.title.toLowerCase().includes(historyQuery.toLowerCase()))).map(j=>({id:'work:'+j.id,title:j.title,kind:'work' as const,path:'/work?job='+encodeURIComponent(j.id),time:j.updated_at??j.created_at??0,pinned:false})))].sort((a,b)=>Number(b.pinned)-Number(a.pinned)||b.time-a.time||a.id.localeCompare(b.id))
 const recent=allHistory?records:records.slice(0,12),dateGroups=['置顶','今天','昨天','较早']
 const active=(r:RecordItem)=>r.kind==='chat'?chat&&r.session?.id===activeSession:r.id==='work:'+activeJob||location.pathname==='/work'&&r.id==='workspace:'+activeWorkspace
 function clearPress(){if(press.current){clearTimeout(press.current.timer);press.current=undefined}}
 function openRecord(r:RecordItem){if(historyBusy)return;setRecordMenu(r.id);setRecordError('');setRenaming(undefined)}
 function beginPress(e:ReactPointerEvent,r:RecordItem){longPressed.current=false;if(!phone||e.pointerType==='mouse'||(e.target as HTMLElement).closest('button'))return;clearPress();press.current={x:e.clientX,y:e.clientY,timer:window.setTimeout(()=>{longPressed.current=true;openRecord(r)},500)}}
 function movePress(e:ReactPointerEvent){const p=press.current;if(p&&Math.hypot(e.clientX-p.x,e.clientY-p.y)>10)clearPress()}
 function endpoint(r:RecordItem){return (r.id.startsWith('workspace:')?'/workspaces/':'/intelligence/jobs/')+encodeURIComponent(r.id.slice(r.id.indexOf(':')+1))}
 async function renameRecord(r:RecordItem){if(r.session){await changeSession(r.session,{title:newTitle.trim()});return}if(inFlight.current||!newTitle.trim())return;inFlight.current=true;setHistoryBusy(true);setRecordError('');try{const updated=await api<PersistentSession&Job>(endpoint(r),{method:'PATCH',body:JSON.stringify({title:newTitle.trim()})});if(r.id.startsWith('workspace:'))setWorkspaces(old=>old.map(x=>x.id===updated.id?updated:x));else setJobs(old=>old.map(x=>x.id===updated.id?updated:x));setRenaming(undefined);setRecordMenu(undefined);window.dispatchEvent(new CustomEvent('wg-work-title-updated',{detail:{kind:r.id.startsWith('workspace:')?'workspace':'job',id:updated.id,title:updated.title}}));window.dispatchEvent(new Event('wg-recent-changed'))}catch(e){setRecordError(e instanceof Error?e.message:'重命名失败')}finally{inFlight.current=false;setHistoryBusy(false)}}
 async function deleteRecord(r:RecordItem){if(r.session){await deleteSession(r.session);return}if(inFlight.current)return;inFlight.current=true;setHistoryBusy(true);setRecordError('');try{if(!await confirmAction('确定删除「'+r.title+'」？删除后无法恢复。原始资料、其他工作共享的识别进度和已生成的录入文档不受影响。运行中的任务将先停止。','删除工作？','删除'))return;const result=await api<{deleted:boolean;id:string;removed_job_ids:string[]}>(endpoint(r),{method:'DELETE'});const ids=new Set(result.removed_job_ids??[]);setJobs(old=>old.filter(x=>!ids.has(x.id)&&r.id!=='work:'+x.id));setWorkspaces(old=>old.filter(x=>r.id!=='workspace:'+x.id));setRecordMenu(undefined);setRenaming(undefined);if(active(r)||(activeJob&&ids.has(activeJob))){navigate('/work?new=1',{replace:true,state:{newWork:true}});onClose()}window.dispatchEvent(new Event('wg-recent-changed'))}catch(e){setRecordError(e instanceof Error?e.message:'删除工作失败')}finally{inFlight.current=false;setHistoryBusy(false)}}
 function actions(r:RecordItem){return <>{r.session&&<button disabled={historyBusy} onClick={()=>void changeSession(r.session!,{pinned:!r.session!.pinned})}>{r.session.pinned?'取消置顶':'置顶'}</button>}<button disabled={historyBusy} onClick={()=>{setRenaming(r.id);setNewTitle(r.title)}}><Icon name="research" size={17}/> 重命名</button><button disabled={historyBusy} className="nav-delete-action" onClick={()=>void deleteRecord(r)}><Icon name="trash" size={17}/> {phone?(r.session?'删除会话':'删除工作'):'删除'}</button></>}
 function renameForm(r:RecordItem){return <form className="nav-record-rename" onSubmit={e=>{e.preventDefault();void renameRecord(r)}}><input aria-label={r.session?'新会话名称':'新工作名称'} maxLength={r.session?160:200} value={newTitle} onChange={e=>setNewTitle(e.target.value)} autoFocus/><div><button type="button" onClick={()=>setRenaming(undefined)}>取消</button><button disabled={historyBusy||!newTitle.trim()}>保存</button></div></form>}
 function historyRow(r:RecordItem){return <div className="nav-history-row" key={r.id} onPointerDown={e=>beginPress(e,r)} onPointerMove={movePress} onPointerUp={clearPress} onPointerCancel={clearPress} onPointerLeave={clearPress} onContextMenu={e=>{if(phone){e.preventDefault();clearPress();openRecord(r)}}}><div className="nav-history-main"><Link to={r.path} className={active(r)?'active':''} aria-current={active(r)?'page':undefined} onClick={e=>{if(longPressed.current){e.preventDefault();longPressed.current=false}}} onApproved={onClose} title={r.title}><Icon name={r.kind==='chat'?'chat':'files'} size={14}/><span className="nav-text">{r.pinned?'★ ':''}<MathText compact content={r.title}/></span></Link><button className="nav-record-more" type="button" aria-label={'管理'+(r.session?'会话 ':'工作 ')+r.title} aria-expanded={recordMenu===r.id} disabled={historyBusy} onClick={()=>{if(recordMenu===r.id)setRecordMenu(undefined);else openRecord(r)}}><Icon name="more" size={16}/></button></div>{!phone&&recordMenu===r.id&&<div className="nav-record-actions">{actions(r)}</div>}{!phone&&renaming===r.id&&renameForm(r)}</div>}
 const menuRecord=records.find(r=>r.id===recordMenu)
 const phoneMenu=phone&&menuRecord?createPortal(<dialog ref={sheet} className="nav-record-sheet" aria-label="记录操作" onCancel={e=>{e.preventDefault();if(!historyBusy)setRecordMenu(undefined)}} onClick={e=>{if(e.target===e.currentTarget&&!historyBusy)setRecordMenu(undefined)}}><section><div className="nav-sheet-handle"/><strong><MathText compact content={menuRecord.title}/></strong>{recordError&&<p role="alert">{recordError}</p>}{renaming===menuRecord.id?renameForm(menuRecord):<div className="nav-record-sheet-actions">{actions(menuRecord)}</div>}<button className="nav-sheet-cancel" disabled={historyBusy} onClick={()=>setRecordMenu(undefined)}>取消</button></section></dialog>,document.body):null

 return <aside ref={nav} id="workspace-navigation" className={'nav'+(open?' open':'')} aria-label="工作空间侧栏" role={phone&&open?'dialog':undefined} aria-modal={phone&&open?true:undefined} inert={phone&&!open?true:undefined}>
 <div className="side-head"><Link className="brand" to="/" aria-label="返回聊天" onApproved={onClose}><BrandMark/>{displayName!=='微光数学'&&<span className="custom-brand-name">{displayName}</span>}</Link><button className="side-toggle icon-button" onClick={onToggle} aria-label={collapsed?'展开侧边栏':'收起侧边栏'} title={collapsed?'展开侧边栏':'收起侧边栏'}><Icon name="sidebar" size={19}/></button><button className="side-mobile-close icon-button" onClick={onClose} aria-label="关闭导航"><Icon name="close"/></button></div>
 <nav className="nav-scroll clean-nav-scroll" aria-label="主导航"><section className="nav-group main-section-links">
 <Link to="/chat?new=1" title="新建对话" onClick={e=>{if(chat&&e.button===0&&!e.metaKey&&!e.ctrlKey&&!e.shiftKey&&!e.altKey){e.preventDefault();window.dispatchEvent(new Event('wg-chat-new'));onClose()}}} onApproved={onClose}><Icon name="plus" size={19}/><span className="nav-text">新建对话</span></Link>
 <Link to="/work?new=1" state={{newWork:true}} title="新建工作" aria-label="新建工作" onApproved={onClose}><Icon name="research" size={18}/><span className="nav-text">新建工作</span></Link>
 <div className="nav-section-divider"/>
 {workspaceGroups.map(groupMenu)}
 </section>
 <section className="nav-group clean-recent nav-combined-history"><div className="clean-recent-heading"><span>{allHistory?'全部记录':'最近记录'}</span><button type="button" className="clean-history-switch" onClick={()=>{setAllHistory(v=>!v);setHistoryQuery('');setHistoryKind('all')}}>{allHistory?'收起':'全部'}</button></div>
 {allHistory&&<div className="clean-history-filter"><input aria-label="搜索会话" placeholder="搜索聊天与工作" value={historyQuery} onChange={e=>setHistoryQuery(e.target.value)}/><select aria-label="记录类型" value={historyKind} onChange={e=>{setHistoryKind(e.target.value as typeof historyKind)}}><option value="all">全部记录</option><option value="chat">聊天记录</option><option value="work">工作记录</option></select></div>}
 {recordError&&<small role="alert" className="nav-history-error">{recordError}</small>}
 {historyError&&<small role="alert">会话读取失败 <button type="button" onClick={()=>setRefresh(v=>v+1)}>重试</button></small>}
 {workError&&historyKind!=='chat'&&<small role="alert">工作记录读取失败 <button type="button" onClick={()=>setRefresh(v=>v+1)}>重试</button></small>}
 {dateGroups.map(d=>{const group=recent.filter(r=>(r.pinned?'置顶':dateGroup(r.time))===d);return group.length?<div key={d} className="nav-history-date"><small>{d}</small>{group.map(historyRow)}</div>:null})}
 {!recent.length&&!historyError&&<small>{historyLoading?'正在读取记录…':historyQuery?'暂无匹配记录':'暂无最近记录'}</small>}
 {allHistory&&historyKind!=='chat'&&<Link to="/work?history=1" onApproved={onClose}>查看录入记录</Link>}</section>
 <section className="nav-group clean-recent"><div className="clean-recent-heading"><span>最近录入</span><Link to="/intake" onApproved={onClose}>全部</Link></div>{docs.map(d=>{const path='/intake?doc='+encodeURIComponent(d.id);return <Link key={d.id} to={path} className={docId===d.id?'active':''} onApproved={onClose} title={d.title}><span className="nav-text"><MathText compact content={d.title}/></span></Link>})}{!docs.length&&<small>暂无最近文档</small>}</section></nav>
 <div className="side-foot" ref={dock}><div className="nav-fixed-tools">{tools.map(m=><Link key={m.path} to={m.path} title={m.name} aria-label={m.name} className={location.pathname===m.path?'active':''} onApproved={onClose}><Icon name={m.icon} size={17}/><span className="nav-text">{m.name}</span></Link>)}</div>
 {account&&<div className="account-popover"><div className="account-popover-heading"><strong>{user}</strong><small>个人教研空间</small></div><button onClick={async()=>{if(!await guardNavigation('/logout'))return;setAccount(false);onLogout()}}><Icon name="logout" size={17}/> 退出登录</button></div>}
 <button className="account-trigger" aria-expanded={account} aria-label="账号菜单" title={user} onClick={()=>setAccount(v=>!v)}><span className="avatar">{user.slice(0,1).toUpperCase()}</span><span className="account"><strong>{user}</strong><small>个人工作空间</small></span><Icon name="chevron" size={16}/></button></div>
 {phoneMenu}
 </aside>
}
