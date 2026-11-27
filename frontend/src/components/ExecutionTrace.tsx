import {useEffect,useRef,useState} from 'react'
import {Icon} from './Icon'
import {effortLabel} from './ReasoningEffort'
import './ExecutionTrace.css'
type Props={state:string;model?:string;detail?:string;startedAt?:number;finishedAt?:number;work?:boolean;hasOutput?:boolean;effort?:string;phase?:string;progress?:number;summary?:string;video?:boolean}
export default function ExecutionTrace({state,model,detail,startedAt,finishedAt,work=false,hasOutput=false,effort,phase,progress,summary,video=false}:Props){
 const running=['running','queued','cancelling'].includes(state),success=['done','review','converted','success','completed'].includes(state),failed=state==='failed'
 const [open,setOpen]=useState(running||failed),[now,setNow]=useState(Date.now()),[observedEnd,setObservedEnd]=useState<number>()
 const wasRunning=useRef(running)
 useEffect(()=>{if(!running)return;setOpen(true);setNow(Date.now());const timer=window.setInterval(()=>setNow(Date.now()),1000);return()=>{window.clearInterval(timer)}},[running])
 useEffect(()=>{if(!running){setOpen(failed);if(wasRunning.current)setObservedEnd(Date.now())}else setObservedEnd(undefined);wasRunning.current=running},[running,failed])
 // Historical completed chat messages have no completion timestamp. Do not fabricate one.
 const end=running?now:finishedAt?finishedAt*1000:observedEnd
 const seconds=startedAt&&end&&end>=startedAt*1000?Math.floor((end-startedAt*1000)/1000):undefined
 const label=state==='queued'?'排队中':state==='cancelling'?'正在取消':running?(video?phase||'正在制作':work?'正在整理资料':hasOutput?'正在生成回答':'等待模型返回'):success?(video?'制作任务完成':work?'资料整理完成':'回答已生成'):['stopped','cancelled'].includes(state)?'已停止':failed?'执行失败':'执行状态'
 return <div className="wg-execution"><button type="button" className="wg-execution-toggle" aria-expanded={open} onClick={()=>setOpen(v=>!v)}><span className={'wg-execution-mark'+(running?' running':'')}><Icon name={running?'clock':success?'check':'more'} size={15}/></span><span>{label}{seconds!==undefined?' · '+seconds+' 秒':''}</span><span className={open?'wg-execution-caret open':'wg-execution-caret'}><Icon name="chevron-down" size={13}/></span></button>{open&&<div className="wg-execution-detail">{!video&&<div><span>AI 平台</span><strong>Qoder CN</strong></div>}{model&&<div><span>模型</span><strong>{model}</strong></div>}{effort&&<div><span>推理强度</span><strong>{effortLabel(effort)}</strong></div>}<div><span>执行状态</span><strong>{label}</strong></div>{work&&success&&<div><span>整理结果</span><strong>已返回结构化草稿</strong></div>}{phase&&<div><span>阶段</span><strong>{phase}</strong></div>}{typeof progress==='number'&&Number.isFinite(progress)&&progress>=0&&progress<=100&&<div><span>进度</span><strong>{progress}%</strong></div>}{detail&&<p>{detail}</p>}{summary?<p>{summary}</p>:!video&&<small>当前接口未提供独立的思考摘要，仅显示实际返回的状态。</small>}</div>}</div>
}
