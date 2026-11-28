import {useEffect,useState,type FormEvent} from 'react'
import {api} from '../auth'
import {MathText} from '../components/MathText'
import StatisticsDistribution from './StatisticsDistribution'
import {WorkspaceLink as Link} from '../components/WorkspaceNavigation'

type Source={source_id:string;title:string;institution:string;year:string;exam_type:string;category:string;source_type:string}
type Scope={source_ids:string[];years:string[];institutions:string[];categories:string[];exam_types:string[];source_types:string[];subject:string;all_sources:boolean}
type SavedScope={id:string;name:string;scope:Scope;created_at:number}
type Topic={subject:string;name:string}
type Drill={total:number;offset:number;limit:number;items:{id:string;code:string;title:string;subject:string;question_type:string;source_count:number;revision:number}[]}
type ReportRow={group_name:string;source_count:number;confirmed_complete_sources:number;question_count:number;source_question_count:number;questions_with_knowledge:number;knowledge_count:number;topic_question_count:number;topic_source_question_count:number}
type Report={items:ReportRow[];total:number;offset:number;limit:number;dimension:'year'|'institution'|'exam_type';knowledge_name:string;knowledge_subject:string}
type Stats={source_count:number;confirmed_complete_sources:number;question_count:number;source_question_count:number;questions_with_knowledge:number;knowledge_count:number;items:{subject:string;name:string;question_count:number;source_question_count:number}[];limit:number;offset:number}
const split=(s:string)=>Array.from(new Set(s.split(/[、，,]/).map(x=>x.trim()).filter(Boolean)))
const pageSize=30
export default function SourceStatistics(){
 const [mode,setMode]=useState<'filters'|'manual'>('filters')
 const [year,setYear]=useState(''),[institution,setInstitution]=useState(''),[category,setCategory]=useState(''),[exam,setExam]=useState(''),[sourceType,setSourceType]=useState('exam'),[subject,setSubject]=useState('')
 const [search,setSearch]=useState(''),[sourcePage,setSourcePage]=useState(0),[sources,setSources]=useState<Source[]>([]),[sourceTotal,setSourceTotal]=useState(0),[chosen,setChosen]=useState<Source[]>([]),[sourceError,setSourceError]=useState('')
 const [result,setResult]=useState<Stats>(),[applied,setApplied]=useState<Scope>(),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const [allowAll,setAllowAll]=useState(false)
 const [saved,setSaved]=useState<SavedScope[]>([]),[scopeName,setScopeName]=useState(''),[saveBusy,setSaveBusy]=useState(false),[saveError,setSaveError]=useState('')
 const [topic,setTopic]=useState<Topic>(),[drill,setDrill]=useState<Drill>(),[drillBusy,setDrillBusy]=useState(false),[drillError,setDrillError]=useState('')
 const [report,setReport]=useState<Report>(),[dimension,setDimension]=useState<Report['dimension']>('year'),[reportTopic,setReportTopic]=useState<Topic>(),[reportBusy,setReportBusy]=useState(false),[reportError,setReportError]=useState('')
 const [picked,setPicked]=useState<string[]>([]),[cartBusy,setCartBusy]=useState(false),[cartNotice,setCartNotice]=useState('')
 useEffect(()=>{const c=new AbortController();api<{items:SavedScope[]}>('/source-catalog/statistics/scopes',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setSaved(r.items)}).catch(e=>{if(!c.signal.aborted)setSaveError(e.message)});return()=>c.abort()},[])
 async function saveCurrent(){
  if(!applied||!scopeName.trim()||saveBusy)return
  setSaveBusy(true);setSaveError('')
  try{const r=await api<SavedScope>('/source-catalog/statistics/scopes',{method:'POST',body:JSON.stringify({name:scopeName.trim(),scope:applied})});setSaved(old=>[r,...old]);setScopeName('')}catch(e){setSaveError(e instanceof Error?e.message:'保存失败')}finally{setSaveBusy(false)}
 }
 async function removeScope(id:string){
  if(saveBusy)return
  setSaveBusy(true);setSaveError('')
  try{const r=await api<{items:SavedScope[]}>('/source-catalog/statistics/scopes/'+encodeURIComponent(id),{method:'DELETE'});setSaved(r.items)}catch(e){setSaveError(e instanceof Error?e.message:'删除失败')}finally{setSaveBusy(false)}
 }
 async function showQuestions(t:Topic,offset=0){
  if(!applied||drillBusy||busy)return
  if(!topic||topic.name!==t.name||topic.subject!==t.subject){setPicked([]);setCartNotice('')}
  setTopic(t);setDrillBusy(true);setDrillError('');setDrill(undefined)
  try{setDrill(await api<Drill>('/source-catalog/statistics/questions',{method:'POST',body:JSON.stringify({...applied,knowledge_name:t.name,knowledge_subject:t.subject,limit:30,offset})}))}catch(e){setDrillError(e instanceof Error?e.message:'读取题目失败')}finally{setDrillBusy(false)}
 }
 async function runReport(offset=0,exportFile=false){
  if(!applied||reportBusy||busy)return
  setReportBusy(true);setReportError('')
  const payload={...applied,dimension,knowledge_name:reportTopic?.name??'',knowledge_subject:reportTopic?.subject??'',limit:30,offset}
  try{
   if(exportFile){
    const response=await fetch('/api/source-catalog/statistics/report/export',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
    if(!response.ok){const e=await response.json().catch(()=>null);throw Error(e?.detail||'导出失败')}
    const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download='knowledge-statistics.csv';a.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
   }else setReport(await api<Report>('/source-catalog/statistics/report',{method:'POST',body:JSON.stringify(payload)}))
  }catch(e){setReportError(e instanceof Error?e.message:'报告生成失败')}finally{setReportBusy(false)}
 }
 async function addToCart(){
  if(!picked.length||cartBusy)return
  setCartBusy(true);setCartNotice('')
  try{const old=await api<{revision:number;ids:string[]}>('/bank/cart');const ids=Array.from(new Set([...old.ids,...picked]));if(ids.length>200)throw Error('选题清单最多200道，请减少选择');await api('/bank/cart',{method:'PUT',body:JSON.stringify({revision:old.revision,ids})});setCartNotice('已加入选题清单');setPicked([])}catch(e){setCartNotice(e instanceof Error?e.message:'加入失败')}finally{setCartBusy(false)}
 }
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
  if(busy||drillBusy||cartBusy||reportBusy)return
  setBusy(true);setError('');setTopic(undefined);setDrill(undefined);setPicked([]);setCartNotice('');setReport(undefined);setReportTopic(undefined)
  try{const r=await api<Stats>('/source-catalog/statistics',{method:'POST',body:JSON.stringify({...s,limit:50,offset})});setResult(r);setApplied(s)}catch(e){setError(e instanceof Error?e.message:'统计失败')}finally{setBusy(false)}
 }
 function submit(e:FormEvent){e.preventDefault();if(valid)void run(scope)}
 function toggle(s:Source,checked:boolean){setChosen(old=>checked?old.some(x=>x.source_id===s.source_id)?old:old.length<1000?[...old,s]:old:old.filter(x=>x.source_id!==s.source_id))}
 const dirty=applied&&JSON.stringify(scope)!==JSON.stringify(applied)
 return <div className="source-statistics">
  <div className="page-heading"><Link to="/sources">← 返回来源库</Link><h1>知识标签统计</h1><p className="muted">统计实际已入库题目及录入的知识标签，不推测原始资料总题数。</p></div>
  <section className="panel"><h2>已保存方案</h2>{saveError&&<p role="alert">{saveError}</p>}{!saved.length&&<p className="muted">暂无方案。完成一次统计后可保存其筛选范围。</p>}{saved.map(s=><div className="source-statistics-source" key={s.id}><span>{s.name}</span><button disabled={busy||drillBusy||cartBusy||saveBusy} onClick={()=>void run(s.scope)}>运行</button><button disabled={saveBusy} onClick={()=>void removeScope(s.id)}>删除</button></div>)}<small className="muted">按条件保存的方案会包含未来新入库且符合条件的资料；自由选择方案只包含选定的来源。</small></section>
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
    {[[result.source_count,'选中来源'],[result.question_count,'独立题目'],[result.source_question_count,'题目—来源关联'],[result.knowledge_count,'不同知识标签'],[result.questions_with_knowledge,'已标注知识标签的题目'],[result.confirmed_complete_sources,'人工确认录入完成的来源']].map(([n,label])=><div key={label}><strong>{n}</strong><small>{label}</small></div>)}
   </div>
   <p className="muted">原件总题数：未知。题目—来源关联按不同试卷与题目的组合计算，同一试卷内重复位置不计为多份试卷；知识标签可重叠。</p>
   <table className="source-statistics-table"><thead><tr><th>学科</th><th>知识标签</th><th>题目数</th><th>来源关联</th></tr></thead><tbody>{result.items.map(r=><tr key={JSON.stringify([r.subject,r.name])}><td>{r.subject||'未分类'}</td><td><button type="button" className="text-link" disabled={busy||drillBusy||cartBusy} onClick={()=>void showQuestions(r)}><MathText content={r.name}/></button></td><td>{r.question_count}</td><td>{r.source_question_count}</td></tr>)}</tbody></table>
   {!result.items.length&&<p className="muted">当前范围内没有已录入的知识标签。</p>}
   <div className="button-row"><input aria-label="统计方案名称" placeholder="输入方案名称" maxLength={80} value={scopeName} onChange={e=>setScopeName(e.target.value)}/><button disabled={saveBusy||busy||!scopeName.trim()} onClick={()=>void saveCurrent()}>保存本次统计方案</button></div>
   <div className="button-row"><button disabled={busy||reportBusy||result.offset===0} onClick={()=>applied&&void run(applied,Math.max(0,result.offset-result.limit))}>上一页</button><small>共 {result.knowledge_count} 项</small><button disabled={busy||result.offset+result.limit>=result.knowledge_count} onClick={()=>applied&&void run(applied,result.offset+result.limit)}>下一页</button></div>
  </section>}
  {result&&<section className="panel">
   <h2>考情对比</h2><div className="source-statistics-fields"><label>对比维度<select value={dimension} disabled={reportBusy} onChange={e=>{setDimension(e.target.value as Report['dimension']);setReport(undefined)}}><option value="year">历年趋势</option><option value="institution">院校对比</option><option value="exam_type">考试类型</option></select></label>
   <label>关注知识标签<select value={reportTopic?JSON.stringify([reportTopic.subject,reportTopic.name]):''} disabled={reportBusy} onChange={e=>{const v=e.target.value?JSON.parse(e.target.value):null;setReportTopic(v?{subject:v[0],name:v[1]}:undefined);setReport(undefined)}}><option value="">全部知识标签</option>{result.items.map(r=><option key={JSON.stringify([r.subject,r.name])} value={JSON.stringify([r.subject,r.name])}>{r.subject} · {r.name}</option>)}</select></label></div>
   <div className="button-row"><button className="primary" disabled={busy||reportBusy} onClick={()=>void runReport()}>生成对比报告</button><button disabled={busy||reportBusy} onClick={()=>void runReport(0,true)}>导出完整 CSV 报告</button></div>
   {reportError&&<p role="alert">{reportError}</p>}{reportBusy&&<p role="status">统计中…</p>}
   {report&&<><p className="muted">当前为各分组已入库统计。未完成录入或未标注的题目不能用于推断未考查；跨组重复题目不应直接求和。</p>{report.items.map(r=><div className="source-statistics-report-row" key={r.group_name}><strong>{r.group_name||'未确认'}</strong><span>{r.source_count} 份来源 · {r.confirmed_complete_sources} 份人工确认完成</span><span>{r.question_count} 道独立题目 · {r.questions_with_knowledge} 道已标注 · {r.knowledge_count} 个知识标签</span>{report.knowledge_name&&<span>指定知识标签：{r.topic_question_count} 道 · {r.topic_source_question_count} 组来源关联</span>}<div className="source-statistics-report-track"><div style={{width:((report.knowledge_name?r.topic_question_count:r.question_count)/Math.max(1,...report.items.map(x=>report.knowledge_name?x.topic_question_count:x.question_count))*100)+'%'}}/></div></div>)}
   {!report.items.length&&<p className="muted">暂无符合条件的来源。</p>}<small className="muted">条形长度按当前页的最大记录数比较。</small>
   <div className="button-row"><button disabled={reportBusy||!report.offset} onClick={()=>void runReport(Math.max(0,report.offset-report.limit))}>上一页</button><small>共 {report.total} 组</small><button disabled={reportBusy||report.offset+report.limit>=report.total} onClick={()=>void runReport(report.offset+report.limit)}>下一页</button></div></>}
  </section>}
  {result&&applied&&<StatisticsDistribution key={JSON.stringify([applied,result.offset])} scope={applied} topics={result.items}/>}
  {topic&&<section className="panel"><div className="button-row"><h2><MathText content={topic.name}/> · 关联题目</h2><button disabled={drillBusy||cartBusy} onClick={()=>{setTopic(undefined);setDrill(undefined);setPicked([])}}>关闭</button></div>
   {drillError&&<p role="alert">{drillError}</p>}{drillBusy&&<p role="status">读取题目中…</p>}
   {drill&&<><p className="muted">当前统计范围内共 {drill.total} 道独立题目</p>{drill.items.map(q=><div className="source-statistics-source" key={q.id}><input type="checkbox" aria-label={'选择 '+q.code} checked={picked.includes(q.id)} disabled={cartBusy||(!picked.includes(q.id)&&picked.length>=200)} onChange={e=>setPicked(old=>e.target.checked?[...old,q.id]:old.filter(id=>id!==q.id))}/><span><Link to={'/resources?q='+encodeURIComponent(q.code)}><MathText content={q.title||q.code}/></Link><small>{q.code} · {q.question_type||'题型未确认'} · {q.source_count} 份来源</small></span></div>)}
   <div className="button-row"><button disabled={drillBusy||cartBusy||!drill.offset} onClick={()=>void showQuestions(topic,Math.max(0,drill.offset-drill.limit))}>上一页</button><button disabled={drillBusy||cartBusy||drill.offset+drill.limit>=drill.total} onClick={()=>void showQuestions(topic,drill.offset+drill.limit)}>下一页</button></div></>}
   <div className="button-row"><button className="primary" disabled={cartBusy||drillBusy||!picked.length} onClick={()=>void addToCart()}>加入选题清单（{picked.length}）</button><Link to="/resources">打开题库</Link></div>{cartNotice&&<p role="status">{cartNotice}</p>}
  </section>}
 </div>
}
