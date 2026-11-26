import {useState} from 'react'
import {WorkspaceLink as Link} from './WorkspaceNavigation'
import {MathText,mathTokens} from './MathText'
import {confirmAction} from './WorkspaceConfirm'
import {Icon} from './Icon'
import katex from 'katex'
import type {Doc} from '../pages/DocWork'
import {PrintableDocument} from '../pages/DocumentPrint'
type Row={uid:string;number:number;kind:'question'|'knowledge';title:string;action:'create'|'reuse'|'update';errors:string[];warnings:string[]}
export type ReviewData={revision:number;rows:Row[]}
export type ResultCounts={question_create:number;question_reuse:number;knowledge_create:number;knowledge_reuse:number;updated:number}
function formulaWarnings(doc:Doc,uid:string){const b=doc.blocks.find(x=>x.uid===uid);if(!b)return [];for(const s of [b.title,b.content,b.answer,b.solution,b.proof])for(const t of mathTokens(s)){if(t.kind==='math'){try{katex.renderToString(t.value.replace(/^\\begin\{align\*?\}/,'\\begin{aligned}').replace(/\\end\{align\*?\}$/,'\\end{aligned}'),{throwOnError:true,trust:false,maxExpand:1000,maxSize:20})}catch{return ['存在无法渲染的 LaTeX 公式']}}}return []}
export function ManualReview({doc,data,busy,error,onBack,onEdit,onConfirm}:{doc:Doc;data:ReviewData;busy:boolean;error:string;onBack:()=>void;onEdit:(uid:string)=>void;onConfirm:(accept:boolean)=>void}){
 const [filter,setFilter]=useState('all'),[accepted,setAccepted]=useState(false)
 const rows=data.rows.map(r=>({...r,errors:[...r.errors,...formulaWarnings(doc,r.uid)]}))
 const errors=rows.filter(r=>r.errors.length).length,warnings=rows.filter(r=>r.warnings.length).length
 const shown=rows.filter(r=>filter==='all'||filter===r.kind||filter==='issues'&&(r.errors.length||r.warnings.length))
 async function submit(){if(errors||!rows.length||warnings&&!accepted)return;if(await confirmAction('将本次 '+rows.length+' 个待处理资源写入正式资源库？','确认入库','确认'))onConfirm(accepted)}
 return <div className="manual-flow manual-review"><button className="manual-back" disabled={busy} onClick={onBack}>← 返回录入工作台</button><h1>入库审核</h1><MathText content={doc.title}/><div className="manual-review-stats">{[['题目',rows.filter(r=>r.kind==='question').length],['知识单元',rows.filter(r=>r.kind==='knowledge').length],['引用已有资源',rows.filter(r=>r.action==='reuse').length],['待处理',errors]].map(([t,n])=><div key={t}><small>{t}</small><strong>{n}</strong></div>)}</div><nav className="manual-filter">{[['all','全部'],['question','题目'],['knowledge','知识单元'],['issues','待处理']].map(([v,t])=><button key={v} aria-pressed={filter===v} onClick={()=>setFilter(v)}>{t}</button>)}</nav>{shown.map(r=><article className="manual-review-row" key={r.uid}><div><small>第 {r.number} 个条目 · {r.kind==='question'?'题目':'知识单元'}</small><strong><MathText compact content={r.title}/></strong></div><span>{r.action==='reuse'?'引用已有资源':r.action==='update'?'更新已有资源':'新增'}</span><div>{r.errors.length?<span className="manual-review-error">{r.errors.join('；')}</span>:r.warnings.length?<small>{r.warnings.join('；')}</small>:<small>检查通过</small>}</div><button disabled={busy} onClick={()=>onEdit(r.uid)}>{r.errors.length||r.warnings.length?'处理':'查看'}</button></article>)}{!shown.length&&<p className="muted">没有符合条件的待入库条目。</p>}{error&&<p role="alert" className="notice">{error}</p>}{warnings>0&&<label className="manual-review-accept"><input type="checkbox" checked={accepted} disabled={busy} onChange={e=>setAccepted(e.target.checked)}/> 已核对 {warnings} 个条目的缺失信息，允许保留</label>}<div className="manual-form-footer"><small>{errors?errors+' 个条目必须处理':rows.length+' 个条目待入库'}</small><button disabled={busy} onClick={onBack}>返回继续编辑</button><button className="primary" disabled={busy||errors>0||!rows.length||warnings>0&&!accepted} onClick={()=>void submit()}>{busy?'正在处理…':'确认入库'}</button></div></div>
}
export function ManualSuccess({doc,counts,onContinue}:{doc:Doc;counts:ResultCounts;onContinue:()=>void}){
 const [preview,setPreview]=useState(false)
 return <div className="manual-flow manual-success">{preview?<><button onClick={()=>setPreview(false)}>← 返回入库结果</button><PrintableDocument doc={doc} stem={false} source/></>:<><Icon name="check" size={40}/><h1>入库成功</h1><MathText content={doc.title}/><div className="manual-result-counts">{[['新增题目',counts.question_create],['引用已有题目',counts.question_reuse],['新增知识单元',counts.knowledge_create],['引用已有知识单元',counts.knowledge_reuse],['更新已有资源',counts.updated],['关联来源',doc.source_id?1:0]].map(([t,n])=><div key={t}><span>{t}</span><strong>{n}</strong></div>)}</div><div className="manual-success-actions"><button onClick={onContinue}>继续录入</button><Link className="button-link primary" to="/intake">返回我的资料</Link></div><button className="manual-back" onClick={()=>setPreview(true)}>查看已入库内容 ›</button></>}</div>
}
