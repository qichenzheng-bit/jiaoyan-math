import {createPortal} from 'react-dom'
import {useLayoutEffect,useState,type ReactNode} from 'react'
export type ModelCatalog={models:{id:string;label:string;efforts?:string[]}[];source?:string}
export type ModelPreferences={model:string;effort?:string;video_model?:string;video_effort?:string}
const labels:Record<string,string>={default:'默认',none:'关闭',off:'关闭',disabled:'关闭',low:'低',medium:'中',high:'高',xhigh:'极高',max:'最大'}
export function effortOptions(catalog:ModelCatalog|undefined,model:string,video=false){
 const available=catalog?.source==='cli'?catalog.models.find(m=>m.id===model)?.efforts??[]:[]
 return ['default',...new Set(available.filter(e=>e!=='default'&&Object.hasOwn(labels,e)&&(!video||['low','medium','high','xhigh','max'].includes(e))))]
}
export default function ReasoningEffort({catalog,model,value,onChange,disabled=false,video=false}:{catalog?:ModelCatalog;model:string;value:string;onChange:(e:string)=>void;disabled?:boolean;video?:boolean}){
 const options=effortOptions(catalog,model,video)
 return <label className="reasoning-effort" title={options.length===1?'CLI 尚未报告此模型可选推理档位，使用模型默认。':'选择本次调用的推理强度'}><span>推理</span><select aria-label="推理强度" value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>{!options.includes(value)&&<option value={value} disabled>{labels[value]??value}（已不可用）</option>}{options.map(e=><option key={e} value={e}>{labels[e]??e}</option>)}</select></label>
}

// The topbar owns the only interactive inference control; page state owns the actual request.
export function InferenceMenu({children}:{children:ReactNode}){
 const [host,setHost]=useState<HTMLElement|null>(null)
 useLayoutEffect(()=>{setHost(document.getElementById('mode-inference-actions'))},[])
 return host?createPortal(children,host):null
}
