import {useEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import {api} from '../auth'
import {AnswerSolutionView} from './AnswerSolutionView'
import type {QuestionData} from './questionData'
import {MathText} from './MathText'
import {Icon} from './Icon'

export type ResourceEntry={id:string;title?:string;name?:string;subject?:string;source_type?:string;chapter?:string;code?:string;cohort_year?:string;edition?:string}
export type ResourceDisplay={question_data?:QuestionData|null;id:string;code?:string;kind?:string;title:string;content:string;answer?:string;solution?:string;analysis?:string;proof?:string;subject?:string;question_type?:string;unit_type?:string;difficulty?:string;tags?:string[];knowledge_points?:{id:string;name:string}[]}

export function ResourceExcerpt({resource}:{resource:ResourceDisplay}){
 return <span className="resource-compact-excerpt"><MathText compact content={resource.content||resource.title}/></span>
}
export function ResourceSections({resource,showKnowledge=false,sectionClass='',stemLabel}:{resource:ResourceDisplay;showKnowledge?:boolean;sectionClass?:string;stemLabel?:string}){
 const question=resource.kind==='question'||!!resource.question_type
 const fields:[string,string|undefined][]=[...(!question?([['参考答案',resource.answer],['参考解析',resource.solution],['思路点拨',resource.analysis]] as [string,string|undefined][]):[]),['证明',resource.proof],...(showKnowledge?[['录入知识点',resource.tags?.join('、')] as [string,string|undefined],['关联知识标签',resource.knowledge_points?.map(p=>p.name).join('、')] as [string,string|undefined]]:[])]
 return <div className="resource-content-sections" key={resource.id}>
  {stemLabel?<details className={sectionClass} open><summary>{stemLabel}</summary><div><MathText content={resource.content||resource.title}/></div></details>:<MathText content={resource.content||resource.title}/>}
  {question&&<AnswerSolutionView value={resource} collapsible defaultExpanded={false}/>}
  {fields.filter(([,value])=>value).map(([label,value])=><details className={sectionClass} key={label}><summary>{label}</summary><div><MathText content={value}/></div></details>)}
 </div>
}
export function ResourceMultiSelect({label,path,chosen,setChosen}:{label:string;path:string;chosen:ResourceEntry[];setChosen:(v:ResourceEntry[])=>void}){
 const [q,setQ]=useState(''),[items,setItems]=useState<ResourceEntry[]>([]),[page,setPage]=useState(0),[total,setTotal]=useState(0),[error,setError]=useState(''),[loading,setLoading]=useState(false),[opened,setOpened]=useState(false)
 const [lastPath,setLastPath]=useState(path)
 // Reset pagination immediately when the scope changes.
 if(path!==lastPath){setLastPath(path);setPage(0)}
 useEffect(()=>{if(!opened)return;const c=new AbortController();setError('');setLoading(true);setItems([])
  const timer=window.setTimeout(()=>api<{items:ResourceEntry[];total:number}>(path+'&q='+encodeURIComponent(q)+'&limit=30&offset='+page*30,{signal:c.signal}).then(r=>{if(!c.signal.aborted){setItems(r.items??[]);setTotal(r.total??0)}}).catch(e=>{if(!c.signal.aborted)setError(e.message||'读取失败')}).finally(()=>{if(!c.signal.aborted)setLoading(false)}),150)
  return()=>{window.clearTimeout(timer);c.abort()}
 },[path,q,page,opened])
 return <details className="assembly-multi resource-multi" onToggle={e=>setOpened(e.currentTarget.open)}><summary>{label}{chosen.length?'（'+chosen.length+'）':''}</summary>
  <div className="assembly-multi-panel resource-multi-panel"><input aria-label={'搜索'+label} placeholder={'搜索'+label} maxLength={200} value={q} onChange={e=>{setQ(e.target.value);setPage(0)}}/>
  {chosen.length>0&&<div className="resource-multi-selected"><small>已选 {chosen.length} 项（跨页保留）</small><button type="button" onClick={()=>setChosen([])}>清除已选</button>{chosen.map(r=><button type="button" key={r.id} className="resource-selected-chip" aria-label={'移除 '+(r.title??r.name??r.id)} onClick={()=>setChosen(chosen.filter(x=>x.id!==r.id))}><MathText compact content={r.title??r.name}/><span>×</span></button>)}</div>}
  {error&&<small role="alert">{error}</small>}{loading&&<small role="status">正在读取…</small>}
  {!loading&&!error&&!items.length&&<small className="muted">暂无匹配记录</small>}
  {items.map(r=><label key={r.id}><input type="checkbox" checked={chosen.some(x=>x.id===r.id)} disabled={chosen.length>=100&&!chosen.some(x=>x.id===r.id)} onChange={()=>setChosen(chosen.some(x=>x.id===r.id)?chosen.filter(x=>x.id!==r.id):[...chosen,r])}/><span><MathText compact content={r.title??r.name}/>{(r.subject||r.chapter||r.cohort_year||r.edition)&&<small>{[r.subject,r.chapter,r.cohort_year,r.edition].filter(Boolean).join(' · ')}</small>}</span></label>)}
  {total>30&&<div className="button-row"><button type="button" disabled={!page||loading} onClick={()=>setPage(v=>v-1)}>上一页</button><small>{page+1}/{Math.ceil(total/30)}</small><button type="button" disabled={(page+1)*30>=total||loading} onClick={()=>setPage(v=>v+1)}>下一页</button></div>}</div></details>
}
export function ResourceAssociationFilters({subject,sources,points,onSources,onPoints,related,onRelated,origin=''}:{subject:string;sources:ResourceEntry[];points:ResourceEntry[];onSources:(v:ResourceEntry[])=>void;onPoints:(v:ResourceEntry[])=>void;related:boolean;onRelated:(v:boolean)=>void;origin?:string}){
 return <div className="resource-association-filters"><ResourceMultiSelect label="具体来源" path={'/resources?kind=source&source_type='+encodeURIComponent(origin)} chosen={sources} setChosen={onSources}/><ResourceMultiSelect label="知识标签" path={'/knowledge/points?subject='+encodeURIComponent(subject)} chosen={points} setChosen={onPoints}/><label className="resource-related-toggle"><input type="checkbox" checked={related} onChange={e=>onRelated(e.target.checked)}/>包含下级、相关及前置知识标签</label></div>
}
export function appendResourceFilters(query:URLSearchParams,sources:ResourceEntry[],points:ResourceEntry[],related:boolean){
 sources.forEach(r=>query.append('source_ids',r.id));points.forEach(r=>query.append('knowledge_ids',r.id));if(related&&points.length)query.set('include_related','true')
 return query
}
// Hover is only a preview, never a selection or a write operation.
export function useResourceHover(){
 const [active,setActive]=useState<{resource:ResourceDisplay;left:number;top:number}>()
 const show=useRef<number|undefined>(undefined),hide=useRef<number|undefined>(undefined)
 function close(){window.clearTimeout(show.current);window.clearTimeout(hide.current);setActive(undefined)}
 function enter(resource:ResourceDisplay,el:HTMLElement,pointerType:string){
  if(pointerType!=='mouse'||!window.matchMedia('(hover: hover) and (min-width: 761px)').matches)return
  window.clearTimeout(hide.current);window.clearTimeout(show.current)
  const rect=el.getBoundingClientRect()
  show.current=window.setTimeout(()=>{const width=Math.min(500,window.innerWidth-24);const left=rect.right+8+width<=innerWidth?rect.right+8:Math.max(12,rect.left-width-8);setActive({resource,left,top:Math.max(12,Math.min(rect.top,innerHeight-260))})},220)
 }
 function leave(){window.clearTimeout(show.current);window.clearTimeout(hide.current);hide.current=window.setTimeout(()=>setActive(undefined),200)}
 useEffect(()=>{const dismiss=(e:KeyboardEvent)=>{if(e.key==='Escape')close()};const resize=()=>close();window.addEventListener('keydown',dismiss);window.addEventListener('resize',resize);return()=>{window.removeEventListener('keydown',dismiss);window.removeEventListener('resize',resize);window.clearTimeout(show.current);window.clearTimeout(hide.current)}},[])
 const preview=active?createPortal(<aside className="resource-hover-preview" role="dialog" aria-label="资源悬停预览" style={{left:active.left,top:active.top,maxHeight:'min(70dvh,600px,calc(100dvh - '+(active.top+12)+'px))'}} onPointerEnter={()=>window.clearTimeout(hide.current)} onPointerLeave={leave}><header><strong>{active.resource.code||'资源预览'}</strong><button type="button" aria-label="关闭悬停预览" onClick={close}><Icon name="close" size={16}/></button></header><div className="resource-hover-body"><ResourceSections resource={active.resource} showKnowledge/></div></aside>,document.body):null
 return {enter,leave,close,preview}
}
export function ResourcePagination({page,size,total,onPage,loading=false,className='',showSingle=true}:{page:number;size:number;total:number;onPage:(v:number)=>void;loading?:boolean;className?:string;showSingle?:boolean}){
 if(!showSingle&&total<=size)return null
 return <div className={'button-row '+className}><button type="button" disabled={page===0||loading} onClick={()=>onPage(page-1)}>上一页</button><small>{page+1}/{Math.max(1,Math.ceil(total/size))}</small><button type="button" disabled={(page+1)*size>=total||loading} onClick={()=>onPage(page+1)}>下一页</button></div>
}
