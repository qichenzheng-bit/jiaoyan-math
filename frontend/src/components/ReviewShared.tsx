import {useState} from 'react'
import {MathText} from './MathText'
import {Icon} from './Icon'
export function ReviewProgress({done,total}:{done:number;total:number}){return <div className="wg-review-progress" role="progressbar" aria-label="审核进度" aria-valuemin={0} aria-valuemax={total||1} aria-valuenow={done}><span style={{width:(total?100*done/total:0)+'%'}}/></div>}
type Row={uid:string;number:number;title:string;approved:boolean;issue?:boolean}
export function ReviewDirectory({items,active,busy,onChoose}:{items:Row[];active:string;busy:boolean;onChoose:(uid:string)=>void}){
 const [filter,setFilter]=useState('all')
 const rows=items.filter(r=>filter==='all'||(filter==='pending'&&!r.approved)||(filter==='approved'&&r.approved)||(filter==='issues'&&r.issue))
 return <aside className="wg-review-list"><h3>审核目录</h3><div className="wg-review-directory-controls"><select aria-label="筛选审核条目" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部题目</option><option value="pending">待审核</option><option value="approved">已通过</option>{items.some(r=>r.issue)&&<option value="issues">待处理</option>}</select></div>{rows.map(r=><button type="button" key={r.uid} aria-current={r.uid===active?'true':undefined} disabled={busy} onClick={()=>onChoose(r.uid)}><span className="wg-index">{r.number}</span><span><MathText compact content={r.title}/><small>{r.issue?'待处理':r.approved?'已通过':'待审核'}</small></span><Icon name={r.approved?'check':'chevron'} size={15}/></button>)}{!rows.length&&<p className="muted">暂无符合条件的条目</p>}</aside>
}
export function ReviewSections({kind,answer,solution,analysis,proof,teachingDetail}:{kind:'question'|'knowledge';answer:string;solution:string;analysis:string;proof:string;teachingDetail?:import('../pages/DocWork').KnowledgeTeachingDetail|null}){
 const rows=kind==='question'?[['答案',answer],['解析',solution]]:[['原文证明',proof],['说明与待核对项',analysis],...([['conditions','适用条件'],['applications','常见应用'],['methods','使用方法'],['mistakes','易错点']] as const).filter(([k])=>!!teachingDetail?.[k]).map(([k,label])=>[label,teachingDetail?.[k]??''])]
 return <div className="wg-review-sections">{rows.map(([label,content])=><details key={label}><summary>{label}{!content&&<small className="muted"> · 未提供</small>}</summary><div>{content?<MathText content={content}/>:<small className="muted">原文未提供 / 待核对</small>}</div></details>)}</div>
}
