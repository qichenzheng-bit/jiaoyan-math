import {useEffect,useState} from 'react'
import {api} from '../auth'
import {MathText} from '../components/MathText'
type Topic={subject:string;name:string}
type Dimension='question_type'|'method'|'cooccurrence'
type Distribution={question_count:number;classified_questions:number;total:number;limit:number;offset:number;items:{subject:string;name:string;question_count:number;source_question_count:number}[]}
const labels:Record<Dimension,string>={question_type:'题型分布',method:'解析中的方法名称',cooccurrence:'知识标签共现'}
export default function StatisticsDistribution({scope,topics}:{scope:object;topics:Topic[]}){
 const [dimension,setDimension]=useState<Dimension>('question_type'),[focus,setFocus]=useState<Topic>(),[search,setSearch]=useState(''),[result,setResult]=useState<Distribution>(),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const [request,setRequest]=useState<{dimension:Dimension;focus?:Topic;offset:number}>()
 useEffect(()=>{
  if(!request)return
  const c=new AbortController()
  setBusy(true);setError('')
  api<Distribution>('/source-catalog/statistics/distribution',{method:'POST',signal:c.signal,body:JSON.stringify({...scope,dimension:request.dimension,knowledge_name:request.focus?.name??'',knowledge_subject:request.focus?.subject??'',limit:30,offset:request.offset})})
    .then(r=>{if(!c.signal.aborted)setResult(r)})
    .catch(e=>{if(!c.signal.aborted){setError(e.message);setResult(undefined)}})
    .finally(()=>{if(!c.signal.aborted)setBusy(false)})
  return()=>c.abort()
 },[request,scope])
 function changeDimension(d:Dimension){setDimension(d);setResult(undefined);setRequest(undefined)}
 function changeFocus(t?:Topic){setFocus(t);setResult(undefined);setRequest(undefined)}
 function run(offset=0){if(dimension==='cooccurrence'&&!focus)return;setRequest({dimension,focus,offset});setResult(undefined)}
 const available=topics.filter(t=>!search.trim()||[t.name,t.subject].some(s=>s.includes(search.trim())))
 return <section className="panel">
  <h2>题型、方法与知识标签共现</h2>
  <div className="button-row">{(Object.keys(labels) as Dimension[]).map(d=><button type="button" key={d} aria-pressed={d===dimension} disabled={busy} onClick={()=>changeDimension(d)}>{labels[d]}</button>)}</div>
  <label>指定知识标签（可选）<input value={search} disabled={busy} onChange={e=>setSearch(e.target.value)} placeholder="搜索当前统计页的知识标签"/></label>
  <select aria-label="选择指定知识标签" disabled={busy} value={focus?JSON.stringify([focus.subject,focus.name]):''} onChange={e=>{const v=e.target.value?JSON.parse(e.target.value):null;changeFocus(v?{subject:v[0],name:v[1]}:undefined)}}><option value="">全部知识标签</option>{focus&&!available.some(t=>t.subject===focus.subject&&t.name===focus.name)&&<option value={JSON.stringify([focus.subject,focus.name])}>{focus.subject} · {focus.name}</option>}{available.map(t=><option key={JSON.stringify([t.subject,t.name])} value={JSON.stringify([t.subject,t.name])}>{t.subject} · {t.name}</option>)}</select>
  <p className="muted">{dimension==='method'?'基于已录入解析中的方法名称索引；未识别不等于没有这种解法。':dimension==='cooccurrence'?'指定一个知识标签，统计同一道题中共同录入的其他知识标签；不表示图谱关系。':'按已录入题型统计，未确认的题型独立显示。'}</p>
  <button className="primary" type="button" disabled={busy||(dimension==='cooccurrence'&&!focus)} onClick={()=>run()}>生成分布</button>
  {busy&&<p role="status">读取中…</p>}{error&&<p role="alert">{error}</p>}
  {result&&<><p>当前范围 {result.question_count} 道独立题目，{result.classified_questions} 道有匹配记录。</p><table className="source-statistics-table"><thead><tr><th>学科</th><th>项目</th><th>独立题目</th><th>来源关联</th></tr></thead><tbody>{result.items.map(r=><tr key={JSON.stringify([r.subject,r.name])}><td>{r.subject||'—'}</td><td><MathText content={r.name||'未确认'}/></td><td>{r.question_count}</td><td>{r.source_question_count}</td></tr>)}</tbody></table>{!result.items.length&&<p className="muted">暂无相应记录。</p>}<div className="button-row"><button type="button" disabled={!result.offset||busy} onClick={()=>run(Math.max(0,result.offset-result.limit))}>上一页</button><small>共 {result.total} 项</small><button type="button" disabled={busy||result.offset+result.limit>=result.total} onClick={()=>run(result.offset+result.limit)}>下一页</button></div><small className="muted">知识标签及方法可能重叠，不能将各项题目数直接相加作为总题数。</small></>}
 </section>
}
