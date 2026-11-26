import {useEffect,useId,useRef,useState} from 'react'
import {Icon} from './Icon'
import ReasoningEffort,{type ModelCatalog} from './ReasoningEffort'
type Props={models:ModelCatalog['models'];catalog?:ModelCatalog;model:string;effort:string;onModel:(model:string)=>void;onEffort:(effort:string)=>void;disabled?:boolean;effortDisabled?:boolean;onOpen?:()=>void}
export default function ComposerInference({models,catalog,model,effort,onModel,onEffort,disabled=false,effortDisabled=false,onOpen}:Props){
 const [open,setOpen]=useState(false),root=useRef<HTMLDivElement>(null),trigger=useRef<HTMLButtonElement>(null),id=useId()
 useEffect(()=>{if(!open)return;const outside=(e:PointerEvent)=>{if(!root.current?.contains(e.target as Node))setOpen(false)};const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'){setOpen(false);trigger.current?.focus()}};document.addEventListener('pointerdown',outside);document.addEventListener('keydown',escape);return()=>{document.removeEventListener('pointerdown',outside);document.removeEventListener('keydown',escape)}},[open])
 useEffect(()=>{if(disabled)setOpen(false)},[disabled])
 const label=models.find(m=>m.id===model)?.label??model
 return <div className="composer-inference" ref={root}>
  <button ref={trigger} type="button" className="chat-model-shortcut" title={label+' · 选择模型及推理强度'} aria-label="打开模型选择" aria-expanded={open} aria-controls={id} disabled={disabled} onClick={()=>{if(!open)onOpen?.();setOpen(v=>!v)}}><span>{label}</span><Icon name="chevron-down" size={14}/></button>
  {open&&<section className="composer-inference-panel" id={id} aria-label="模型及推理强度"><div className="composer-inference-heading"><strong>模型选择</strong><button type="button" aria-label="关闭模型选择" onClick={()=>{setOpen(false);trigger.current?.focus()}}><Icon name="close" size={16}/></button></div><div className="composer-model-list" role="group" aria-label="可用模型">{!models.some(m=>m.id===model)&&<p className="muted">当前模型：{model}（待确认）</p>}{models.map(m=><button key={m.id} type="button" aria-pressed={m.id===model} disabled={disabled} onClick={()=>onModel(m.id)}><span>{m.label}</span>{m.id===model&&<Icon name="check" size={17}/>}</button>)}{!models.length&&<p className="muted">暂无可用模型，请在 AI 账号管理中刷新。</p>}</div><div className="composer-inference-effort"><ReasoningEffort catalog={catalog} model={model} value={effort} onChange={onEffort} disabled={disabled||effortDisabled}/></div><button type="button" className="composer-inference-done" onClick={()=>{setOpen(false);trigger.current?.focus()}}>完成</button></section>}
 </div>
}
