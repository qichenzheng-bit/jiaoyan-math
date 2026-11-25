import {useEffect,useRef,useState,type ReactNode} from 'react'
import {Link} from 'react-router-dom'
import type {Block,Doc,Kind} from '../pages/DocWork'
import type {CardPanel} from './MobileDocWork'
import {MathText} from './MathText'
import ChatText from '../pages/ChatText'
import {Icon} from './Icon'

export const questionTypes=['单选题','多选题','填空题','解答题','计算题','证明题','其他']
type QuestionValue={subject?:string|null;chapter:string;question_type:string;content:string;answer:string;solution:string}
type Props={value:QuestionValue;subject:string;subjects:string[];locked:boolean;onChange:(p:Partial<QuestionValue>)=>void}
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
function Field({label,value,onChange,locked,placeholder,rows=3}:{label:string;value:string;onChange:(v:string)=>void;locked:boolean;placeholder?:string;rows?:number}){
 return <label className="manual-field">{label}<textarea aria-label={label} rows={rows} maxLength={label==='答案'?20000:50000} disabled={locked} value={value} placeholder={placeholder} onChange={e=>onChange(e.target.value)}/>{value.trim()&&<div className="manual-field-preview"><ChatText content={value}/></div>}</label>
}
export function QuestionFields({value,subject,subjects,locked,onChange}:Props){
 const type=value.question_type||'解答题',choice=type==='单选题'||type==='多选题'||type==='选择题',multiple=type==='多选题',fill=type==='填空题',big=!choice&&!fill
 const options=marked(value.content,choicesPattern),sub=marked(value.content,subPattern),answers=marked(value.answer,subPattern),solutions=marked(value.solution,subPattern)
 const [optionCount,setOptionCount]=useState(Math.max(4,...options.order.map(k=>k.charCodeAt(0)-64))),[subCount,setSubCount]=useState(Math.max(0,...[...sub.order,...answers.order,...solutions.order].map(Number)))
 const stemRef=useRef<HTMLTextAreaElement>(null)
 const optKeys=Array.from({length:Math.min(26,optionCount)},(_,i)=>String.fromCharCode(65+i))
 const subKeys=Array.from({length:Math.min(30,subCount)},(_,i)=>String(i+1))
 const hasSubs=big&&subCount>0
 const stem=choice?options.main:hasSubs?sub.main:value.content
 const selectedLetters=/^[A-Z\s,，、]+$/.test(value.answer.trim())?value.answer.match(/[A-Z]/g)??[]:[]
 function setStem(v:string){onChange({content:choice?combine(v,options.parts,optKeys,k=>k+'. '):hasSubs?combine(v,sub.parts,subKeys,k=>'('+k+') '):v})}
 function setOption(k:string,v:string){onChange({content:combine(options.main,{...options.parts,[k]:v},optKeys,l=>l+'. ')})}
 function setSub(k:string,field:'content'|'answer'|'solution',v:string){
  const data=field==='content'?sub:field==='answer'?answers:solutions
  onChange({[field]:combine(data.main,{...data.parts,[k]:v},subKeys,l=>'('+l+') ')})
 }
 function removeSub(k:string){
  if([sub.parts[k],answers.parts[k],solutions.parts[k]].some(v=>v?.trim())&&!window.confirm('移除该小问及其答案、解析？'))return
  const remaining=subKeys.filter(l=>l!==k)
  const renumber=(data:ReturnType<typeof marked>)=>combine(data.main,Object.fromEntries(remaining.map((old,i)=>[String(i+1),data.parts[old]??''])),remaining.map((_,i)=>String(i+1)),l=>'('+l+') ')
  onChange({content:renumber(sub),answer:renumber(answers),solution:renumber(solutions)})
  setSubCount(n=>Math.max(0,n-1))
 }
 function toggleLetter(k:string){
  if(multiple){const next=selectedLetters.includes(k)?selectedLetters.filter(v=>v!==k):[...selectedLetters,k];onChange({answer:[...new Set(next)].sort().join('')})}
  else onChange({answer:k})
 }
 function addBlank(){const el=stemRef.current,start=el?.selectionStart??stem.length,end=el?.selectionEnd??start;const blank='$\\underline{\\qquad}$';setStem(stem.slice(0,start)+blank+stem.slice(end))}
 const commonAnswer=hasSubs?answers.main:value.answer,commonSolution=hasSubs?solutions.main:value.solution
 return <div className="manual-question-fields">
  <div className="manual-attributes"><label>科目<select aria-label="科目" disabled={locked} value={value.subject??subject} onChange={e=>onChange({subject:e.target.value})}>{Array.from(new Set([value.subject??subject,...subjects])).map(s=><option key={s} value={s}>{s||'未分类'}</option>)}</select></label><label>所在章节（选填）<input aria-label="所在章节" disabled={locked} maxLength={120} value={value.chapter} onChange={e=>onChange({chapter:e.target.value})}/></label><label>题型<select aria-label="题型" disabled={locked} value={type} onChange={e=>{onChange({question_type:e.target.value});setOptionCount(Math.max(4,...options.order.map(k=>k.charCodeAt(0)-64)));setSubCount(Math.max(0,...[...sub.order,...answers.order,...solutions.order].map(Number)))}}>{Array.from(new Set([type,...questionTypes])).map(t=><option key={t}>{t}</option>)}</select></label></div>
  <label className="manual-field">题目<textarea ref={stemRef} aria-label="题目" disabled={locked} rows={5} maxLength={50000} value={stem} onChange={e=>setStem(e.target.value)} placeholder="输入题干，支持 LaTeX"/>{stem.trim()&&<div className="manual-field-preview"><ChatText content={stem}/></div>}</label>
  {fill&&<button type="button" disabled={locked} onClick={addBlank}>＋ 插入填空空位</button>}
  {choice&&<div className="manual-options"><strong>选项</strong>{optKeys.map(k=><Field key={k} label={k+' 选项'} value={options.parts[k]??''} locked={locked} rows={2} onChange={v=>setOption(k,v)}/>)}<div className="button-row"><button type="button" disabled={locked||optionCount>=26} onClick={()=>setOptionCount(n=>n+1)}>＋ 添加选项</button><button type="button" disabled={locked||optionCount<=2} onClick={()=>{const k=optKeys.at(-1)!;if(options.parts[k]?.trim()&&!window.confirm('移除最后一个选项？'))return;setOption(k,'');setOptionCount(n=>n-1)}}>减少选项</button></div><strong>{multiple?'选择正确选项（可多选）':'选择正确选项（单选）'}</strong><div className="button-row manual-answer-choices">{optKeys.map(k=><button type="button" key={k} disabled={locked} aria-pressed={selectedLetters.includes(k)} onClick={()=>toggleLetter(k)}>{k}</button>)}</div></div>}
  <Field label="答案" value={commonAnswer} locked={locked} placeholder={fill?'多个空的答案按顺序填写':hasSubs?'共用答案（可留空）':'输入答案'} onChange={v=>onChange({answer:hasSubs?combine(v,answers.parts,subKeys,k=>'('+k+') '):v})}/>
  <Field label="解析" value={commonSolution} locked={locked} rows={5} placeholder={hasSubs?'共用解析（可留空）':'输入解析'} onChange={v=>onChange({solution:hasSubs?combine(v,solutions.parts,subKeys,k=>'('+k+') '):v})}/>
  {big&&<div className="manual-subquestions">{subKeys.map(k=><section className="manual-subquestion" key={k}><div className="mobile-doc-title"><strong>第 {k} 小问</strong><button type="button" disabled={locked} onClick={()=>removeSub(k)}>移除</button></div>{(['content','answer','solution'] as const).map(f=><Field key={f} label={'第 '+k+' 小问'+({content:'题目',answer:'答案',solution:'解析'}[f])} value={(f==='content'?sub:f==='answer'?answers:solutions).parts[k]??''} locked={locked} onChange={v=>setSub(k,f,v)}/>)}</section>)}<button type="button" disabled={locked||subCount>=30} onClick={()=>setSubCount(n=>n+1)}>＋ 添加小问（可选）</button></div>}
 </div>
}

type CardProps={doc:Doc;selected:string;panel:CardPanel;subjects:string[];dirty:boolean;busy:boolean;onPanel:(p:CardPanel)=>void;onSelect:(uid:string)=>void;onEdit:(p:Partial<Block>)=>void;onAdd:(kind:Kind,type?:string)=>void;onRemove:()=>void;onMove:(n:number)=>void;onSave:()=>void;onSaveNext:(uid?:string)=>void;onReference:()=>void;children:ReactNode}
export default function ManualIntakeCards({doc,selected,panel,subjects,dirty,busy,onPanel,onSelect,onEdit,onAdd,onRemove,onMove,onSave,onSaveNext,onReference,children}:CardProps){
 const [preview,setPreview]=useState(false)
 const i=doc.blocks.findIndex(b=>b.uid===selected),block=doc.blocks[i],locked=busy||doc.archived
 const pending=doc.blocks.some(b=>b.kind==='question'||b.kind==='knowledge')
 const questionNumber=(b:Block)=>doc.blocks.slice(0,doc.blocks.indexOf(b)+1).filter(x=>x.kind==='question'||x.snapshot?.kind==='question').length
 useEffect(()=>{if(panel!=='list')setPreview(false)},[panel])
 function renderBlock(b:Block){
  const v=b.snapshot??b,isQuestion=v.kind==='question'
  return <div className="manual-render">{isQuestion?<strong>第 {questionNumber(b)} 题</strong>:b.kind==='heading'&&<strong>章节</strong>}{b.kind==='image'?<img src={'/api/files/'+encodeURIComponent(b.file_id??'')+'/preview'} alt={b.title}/>:b.kind==='pagebreak'?<p>—— 分页 ——</p>:<><ChatText content={b.kind==='heading'?b.title||b.content:v.content||'（尚未填写）'}/>{(v.answer||v.solution)&&<><div><strong>答案</strong><ChatText content={v.answer}/></div><div><strong>解析</strong><ChatText content={v.solution}/></div></>}{v.proof&&<ChatText content={v.proof}/>}</>}</div>
 }
 return <section className="mobile-doc-work manual-intake-cards">
  <header className="mobile-doc-header"><div className="mobile-doc-title"><div><h2><MathText compact content={doc.title}/></h2><small className="muted">{doc.blocks.length} 个条目 · {doc.archived?'已归档':dirty?'未保存':pending?'有待入库条目':'已保存'}</small></div><button type="button" className="primary" disabled={locked||(!dirty&&!pending)} onClick={onSave}>{busy?'保存中…':'保存并入库'}</button></div>
  <nav className="mobile-doc-nav" aria-label="手机录入方式"><button type="button" aria-pressed={panel==='card'} onClick={()=>onPanel('card')}>逐题编辑</button><button type="button" aria-pressed={panel==='list'&&!preview} onClick={()=>{setPreview(false);onPanel('list')}}>全部题目</button><button type="button" aria-pressed={panel==='list'&&preview} onClick={()=>{setPreview(true);onPanel('list')}}>整套预览</button></nav></header>
  {panel==='tools'?<div className="mobile-doc-tool"><button type="button" onClick={()=>onPanel('card')}>← 返回录入</button>{children}</div>:panel==='list'?<section className="manual-all">{doc.blocks.map((b,n)=><article key={b.uid} className="panel manual-list-row">{preview?renderBlock(b):<div><strong>{b.kind==='question'||b.snapshot?.kind==='question'?'第 '+questionNumber(b)+' 题':b.kind==='heading'?'章节':b.kind==='knowledge'||b.snapshot?.kind==='knowledge'?'知识单元':'正文'}</strong><div className="manual-list-excerpt"><ChatText content={b.snapshot?.content||b.content||b.title||'空白条目'}/></div></div>}<button type="button" aria-label={'编辑第 '+(n+1)+' 个条目'} disabled={busy} onClick={()=>onSelect(b.uid)}>编辑 <Icon name="chevron" size={14}/></button></article>)}{!doc.blocks.length&&<p className="muted">尚未录入内容。</p>}</section>:block?<section className="panel mobile-doc-card"><div className="mobile-doc-title"><h2>{block.kind==='question'||block.snapshot?.kind==='question'?'第 '+questionNumber(block)+' 题':block.kind==='knowledge'||block.snapshot?.kind==='knowledge'?'知识单元':block.kind==='heading'?'章节标题':'正文'}</h2><small>{i+1}/{doc.blocks.length}</small></div>
  {block.kind==='question'?<QuestionFields key={block.uid} value={block} subject={doc.subject} subjects={subjects} locked={locked} onChange={onEdit}/>:block.kind==='knowledge'?<><div className="manual-attributes"><label>科目<select value={block.subject??doc.subject} disabled={locked} onChange={e=>onEdit({subject:e.target.value})}>{Array.from(new Set([block.subject??doc.subject,...subjects])).map(s=><option key={s}>{s}</option>)}</select></label><label>章节（选填）<input value={block.chapter} disabled={locked} onChange={e=>onEdit({chapter:e.target.value})}/></label></div><Field label="知识正文" value={block.content} locked={locked} onChange={v=>onEdit({content:v})}/><Field label="解析 / 证明" value={block.proof} locked={locked} onChange={v=>onEdit({proof:v})}/></>:block.kind==='reference'?<>{renderBlock(block)}<p className="muted">已入库或引用题库</p>{block.resource_id&&<Link className="button-link" to={'/intake?resource='+encodeURIComponent(block.resource_id)} onClick={e=>{if(dirty&&!window.confirm('有未保存修改，确认离开？'))e.preventDefault()}}>修改正式资源</Link>}</>:block.kind==='heading'?<Field label="章节标题" value={block.title} locked={locked} onChange={v=>onEdit({title:v})}/>:block.kind==='text'?<Field label="正文" value={block.content} locked={locked} onChange={v=>onEdit({content:v})}/>:renderBlock(block)}
  <div className="button-row"><button type="button" disabled={locked||i===0} onClick={()=>onMove(-1)}>上移</button><button type="button" disabled={locked||i+1===doc.blocks.length} onClick={()=>onMove(1)}>下移</button><button type="button" disabled={locked} onClick={onRemove}>移除</button></div></section>:<p className="muted">选择下方题型开始录入。</p>}
  {panel!=='tools'&&<section className="manual-add"><strong>添加内容</strong><div className="manual-add-grid">{questionTypes.slice(0,6).map(t=><button key={t} type="button" disabled={locked} onClick={()=>onAdd('question',t)}>＋ {t}</button>)}<button type="button" disabled={locked} onClick={()=>onAdd('knowledge')}>＋ 知识单元</button><button type="button" disabled={locked} onClick={()=>onAdd('heading')}>＋ 章节</button><button type="button" disabled={locked} onClick={()=>onAdd('text')}>＋ 正文</button><button type="button" disabled={locked} onClick={onReference}>＋ 引用题库</button></div></section>}
  {panel==='card'&&block&&<nav className="mobile-doc-bottom" aria-label="逐题导航"><button type="button" disabled={busy||i<=0} onClick={()=>onSelect(doc.blocks[i-1].uid)}>上一条</button><button type="button" className="primary" disabled={locked||(!dirty&&!pending)} onClick={()=>onSaveNext(doc.blocks[i+1]?.uid)}>保存并入库</button><button type="button" disabled={busy||i+1>=doc.blocks.length} onClick={()=>onSelect(doc.blocks[i+1].uid)}>下一条</button></nav>}
 </section>
}
