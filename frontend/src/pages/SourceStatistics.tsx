import {useEffect,useState,type FormEvent} from 'react'
import {api} from '../auth'
import {MathText} from '../components/MathText'
import {WorkspaceLink as Link} from '../components/WorkspaceNavigation'

type Source={source_id:string;title:string;institution:string;year:string;exam_type:string;category:string;source_type:string}
type Scope={source_ids:string[];years:string[];institutions:string[];categories:string[];exam_types:string[];source_types:string[];subject:string;all_sources:boolean}
type Stats={source_count:number;confirmed_complete_sources:number;question_count:number;source_question_count:number;questions_with_knowledge:number;knowledge_count:number;items:{subject:string;name:string;question_count:number;source_question_count:number}[];limit:number;offset:number}
const split=(s:string)=>Array.from(new Set(s.split(/[、，,]/).map(x=>x.trim()).filter(Boolean)))
const pageSize=30
export default function SourceStatistics(){
 const [mode,setMode]=useState<'filters'|'manual'>('filters')
 const [year,setYear]=useState(''),[institution,setInstitution]=useState(''),[category,setCategory]=useState(''),[exam,setExam]=useState(''),[sourceType,setSourceType]=useState('exam'),[subject,setSubject]=useState('')
 const [search,setSearch]=useState(''),[sourcePage,setSourcePage]=useState(0),[sources,setSources]=useState<Source[]>([]),[sourceTotal,setSourceTotal]=useState(0),[chosen,setChosen]=useState<Source[]>([]),[sourceError,setSourceError]=useState('')
 const [result,setResult]=useState<Stats>(),[applied,setApplied]=useState<Scope>(),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const [allowAll,setAllowAll]=useState(false)
 useEffect(()=>{
  if(mode!=='manual')return
  const controller=new AbortController()
  setSourceError('')
  setSources([])
  const p=new URLSearchParams({q:search,limit:String(pageSize),offset:String(sourcePage*pageSize)})
  for(const [key,values] of Object.entries({years:split(year),institutions:split(institution),categories:split(category),exam_types:split(exam),source_types:sourceType?[sourceType]:[]}))for(const value of values)p.append(key,value)
  const timer=window.setTimeout(()=>api<{items:Source[];total:number}>('/source-catalog/sources?'+p,{signal:controller.signal}).then(r=>{if(!controller.signal.aborted){setSources(r.items);setSourceTotal(r.total)}}).catch(e=>{if(!controller.signal.aborted)setSourceError(e.message)}),180)
  return()=>{clearTimeout(timer);controller.abort()}
 },[mode,search,sourcePage,year,institution,category,exam,sourceType])
 const scope:Scope={source_ids:mode==='manual'?chosen.map(s=>s.source_id):[],years:mode==='filters'?split(year):[],institutions:mode==='filters'?split(institution):[],categories:mode==='filters'?split(category):[],exam_types:mode==='filters'?split(exam):[],source_types:mode==='filters'&&sourceType?[sourceType]:[],subject:subject.trim(),all_sources:mode==='filters'&&allowAll}
 const valid=mode==='manual'?chosen.length>0:allowAll||Boolean(scope.years.length||scope.institutions.length||scope.categories.length||scope.exam_types.length||scope.source_types.length)
 async function run(s:Scope,offset=0){
  if(busy)return
  setBusy(true);setError('')
  try{const r=await api<Stats>('/source-catalog/statistics',{method:'POST',body:JSON.stringify({...s,limit:50,offset})});setResult(r);setApplied(s)}catch(e){setError(e instanceof Error?e.message:'统计失败')}finally{setBusy(false)}
 }
 function submit(e:FormEvent){e.preventDefault();if(valid)void run(scope)}
 function toggle(s:Source,checked:boolean){setChosen(old=>checked?old.some(x=>x.source_id===s.source_id)?old:old.length<1000?[...old,s]:old:old.filter(x=>x.source_id!==s.source_id))}
 const dirty=applied&&JSON.stringify(scope)!==JSON.stringify(applied)
 return <div className="source-statistics">
  <div className="page-heading"><Link to="/sources">← 返回来源库</Link><h1>知识点统计</h1><p className="muted">统计实际已入库题目及录入的知识点，不推测原始资料总题数。</p></div>
  <form className="panel resource-form" onSubmit={submit}>
   <div className="button-row"><button type="button" aria-pressed={mode==='filters'} onClick={()=>{setMode('filters');setSourcePage(0)}}>按条件统计</button><button type="button" aria-pressed={mode==='manual'} onClick={()=>{setMode('manual');setSourcePage(0)}}>自由选择资料</button></div>
   <div className="source-statistics-fields">
    <label>年份<input value={year} onChange={e=>{setYear(e.target.value);setSourcePage(0)}} placeholder="2026，2025"/></label>
    <label>院校或机构<input value={institution} onChange={e=>{setInstitution(e.target.value);setSourcePage(0)}} placeholder="郑州大学"/></label>
    <label>资料分类<input value={category} onChange={e=>{setCategory(e.target.value);setSourcePage(0)}} placeholder="院校真题"/></label>
    <label>考试类型<input value={exam} onChange={e=>{setExam(e.target.value);setSourcePage(0)}} placeholder="数学一"/></label>
    <label>来源类型<select value={sourceType} onChange={e=>{setSourceType(e.target.value);setSourcePage(0)}}><option value="">全部</option><option value="exam">试卷</option><option value="textbook">教材</option><option value="handout">讲义</option><option value="other">其他</option></select></label>
    <label>题目学科<input value={subject} onChange={e=>setSubject(e.target.value)} placeholder="不限"/></label>
   </div>
   <small className="muted">同一条件内可用逗号选择多个值；不同条件同时满足。院校名称按已确认的来源属性匹配。</small>
   {mode==='filters'?<label><input type="checkbox" checked={allowAll} onChange={e=>setAllowAll(e.target.checked)}/> 允许在未指定来源条件时统计全部资料</label>:<>
    <label>搜索资料<input value={search} onChange={e=>{setSearch(e.target.value);setSourcePage(0)}} placeholder="试卷名称或编号"/></label>
    <div className="button-row"><strong>已选 {chosen.length} 份</strong><button type="button" onClick={()=>setChosen([])}>清空选择</button></div>
    {chosen.length>0&&<details><summary>查看已选资料</summary>{chosen.map(s=><div className="source-statistics-source" key={s.source_id}><span><MathText content={s.title}/></span><button type="button" onClick={()=>toggle(s,false)}>移除</button></div>)}</details>}
    {sourceError&&<p role="alert">{sourceError}</p>}
    {sources.map(s=><label className="source-statistics-source" key={s.source_id}><input type="checkbox" checked={chosen.some(x=>x.source_id===s.source_id)} disabled={chosen.length>=1000&&!chosen.some(x=>x.source_id===s.source_id)} onChange={e=>toggle(s,e.target.checked)}/><span><MathText content={s.title}/><small>{[s.year,s.institution,s.exam_type].filter(Boolean).join(' · ')}</small></span></label>)}
    <div className="button-row"><button type="button" disabled={!sourcePage} onClick={()=>setSourcePage(p=>p-1)}>上一页</button><small>共 {sourceTotal} 份</small><button type="button" disabled={(sourcePage+1)*pageSize>=sourceTotal} onClick={()=>setSourcePage(p=>p+1)}>下一页</button></div>
    <small className="muted">选择可跨页保留，筛选条件只影响待选列表，统计仅使用已选资料与题目学科。</small>
   </>}
   <button className="primary" disabled={!valid||busy}>{busy?'统计中…':'开始统计'}</button>
  </form>
  {error&&<p role="alert">{error}</p>}
  {result&&<section className="panel"><h2>统计结果</h2>{dirty&&<p role="status" className="muted">筛选条件已变化，当前仍显示上次统计结果。</p>}
   <div className="source-overview-grid source-statistics-fields">
    {[[result.source_count,'选中来源'],[result.question_count,'独立题目'],[result.source_question_count,'题目—来源关联'],[result.knowledge_count,'不同知识点'],[result.questions_with_knowledge,'已标注知识点的题目'],[result.confirmed_complete_sources,'人工确认录入完成的来源']].map(([n,label])=><div key={label}><strong>{n}</strong><small>{label}</small></div>)}
   </div>
   <p className="muted">原件总题数：未知。题目—来源关联按不同试卷与题目的组合计算，同一试卷内重复位置不计为多份试卷；知识点可重叠。</p>
   <table className="source-statistics-table"><thead><tr><th>学科</th><th>知识点</th><th>题目数</th><th>来源关联</th></tr></thead><tbody>{result.items.map(r=><tr key={JSON.stringify([r.subject,r.name])}><td>{r.subject||'未分类'}</td><td><MathText content={r.name}/></td><td>{r.question_count}</td><td>{r.source_question_count}</td></tr>)}</tbody></table>
   {!result.items.length&&<p className="muted">当前范围内没有已录入的知识点。</p>}
   <div className="button-row"><button disabled={busy||result.offset===0} onClick={()=>applied&&void run(applied,Math.max(0,result.offset-result.limit))}>上一页</button><small>共 {result.knowledge_count} 项</small><button disabled={busy||result.offset+result.limit>=result.knowledge_count} onClick={()=>applied&&void run(applied,result.offset+result.limit)}>下一页</button></div>
  </section>}
 </div>
}
