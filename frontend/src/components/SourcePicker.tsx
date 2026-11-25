import {useEffect,useState} from 'react'
import {api} from '../auth'
import {MathChoice,MathText} from './MathText'
import {Icon} from './Icon'
export type Source={id:string;code:string;title:string;subject:string;source_type:string;exam_type:string;cohort_year:string;edition:string;series_key:string;archived:boolean}
export const sourceTypes=[['exam','试卷'],['textbook','教材'],['handout','讲义'],['other','其他']]
export function sourceLabel(s:Source){return [s.code,s.title,s.cohort_year,s.exam_type,s.edition].filter(Boolean).join(' · ')}
type Props={value:string;onChange:(id:string,source?:Source)=>void;disabled?:boolean;allowCreate?:boolean;subject?:string}
export default function SourcePicker({value,onChange,disabled=false,allowCreate=true,subject=''}:Props){
 const [q,setQ]=useState(''),[rows,setRows]=useState<Source[]>([]),[selected,setSelected]=useState<Source>(),[error,setError]=useState(''),[loading,setLoading]=useState(false),[version,setVersion]=useState(0),[creating,setCreating]=useState(false),[busy,setBusy]=useState(false),[total,setTotal]=useState(0)
 const [title,setTitle]=useState(''),[type,setType]=useState('exam'),[year,setYear]=useState(''),[exam,setExam]=useState(''),[edition,setEdition]=useState(''),[notes,setNotes]=useState(''),[matches,setMatches]=useState<Source[]|null>(null)
 useEffect(()=>{const c=new AbortController();setLoading(true);setError('');api<{items:Source[];total:number}>('/resources?'+new URLSearchParams({kind:'source',q,limit:'30'}),{signal:c.signal}).then(r=>{if(!c.signal.aborted){setRows(r.items);setTotal(r.total)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)}).finally(()=>{if(!c.signal.aborted)setLoading(false)});return()=>c.abort()},[q,version])
 useEffect(()=>{if(!value){setSelected(undefined);return}const c=new AbortController();api<Source>('/resources/'+encodeURIComponent(value),{signal:c.signal}).then(s=>{if(!c.signal.aborted)setSelected(s)}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[value])
 const draft={kind:'source',title,subject,source_type:type,cohort_year:year,exam_type:exam,edition,content:notes.trim()||title}
 function pick(id:string){const s=rows.find(r=>r.id===id)??(selected?.id===id?selected:undefined)??matches?.find(r=>r.id===id);setSelected(s);onChange(id,s);setCreating(false);setMatches(null)}
 async function create(){if(!title.trim()||busy)return;setBusy(true);setError('');try{const found=await api<Source[]>('/resources/source-matches',{method:'POST',body:JSON.stringify(draft)});setMatches(found);if(found.length)return;const s=await api<Source>('/resources',{method:'POST',body:JSON.stringify(draft)});setSelected(s);onChange(s.id,s);setCreating(false);setVersion(v=>v+1)}catch(e){setError(e instanceof Error?e.message:'来源创建失败')}finally{setBusy(false)}}
 const options=[{value:'',label:'暂不绑定来源'},...(selected&&value===selected.id&&!rows.some(r=>r.id===selected.id)?[{value:selected.id,label:sourceLabel(selected)}]:[]),...rows.map(s=>({value:s.id,label:sourceLabel(s)}))]
 return <div className="source-picker"><div className="source-picker-head"><strong>来源资料</strong>{allowCreate&&<button type="button" disabled={disabled||busy} onClick={()=>{setCreating(v=>!v);setMatches(null)}}><Icon name="plus" size={15}/> {creating?'取消新建':'登记新来源'}</button>}</div>
 <input aria-label="搜索已有来源" placeholder="搜索试卷、教材、讲义或编号" maxLength={200} value={q} disabled={disabled} onChange={e=>setQ(e.target.value)}/>
 <MathChoice label="选择来源资料" value={value} disabled={disabled||busy} onChange={pick} options={options}/>
 <small className="muted">{loading?'正在检索…':total>30?'显示前30项，请缩小检索范围':total+' 项可选来源'}。选择已有来源不会修改原资料。</small>
 {selected?.id===value&&<div className="source-selected"><MathText compact content={sourceLabel(selected)}/><small>{selected.subject||'未分类'}{selected.archived?' · 已归档，不可使用':''}</small></div>}
 {creating&&<div className="source-create-fields"><label>资料名称<input maxLength={200} value={title} disabled={disabled||busy} onChange={e=>{setTitle(e.target.value);setMatches(null)}}/></label><div className="resource-meta-grid"><label>资料类型<select value={type} disabled={disabled||busy} onChange={e=>{setType(e.target.value);setMatches(null)}}>{sourceTypes.map(([k,n])=><option key={k} value={k}>{n}</option>)}</select></label><label>年份<input maxLength={12} value={year} onChange={e=>{setYear(e.target.value);setMatches(null)}} disabled={busy||disabled}/></label><label>考试类别<input maxLength={80} value={exam} onChange={e=>{setExam(e.target.value);setMatches(null)}} disabled={busy||disabled}/></label><label>版次<input maxLength={60} value={edition} onChange={e=>{setEdition(e.target.value);setMatches(null)}} disabled={busy||disabled}/></label></div><label>资料说明<textarea rows={2} maxLength={1000} value={notes} onChange={e=>setNotes(e.target.value)} disabled={busy||disabled}/></label>
 <button type="button" className="primary" disabled={disabled||busy||!title.trim()} onClick={()=>void create()}>{busy?'检查中…':'查重并登记来源'}</button>
 {matches&&matches.length>0&&<div className="source-matches"><strong>发现可能相同的来源，请复用或核对资料信息</strong>{matches.map(s=><button key={s.id} type="button" disabled={s.archived||busy||disabled} onClick={()=>pick(s.id)}><MathText compact content={sourceLabel(s)}/><small>{s.archived?'已归档，请到来源资料恢复':'使用此来源'}</small></button>)}</div>}</div>}
 {error&&<p role="alert" className="inline-error">{error}</p>}</div>
}
