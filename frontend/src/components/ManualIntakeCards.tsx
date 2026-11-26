import {memo,useEffect,useRef,useState,type ReactNode} from 'react'
import {api} from '../auth'
import {Link,useNavigate} from 'react-router-dom'
import {confirmAction} from './WorkspaceConfirm'
import type {Block,Doc,Kind,CardPanel} from '../pages/DocWork'
import {MathText} from './MathText'
import ChatText from '../pages/ChatText'
import {Icon} from './Icon'
import InlineMathEditor from './InlineMathEditor'
import './ManualWordWork.css'
import {PrintableDocument} from '../pages/DocumentPrint'

export const questionTypes=['选择题','填空题','综合题']
export const resourceQuestionTypes=['选择题','单选题','多选题','填空题','综合题']
export const displayQuestionType=(type:string)=>['解答题','计算题','证明题'].includes(type)?'综合题':type
type QuestionValue={subject?:string|null;chapter:string;question_type:string;difficulty?:string;content:string;answer:string;solution:string}
type Props={value:QuestionValue;subject:string;subjects:string[];locked:boolean;onChange:(p:Partial<QuestionValue>)=>void;knowledge?:ReactNode;contentOnly?:boolean}
function marked(text:string,pattern:RegExp){
 const parts:Record<string,string>={},order:string[]=[]
 let main='',current=''
 for(const line of text.split('\n')){
  const match=line.match(pattern)
  if(match){current=match[1];if(!order.includes(current))order.push(current);parts[current]=match[2]}
  else if(current)parts[current]+='\n'+line
  else main+=(main?'\n':'')+line
 }
 return {main,parts,order}
}
const choicesPattern=/^([A-Z])[.、)]\s+(.*)$/
const subPattern=/^[（(]([1-9][0-9]*)[）)]\s*(.*)$/
function combine(main:string,parts:Record<string,string>,keys:string[],label:(k:string)=>string){
 return [main,...keys.filter(k=>parts[k]?.trim()).map(k=>label(k)+parts[k])].filter(s=>s.trim()).join('\n')
}
// Keep empty subquestion markers in the stem so collapsing a card does not lose newly added slots.
function combineSubStem(main:string,parts:Record<string,string>,keys:string[]){
 return [main,...keys.map(k=>'('+k+')'+(parts[k]?.trim()?' '+parts[k]:''))].filter(s=>s.trim()).join('\n')
}
function Field(props:{label:string;value:string;onChange:(v:string)=>void;locked:boolean;placeholder?:string;rows?:number}){
 return <InlineMathEditor {...props}/>
}
export function QuestionFields({value,subject,subjects,locked,onChange,knowledge,contentOnly=false}:Props){
 const type=['单选题','多选题','选择题'].includes(value.question_type)?'选择题':value.question_type==='填空题'?'填空题':'综合题',choice=type==='选择题',fill=type==='填空题',big=!choice&&!fill
 const options=marked(value.content,choicesPattern),sub=marked(value.content,subPattern),answers=marked(value.answer,subPattern),solutions=marked(value.solution,subPattern)
 const [optionCount,setOptionCount]=useState(Math.max(4,...options.order.map(k=>k.charCodeAt(0)-64))),[subCount,setSubCount]=useState(Math.max(0,...[...sub.order,...answers.order,...solutions.order].map(Number)))
 const optKeys=Array.from({length:Math.min(26,optionCount)},(_,i)=>String.fromCharCode(65+i))
 const subKeys=Array.from({length:Math.min(30,subCount)},(_,i)=>String(i+1))
 const hasSubs=big&&subCount>0
 const stem=choice?options.main:hasSubs?sub.main:value.content
 const selectedLetters:string[]=/^[A-Z\s,，、]+$/.test(value.answer.trim())?value.answer.match(/[A-Z]/g)??[]:[]
 function setStem(v:string){onChange({content:choice?combine(v,options.parts,optKeys,k=>k+'. '):hasSubs?combineSubStem(v,sub.parts,subKeys):v})}
 function setOption(k:string,v:string){onChange({content:combine(options.main,{...options.parts,[k]:v},optKeys,l=>l+'. ')})}
 function setSub(k:string,field:'content'|'answer'|'solution',v:string){
  const data=field==='content'?sub:field==='answer'?answers:solutions
  const parts={...data.parts,[k]:v}
  onChange({[field]:field==='content'?combineSubStem(data.main,parts,subKeys):combine(data.main,parts,subKeys,l=>'('+l+') ')})
 }
 async function addSub(){
  const keys=[...subKeys,String(subCount+1)]
  if(!hasSubs&&(value.answer.trim()||value.solution.trim())){
   if(!await confirmAction('添加小问后不再使用公共答案和解析。将现有内容移入第 1 小问，是否继续？'))return
   onChange({content:combineSubStem(sub.main,sub.parts,keys),answer:combine('',{'1':value.answer},keys,k=>'('+k+') '),solution:combine('',{'1':value.solution},keys,k=>'('+k+') ')})
  }else onChange({content:combineSubStem(sub.main,sub.parts,keys)})
  setSubCount(n=>n+1)
 }
 async function migrateCommon(){
  if(!await confirmAction('将原公共答案、解析合并到第 1 小问，保留现有内容？'))return
  const merge=(data:ReturnType<typeof marked>)=>combine('',{...data.parts,'1':[data.parts['1'],data.main].filter(v=>v?.trim()).join('\n')},subKeys,k=>'('+k+') ')
  onChange({answer:merge(answers),solution:merge(solutions)})
 }
 async function removeSub(k:string){
  if([sub.parts[k],answers.parts[k],solutions.parts[k]].some(v=>v?.trim())&&!await confirmAction('移除该小问及其答案、解析？'))return
  const remaining=subKeys.filter(l=>l!==k)
  const renumber=(data:ReturnType<typeof marked>)=>combine(data.main,Object.fromEntries(remaining.map((old,i)=>[String(i+1),data.parts[old]??''])),remaining.map((_,i)=>String(i+1)),l=>'('+l+') ')
  onChange({content:combineSubStem(sub.main,Object.fromEntries(remaining.map((old,i)=>[String(i+1),sub.parts[old]??''])),remaining.map((_,i)=>String(i+1))),answer:renumber(answers),solution:renumber(solutions)})
  setSubCount(n=>Math.max(0,n-1))
 }
 function setChoiceAnswer(v:string){
  const letters=/^[A-Z\s,，、]*$/.test(v)?[...new Set(v.match(/[A-Z]/g)??[])]:[]
  onChange({answer:v,question_type:letters.length>1?'多选题':letters.length===1?'单选题':'选择题'})
 }
 function toggleLetter(k:string){
  const next=selectedLetters.includes(k)?selectedLetters.filter(v=>v!==k):[...selectedLetters,k]
  setChoiceAnswer([...new Set(next)].sort().join(''))
 }
 function addBlank(){setStem(stem+'$\\underline{\\qquad}$')}
 return <div className="manual-question-fields">
  {!contentOnly&&<div className="manual-attributes"><label>科目<select aria-label="科目" disabled={locked} value={value.subject??subject} onChange={e=>onChange({subject:e.target.value})}>{Array.from(new Set(['',value.subject??subject,...subjects])).map(s=><option key={s} value={s}>{s||'请选择科目'}</option>)}</select></label><label>所在章节（选填）<input aria-label="所在章节" disabled={locked} maxLength={120} value={value.chapter} onChange={e=>onChange({chapter:e.target.value})}/></label><label>题型<select aria-label="题型" disabled={locked} value={type} onChange={e=>{onChange({question_type:e.target.value});setOptionCount(Math.max(4,...options.order.map(k=>k.charCodeAt(0)-64)));setSubCount(Math.max(0,...[...sub.order,...answers.order,...solutions.order].map(Number)))}}>{questionTypes.map(t=><option key={t}>{t}</option>)}</select></label><label>难度<select aria-label="难度" disabled={locked} value={value.difficulty??''} onChange={e=>onChange({difficulty:e.target.value})}><option value="">未设置</option>{['简单','中等','困难'].map(t=><option key={t}>{t}</option>)}</select></label></div>}
  {!contentOnly&&knowledge}
  <InlineMathEditor label="题目" value={stem} onChange={setStem} locked={locked} rows={5} placeholder="输入题干，公式用 $...$ 包裹，可直接粘贴图片"/>
  {fill&&<button type="button" disabled={locked} onClick={addBlank}>＋ 插入填空空位</button>}
  {choice&&<div className="manual-options"><strong>选项</strong>{optKeys.map(k=><Field key={k} label={k+' 选项'} value={options.parts[k]??''} locked={locked} rows={2} onChange={v=>setOption(k,v)}/>)}<div className="button-row"><button type="button" disabled={locked||optionCount>=26} onClick={()=>setOptionCount(n=>n+1)}>＋ 添加选项</button><button type="button" disabled={locked||optionCount<=2} onClick={async()=>{const k=optKeys[optKeys.length-1];if(options.parts[k]?.trim()&&!await confirmAction('移除最后一个选项？'))return;setOption(k,'');setOptionCount(n=>n-1)}}>减少选项</button></div><strong>正确选项{selectedLetters.length>1?' · 多选题':selectedLetters.length===1?' · 单选题':''}</strong><div className="button-row manual-answer-choices">{optKeys.map(k=><button type="button" key={k} disabled={locked} aria-pressed={selectedLetters.includes(k)} onClick={()=>toggleLetter(k)}>{k}</button>)}</div></div>}
  {!choice&&!hasSubs&&<Field label="答案" value={value.answer} locked={locked} placeholder={fill?'多个空的答案按顺序填写':'输入答案'} onChange={v=>onChange({answer:v})}/>}
  {!hasSubs&&<Field label="解析" value={value.solution} locked={locked} rows={5} placeholder="输入解析" onChange={v=>onChange({solution:v})}/>}
  {hasSubs&&(answers.main.trim()||solutions.main.trim())&&<div className="manual-match"><small>此旧题仍有公共答案或解析，原内容已保留。</small><button type="button" disabled={locked} onClick={migrateCommon}>合并至第 1 小问</button></div>}
  {big&&<div className="manual-subquestions">{subKeys.map(k=><section className="manual-subquestion" key={k}><div className="mobile-doc-title"><strong>第 {k} 小问</strong><button type="button" disabled={locked} onClick={()=>removeSub(k)}>移除</button></div>{(['content','answer','solution'] as const).map(f=><Field key={f} label={'第 '+k+' 小问'+({content:'题目',answer:'答案',solution:'解析'}[f])} value={(f==='content'?sub:f==='answer'?answers:solutions).parts[k]??''} locked={locked} onChange={v=>setSub(k,f,v)}/>)}</section>)}<button type="button" disabled={locked||subCount>=30} onClick={addSub}>＋ 添加小问（可选）</button></div>}
 </div>
}

type MatchResource={id:string;kind?:string;proof?:string;unit_type?:string;code:string;revision:number;subject:string;chapter:string;question_type:string;difficulty?:string;title:string;content:string;answer:string;solution:string;tags:string[];knowledge_tags?:string[]}
type Match={resource:MatchResource;match_kind:'exact'|'same_stem'|'similar'|'same_title';similarity:number}
type Point={id:string;name:string;chapter:string;child_count:number}
type Chapter={chapter:string;count:number}
type Browse={mode:'chapters';items:Chapter[];total:number}|{mode:'points';items:Point[];total:number}
export function KnowledgePoints({value,subject,locked,onChange}:{value:string[];subject:string;locked:boolean;onChange:(tags:string[])=>void}){
 const [text,setText]=useState(''),[query,setQuery]=useState(''),[open,setOpen]=useState(false),[chapter,setChapter]=useState<string|null>(null),[parents,setParents]=useState<Point[]>([]),[page,setPage]=useState(0),[data,setData]=useState<Browse>(),[loading,setLoading]=useState(false),[error,setError]=useState('')
 const size=20,disabled=locked||!subject||value.length>=20
 const parent=parents[parents.length-1]
 useEffect(()=>{setChapter(null);setParents([]);setQuery('');setText('');setPage(0);setData(undefined);setOpen(false)},[subject])
 useEffect(()=>{
  const c=new AbortController()
  if(!subject||!open){setData(undefined);setLoading(false);return}
  setLoading(true);setData(undefined);setError('')
  const params=new URLSearchParams({subject,limit:String(size),offset:String(page*size)})
  if(query.trim())params.set('q',query.trim())
  else if(parent)params.set('parent_id',parent.id)
  else if(chapter!==null)params.set('chapter',chapter)
  const t=window.setTimeout(()=>api<Browse>('/knowledge/browse?'+params,{signal:c.signal}).then(r=>{if(!c.signal.aborted){if(!Array.isArray(r.items)||!['chapters','points'].includes(r.mode))throw Error('知识点分类数据格式无效');setData(r)}}).catch(e=>{if(!c.signal.aborted)setError(e.message||'知识点读取失败')}).finally(()=>{if(!c.signal.aborted)setLoading(false)}),query?250:0)
  return()=>{clearTimeout(t);c.abort()}
 },[subject,open,chapter,parent?.id,query,page])
 function add(name:string){const n=name.trim();if(disabled||!n||n.length>60)return;if(!value.includes(n))onChange([...value,n]);setText('')}
 function root(){setChapter(null);setParents([]);setQuery('');setPage(0)}
 function drill(p:Point){setParents(v=>[...v,p]);setQuery('');setPage(0)}
 const total=data?.total??0
 return <section className="manual-knowledge-tags"><strong>知识点</strong><div className="manual-tag-list">{value.map(tag=><button key={tag} type="button" disabled={locked} aria-label={'移除知识点 '+tag} onClick={()=>onChange(value.filter(v=>v!==tag))}>{tag} ×</button>)}</div><button type="button" aria-expanded={open} disabled={disabled} onClick={()=>{setOpen(v=>!v);root()}}>{open?'收起已有知识点':'选择已有知识点'}</button>
 {open&&<div className="manual-tag-browser"><input aria-label="搜索已有知识点" value={query} placeholder="搜索当前科目知识点" onChange={e=>{setQuery(e.target.value);setPage(0)}}/><nav className="manual-tag-path" aria-label="知识点分类路径"><button type="button" onClick={root}>{subject}</button>{!query.trim()&&chapter!==null&&<><span>›</span><button type="button" onClick={()=>{setParents([]);setPage(0)}}>{chapter||'未分类'}</button></>}{!query.trim()&&parents.map((p,i)=><span key={p.id}>› <button type="button" onClick={()=>{setParents(v=>v.slice(0,i+1));setPage(0)}}>{p.name}</button></span>)}{query.trim()&&<span>› 搜索结果</span>}</nav>
 <div className="manual-tag-catalog">{loading?<small role="status">正在读取分类…</small>:error?<small role="alert">{error}</small>:data?.mode==='chapters'?<>{data.items.map(c=><button key={c.chapter} type="button" className="manual-tag-category" onClick={()=>{setChapter(c.chapter);setParents([]);setPage(0)}}><span>{c.chapter||'未分类'}</span><small>{c.count} 个上级知识点 ›</small></button>)}{!data.items.length&&<small className="muted">当前科目暂无知识点。</small>}</>:data?.mode==='points'?<>{data.items.map(p=><div className="manual-tag-node" key={p.id}><button className="manual-tag-suggestion" type="button" disabled={disabled||value.includes(p.name)} onClick={()=>add(p.name)}><span>{p.name}</span>{query.trim()&&p.chapter&&<small>{p.chapter}</small>}{value.includes(p.name)&&<small>已选择</small>}</button>{p.child_count>0&&<button type="button" aria-label={'展开 '+p.name} onClick={()=>{if(query.trim()){setChapter(p.chapter);setParents([p]);setQuery('');setPage(0)}else drill(p)}}>{p.child_count} ›</button>}</div>)}{!data.items.length&&<small className="muted">本级暂无匹配知识点。</small>}</>:null}</div>
 {total>size&&<div className="button-row"><button type="button" disabled={page===0||loading} onClick={()=>setPage(v=>v-1)}>上一页</button><small>{page+1}/{Math.ceil(total/size)}</small><button type="button" disabled={(page+1)*size>=total||loading} onClick={()=>setPage(v=>v+1)}>下一页</button></div>}</div>}
 <div className="manual-tag-entry"><input aria-label="知识点" value={text} disabled={disabled} maxLength={60} placeholder="输入新知识点名称" onChange={e=>setText(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();add(text)}}}/><button type="button" disabled={disabled||!text.trim()} onClick={()=>add(text)}>新增知识点</button></div><small className="muted">按当前科目、章节和知识图谱父子关系逐级选择；新知识点随整套资料入库。</small></section>
}
function DuplicateMatches({block,locked,onChoose,excludeId,onKeep}:{block:Block;locked:boolean;onChoose?:(resource:MatchResource,reuse:boolean)=>void;excludeId?:string;onKeep?:(reason:string)=>void}){
 const [matches,setMatches]=useState<Match[]>([]),[status,setStatus]=useState(''),[scanned,setScanned]=useState<number>(),[attempt,setAttempt]=useState(0)
 const [reason,setReason]=useState(block.dedup_reason??'');const knowledge=block.kind==='knowledge'
 const content=block.content,answer=block.answer,solution=block.solution
 useEffect(()=>{
  const c=new AbortController();setMatches([]);setScanned(undefined);setStatus('')
  if(!content.trim()||block.reuse_resource_id||locked)return
  setStatus('等待查重…')
  const t=window.setTimeout(()=>{setStatus('正在查重…');api<{items:Match[];scanned:number}>('/documents/manual-matches',{method:'POST',body:JSON.stringify({kind:knowledge?'knowledge':'question',title:block.title,content,answer,solution}),signal:c.signal}).then(r=>{if(!c.signal.aborted){if(!Array.isArray(r.items))throw new Error('查重结果格式无效');const filtered=r.items.filter(m=>m.resource.id!==excludeId&&(m.similarity>=.8||m.match_kind==='same_title'));setMatches(filtered);setScanned(r.scanned);setStatus(filtered.length?'':'未发现重复候选')}}).catch(e=>{if(!c.signal.aborted)setStatus(e.message||'查重失败，请重试')})},attempt?400:900)
  return()=>{clearTimeout(t);c.abort()}
 },[content,answer,solution,block.kind,block.title,block.reuse_resource_id,locked,attempt,excludeId,knowledge])
 if(block.reuse_resource_id)return null
 return <section className="manual-matches"><div className="mobile-doc-title"><strong>{knowledge?'知识库查重':'题库查重'}</strong><button type="button" disabled={locked||!content.trim()} onClick={()=>setAttempt(n=>n+1)}>重新查重</button></div>{status&&<p className="muted" role="status">{status}</p>}{scanned!==undefined&&<small className="muted">已查询 {scanned} 个{knowledge?'知识单元':'题目'} · 找到 {matches.length} 个候选</small>}{matches.map(({resource:r,match_kind,similarity})=><article className="manual-match" key={r.id}><div><strong>{r.code}</strong><small> · {match_kind==='same_title'?'名称相同':match_kind==='exact'?'内容相同 · 100%':match_kind==='same_stem'?'题干相同 · 100%':'相似度 '+(similarity*100).toFixed(1)+'%'}</small></div>{knowledge&&<strong><MathText compact content={r.title}/></strong>}<ChatText content={r.content}/><details><summary>{knowledge?'查看证明及属性':'查看答案、解析及属性'}</summary><p className="muted">{r.subject||'未分类'} · {r.chapter||'无章节'} · {displayQuestionType(r.question_type)||'未分类'}</p>{knowledge?<><strong>证明 / 说明</strong><ChatText content={r.proof||'（未填写）'}/></>:<><strong>答案</strong><ChatText content={r.answer||'（未填写）'}/><strong>解析</strong><ChatText content={r.solution||'（未填写）'}/></>}</details>{onChoose&&<div className="button-row"><button type="button" className="primary" disabled={locked} onClick={()=>onChoose(r,true)}>{knowledge?'使用已有知识':'使用原题 · 编号不变'}</button><button type="button" disabled={locked} onClick={()=>onChoose(r,false)} >{knowledge?'编辑为新知识':'编辑为新题'}</button></div>}</article>)}{matches.length>0&&onKeep&&<div className="manual-dedup-choice"><label>独立保留原因<input value={reason} maxLength={200} onChange={e=>setReason(e.target.value)} placeholder="例如：条件不同"/></label><button type="button" disabled={locked||!reason.trim()} onClick={()=>onKeep(reason.trim())}>保留当前录入内容</button>{block.dedup_reason&&<small>已确认：{block.dedup_reason}</small>}</div>}</section>
}
function effectiveBlock(b:Block){
 if(b.kind!=='reference'||!b.snapshot||!b.edit_reference_revision)return b.snapshot??b
 return {...b.snapshot,title:b.title,content:b.content,answer:b.answer,solution:b.solution,analysis:b.analysis,proof:b.proof,question_type:b.question_type}
}
function SourcePreview({doc,stem}:{doc:Doc;stem:boolean}){
 const ref=useRef<HTMLDivElement>(null),[zoom,setZoom]=useState(1)
 useEffect(()=>{const el=ref.current;if(!el)return;const resize=()=>setZoom(Math.min(1,Math.max(.1,(el.clientWidth-12)/(210*96/25.4))));const ro=new ResizeObserver(resize);ro.observe(el);resize();return()=>ro.disconnect()},[])
 return <div className="manual-a4-fit" ref={ref}><div className="manual-a4-paper" style={{zoom}}><PrintableDocument doc={{...doc,blocks:doc.blocks.map(b=>b.edit_reference_revision&&b.snapshot?{...b,snapshot:effectiveBlock(b)}:b)}} stem={stem} source={doc.kind==='intake'}/></div></div>
}
const WordBlockPreview=memo(function WordBlockPreview({block:b,number}:{block:Block;number:number}){
 const v=effectiveBlock(b),question=v.kind==='question'
 if(b.kind==='image')return <figure><img src={'/api/files/'+encodeURIComponent(b.file_id??'')+'/preview'} alt={b.title} style={{width:b.width+'%'}}/>{b.title&&<figcaption><MathText compact content={b.title}/></figcaption>}</figure>
 if(b.kind==='pagebreak')return <div className="manual-word-pagebreak">分页符</div>
 if(b.kind==='heading'){const Heading=b.heading_level===2?'h3':'h2';return <div className={'manual-word-heading level-'+(b.heading_level??1)}><Heading><MathText compact content={b.title||b.content||'未填写标题'}/></Heading>{b.title&&b.content&&<ChatText content={b.content}/>}</div>}
 return <div className="manual-word-typeset">
 {question?<div className="manual-word-stem"><strong className="manual-word-number">{number}.</strong><div><ChatText content={v.content||'（点击录入题目）'}/></div>{!!b.score&&<small>（{b.score} 分）</small>}</div>:<>{v.title&&<h3><MathText compact content={v.title}/></h3>}<ChatText content={v.content||'（点击录入内容）'}/></>}
 {v.answer&&<div className="manual-word-answer"><strong>答案：</strong><ChatText content={v.answer}/></div>}{v.analysis&&<div className="manual-word-answer"><strong>思路：</strong><ChatText content={v.analysis}/></div>}{v.solution&&<div className="manual-word-answer"><strong>解析：</strong><ChatText content={v.solution}/></div>}{v.proof&&<div className="manual-word-answer"><strong>证明：</strong><ChatText content={v.proof}/></div>}
 </div>
})
type CardProps={doc:Doc;selected:string;panel:CardPanel;subjects:string[];dirty:boolean;busy:boolean;onPanel:(p:CardPanel)=>void;onSelect:(uid:string)=>void;onEdit:(p:Partial<Block>)=>void;onAdd:(kind:Kind,type?:string,level?:1|2)=>void;onRemove:()=>void;onMove:(n:number)=>void;onSave:()=>void;onReview?:()=>void;desktop?:boolean;onTitle?:(title:string)=>void;onImage?:(file:File)=>void;onReorder?:(uid:string,target:string)=>void;onPick?:()=>void;}
export default function ManualIntakeCards({doc,selected,panel,subjects,dirty,busy,onPanel,onSelect,onEdit,onAdd,onRemove,onMove,onSave,onReview,desktop=false,onTitle,onImage,onReorder,onPick}:CardProps){
 const navigate=useNavigate()
 const [preview,setPreview]=useState(false),[desktopPreview,setDesktopPreview]=useState(false),[outlineQuery,setOutlineQuery]=useState('')
 const imageInput=useRef<HTMLInputElement>(null)
 const [editorVersion,setEditorVersion]=useState(0),[adding,setAdding]=useState(false),[stemOnly,setStemOnly]=useState(doc.kind==='paper')
 function newItem(kind:Kind,type?:string,level?:1|2){onAdd(kind,type,level);setAdding(false)}
 const i=doc.blocks.findIndex(b=>b.uid===selected),block=doc.blocks[i],locked=busy||doc.archived
 const production=doc.kind!=='intake'
 const pending=doc.blocks.some(b=>b.kind==='question'||b.kind==='knowledge'||!!b.edit_reference_revision)
 const questionNumber=(b:Block)=>doc.blocks.slice(0,doc.blocks.indexOf(b)+1).filter(x=>x.kind==='question'||x.snapshot?.kind==='question').length
 useEffect(()=>{if(panel!=='list')setPreview(false)},[panel])
 useEffect(()=>{if(desktop&&!desktopPreview&&selected)document.getElementById('manual-word-'+selected)?.scrollIntoView({block:'nearest',inline:'nearest'})},[desktop,desktopPreview,selected])
 // Listen across the workbench, not just the paper: the outline, gutters,
 // and surrounding whitespace are all outside the active question card.
 useEffect(()=>{
  if(!desktop||desktopPreview||!selected||busy)return
  const outside=(event:MouseEvent)=>{
   const target=event.target instanceof Element?event.target:event.target instanceof Node?event.target.parentElement:null
   if(!target)return
   // Clicking another question switches directly to its editor. Keep
   // toolbar, outline, duplicate-match actions and form controls functional.
   if(target.closest('.workspace-confirm,[data-word-block],button,a,input,select,textarea,label,summary,[role="button"],[role="link"],[contenteditable="true"]'))return
   const active=document.activeElement
   const card=document.getElementById('manual-word-'+selected)
   if(active instanceof HTMLElement&&card?.contains(active))active.blur()
   onSelect('')
  }
  // The click phase follows the formula editor's pointerdown/blur commit.
  // Capture also handles surrounding UI which stops click propagation.
  document.addEventListener('click',outside,true)
  return()=>document.removeEventListener('click',outside,true)
 },[desktop,desktopPreview,selected,busy,onSelect])
 async function chooseMatch(r:MatchResource,reuse:boolean){
  if(block?.kind==='knowledge'){if(!await confirmAction('以候选知识单元替换当前草稿？'))return;onEdit({title:r.title,content:r.content,proof:r.proof??'',subject:r.subject,chapter:r.chapter,unit_type:r.unit_type??'',knowledge_tags:r.tags??[],reuse_resource_id:reuse?r.id:null,reuse_revision:reuse?r.revision:null,reuse_code:reuse?r.code:undefined,fork_from_id:reuse?null:r.id,dedup_reason:reuse?'':'以候选知识为基础编辑'});setEditorVersion(v=>v+1);return}
  if(block?.content.trim()&&block.content!==r.content&&!await confirmAction('使用候选题的题干、答案和解析替换当前草稿？'))return
  onEdit({content:r.content,answer:r.answer,solution:r.solution,subject:r.subject,chapter:r.chapter,question_type:r.question_type||'',difficulty:r.difficulty??'',title:'',analysis:'',knowledge_tags:r.knowledge_tags??r.tags??[],reuse_resource_id:reuse?r.id:null,reuse_revision:reuse?r.revision:null,reuse_code:reuse?r.code:undefined,fork_from_id:reuse?null:r.id,dedup_reason:reuse?'':'以候选题为基础编辑'})
  setEditorVersion(v=>v+1)
 }
 async function forkReference(){
  const v=block?.snapshot;if(!v||v.kind!=='question')return
  if(!await confirmAction('另存为新题？原题及原编号不会改变。'))return
  onEdit({kind:'question',resource_id:null,snapshot:undefined,edit_reference_revision:null,content:v.content,answer:v.answer,solution:v.solution,subject:v.subject??doc.subject,chapter:v.chapter,question_type:v.question_type??'',difficulty:v.difficulty??'',title:'',analysis:'',knowledge_tags:v.tags??[],reuse_resource_id:null,reuse_revision:null,fork_from_id:v.id})
  setEditorVersion(v=>v+1)
 }
 async function editReference(){
  const v=block?.snapshot;if(!v?.revision||!['question','knowledge'].includes(v.kind))return
  if(!await confirmAction('微调后保存将更新题库原资源，保留原编号及来源。确认？'))return
  onEdit({edit_reference_revision:v.revision,title:v.title,content:v.content,answer:v.answer,solution:v.solution,analysis:v.analysis,proof:v.proof,subject:v.subject??doc.subject,chapter:v.chapter,question_type:v.question_type??'',difficulty:v.difficulty??'',knowledge_tags:v.tags??[]})
  setEditorVersion(n=>n+1)
 }
 function cancelReferenceEdit(){onEdit({edit_reference_revision:null,title:"",content:"",answer:"",solution:"",analysis:"",proof:"",subject:null,chapter:"",question_type:"",difficulty:"",knowledge_tags:[]});setEditorVersion(n=>n+1)}
 function renderBlock(b:Block){
  const v=effectiveBlock(b),isQuestion=v.kind==='question'
  return <div className="manual-render">{isQuestion?<strong>第 {questionNumber(b)} 题</strong>:b.kind==='heading'&&<strong>{b.heading_level===2?'节标题':'章标题'}</strong>}{b.kind==='image'?<img src={'/api/files/'+encodeURIComponent(b.file_id??'')+'/preview'} alt={b.title} style={{width:b.width+'%'}}/>:b.kind==='pagebreak'?<p>—— 分页 ——</p>:<><ChatText content={b.kind==='heading'?b.title||b.content:v.content||'（尚未填写）'}/>{(v.answer||v.solution)&&<><div><strong>答案</strong><ChatText content={v.answer}/></div><div><strong>解析</strong><ChatText content={v.solution}/></div></>}{v.proof&&<ChatText content={v.proof}/>}</>}</div>
 }

 const editor=block?(<section className={desktop?'manual-word-editor':'panel mobile-doc-card'}><div className="mobile-doc-title"><h2>{block.kind==='question'||block.snapshot?.kind==='question'?'第 '+questionNumber(block)+' 题':block.kind==='knowledge'||block.snapshot?.kind==='knowledge'?'知识单元':block.kind==='heading'?(block.heading_level===2?'节标题':'章标题'):'正文'}</h2><small>{i+1}/{doc.blocks.length}</small></div>
  {production&&doc.kind==='paper'&&(block.kind==='question'||block.snapshot?.kind==='question')&&<label className="assembly-score">本题分值<input type="number" aria-label="本题分值" min={0} max={1000} step="0.5" disabled={locked} value={block.score??0} onChange={e=>onEdit({score:Math.min(1000,Math.max(0,Number(e.target.value)||0))})}/></label>}
  {production&&block.kind==='reference'?<>{renderBlock(block)}<small className="muted">{block.snapshot?.code} · 题库引用，原资源保持不变</small></>:block.kind==='question'?<><QuestionFields key={block.uid+'-'+editorVersion} value={block} subject={doc.subject} subjects={subjects} locked={locked||Boolean(block.reuse_resource_id)} onChange={async patch=>{if(patch.subject!==undefined&&patch.subject!==(block.subject??doc.subject)){if((block.chapter||block.knowledge_tags?.length)&&!await confirmAction('切换科目将清空原章节和知识点，确认？'))return;onEdit({...patch,chapter:'',knowledge_tags:[]})}else onEdit(patch)}} knowledge={production?undefined:<KnowledgePoints key={block.uid} value={block.knowledge_tags??[]} subject={block.subject??doc.subject} locked={locked} onChange={tags=>onEdit({knowledge_tags:tags})}/>}/>{block.reuse_resource_id?<div className="manual-match"><strong>已选择原题 {block.reuse_code||''}，保存后沿用原编号</strong><button type="button" disabled={locked} onClick={()=>{onEdit({fork_from_id:block.reuse_resource_id,reuse_resource_id:null,reuse_revision:null,reuse_code:undefined,dedup_reason:'以原题为基础另存'});setEditorVersion(v=>v+1)}}>编辑相关信息 · 另存为新题</button></div>:!desktop&&!production&&<DuplicateMatches key={block.uid} block={block} locked={locked} onChoose={chooseMatch} onKeep={reason=>onEdit({dedup_reason:reason})}/>}</>:block.kind==='knowledge'?<><label>知识类型<select value={block.unit_type} disabled={locked||Boolean(block.reuse_resource_id)} onChange={e=>onEdit({unit_type:e.target.value})}><option value="">请选择</option>{['定义','定理','公式','性质','推论','方法'].map(t=><option key={t}>{t}</option>)}</select></label><Field label="知识单元名称" value={block.title} locked={locked||Boolean(block.reuse_resource_id)} onChange={v=>onEdit({title:v})}/><div className="manual-attributes"><label>科目<select value={block.subject??doc.subject} disabled={locked||Boolean(block.reuse_resource_id)} onChange={e=>onEdit({subject:e.target.value,chapter:'',knowledge_tags:[]})}>{Array.from(new Set(['',block.subject??doc.subject,...subjects])).map(s=><option key={s} value={s}>{s||'请选择科目'}</option>)}</select></label><label>章节（选填）<input value={block.chapter} disabled={locked||Boolean(block.reuse_resource_id)} onChange={e=>onEdit({chapter:e.target.value})}/></label></div><Field label="知识正文" value={block.content} locked={locked||Boolean(block.reuse_resource_id)} onChange={v=>onEdit({content:v})}/><Field label="解析 / 证明" value={block.proof} locked={locked||Boolean(block.reuse_resource_id)} onChange={v=>onEdit({proof:v})}/>{!production&&<KnowledgePoints key={block.uid} value={block.knowledge_tags??[]} subject={block.subject??doc.subject} locked={locked||Boolean(block.reuse_resource_id)} onChange={tags=>onEdit({knowledge_tags:tags})}/>}{block.reuse_resource_id?<div className="manual-match">已选择 {block.reuse_code}<button type="button" disabled={locked} onClick={()=>onEdit({reuse_resource_id:null,reuse_revision:null,reuse_code:undefined,dedup_reason:'另存为独立知识单元'})}>编辑为新知识</button></div>:!desktop&&!production&&<DuplicateMatches key={block.uid} block={block} locked={locked} onChoose={chooseMatch} onKeep={reason=>onEdit({dedup_reason:reason})}/>}</>:block.kind==='reference'?block.edit_reference_revision?<><div className="manual-word-side-head"><strong>微调原资源 {block.snapshot?.code}</strong><button type="button" disabled={locked} onClick={cancelReferenceEdit}>取消微调</button></div>{block.snapshot?.kind==='question'?<><QuestionFields key={block.uid+'-ref-'+editorVersion} value={block} subject={doc.subject} subjects={subjects} locked={locked} contentOnly onChange={onEdit}/><Field label="思路" value={block.analysis} locked={locked} onChange={v=>onEdit({analysis:v})}/></>:<><Field label="标题" value={block.title} locked={locked} onChange={v=>onEdit({title:v})}/><Field label="知识正文" value={block.content} locked={locked} onChange={v=>onEdit({content:v})}/><Field label="解析 / 证明" value={block.proof} locked={locked} onChange={v=>onEdit({proof:v})}/></>}<small className="muted">保存时更新原资源，编号与来源不变；不覆盖其他文档快照。</small></>:<>{renderBlock(block)}<p className="muted">已入库 · {block.snapshot?.code}</p>{Boolean(block.snapshot?.tags?.length)&&<p className="muted">知识点：{block.snapshot?.tags?.join('、')}</p>}{block.snapshot?.revision&&<button type="button" disabled={locked} onClick={editReference}>微调原题 / 知识单元</button>}{block.snapshot?.kind==='question'&&<button type="button" disabled={locked} onClick={forkReference}>编辑为新题</button>}{block.resource_id&&<Link className="button-link" to={'/intake?resource='+encodeURIComponent(block.resource_id)} onClick={e=>{if(dirty){e.preventDefault();const url='/intake?resource='+encodeURIComponent(block.resource_id??'');void confirmAction('当前修改尚未保存，确认离开？','离开工作台','离开').then(ok=>{if(ok)navigate(url)})}}}>修改正式资源</Link>}</>:block.kind==='heading'?<><label>标题层级<select aria-label="标题层级" value={block.heading_level??1} disabled={locked} onChange={e=>onEdit({heading_level:e.target.value==='2'?2:1})}><option value={1}>章</option><option value={2}>节</option></select></label><div className={'manual-heading-input level-'+(block.heading_level??1)}><Field label={block.heading_level===2?'节标题':'章标题'} value={block.title} locked={locked} onChange={v=>onEdit({title:v})}/></div></>:block.kind==='text'?<Field label="正文" value={block.content} locked={locked} onChange={v=>onEdit({content:v})}/>:block.kind==='image'?<><div className="standalone-image-thumb">{renderBlock(block)}</div><div className="button-row image-presets">{[25,50,75,100].map(w=><button type="button" key={w} aria-pressed={block.width===w} disabled={locked} onClick={()=>onEdit({width:w})}>{w}%</button>)}{block.file_id&&<a className="button-link" target="_blank" rel="noopener noreferrer" href={'/api/files/'+block.file_id+'/preview'}>查看原图</a>}</div><label>图片宽度 {block.width}%<input type="range" min={20} max={100} step={5} value={block.width} disabled={locked} onChange={e=>onEdit({width:Number(e.target.value)})}/></label><Field label="图片说明" value={block.title} locked={locked} onChange={v=>onEdit({title:v})}/></>:renderBlock(block)}
  <div className="button-row">{!production&&<button type="button" disabled={locked} onClick={()=>{onSelect('');onPanel('list')}}>完成录入</button>}{!production&&block.kind==='question'&&<button type="button" disabled={locked} onClick={()=>newItem('question',block.question_type||'综合题')}>添加下一题</button>}{!desktop&&<><button type="button" disabled={locked||i===0} onClick={()=>onMove(-1)}>上移</button><button type="button" disabled={locked||i+1===doc.blocks.length} onClick={()=>onMove(1)}>下移</button></>}<button type="button" disabled={locked} onClick={onRemove}>移除</button></div></section>):null
 if(desktop){
  const matchBlock=block?.kind==='reference'&&block.snapshot?.kind==='question'&&!block.edit_reference_revision?{...block,content:block.snapshot.content,answer:block.snapshot.answer,solution:block.snapshot.solution}:block
  const question=matchBlock&&block?.kind==='question'
  const knowledge=block?.kind==='knowledge'
  const blockLabel=(b:Block)=>b.kind==='question'||b.snapshot?.kind==='question'?'第 '+questionNumber(b)+' 题':b.kind==='heading'?(b.heading_level===2?'节标题':'章标题'):b.kind==='knowledge'||b.snapshot?.kind==='knowledge'?'知识单元':b.kind==='image'?'图片':b.kind==='pagebreak'?'分页':'正文'
  const go=(uid:string)=>{if(busy)return;setDesktopPreview(false);setAdding(false);onSelect(uid)}
  const closeEditor=()=>{if(!busy)onSelect('')}
  const sheets:{key:string;blocks:Block[]}[]=[{key:'first',blocks:[]}];for(const b of doc.blocks){sheets[sheets.length-1].blocks.push(b);if(b.kind==='pagebreak')sheets.push({key:b.uid,blocks:[]})}
  return <section className={'manual-intake-cards manual-word-work'+(production?' assembly-word':'')}>
   <header className="manual-word-toolbar"><div className="manual-word-name"><strong><MathText compact content={doc.title}/></strong><small>{doc.archived?'已归档':dirty?'未保存':'已保存'} · {doc.blocks.length} 项</small></div><button type="button" aria-pressed={!desktopPreview} onClick={()=>{setDesktopPreview(false);closeEditor()}}>编辑</button><button type="button" aria-pressed={desktopPreview} onClick={()=>{closeEditor();setDesktopPreview(true)}}>整套预览</button><button type="button" className="primary" disabled={locked||!dirty} onClick={onSave}>{busy?'保存中…':production?'保存编排':'保存草稿'}</button>{!production&&<button type="button" className="primary" disabled={locked||!pending} onClick={onReview}>检查并入库</button>}{production&&<Link className="button-link" to={'/print/'+doc.id+(stemOnly?'?stem=1':'')} onClick={e=>{if(dirty||busy){e.preventDefault();void confirmAction('请先保存编排，再进行打印或导出。','请先保存','知道了')}}}>打印 / PDF</Link>}</header>
   <div className="manual-word-toolbar manual-word-insert">{production?<button type="button" disabled={locked} onClick={onPick}>＋ 继续选题</button>:<>{questionTypes.map(t=><button key={t} type="button" disabled={locked} onClick={()=>{setDesktopPreview(false);newItem('question',t)}}>＋ {t}</button>)}<button type="button" disabled={locked} onClick={()=>{setDesktopPreview(false);newItem('knowledge')}}>＋ 知识单元</button></>}<button type="button" disabled={locked} onClick={()=>{setDesktopPreview(false);newItem('heading',undefined,1)}}>＋ 章</button><button type="button" disabled={locked} onClick={()=>{setDesktopPreview(false);newItem('heading',undefined,2)}}>＋ 节</button><button type="button" disabled={locked} onClick={()=>{setDesktopPreview(false);newItem('text')}}>＋ 正文</button>{onImage&&<><input ref={imageInput} type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={e=>{const f=e.target.files?.[0];if(f){setDesktopPreview(false);onImage(f)}e.target.value=''}}/><button type="button" disabled={locked} onClick={()=>imageInput.current?.click()}>图片</button></>}<button type="button" disabled={locked} onClick={()=>{setDesktopPreview(false);newItem('pagebreak')}}>分页</button><button type="button" disabled={!block||locked||i<=0} onClick={()=>onMove(-1)}>上移</button><button type="button" disabled={!block||locked||i+1>=doc.blocks.length} onClick={()=>onMove(1)}>下移</button></div>
   <div className={'manual-word-layout'+(!production&&!desktopPreview&&(question||knowledge)?' has-matches':production?' has-matches':' no-matches')}>
    <aside className="manual-word-outline"><div className="manual-word-side-head"><strong>文档目录</strong><small>{doc.blocks.length} 项</small></div><input aria-label="搜索文档大纲" placeholder="搜索题目或编号" value={outlineQuery} onChange={e=>setOutlineQuery(e.target.value)}/><nav aria-label="文档大纲">{doc.blocks.filter(b=>!outlineQuery.trim()||[blockLabel(b),b.title,b.snapshot?.code,effectiveBlock(b).content].join(' ').includes(outlineQuery.trim())).map(b=><button key={b.uid} type="button" aria-current={b.uid===selected?'true':undefined} draggable={!locked&&!!onReorder} onDragStart={e=>{e.dataTransfer.setData('application/x-wg-block',b.uid);e.dataTransfer.effectAllowed='move'}} onDragOver={e=>{if(!locked&&e.dataTransfer.types.includes('application/x-wg-block')){e.preventDefault();e.dataTransfer.dropEffect='move'}}} onDrop={e=>{e.preventDefault();const uid=e.dataTransfer.getData('application/x-wg-block');if(!locked&&uid&&onReorder){setDesktopPreview(false);onReorder(uid,b.uid)}}} onClick={()=>{if(b.uid===selected)closeEditor();else go(b.uid)}}><span>{blockLabel(b)}</span><small><MathText compact content={b.snapshot?.code||b.title||effectiveBlock(b).content.slice(0,60)||'空白'}/></small></button>)}</nav><details><summary>文档设置</summary>{onTitle&&<label>标题<input value={doc.title} maxLength={200} disabled={locked} onChange={e=>onTitle(e.target.value)}/></label>}</details></aside>
    <main className="manual-word-canvas">
     {desktopPreview?<section className="manual-intake-preview"><label className="manual-word-preview-toggle"><input type="checkbox" checked={stemOnly} onChange={e=>setStemOnly(e.target.checked)}/> 仅题目</label><SourcePreview doc={doc} stem={stemOnly}/></section>:<div className="manual-word-stage" aria-label="Word 文档">
      {sheets.map((sheet,index)=><section key={sheet.key} className="manual-word-paper" aria-label={'文档页 '+(index+1)}>
       {index===0&&<header className="manual-word-paper-header"><h1><MathText compact content={doc.title}/></h1>{(doc.subject||doc.kind==='paper')&&<p>{doc.subject}{doc.kind==='paper'?' 总分：'+doc.blocks.reduce((sum,b)=>sum+(b.score??0),0):''}</p>}</header>}
       {sheet.blocks.map(b=><article key={b.uid} id={'manual-word-'+b.uid} data-word-block={b.uid} className={'manual-word-item '+(selected===b.uid?'active':'')}>
        {selected===b.uid?<><div className="manual-word-editbar"><small>{blockLabel(b)} · 编辑中</small><button type="button" disabled={busy} onClick={closeEditor}>完成编辑</button></div>{editor}</>:<div role="button" tabIndex={0} aria-label={'编辑 '+blockLabel(b)} className="manual-word-read" onClick={()=>go(b.uid)} onKeyDown={e=>{if(e.target===e.currentTarget&&(e.key==='Enter'||e.key===' ')){e.preventDefault();go(b.uid)}}}><WordBlockPreview block={b} number={questionNumber(b)}/></div>}
       </article>)}
       {!production&&index===sheets.length-1&&<button type="button" className="manual-paper-add" disabled={locked} onClick={()=>{setAdding(v=>!v)}}>＋ 添加内容</button>}{!production&&adding&&index===sheets.length-1&&<div className="manual-add-grid">{questionTypes.map(t=><button key={t} onClick={()=>newItem('question',t)}>{t}</button>)}<button onClick={()=>newItem('knowledge')}>知识单元</button><button onClick={()=>newItem('heading',undefined,1)}>章标题</button><button onClick={()=>newItem('heading',undefined,2)}>节标题</button><button onClick={()=>newItem('text')}>正文</button></div>}{!sheet.blocks.length&&production&&<p className="muted manual-word-empty">从上方添加题目或正文。</p>}
       <div className="manual-word-paper-tail" aria-label="纸张空白区域"/>
      </section>)}
     </div>}
    </main>
    {production?<aside className="manual-word-matches"><div className="manual-word-side-head"><strong>编排信息</strong></div><p>题目：{doc.blocks.filter(b=>b.kind==='question'||b.snapshot?.kind==='question').length}</p>{doc.kind!=='paper'&&<p>知识单元：{doc.blocks.filter(b=>b.kind==='knowledge'||b.snapshot?.kind==='knowledge').length}</p>}{doc.kind==='paper'&&<p>总分：{doc.blocks.reduce((sum,b)=>sum+(b.score??0),0)}</p>}<p className="muted">在左侧拖动调整顺序；点击正文或标题编辑。题库引用不会随编排改变。</p></aside>:!desktopPreview&&block&&(question||knowledge)?<aside className="manual-word-matches"><div className="manual-word-side-head"><strong>{knowledge?'知识库查重':'题库查重'}</strong><small>同类型资源</small></div><DuplicateMatches key={block.uid} block={block} locked={busy} onChoose={!locked?chooseMatch:undefined} onKeep={reason=>onEdit({dedup_reason:reason})}/>{block.reuse_resource_id&&<p className="muted">已复用 {block.reuse_code}</p>}</aside>:null}
   </div>
  </section>
 }
 return <section className="mobile-doc-work manual-intake-cards">
  <header className="mobile-doc-header"><div className="mobile-doc-title"><div><h2><MathText compact content={doc.title}/></h2><small className="muted">{doc.blocks.length} 个条目 · {doc.archived?'已归档':dirty?'未保存':pending?'有待入库条目':'已保存'}</small></div><button type="button" className="primary" disabled={locked||!dirty} onClick={onSave}>保存草稿</button><button type="button" className="primary" disabled={locked||!pending} onClick={onReview}>检查并入库</button></div>
  <nav className="mobile-doc-nav" aria-label="手机录入方式"><button type="button" aria-pressed={!preview} onClick={()=>{setPreview(false);setAdding(false);onPanel('list')}}>录入编辑</button><button type="button" aria-pressed={panel==='list'&&preview} onClick={()=>{setPreview(true);onPanel('list')}}>Word 预览</button></nav></header>
  {panel==='list'&&preview?<section className="manual-intake-preview"><div className="button-row"><label><input type="checkbox" checked={stemOnly} onChange={e=>setStemOnly(e.target.checked)}/> 仅题目</label></div><SourcePreview doc={doc} stem={stemOnly}/></section>:panel==='list'?<section className="manual-all">{doc.blocks.map((b,n)=><article key={b.uid} className="panel manual-list-row">{preview?renderBlock(b):<div><strong>{b.kind==='question'||b.snapshot?.kind==='question'?'第 '+questionNumber(b)+' 题':b.kind==='heading'?(b.heading_level===2?'节标题':'章标题'):b.kind==='knowledge'||b.snapshot?.kind==='knowledge'?effectiveBlock(b).title||'知识单元':'正文'}</strong><small className="muted">{b.kind==='reference'&&!b.edit_reference_revision?'已入库':b.reuse_resource_id?'引用已有资源':'草稿'}</small><div className="manual-list-excerpt">{b.kind==='image'?<div className="standalone-image-thumb">{renderBlock(b)}</div>:<ChatText content={effectiveBlock(b).content||effectiveBlock(b).title||'空白条目'}/>}{(effectiveBlock(b).answer||effectiveBlock(b).solution||effectiveBlock(b).proof)&&<details><summary>答案、解析或证明</summary><ChatText content={[effectiveBlock(b).answer,effectiveBlock(b).solution,effectiveBlock(b).proof].filter(Boolean).join('\n\n')}/></details>}</div></div>}<button type="button" aria-label={'编辑第 '+(n+1)+' 个条目'} disabled={busy} onClick={()=>{setAdding(false);onSelect(b.uid)}}>编辑 <Icon name="chevron" size={14}/></button></article>)}{!doc.blocks.length&&<p className="muted">尚未录入内容。</p>}<button type="button" className="manual-paper-add" disabled={locked} onClick={()=>{setAdding(true);onPanel('card')}}>＋ 添加内容</button></section>:adding||!block?<section className="panel mobile-doc-card manual-add"><h2>添加下一条内容</h2><div className="manual-add-grid">{questionTypes.map(t=><button key={t} type="button" disabled={locked} onClick={()=>newItem('question',t)}>＋ {t}</button>)}<button type="button" disabled={locked} onClick={()=>newItem('knowledge')}>＋ 知识单元</button><button type="button" disabled={locked} onClick={()=>newItem('heading',undefined,1)}>＋ 章</button><button type="button" disabled={locked} onClick={()=>newItem('heading',undefined,2)}>＋ 节</button><button type="button" disabled={locked} onClick={()=>newItem('text')}>＋ 正文</button></div>{onImage&&<><input ref={imageInput} type="file" hidden accept="image/png,image/jpeg,image/webp,image/gif" onChange={e=>{const f=e.target.files?.[0];if(f){setAdding(false);onImage(f)}e.target.value=''}}/><button type="button" disabled={locked} onClick={()=>imageInput.current?.click()}>＋ 图片</button></>}<button type="button" onClick={()=>{setAdding(false);onPanel('list')}}>返回录入列表</button></section>:editor}
  {panel==='card'&&block&&!adding&&<nav className="mobile-doc-bottom" aria-label="逐题导航"><button type="button" disabled={busy||i<=0} onClick={()=>onSelect(doc.blocks[i-1].uid)}>上一条</button><button type="button" className="primary" disabled={busy||doc.archived&&i+1>=doc.blocks.length} onClick={()=>{if(i+1<doc.blocks.length)onSelect(doc.blocks[i+1].uid);else setAdding(true)}}>{i+1<doc.blocks.length?'下一条':'下一条 · 新增'}</button></nav>}
 </section>
}
