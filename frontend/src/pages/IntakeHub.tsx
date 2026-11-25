import {useEffect,useState} from 'react'
import {Link} from 'react-router-dom'
import {api} from '../auth'
import {Icon} from '../components/Icon'
import {MathText} from '../components/MathText'
type Job={id:string;title:string;state:string;document_id:string|null;updated_at:number}
type Document={id:string;title:string;subject:string;source_id:string|null;updated_at:number}
const states:Record<string,string>={running:'提取中',review:'待审核',converted:'已生成文档',failed:'执行失败',stopped:'已停止'}
const entries=[
 {name:'AI 智能录入',desc:'粘贴题目、导入文本或文字版 PDF，交给 AI 拆分整理。',icon:'spark',path:'/intelligence',detail:'推荐 · 多条内容'},
 {name:'整套资料录入',desc:'先登记试卷、教材或讲义，再到 Word 工作台逐题编辑。',icon:'files',path:'/intake?mode=document',detail:'适合完整资料'},
 {name:'单道题目录入',desc:'已有题目、答案和解析时，直接编辑并确认保存。',icon:'resources',path:'/intake-single?kind=question',detail:'手动录入'},
 {name:'知识单元录入',desc:'整理定义、定理、性质、公式或方法。',icon:'book',path:'/intake-single?kind=knowledge',detail:'手动录入'},
]
export default function IntakeHub(){
 const [jobs,setJobs]=useState<Job[]>(),[docs,setDocs]=useState<Document[]>(),[errors,setErrors]=useState<string[]>([]),[refresh,setRefresh]=useState(0)
 useEffect(()=>{const c=new AbortController();setErrors([]);setJobs(undefined);setDocs(undefined)
 api<Job[]>('/intelligence/jobs',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setJobs(r)}).catch(()=>{if(!c.signal.aborted)setErrors(old=>[...old,'AI 录入任务'])})
 api<{items:Document[]}>('/documents?kind=intake&limit=30',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setDocs(r.items)}).catch(()=>{if(!c.signal.aborted)setErrors(old=>[...old,'录入文档'])})
 return()=>c.abort()},[refresh])
 const pending=jobs?.filter(j=>j.state==='running'||j.state==='review'||j.state==='failed'||j.state==='stopped')
 return <div className="intake-hub">
 <header className="bank-heading"><div><p className="workspace-kicker">AI 助手 · 统一录入</p><h1>录入工作台</h1><p className="muted">从原始资料到正式教学资源。一次录入，后续反复使用。</p></div><Link className="button-link" to="/chat"><Icon name="chat" size={17}/> 返回 AI 助手</Link></header>
 <section className="panel intake-flow"><div className="home-panel-head"><h2>录入流程</h2><Link className="text-link" to="/library">查看教学资源 <Icon name="arrow" size={15}/></Link></div><div className="intake-flow-steps">{[{name:'接收原文',note:'选择录入方式'},{name:'整理与核对',note:'AI 提取或手动编辑'},{name:'文档工作台',note:'排版、查重与编辑'},{name:'确认入库',note:'保存正式资源'}].map((s,i)=><div key={s.name}><span>{String(i+1).padStart(2,'0')}</span><strong>{s.name}</strong><small>{s.note}</small></div>)}</div><p className="muted">单条手动录入可直接确认保存，不必建立整套资料文档；AI 提取结果不会自动入库。</p></section>
 <section className="intake-entry-section"><div className="home-panel-head"><h2>开始录入</h2><Link className="text-link" to="/intake-single?kind=source">单独登记来源资料 <Icon name="chevron" size={14}/></Link></div><div className="intake-entry-grid">{entries.map((e,i)=><Link key={e.path} to={e.path} className={'panel intake-entry'+(i===0?' intake-entry-featured':'')}><span className="soft-icon"><Icon name={e.icon} size={24}/></span><div><small>{e.detail}</small><h3>{e.name}</h3><p className="muted">{e.desc}</p></div><Icon name="arrow" size={18}/></Link>)}</div></section>
 {errors.length>0&&<div className="home-error" role="status"><span>读取失败：{errors.join('、')}</span><button onClick={()=>setRefresh(v=>v+1)}>重试</button></div>}
 <div className="intake-continue-grid"><section className="panel"><div className="home-panel-head"><h2>继续整理</h2><Link className="text-link" to="/intelligence">全部 AI 任务</Link></div>{pending?.slice(0,8).map(j=><Link key={j.id} className="intake-history-row" to={'/intelligence?job='+encodeURIComponent(j.id)}><Icon name="clock" size={18}/><span><MathText compact content={j.title}/><small>{states[j.state]??j.state}</small></span><Icon name="chevron" size={14}/></Link>)}{!pending?.length&&<p className="muted intake-empty">{jobs?'暂无待处理任务':errors.includes('AI 录入任务')?'任务读取失败':'正在读取任务…'}</p>}</section>
 <section className="panel"><div className="home-panel-head"><h2>最近录入文档</h2><Link className="text-link" to="/intake?mode=document">查看文档</Link></div>{docs?.slice(0,8).map(d=><Link key={d.id} className="intake-history-row" to={'/intake?doc='+encodeURIComponent(d.id)}><Icon name="files" size={18}/><span><MathText compact content={d.title}/><small>{d.subject||'未分类'} · {d.source_id?'已关联来源':'未关联来源'}</small></span><Icon name="chevron" size={14}/></Link>)}{!docs?.length&&<p className="muted intake-empty">{docs?'暂无录入文档':errors.includes('录入文档')?'文档读取失败':'正在读取文档…'}</p>}</section></div>
 </div>
}
