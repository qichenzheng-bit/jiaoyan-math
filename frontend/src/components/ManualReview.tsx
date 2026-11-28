import {useEffect,useState} from 'react'
import {WorkspaceLink as Link} from './WorkspaceNavigation'
import {MathText,mathTokens} from './MathText'
import {Icon} from './Icon'
import {renderMathHtml} from './mathRendering'
import {WorkspaceFeedback} from './WorkspaceFeedback'
import type {Doc} from '../pages/DocWork'
import {PrintableDocument} from '../pages/DocumentPrint'
import {api} from '../auth'
import {ReviewProgress,ReviewDirectory,ReviewSections} from './ReviewShared'
import {SourceView,type SourceJob} from './ReviewSource'
import {DuplicateMatches} from './ManualIntakeCards'
import '../pages/WorkReview.css'
type Row={uid:string;number:number;kind:'question'|'knowledge';title:string;action:'create'|'reuse'|'update'|'append'|'batch_reuse';errors:string[];warnings:string[]}
export type ReviewData={revision:number;rows:Row[];reviewed_uids?:string[]}
export type ResultCounts={question_create:number;question_reuse:number;knowledge_create:number;knowledge_reuse:number;updated:number}
type Origin=Omit<SourceJob,'id'>&{job_id:string;item_uids?:string[];batches?:Origin[]}
export function formulaWarnings(doc:Doc,uid:string){const b=doc.blocks.find(x=>x.uid===uid);if(!b)return [];for(const s of [b.title,b.content,b.answer,b.solution,b.proof])for(const t of mathTokens(s)){if(t.kind==='math'){try{renderMathHtml(t.value,true)}catch{return ['存在无法渲染的 LaTeX 公式']}}}return []}
export function ManualReview({doc,data,busy,error,onBack,onEdit,onConfirm,onProgress}:{doc:Doc;data:ReviewData;busy:boolean;error:string;onBack:()=>void;onEdit:(uid:string)=>void;onConfirm:(accept:boolean)=>void;onProgress:(uid:string,approved:boolean)=>Promise<boolean>}){
 const [current,setCurrent]=useState(()=>data.rows.find(r=>!(data.reviewed_uids??[]).includes(r.uid))?.uid??data.rows[0]?.uid??''),[origins,setOrigins]=useState<Origin[]>([]),[sourceError,setSourceError]=useState(''),[tab,setTab]=useState<'compare'|'matches'>('compare')
 const rows=data.rows.map(r=>({...r,errors:[...r.errors,...formulaWarnings(doc,r.uid)]})),approved=new Set(data.reviewed_uids??[])
 const active=rows.find(r=>r.uid===current)??rows[0],index=rows.findIndex(r=>r.uid===active?.uid),b=doc.blocks.find(x=>x.uid===active?.uid)
 const errors=rows.filter(r=>r.errors.length).length,warnings=rows.filter(r=>r.warnings.length).length,done=rows.filter(r=>approved.has(r.uid)&&!r.errors.length).length
 const original=origins.find(o=>o.item_uids?.includes(active?.uid??'')),hasOriginal=!!original
 useEffect(()=>{const c=new AbortController();setSourceError('');api<Origin|null>('/documents/'+encodeURIComponent(doc.id)+'/origin',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setOrigins(r?.job_id?r.batches??[r]:[])}).catch(e=>{if(!c.signal.aborted)setSourceError(e.message)});return()=>c.abort()},[doc.id])
 function choose(uid:string){setCurrent(uid);setTab('compare')}
 async function approve(){if(!active||active.errors.length)return;if(await onProgress(active.uid,true)){const following=rows.slice(index+1).find(r=>!approved.has(r.uid))??rows.find(r=>r.uid!==active.uid&&!approved.has(r.uid));choose(following?.uid??active.uid)}}
 async function submit(){if(errors||!rows.length||done!==rows.length)return;onConfirm(false)}
 return <div className="manual-flow manual-review manual-unified-review wg-review-workbench"><button className="manual-back" disabled={busy} onClick={onBack}>← 返回录入工作台</button><div className="wg-review-header"><div><h1>入库审核</h1><MathText content={doc.title}/><small className="muted">{done} / {rows.length} 条已通过 · {errors} 条待处理</small></div><ReviewProgress done={done} total={rows.length}/></div>
 {sourceError&&<p className="muted" role="status">原始资料读取失败：{sourceError}</p>}
 {rows.length? <><div className="wg-review-mobile-tabs"><select aria-label="选择审核条目" value={active?.uid??''} disabled={busy} onChange={e=>choose(e.target.value)}>{rows.map(r=><option key={r.uid} value={r.uid}>{r.number}. {r.title.slice(0,35)}{approved.has(r.uid)?' · 已通过':''}</option>)}</select><div className="wg-segment"><button aria-pressed={tab==='compare'} onClick={()=>setTab('compare')}>{hasOriginal?'原文对照':'题目内容'}</button><button aria-pressed={tab==='matches'} onClick={()=>setTab('matches')}>查重结果</button></div></div>
 <div className={'wg-review-grid'+(hasOriginal||tab==='matches'?' has-side':'')} data-tab={tab}>
 <ReviewDirectory items={rows.map(r=>({uid:r.uid,number:r.number,title:r.title,approved:approved.has(r.uid),issue:!!r.errors.length}))} active={active?.uid??''} busy={busy} onChoose={choose}/>
 <section className="wg-review-editor">{active&&b&&<><div className="wg-panel-head"><div><h3>第 {active.number} 条 · {active.kind==='question'?'题目':'知识单元'}</h3><small>{approved.has(active.uid)?'已通过':'待审核'}</small></div><button disabled={busy} onClick={()=>onEdit(active.uid)}>修改</button></div>
 <h3><MathText content={active.title}/></h3><div className="wg-review-content"><MathText content={b.content}/></div><ReviewSections key={active.uid} kind={active.kind} answer={b.answer} solution={b.solution} analysis={b.analysis} proof={b.proof} teachingDetail={b.teaching_detail}/>
 <dl className="wg-review-meta">{[['科目',b.subject??doc.subject],['题型 / 类型',b.question_type||b.unit_type],['知识标签',(b.knowledge_tags??[]).join('、')]].map(([k,v])=><div key={k}><dt>{k}</dt><dd><MathText compact content={v||'待确认'}/></dd></div>)}</dl>
 <div className="wg-review-checks"><strong>{active.action==='batch_reuse'?'本批次合并至同一题':active.action==='append'?'追加新解法':active.action==='reuse'?'引用已有资源':active.action==='update'?'更新已有资源':'新增'}</strong>{active.errors.map(s=><p key={s} className="issue">{s}</p>)}{active.warnings.map(s=><p key={s} className="muted">{s}</p>)}{!active.errors.length&&!active.warnings.length&&<p>检查通过</p>}<button disabled={busy} onClick={()=>setTab(tab==='matches'?'compare':'matches')}>{tab==='matches'?'返回题目内容':'查看查重候选'}</button></div>
 <div className="wg-item-actions"><button disabled={busy||index<1} onClick={()=>choose(rows[index-1].uid)}>上一条</button><button disabled={busy||index>=rows.length-1} onClick={()=>choose(rows[index+1].uid)}>下一条</button>{approved.has(active.uid)&&<button disabled={busy} onClick={()=>void onProgress(active.uid,false)}>撤销通过</button>}<button className="primary" disabled={busy||!!active.errors.length} onClick={()=>void approve()}>通过并继续</button></div></>}</section>
 {(hasOriginal||tab==='matches')&&active&&<aside className="wg-review-side" data-side={tab==='matches'?'matches':'source'}>{hasOriginal&&<div className="wg-segment wg-desktop-review-tabs"><button aria-pressed={tab==='compare'} onClick={()=>setTab('compare')}>原始资料</button><button aria-pressed={tab==='matches'} onClick={()=>setTab('matches')}>查重结果</button></div>}<section className="wg-review-matches">{b&&<DuplicateMatches key={active.uid} block={b} excludeId={b.resource_id??undefined} locked={false}/>}<button disabled={busy} onClick={()=>onEdit(active.uid)}>返回条目处理查重</button><button onClick={()=>setTab('compare')}>返回题目内容</button></section>{original&&<SourceView key={original.job_id} job={{id:original.job_id,input_text:original.input_text,provenance:original.provenance}} item={{uid:active.uid,kind:active.kind}} busy={busy}/>}</aside>}
 </div></>:<WorkspaceFeedback state="empty" title="没有符合条件的待入库条目。"/>}
 {error&&<p role="alert" className="notice">{error}</p>}{warnings>0&&<p className="muted">{warnings} 条存在缺失信息或合并提示，请在入库预览中确认。</p>}
 <div className="manual-form-footer"><small>{errors?errors+' 个条目必须处理':done+'/'+rows.length+' 条已审核'}</small><button disabled={busy} onClick={onBack}>返回继续编辑</button><button className="primary" disabled={busy||errors>0||!rows.length||done!==rows.length} onClick={()=>void submit()}>{busy?'正在处理…':'入库预览'}</button></div></div>
}
export function ManualSuccess({doc,counts,onContinue}:{doc:Doc;counts:ResultCounts;onContinue:()=>void}){
 const [preview,setPreview]=useState(false)
 return <div className="manual-flow manual-success">{preview?<><button onClick={()=>setPreview(false)}>← 返回入库结果</button><PrintableDocument doc={doc} stem={false} source/></>:<><Icon name="check" size={40}/><h1>入库成功</h1><MathText content={doc.title}/><div className="manual-result-counts">{[['新增题目',counts.question_create],['引用已有题目',counts.question_reuse],['新增知识单元',counts.knowledge_create],['引用已有知识单元',counts.knowledge_reuse],['更新已有资源',counts.updated],['关联来源',doc.source_id?1:0]].map(([t,n])=><div key={t}><span>{t}</span><strong>{n}</strong></div>)}</div><div className="manual-success-actions"><button onClick={onContinue}>继续录入</button><Link className="button-link primary" to="/intake">返回我的资料</Link></div><button className="manual-back" onClick={()=>setPreview(true)}>查看已入库内容 ›</button></>}</div>
}
