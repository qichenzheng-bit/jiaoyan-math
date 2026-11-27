import {useEffect,useState,type FormEvent} from 'react'
import {useParams} from 'react-router-dom'
import {api} from '../auth'
import {MathText} from '../components/MathText'
import {WorkspaceLink as Link,useWorkspaceGuard} from '../components/WorkspaceNavigation'
type Meta={source_id:string;title:string;code:string;source_type:string;year:string;exam_type:string;edition:string;series_key:string;archived:boolean;revision:number;category:string;institution:string;subject_code:string;subjects:string[];author:string;publisher:string;intake_status:string}
const statuses:Record<string,string>={unknown:'未确认',not_started:'未开始',in_progress:'录入中',completed:'人工确认完成',stopped:'停止录入'}
function useMeta(id:string){
 const [meta,setMeta]=useState<Meta>(),[error,setError]=useState('')
 useEffect(()=>{const c=new AbortController();setMeta(undefined);setError('');api<Meta>('/source-catalog/sources/'+encodeURIComponent(id),{signal:c.signal}).then(m=>{if(!c.signal.aborted&&Array.isArray(m.subjects))setMeta(m)}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[id])
 return {meta,setMeta,error,setError}
}
type FileProgress={file_id:string;name:string;media_type:string;archived:boolean;purged:boolean;total_units:number|null;recognized_units:number;verified_units:number;registered_units:number;recognized_ranges:number[][];verified_ranges:number[][];registered_ranges:number[][];unverified_ranges:number[][]|null;batches:number}
const ranges=(value:number[][]|null)=>value===null?'未知':value.length?value.map(([a,b])=>a===b?String(a):a+'–'+b).join('、'):'无'
function SourceFileProgress({id}:{id:string}){
 const [open,setOpen]=useState(false),[items,setItems]=useState<FileProgress[]>(),[error,setError]=useState('')
 useEffect(()=>{if(!open)return;const c=new AbortController();setItems(undefined);setError('');api<{items:FileProgress[]}>('/source-catalog/sources/'+encodeURIComponent(id)+'/file-progress',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setItems(r.items)}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[id,open])
 return <details className="bank-section" onToggle={e=>setOpen(e.currentTarget.open)}><summary>原始文件与录入进度</summary>
 <p className="muted">仅显示已经明确关联本资料的识别批次。文件总页数与原题总数不是同一概念，原题总数未知。</p>
 {error?<p role="alert">{error}</p>:!items?<p>读取中…</p>:!items.length?<p>暂无已确认关联的原始文件批次。未关联不等于未录入。</p>:items.map(f=>{const unit=f.media_type==='application/pdf'?'页':'识别单元';return <section className="source-statistics-report-row" key={f.file_id}><strong>{f.name}</strong><small>{f.purged?'原件已清理，历史记录保留':f.archived?'原件已归档':'原件已保留'} · {f.batches} 个关联批次</small><p>文件总{unit}数：{f.total_units??'未知'}</p><p>已识别：{f.recognized_units} · 已核对：{f.verified_units} · 已正式登记：{f.registered_units}</p><small>已识别范围：{ranges(f.recognized_ranges)}</small><small>已核对范围：{ranges(f.verified_ranges)}</small><small>已登记范围：{ranges(f.registered_ranges)}</small><small>本来源尚无核对记录的范围：{ranges(f.unverified_ranges)}</small></section>})}
 <Link to="/original-library">打开原始资料库</Link></details>
}
export function SourceCatalogSummary({id,archived}:{id:string;archived:boolean}){
 const {meta,error}=useMeta(id)
 return <section className="bank-section source-catalog-summary"><div className="panel-heading"><h3>资料属性</h3>{!archived&&<Link className="button-link" to={'/source-catalog/'+encodeURIComponent(id)}>编辑资料属性</Link>}</div>{error?<small role="status">资料属性暂不可读取</small>:meta?<><p className="muted">{[meta.category||'分类未确认',meta.institution,meta.subject_code,meta.year,meta.edition].filter(Boolean).join(' · ')}</p><p>学科：{meta.subjects.join('、')||'未确认'}</p><p>录入状态：{statuses[meta.intake_status]||'未确认'}</p><small className="muted">仅统计已入库资源，不推测原件总题数。</small></>:<small>正在读取资料属性…</small>}<SourceFileProgress key={id} id={id}/></section>
}
export default function SourceCatalog(){
 const {id=''}=useParams(),{meta,setMeta,error,setError}=useMeta(id)
 const [draft,setDraft]=useState<Meta>(),[subjects,setSubjects]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('')
 const [history,setHistory]=useState<{id:string;created_at:number;revision:number;before:Meta;after:Meta}[]>([])
 useEffect(()=>{if(meta){setDraft(meta);setSubjects(meta.subjects.join('、'))}},[meta])
 useEffect(()=>{const c=new AbortController();api<{items:typeof history}>('/source-catalog/sources/'+encodeURIComponent(id)+'/history',{signal:c.signal}).then(r=>{if(!c.signal.aborted&&Array.isArray(r.items))setHistory(r.items)}).catch(()=>{});return()=>c.abort()},[id,meta?.revision])
 const dirty=Boolean(meta&&draft&&(JSON.stringify(meta)!==JSON.stringify(draft)||subjects!==meta.subjects.join('、')))
 useWorkspaceGuard({busy,dirty,message:'资料属性尚未保存，确认离开？'})
 async function save(e:FormEvent){e.preventDefault();if(!draft||busy)return;setBusy(true);setError('');setNotice('');try{const r=await api<Meta>('/source-catalog/sources/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify({...draft,subjects:subjects.split(/[、，,]/).map(s=>s.trim()).filter(Boolean)})});setMeta(r);setNotice('资料属性已保存')}catch(e){setError(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}}
 const fields=[['category','细分类别',60],['institution','院校或机构',120],['subject_code','考试科目代码',40],['author','作者',180],['publisher','出版社',180]] as const
 return <div className="source-catalog-editor"><div className="page-heading"><Link to={meta?'/sources?q='+encodeURIComponent(meta.code):'/sources'}>← 返回来源库</Link><h1>编辑资料属性</h1>{meta&&<p><MathText content={meta.title}/></p>}</div>{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}{draft&&<form className="panel resource-form" onSubmit={save}><p className="muted">年份、版次、考试类别继续使用来源原有字段；此处补充结构化信息。不确定的信息请留空。</p>{fields.map(([k,label,max])=><label key={k}>{label}<input maxLength={max} disabled={busy||draft.archived} value={draft[k]} onChange={e=>setDraft(d=>d&&({...d,[k]:e.target.value}))}/></label>)}<label>涉及学科（顿号分隔）<input value={subjects} disabled={busy||draft.archived} onChange={e=>setSubjects(e.target.value)} placeholder="高等数学、线性代数"/></label><label>录入状态<select value={draft.intake_status} disabled={busy||draft.archived} onChange={e=>setDraft(d=>d&&({...d,intake_status:e.target.value}))}>{Object.entries(statuses).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label><p className="muted">已完成仅表示人工确认；不会自动扫描文件或计算剩余题数。</p><button className="primary" disabled={busy||draft.archived||!dirty}>保存资料属性</button></form>}{history.length>0&&<section className="panel"><h2>属性修改记录</h2>{history.map(h=><details key={h.id}><summary>版本 {h.revision} · {new Date(h.created_at*1000).toLocaleString()}</summary>{fields.map(([k,label])=>h.before[k]!==h.after[k]?<p key={k}>{label}：{h.before[k]||'未确认'} → {h.after[k]||'未确认'}</p>:null)}<p>录入状态：{statuses[h.before.intake_status]} → {statuses[h.after.intake_status]}</p></details>)}</section>}</div>
}
