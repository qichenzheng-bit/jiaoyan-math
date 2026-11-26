import {useEffect,useId,useRef,useState,useCallback} from 'react'
import {api} from '../auth'
import {Icon} from './Icon'
import {effortOptions,effortLabel,type ModelCatalog} from './ReasoningEffort'
type Props={models:ModelCatalog['models'];catalog?:ModelCatalog;model:string;effort:string;onModel:(model:string)=>void;onEffort:(effort:string)=>void;onCatalog:(catalog:ModelCatalog)=>void;disabled?:boolean;effortDisabled?:boolean;onOpen?:()=>void}
export default function ComposerInference({models,catalog,model,effort,onModel,onEffort,onCatalog,disabled=false,effortDisabled=false,onOpen}:Props){
 const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[syncing,setSyncing]=useState(false),[warning,setWarning]=useState('')
 const root=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null),id=useId(),request=useRef<AbortController|null>(null),listener=useRef(onCatalog)
 useEffect(()=>{listener.current=onCatalog},[onCatalog])
 const sync=useCallback(async(force=false)=>{
  if(request.current)return
  const ctrl=new AbortController();request.current=ctrl
  setSyncing(true);setWarning('')
  try{
   const result=await api<ModelCatalog>(force?'/qoder/models/refresh':'/qoder/models',{...(force?{method:'POST',body:'{}'}:{}),signal:ctrl.signal})
   if(ctrl.signal.aborted)return
   if(result.source!=='cli'||!Array.isArray(result.models)){setWarning('暂未取得官方模型清单，请刷新或检查 AI 登录状态。');return}
   listener.current(result)
  }catch(e){if(!ctrl.signal.aborted)setWarning(e instanceof Error?e.message:'模型同步失败')}
  finally{if(request.current===ctrl){request.current=null;if(!ctrl.signal.aborted)setSyncing(false)}}
 },[])
 useEffect(()=>{const refresh=()=>{if(document.visibilityState==='visible')void sync()};const timer=window.setInterval(refresh,60000);window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);return()=>{window.clearInterval(timer);window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh);request.current?.abort();request.current=null}},[sync])
 useEffect(()=>{if(!open)return;const outside=(e:PointerEvent)=>{if(!root.current?.contains(e.target as Node))setOpen(false)};const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){setOpen(false);trigger.current?.focus()}};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[open])
 useEffect(()=>{if(disabled)setOpen(false)},[disabled])
 const official=catalog?.source==='cli',available=official?models:[],selected=available.find(m=>m.id===model),label=selected?.label??model,choices=effortOptions(catalog,model),filtered=available.filter(m=>(m.label+' '+m.id).toLowerCase().includes(query.trim().toLowerCase()))
 function close(){setOpen(false);trigger.current?.focus()}
 function chooseModel(next:string){onModel(next);if(effortOptions(catalog,next).length===1){onEffort('default');close()}}
 return <div className="composer-inference" ref={root}>
  <button ref={trigger} type="button" className="chat-model-shortcut" title={label+' · '+effortLabel(effort)+' · 选择模型及推理强度'} aria-label="打开模型选择" aria-expanded={open} aria-controls={open?id:undefined} disabled={disabled} onClick={()=>{if(!open){onOpen?.();setQuery('');void sync()}setOpen(v=>!v)}}><Icon name="brain" size={23}/></button>
  {open&&<section className="composer-inference-panel" id={id} aria-label="模型及推理强度">
   <div className="composer-inference-heading"><strong>模型</strong><button type="button" aria-label="刷新模型" title="从 Qoder CN 重新拉取" disabled={syncing||disabled} onClick={()=>void sync(true)}><Icon name="refresh" size={16}/></button></div>
   {available.length>6&&<div className="composer-model-search"><Icon name="search" size={15}/><input type="search" aria-label="搜索模型" placeholder="搜索模型" value={query} onChange={e=>setQuery(e.target.value)}/></div>}
   {syncing&&<small className="composer-catalog-status" role="status">正在同步模型…</small>}{warning&&<small className="composer-catalog-status" role="status">{warning}</small>}
   <div className="composer-model-list" role="group" aria-label="可用模型">{!selected&&<small className="composer-catalog-status">当前模型 {model} 尚未确认可用</small>}{filtered.map(m=><button key={m.id} type="button" aria-pressed={m.id===model} disabled={disabled} onClick={()=>chooseModel(m.id)}><span>{m.label}</span>{m.id===model&&<Icon name="check" size={17}/>}</button>)}{!available.length&&!syncing&&<p className="muted">暂无官方模型清单。</p>}{available.length>0&&!filtered.length&&<p className="muted">没有匹配的模型。</p>}</div>
   {selected&&<div className="composer-inference-effort"><div className="composer-effort-label"><strong>推理强度</strong>{!choices.includes(effort)&&<small>原档位已不可用</small>}</div><div className="composer-effort-options" role="group" aria-label="推理强度">{choices.map(e=><button key={e} type="button" aria-pressed={e===effort} disabled={disabled||effortDisabled} onClick={()=>{onEffort(e);close()}}>{effortLabel(e)}</button>)}</div></div>}
  </section>}
 </div>
}
