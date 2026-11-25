import {useEffect,useState} from 'react'
import {Link} from 'react-router-dom'
import {api} from '../auth'
import {Icon} from '../components/Icon'
import {MathText} from '../components/MathText'
type Job={id:string;title:string;state:string;document_id:string|null;updated_at:number}
type Document={id:string;title:string;subject:string;source_id:string|null;updated_at:number}
const states:Record<string,string>={running:'提取中',review:'待审核',converted:'已生成文档',failed:'执行失败',stopped:'已停止'}
const entries=[
 {name:'AI 录入',desc:'发送图片、PDF、Word 或文字，交给 AI 整理并审核。',icon:'spark',path:'/work'},
 {name:'整套资料录入',desc:'登记或复用试卷、教材、讲义来源，在同一文档内逐条录入题目和知识单元。',icon:'files',path:'/intake?mode=document'},
]
export default function IntakeHub(){
 const [jobs,setJobs]=useState<Job[]>(),[docs,setDocs]=useState<Document[]>(),[errors,setErrors]=useState<string[]>([]),[refresh,setRefresh]=useState(0)
 useEffect(()=>{const c=new AbortController();setErrors([]);setJobs(undefined);setDocs(undefined)
 api<Job[]>('/intelligence/jobs',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setJobs(r)}).catch(()=>{if(!c.signal.aborted)setErrors(old=>[...old,'AI 录入任务'])})
 api<{items:Document[]}>('/documents?kind=intake&limit=30',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setDocs(r.items)}).catch(()=>{if(!c.signal.aborted)setErrors(old=>[...old,'录入文档'])})
 return()=>c.abort()},[refresh])
 const pending=jobs?.filter(j=>j.state==='running'||j.state==='review'||j.state==='failed'||j.state==='stopped')
 return <div className="intake-hub">
 <header className="bank-heading"><div><h1>录入工作台</h1><p className="muted">从原始资料到正式教学资源。一次录入，后续反复使用。</p></div><Link className="button-link" to="/chat"><Icon name="chat" size={17}/> 返回 AI 助手</Link></header>
 <details className="intake-flow"><summary>录入流程说明</summary><div className="intake-flow-steps">{[{name:'接收原文',note:'选择录入方式'},{name:'整理与核对',note:'AI 提取或手动编辑'},{name:'文档工作台',note:'排版、查重与编辑'},{name:'确认入库',note:'保存正式资源'}].map((s,i)=><div key={s.name}><span>{String(i+1).padStart(2,'0')}</span><strong>{s.name}</strong><small>{s.note}</small></div>)}</div><p className="muted">整套资料可包含一道题、多个题目或知识单元；AI 提取结果须审核后入库。</p></details>
 <section className="intake-entry-section"><div className="home-panel-head"><h2>开始录入</h2></div><div className="intake-entry-grid">{entries.map(e=><Link key={e.path} to={e.path} className="intake-entry clean-tool-row"><Icon name={e.icon} size={21}/><div><h3>{e.name}</h3><p className="muted">{e.desc}</p></div><Icon name="arrow" size={18}/></Link>)}</div></section>
 {errors.length>0&&<div className="home-error" role="status"><span>读取失败：{errors.join('、')}</span><button onClick={()=>setRefresh(v=>v+1)}>重试</button></div>}
 <div className="intake-continue-grid"><section className="panel"><div className="home-panel-head"><h2>继续整理</h2><Link className="text-link" to="/intelligence">全部 AI 任务</Link></div>{pending?.slice(0,8).map(j=><Link key={j.id} className="intake-history-row" to={'/intelligence?job='+encodeURIComponent(j.id)}><Icon name="clock" size={18}/><span><MathText compact content={j.title}/><small>{states[j.state]??j.state}</small></span><Icon name="chevron" size={14}/></Link>)}{!pending?.length&&<p className="muted intake-empty">{jobs?'暂无待处理任务':errors.includes('AI 录入任务')?'任务读取失败':'正在读取任务…'}</p>}</section>
 <section className="panel"><div className="home-panel-head"><h2>最近录入文档</h2><Link className="text-link" to="/intake?mode=document">查看文档</Link></div>{docs?.slice(0,8).map(d=><Link key={d.id} className="intake-history-row" to={'/intake?doc='+encodeURIComponent(d.id)}><Icon name="files" size={18}/><span><MathText compact content={d.title}/><small>{d.subject||'未分类'} · {d.source_id?'已关联来源':'未关联来源'}</small></span><Icon name="chevron" size={14}/></Link>)}{!docs?.length&&<p className="muted intake-empty">{docs?'暂无录入文档':errors.includes('录入文档')?'文档读取失败':'正在读取文档…'}</p>}</section></div>
 </div>
}
