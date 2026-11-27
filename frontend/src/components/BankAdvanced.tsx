import {useState} from 'react'
export const emptyBankFilters={origin_type:'',origin_authority:'',origin_exam:'',origin_edition:'',year_from:'',year_to:'',origin_chapter:'',original_number:'',original_page:'',knowledge_mode:'any',method_name:'',integrity:'',method_state:'',source_count:'',video_state:'',usage_state:'',sort:'updated'}
export type BankFilters=typeof emptyBankFilters
const fields:[keyof BankFilters,string,[string,string][]][]=[
 ['origin_type','来源类别',[['','不限'],['exam','试卷'],['textbook','教材'],['handout','讲义'],['other','其他']]],
 ['origin_authority','资料等级',[['','不限'],['official_exam','官方真题'],['mock_practice','模拟练习'],['core_textbook','经典教材'],['internal_handout','自编讲义']]],
 ['origin_exam','来源考试类别',[['','不限'],['数学一','数学一'],['数学二','数学二'],['数学三','数学三']]],
 ['knowledge_mode','知识点匹配',[['any','任意一个'],['all','同时包含全部']]],
 ['integrity','内容完整性',[['','不限'],['complete','答案解析完整'],['missing_answer','缺少答案'],['missing_solution','缺少解析'],['ambiguous','结构待核对']]],
 ['method_state','解法状态',[['','不限'],['single','各小问单解法'],['multi','存在多解法'],['pending','待评价或评价中'],['review','待人工确认推荐'],['failed','评价失败'],['confirmed','已确认推荐']]],
 ['source_count','来源数量',[['','不限'],['none','无来源'],['single','单来源'],['multiple','多来源']]],
 ['video_state','视频制作',[['','不限'],['made','已审核归档'],['unmade','未归档']]],
 ['usage_state','教研引用',[['','不限'],['used','已引用'],['unused','未引用']]],
 ['sort','排序',[['updated','最近更新'],['created','录入时间'],['year','来源年份（新到旧）'],['number','原始题号（小到大）'],['difficulty','难度（易到难）'],['sources','来源数量（多到少）']]]
]
const inputs:[keyof BankFilters,string,string][]=[['origin_edition','来源版次','如第八版'],['origin_chapter','来源章节','资料中的章节'],['original_number','原始题号','如 12'],['original_page','原始页码','如 25'],['method_name','解题方法','如 泰勒展开']]
export function BankAdvanced({value,onApply}:{value:BankFilters;onApply:(v:BankFilters)=>void}){
 const [draft,setDraft]=useState(value)
 function set(k:keyof BankFilters,v:string){setDraft(old=>({...old,[k]:v}))}
 const validYear=(x:string)=>!x||/^\d{4}$/.test(x)&&Number(x)>=1900&&Number(x)<=2200
 const invalid=!validYear(draft.year_from)||!validYear(draft.year_to)||Boolean(draft.year_from&&draft.year_to&&Number(draft.year_from)>Number(draft.year_to))||Boolean(draft.original_page&&(!/^\d+$/.test(draft.original_page)||Number(draft.original_page)<1))
 return <section className="question-bank-advanced" aria-label="组合筛选"><div className="question-bank-filter-grid">{fields.map(([key,label,opts])=><label key={key}>{label}<select aria-label={label} value={draft[key]} onChange={e=>set(key,e.target.value)}>{opts.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>)}<label>起始年份<input aria-label="起始年份" inputMode="numeric" maxLength={4} value={draft.year_from} onChange={e=>set('year_from',e.target.value)}/></label><label>结束年份<input aria-label="结束年份" inputMode="numeric" maxLength={4} value={draft.year_to} onChange={e=>set('year_to',e.target.value)}/></label>{inputs.map(([key,label,placeholder])=><label key={key}>{label}<input aria-label={label} maxLength={60} placeholder={placeholder} value={draft[key]} onChange={e=>set(key,e.target.value)}/></label>)}</div>{invalid&&<p role="alert">请检查年份范围或页码。</p>}<small className="muted">来源属性必须属于同一份资料；解法名称仅按文本匹配，不推断数学等价性。</small><div className="button-row"><button type="button" onClick={()=>setDraft({...emptyBankFilters})}>清空高级条件</button><button type="button" className="primary" disabled={invalid} onClick={()=>onApply(draft)}>应用筛选</button></div></section>
}
export function activeFilterLabels(value:BankFilters){return Object.entries(value).filter(([k,v])=>v&&v!==emptyBankFilters[k as keyof BankFilters]).map(([key,v])=>({key:key as keyof BankFilters,label:(fields.find(f=>f[0]===key)?.[1]??inputs.find(f=>f[0]===key)?.[1]??(key==='year_from'?'起始年份':'结束年份'))+': '+(fields.find(f=>f[0]===key)?.[2].find(o=>o[0]===v)?.[1]??v)}))}
export function bankParams(value:BankFilters){return Object.fromEntries(Object.entries(value).filter(([,v])=>v))}
