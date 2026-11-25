import {useEffect,useState,type FormEvent} from 'react'
import {api} from '../auth'
type Status={available:boolean;detail:string}
export default function Qoder(){
 const [status,setStatus]=useState<Status>(),[model,setModel]=useState<'Auto'|'Fast'>('Auto'),[prompt,setPrompt]=useState(''),[answer,setAnswer]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 async function refresh(){try{setStatus(await api<Status>('/qoder/status'))}catch(e){setError(e instanceof Error?e.message:'连接失败')}}
 useEffect(()=>{void refresh()},[])
 async function send(e:FormEvent){e.preventDefault();setBusy(true);setError('');setAnswer('');try{const r=await api<{answer:string}>('/qoder/test',{method:'POST',body:JSON.stringify({model,prompt})});setAnswer(r.answer)}catch(e){setError(e instanceof Error?e.message:'测试失败')}finally{setBusy(false)}}
 return <div className="qoder-page"><div className="page-heading"><h1>Qoder CN 模型测试</h1><p className="muted">独立 CLI 执行服务 · 当前仅单轮测试，不执行生成的代码</p></div><section className="panel"><div className="panel-heading"><h2>连接状态</h2><button onClick={()=>void refresh()}>刷新</button></div><p>{status?.detail??'正在检测…'}</p><p className="muted">首次登录须在服务器 CLI 完成，网页不接收账号密码或 Token。</p></section><form className="panel resource-form" onSubmit={send}><label>模型档位<select value={model} onChange={e=>setModel(e.target.value as 'Auto'|'Fast')}><option>Auto</option><option>Fast</option></select></label><label>数学题目或教研要求<textarea rows={6} required maxLength={12000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="输入一道题，观察 Qoder CN 的回答质量"/></label><button className="primary" disabled={busy||!status?.available}>{busy?'调用中…':'发送测试'}</button>{error&&<p role="alert" className="inline-error">{error}</p>}</form>{answer&&<section className="panel"><h2>模型原始回答</h2><div className="resource-text">{answer}</div></section>}</div>
}
