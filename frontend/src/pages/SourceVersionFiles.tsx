import {useEffect,useState} from 'react'
import {api} from '../auth'
import {MathText} from '../components/MathText'
import {confirmAction} from '../components/WorkspaceConfirm'
type Role='original'|'supplement'|'correction'
const roles:Record<Role,string>={original:'原始文件',supplement:'补充资料',correction:'勘误文件'}
type Binding={id:string;version:number;file_id:string;file_name:string;file_archived:boolean;file_purged:boolean;role:Role;note:string;active:boolean;created_at:number;unbound_at:number|null}
type State={revision:number;source_revision:number;archived:boolean;versions:{version:number;title:string;edition:string;created_at:number}[];items:Binding[]}
type Original={id:string;name:string;total_units:number|null}
export default function SourceVersionFiles({id}:{id:string}){
 const [open,setOpen]=useState(false),[state,setState]=useState<State>(),[version,setVersion]=useState(0),[role,setRole]=useState<Role>('original'),[note,setNote]=useState('')
 const [query,setQuery]=useState(''),[files,setFiles]=useState<Original[]>([]),[page,setPage]=useState(0),[total,setTotal]=useState(0),[chosen,setChosen]=useState<Original>(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[fileError,setFileError]=useState('')
 const path='/source-catalog/sources/'+encodeURIComponent(id)+'/version-files'
 useEffect(()=>{if(!open)return;const c=new AbortController();api<State>(path,{signal:c.signal}).then(r=>{if(!c.signal.aborted){setState(r);setVersion(v=>v||r.versions[0]?.version||0)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[open,path])
 useEffect(()=>{if(!open||!state||state.archived)return;const c=new AbortController();setFiles([]);setFileError('');const timer=window.setTimeout(()=>api<{items:Original[];total:number}>('/workspaces/library?'+new URLSearchParams({q:query,limit:'20',offset:String(page*20)}),{signal:c.signal}).then(r=>{if(!c.signal.aborted){setFiles(r.items);setTotal(r.total)}}).catch(e=>{if(!c.signal.aborted)setFileError(e.message)}),180);return()=>{clearTimeout(timer);c.abort()}},[open,state?.archived,query,page])
 async function bind(){if(!state||!chosen||!version||busy)return;setBusy(true);setError('');try{setState(await api<State>(path,{method:'POST',body:JSON.stringify({revision:state.revision,version,file_id:chosen.id,role,note})}));setChosen(undefined);setNote('')}catch(e){setError(e instanceof Error?e.message:'关联失败')}finally{setBusy(false)}}
 async function unbind(b:Binding){if(!state||busy||!await confirmAction('解除当前版本的文件关联？不会删除原件或已入库题目，历史记录仍保留。'))return;setBusy(true);setError('');try{setState(await api<State>(path+'/'+encodeURIComponent(b.id)+'/unbind',{method:'POST',body:JSON.stringify({revision:state.revision})}))}catch(e){setError(e instanceof Error?e.message:'解除失败')}finally{setBusy(false)}}
 return <details className="bank-section" onToggle={e=>setOpen(e.currentTarget.open)}><summary>资料版本与原件关联</summary><p className="muted">这里的版本为同一来源的修订快照，不等同于不同出版版次；不同版次应建立独立来源。绑定文件不会自动登记题目或确认录入完成。</p>
 {error&&<p role="alert">{error}</p>}{open&&!state&&!error&&<p>读取中…</p>}
 {state&&<>{state.items.filter(b=>b.active).map(b=><div className="source-statistics-report-row" key={b.id}><strong><MathText content={b.file_name}/></strong><small>版本 {b.version} · {roles[b.role]} · {b.file_purged?'原件已清理':b.file_archived?'原件已归档':'原件保留'}</small>{b.note&&<MathText content={b.note}/>}<button type="button" disabled={busy||state.archived} onClick={()=>void unbind(b)}>解除关联</button></div>)}
 {!state.items.some(b=>b.active)&&<p className="muted">尚未手动绑定原件。</p>}
 {state.items.some(b=>!b.active)&&<details><summary>历史解除记录</summary>{state.items.filter(b=>!b.active).map(b=><p key={b.id}><MathText content={b.file_name}/> · 版本 {b.version} · {b.unbound_at?new Date(b.unbound_at*1000).toLocaleString():''}</p>)}</details>}
 {!state.archived&&<div className="resource-form"><label>目标资料版本<select value={version} disabled={busy} onChange={e=>setVersion(Number(e.target.value))}>{state.versions.map(v=><option key={v.version} value={v.version}>版本 {v.version} {v.edition||''}</option>)}</select></label><label>文件用途<select value={role} disabled={busy} onChange={e=>setRole(e.target.value as Role)}>{Object.entries(roles).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><label>搜索原始资料库<input value={query} disabled={busy} onChange={e=>{setQuery(e.target.value);setPage(0)}}/></label>{fileError&&<p role="alert">{fileError}</p>}
 {files.map(f=><label className="source-statistics-source" key={f.id}><input type="radio" name={'source-file-'+id} checked={chosen?.id===f.id} disabled={busy} onChange={()=>setChosen(f)}/><span>{f.name}<small>{f.total_units===null?'总单元数未知':f.total_units+' 个识别单元'}</small></span></label>)}
 <div className="button-row"><button type="button" disabled={busy||!page} onClick={()=>setPage(p=>p-1)}>上一页</button><small>共 {total} 份</small><button type="button" disabled={busy||(page+1)*20>=total} onClick={()=>setPage(p=>p+1)}>下一页</button></div>{chosen&&<p>已选：{chosen.name}</p>}<label>备注<input maxLength={300} value={note} disabled={busy} onChange={e=>setNote(e.target.value)}/></label><button className="primary" type="button" disabled={busy||!chosen||!version} onClick={()=>void bind()}>绑定到所选版本</button></div>}</>}
 </details>
}
