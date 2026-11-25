import {useEffect,useState,type FormEvent} from 'react'
import {api} from '../auth'
import {Icon} from '../components/Icon'
type Login={state:string;url:string;detail:string}
type Status={available:boolean;detail:string;verified_at?:number|null;login?:Login;auth_ui?:boolean}
export default function Qoder(){
 const [status,setStatus]=useState<Status>(),[model,setModel]=useState<'Auto'|'Fast'>('Auto'),[prompt,setPrompt]=useState(''),[answer,setAnswer]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[authBusy,setAuthBusy]=useState(false)
 async function refresh(){try{setStatus(await api<Status>('/qoder/status'))}catch(e){setError(e instanceof Error?e.message:'连接失败')}}
 useEffect(()=>{void refresh()},[])
 const waiting=status?.login?.state==='starting'||status?.login?.state==='waiting'
 useEffect(()=>{if(!waiting)return;const timer=window.setInterval(()=>void refresh(),2000);return()=>window.clearInterval(timer)},[waiting])
 async function authorize(action:'start'|'cancel'){
  setAuthBusy(true);setError('')
  try{await api('/qoder/login/'+action,{method:'POST'});await refresh()}catch(e){setError(e instanceof Error?e.message:'授权操作失败')}finally{setAuthBusy(false)}
 }
 async function run(text:string,verify=false){
  setBusy(true);setError('');if(!verify)setAnswer('')
  try{const r=await api<{answer:string}>('/qoder/test',{method:'POST',body:JSON.stringify({model,prompt:text})});setAnswer(r.answer)}catch(e){setError(e instanceof Error?e.message:'测试失败')}finally{setBusy(false);await refresh()}
 }
 function send(e:FormEvent){e.preventDefault();void run(prompt)}
 const authUrl=status?.login?.url
 const connected=status?.verified_at?'模型已验证':waiting?'等待授权':'尚未验证'
 return <div className="qoder-page">
  <div className="page-heading"><div className="eyebrow">AI / MODEL CONNECTION</div><h1>Qoder CN</h1><p className="muted">账号授权与教研能力测试</p></div>
  <section className="panel">
   <div className="panel-heading"><div><h2><span className="soft-icon"><Icon name="spark"/></span> 模型账号</h2><p>服务器独立 CLI · 国内版</p></div><button onClick={()=>void refresh()} disabled={busy||authBusy}>刷新状态</button></div>
   <div className="notice"><strong>{status?.available?connected:'执行服务未就绪'}</strong><p className="muted">{status?.detail??'正在检测…'}</p>{status?.verified_at&&<p className="muted">最近成功调用：{new Date(status.verified_at*1000).toLocaleString()}</p>}</div>
   <p className="muted">{status?.login?.detail??'已有 CLI 登录可直接验证；新账号通过官方授权页面登录。'}</p>
   {status?.available&&!status.auth_ui&&<p className="inline-error">执行服务需要升级，才能使用网页授权。</p>}
   <div className="button-row">
    <button className="primary" disabled={busy||authBusy||waiting||!status?.available||!status.auth_ui} onClick={()=>void authorize('start')}>{authBusy?'处理中…':'浏览器授权登录'}</button>
    <button disabled={busy||authBusy||waiting||!status?.available} onClick={()=>void run('请直接回答：1+1等于多少？',true)}>验证模型连接</button>
    {waiting&&<button disabled={authBusy} onClick={()=>void authorize('cancel')}>取消授权</button>}
   </div>
   {waiting&&<div className="notice"><p>{authUrl?'请打开官方授权页面完成登录，授权成功后返回此页。':'正在等待 CLI 生成授权地址…'}</p>{authUrl&&<div className="button-row"><a className="button-link primary" href={authUrl} target="_blank" rel="noopener noreferrer">打开官方授权页面 <Icon name="arrow" size={16}/></a><button onClick={()=>{void navigator.clipboard.writeText(authUrl).catch(()=>setError('复制失败，请直接打开授权页面'))}}>复制链接</button></div>}</div>}
   <p className="muted">授权信息由官方 CLI 保存，不在教研网页中输入账号密码。若手机端回调失败，可继续使用已有 CLI 登录或服务器终端授权。</p>
  </section>
  <form className="panel resource-form" onSubmit={send}><h2>模型测试</h2><label>模型档位<select value={model} onChange={e=>setModel(e.target.value as 'Auto'|'Fast')}><option>Auto</option><option>Fast</option></select></label><label>数学题目或教研要求<textarea rows={6} required maxLength={12000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="输入一道题，观察 Qoder CN 的回答质量"/></label><button className="primary" disabled={busy||waiting||authBusy||!status?.available}>{busy?'调用中…':'发送测试'}</button></form>
  {error&&<p role="alert" className="inline-error">{error}</p>}{answer&&<section className="panel"><h2>模型原始回答</h2><div className="resource-text">{answer}</div></section>}
 </div>
}
