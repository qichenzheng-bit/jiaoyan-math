import {Children,isValidElement,useState,type ReactNode} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import {MathFormula} from './MathFormula'
import {MathText} from './MathText'
import {Icon} from './Icon'
import {WorkspaceLink as Link} from './WorkspaceNavigation'
import {api} from '../auth'
import {taskLink} from '../task-links'

type Ref={id:string;code:string;kind:string;title:string}
type Resource=Ref&{content:string;answer:string;solution:string;proof:string;analysis:string;subject:string;archived:boolean;tags?:string[]}
type Entry={label:string;text:string}
type CardSpec=
 | {type:'comparison'|'steps';title:string;items:Entry[]}
 | {type:'plot';title:string;family:'quadratic'|'cubic';a:number;b:number;c:number}
 | {type:'bar';title:string;items:{label:string;value:number}[]}
 | {type:'tasks'|'documents'|'videos';title:string}
type Dict=Record<string,unknown>
const dict=(v:unknown):v is Dict=>!!v&&typeof v==='object'&&!Array.isArray(v)
const bounded=(v:unknown,n:number):v is string=>typeof v==='string'&&v.length>0&&v.length<=n
const finite=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)
const param=(v:unknown,d:number)=>finite(v)?Math.max(-3,Math.min(3,v)):d
export function parseCard(raw:string):CardSpec|null{
 if(raw.length>16000)return null
 try{
  const v:unknown=JSON.parse(raw)
  if(!dict(v)||!bounded(v.title,120))return null
  const title=v.title
  if(v.type==='comparison'||v.type==='steps'){
   if(!Array.isArray(v.items)||!v.items.length||v.items.length>8||!v.items.every(x=>dict(x)&&bounded(x.label,80)&&bounded(x.text,5000)))return null
   return {type:v.type,title,items:v.items.map(x=>({label:x.label,text:x.text}))}
  }
  if(v.type==='plot'&&(v.family==='quadratic'||v.family==='cubic'))return {type:'plot',title,family:v.family,a:param(v.a,1),b:param(v.b,0),c:param(v.c,0)}
  if(v.type==='bar'){
   if(!Array.isArray(v.items)||!v.items.length||v.items.length>12||!v.items.every(x=>dict(x)&&bounded(x.label,60)&&finite(x.value)&&x.value>=0&&x.value<=1e12))return null
   return {type:'bar',title,items:v.items.map(x=>({label:x.label,value:x.value}))}
  }
  if(v.type==='tasks'||v.type==='documents'||v.type==='videos')return {type:v.type,title}
 }catch{/* malformed model output remains non-executable */}
 return null
}
function Frame({title,icon='book',children}:{title:string;icon?:string;children:ReactNode}){
 return <section className="rich-card"><div className="rich-card-head"><Icon name={icon} size={19}/><MathText compact content={title}/></div>{children}</section>
}
function Comparison({spec}:{spec:Extract<CardSpec,{type:'comparison'|'steps'}>}){
 const [tab,setTab]=useState(0)
 const item=spec.items[Math.min(tab,spec.items.length-1)]
 return <Frame title={spec.title} icon="formulas">{spec.type==='comparison'?<><div className="rich-card-tabs" role="group" aria-label="切换解法">{spec.items.map((x,i)=><button type="button" key={i} aria-pressed={tab===i} onClick={()=>setTab(i)}><MathText compact content={x.label}/></button>)}</div><MathText content={item.text}/></>:spec.items.map((x,i)=><div key={i} className="rich-card-step"><span>{i+1}</span><div><strong><MathText compact content={x.label}/></strong><MathText content={x.text}/></div></div>)}</Frame>
}
function Plot({spec}:{spec:Extract<CardSpec,{type:'plot'}>}){
 const [a,setA]=useState(spec.a),[b,setB]=useState(spec.b),[c,setC]=useState(spec.c)
 const cubic=spec.family==='cubic',f=(x:number)=>cubic?x*x*x-3*a*x:a*x*x+b*x+c
 const path=Array.from({length:181},(_,i)=>{const x=-4+i*8/180;return (i===0?'M':'L')+(160+x*33).toFixed(2)+','+(110-f(x)*12).toFixed(2)}).join(' ')
 const sign=(v:number)=>v>=0?'+'+v:String(v)
 return <Frame title={spec.title} icon="chart"><MathFormula latex={cubic?'f(x)=x^3'+sign(-3*a)+'x':'f(x)='+a+'x^2'+sign(b)+'x'+sign(c)}/><svg className="rich-card-plot" viewBox="0 0 320 220" role="img" aria-label="函数图像" style={{overflow:'hidden'}}>{Array.from({length:9},(_,i)=><path key={i} d={'M'+(28+i*33)+' 10V210'} stroke="currentColor" opacity=".08"/>)}{Array.from({length:9},(_,i)=><path key={i} d={'M15 '+(14+i*24)+'H305'} stroke="currentColor" opacity=".08"/>)}<path d="M15 110H305M160 10V210" stroke="currentColor" fill="none" opacity=".5"/><text x="304" y="104" fontSize="11" fill="currentColor">x</text><text x="168" y="18" fontSize="11" fill="currentColor">y</text><path d={path} stroke="currentColor" strokeWidth="2" fill="none"/>{(cubic?(a>0?[-Math.sqrt(a),Math.sqrt(a)]:[]):a!==0?[-b/(2*a)]:[]).filter(x=>Math.abs(x)<=4&&Math.abs(f(x))<=9).map(x=><circle key={x} cx={160+x*33} cy={110-f(x)*12} r="4" fill="currentColor"/>)}</svg>{([{label:'a',value:a,change:setA},{label:'b',value:b,change:setB},{label:'c',value:c,change:setC}].slice(0,cubic?1:3)).map(p=><label className="rich-card-slider" key={p.label}><span>{p.label}</span><input type="range" min={-3} max={3} step={.25} value={p.value} onChange={e=>p.change(Number(e.target.value))}/><span>{p.value.toFixed(2)}</span></label>)}<div className="rich-card-actions"><button type="button" onClick={()=>{setA(spec.a);setB(spec.b);setC(spec.c)}}>重置参数</button><small>{cubic?(a>0?'有两个极值点':'无极值点'):(a===0?'当前不是二次函数':a>0?'开口向上':'开口向下')}</small></div></Frame>
}
type ListRow={id:string;title?:string;state?:string;kind?:string;session_id?:string|null;document_id?:string;document_kind?:string;engine_id?:string|null;source_snapshot?:{title?:string}}
function LiveList({spec}:{spec:Extract<CardSpec,{type:'tasks'|'documents'|'videos'}>}){
 const [rows,setRows]=useState<ListRow[]|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
 const target=spec.type==='tasks'?'/tasks':spec.type==='videos'?'/videos':'/papers'
 async function load(){setBusy(true);setError('');try{const v=spec.type==='documents'?(await api<{items:ListRow[]}>('/documents?limit=8')).items:await api<ListRow[]>(spec.type==='tasks'?'/tasks':'/video/projects');setRows(v.slice(0,8))}catch(e){setError(e instanceof Error?e.message:'读取失败')}finally{setBusy(false)}}
 function route(r:ListRow){if(spec.type==='tasks')return taskLink({id:r.id,kind:r.kind??'',session_id:r.session_id??null,document_id:r.document_id,document_kind:r.document_kind});if(spec.type==='videos')return '/videos?project='+encodeURIComponent(r.id);return (r.kind==='handout'?'/handouts':r.kind==='textbook'?'/textbooks':r.kind==='intake'?'/intake':'/papers')+'?doc='+encodeURIComponent(r.id)}
 const states:Record<string,string>={running:'执行中',done:'完成',review:'待审核',failed:'失败',stopped:'已停止',accepted:'已采纳',discarded:'已舍弃',converted:'已生成文档'}
 return <Frame title={spec.title} icon={spec.type==='videos'?'media':spec.type==='tasks'?'clock':'files'}><small>真实业务数据 · 点击读取，任务状态为最近保存记录</small>{rows?.map(r=><div className="rich-card-row" key={r.id}><div><MathText compact content={r.title??r.source_snapshot?.title??'未命名项目'}/>{r.state&&<div><small>{states[r.state]??r.state}</small></div>}</div><Link to={route(r)}>打开</Link></div>)}{rows?.length===0&&<p>暂无记录</p>}{error&&<p role="alert">{error}</p>}<div className="rich-card-actions"><button type="button" disabled={busy} onClick={()=>void load()}>{busy?'读取中…':rows?'刷新列表':'读取真实数据'}</button><Link to={target}>进入工作台</Link></div></Frame>
}
function Card({spec}:{spec:CardSpec}){
 if(spec.type==='comparison'||spec.type==='steps')return <Comparison spec={spec}/>
 if(spec.type==='plot')return <Plot spec={spec}/>
 if(spec.type==='bar'){const max=Math.max(1,...spec.items.map(x=>x.value));return <Frame title={spec.title} icon="chart"><small>根据 AI 回复提供的数据绘制，非实时系统统计</small>{spec.items.map((x,i)=><div key={i} className="rich-card-bar"><MathText compact content={x.label}/><div className="rich-card-track"><span style={{width:(100*x.value/max)+'%'}}/></div><span>{x.value.toLocaleString()}</span></div>)}</Frame>}
 if(spec.type==='tasks'||spec.type==='documents'||spec.type==='videos')return <LiveList spec={spec}/>
 return null
}
function ResourceCard({reference}:{reference:Ref}){
 const [data,setData]=useState<Resource|null>(null),[tab,setTab]=useState('content'),[busy,setBusy]=useState(false),[error,setError]=useState('')
 async function load(){setBusy(true);setError('');try{const r=await api<Resource>('/resources/'+encodeURIComponent(reference.id));if(r.archived)throw Error('资源已归档');setData(r)}catch(e){setError(e instanceof Error?e.message:'读取失败')}finally{setBusy(false)}}
 const route=(reference.kind==='source'?'/sources':reference.kind==='knowledge'?'/knowledge-library':'/resources')+'?q='+encodeURIComponent(reference.code)
 const fields=([{key:'content',label:'正文'},{key:'answer',label:'答案'},{key:'solution',label:'解析'},{key:'analysis',label:'思路'},{key:'proof',label:'证明'},{key:'tags',label:'知识点'}] as const).filter(x=>x.key==='content'||Boolean(data?.[x.key]?.length))
 const value=data&&fields.find(x=>x.key===tab)?data[tab as keyof Resource]:data?.content
 return <Frame title={reference.title} icon={reference.kind==='source'?'files':'book'}><small>{reference.code} · {reference.kind==='question'?'题库':reference.kind==='knowledge'?'知识库':'来源库'}{data?.subject?' · '+data.subject:''}</small>{data&&<><div className="rich-card-tabs" role="group" aria-label="资源详情">{fields.map(x=><button key={x.key} type="button" aria-pressed={tab===x.key} onClick={()=>setTab(x.key)}>{x.label}</button>)}</div><MathText content={Array.isArray(value)?value.join('、'):typeof value==='string'?value:''}/></>}{error&&<p role="alert">{error}</p>}<div className="rich-card-actions"><button type="button" onClick={()=>data?setData(null):void load()} disabled={busy}>{busy?'读取中…':data?'收起详情':'展开详情'}</button><Link to={route}>打开资源</Link>{data&&reference.kind==='question'&&<Link to={'/videos?resource='+encodeURIComponent(reference.id)}>制作视频</Link>}</div></Frame>
}
export function ResourceCards({refs}:{refs:Ref[]}){
 return refs.length?<div aria-label="本次真实检索资源"><small className="muted">本次引用或检索到的资源</small>{refs.map(r=><ResourceCard key={r.id} reference={r}/>)}</div>:null
}
// Explicit legacy delimiters are normalized outside code spans and fences.
function normalize(content:string){
 return content.split(/(\x60{3}[\s\S]*?(?:\x60{3}|$)|\x60[^\x60\n]+\x60)/g).map((s,i)=>i%2?s:s.replace(/\\\[([\s\S]+?)\\\]/g,(_,m)=>'\n\n$$\n'+m+'\n$$\n\n').replace(/\\\(([^\n]+?)\\\)/g,(_,m)=>'$'+m+'$')).join('')
}
export function RichChat({content,complete}:{content:string;complete:boolean}){
 return <div className="rich-reply"><ReactMarkdown remarkPlugins={[remarkGfm,remarkMath]} skipHtml components={{
  img:({alt})=><span>{alt??'图片'}</span>,
  a:({children})=><span>{children}</span>,
  table:({children})=><div className="rich-table"><table>{children}</table></div>,
  code:({className,children})=>className?.includes('math-inline')||className?.includes('math-display')?<MathFormula latex={String(children).trim()} display={className.includes('math-display')}/>:<code className={className}>{children}</code>,
  pre:({children})=>{
   const child=Children.toArray(children)[0]
   if(isValidElement<{className?:string;children?:ReactNode}>(child)){
    const cls=child.props.className??''
    if(cls.includes('math-display'))return <>{child}</>
    if(cls.split(/\s+/).includes('language-wg-card')){
     if(!complete)return null
     const spec=parseCard(String(child.props.children??''))
     return spec?<Card spec={spec}/>:<p className="rich-card-error">交互内容格式不完整，请让 AI 重新生成。</p>
    }
   }
   return <pre>{children}</pre>
  }
 }}>{normalize(content)}</ReactMarkdown></div>
}
