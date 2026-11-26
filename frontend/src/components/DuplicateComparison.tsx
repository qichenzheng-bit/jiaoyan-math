import {MathText} from './MathText'
type CompareItem={title?:string;content:string;answer?:string;solution?:string;proof?:string;subject?:string|null;chapter?:string;code?:string}
export function DuplicateComparison({current,candidate,kind,similarity,reason,knowledge=false}:{current:CompareItem;candidate:CompareItem;kind:string;similarity:number;reason?:string;knowledge?:boolean}){
 const label=kind==='same_title'?'名称相同':kind==='exact'?'内容相同 · 100%':kind==='same_stem'?'题干相同 · 100%':'相似度 '+(similarity*100).toFixed(1)+'%'
 return <><div className="workspace-match-heading"><strong>{candidate.code}</strong><small>{label}</small></div>
 <div className="workspace-match-compare" aria-label="当前录入与题库候选对比">{([['当前录入',current],['题库已有资源',candidate]] as const).map(([title,item])=><div className="workspace-match-side" key={title}><small>{title}</small>{knowledge&&item.title&&<strong><MathText compact content={item.title}/></strong>}<MathText content={item.content}/>{(item.subject||item.chapter)&&<small>{[item.subject,item.chapter].filter(Boolean).join(' · ')}</small>}</div>)}</div>
 <small className="workspace-match-reason">{reason|| (kind==='exact'?'接口判定内容相同':kind==='same_stem'?'接口判定题干相同，仍需核对答案及解析':kind==='same_title'?'接口判定名称相同':'正文文本相似，需人工核对；不代表数学等价或解题逻辑相同。')}</small>
 <details><summary>{knowledge?'查看证明及属性':'查看答案、解析及属性'}</summary><div className="workspace-match-compare">{([['当前录入',current],['题库已有资源',candidate]] as const).map(([title,item])=><div className="workspace-match-side" key={title}><small>{title}</small>{knowledge?<><strong>证明 / 说明</strong><MathText content={item.proof||'（未填写）'}/></>:<><strong>答案</strong><MathText content={item.answer||'（未填写）'}/><strong>解析</strong><MathText content={item.solution||'（未填写）'}/></>}</div>)}</div></details></>
}
