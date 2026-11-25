import {useEffect,useRef,useState,type FormEvent} from 'react'
import {api} from '../auth'
import {Icon} from '../components/Icon'
import {MathText} from '../components/MathText'
type Login={state:string;url:string;detail:string}
type Status={available:boolean;detail:string;verified_at?:number|null;login?:Login;auth_ui?:boolean;model_discovery?:boolean;worker_version?:number}
type Catalog={models:{id:string;label:string;efforts:string[]}[];source:string;updated_at?:number|null}
const date=(s:number)=>new Date(s*1000).toLocaleString()

export default function Qoder(){
 const [status,setStatus]=useState<Status>(),[catalog,setCatalog]=useState<Catalog>(),[saved,setSaved]=useState('Auto'),[draft,setDraft]=useState('Auto'),[editing,setEditing]=useState(false)
 const [prompt,setPrompt]=useState(''),[answer,setAnswer]=useState(''),[message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(''),[tab,setTab]=useState<'accounts'|'models'|'test'>('accounts')
 const alive=useRef(true), pending=useRef(false)
 const waiting=status?.login?.state==='starting'||status?.login?.state==='waiting'
 const options=catalog?.models??[]
 const selected=options.find(m=>m.id===saved)
 const connected=status?.verified_at?'已验证':waiting?'等待授权':status?.available?'尚未验证':status?'未连接':'检测中'
 async function refresh(){if(pending.current)return;pending.current=true;try{const r=await api<Status>('/qoder/status');if(alive.current)setStatus(r)}catch(e){if(alive.current)setError(e instanceof Error?e.message:'连接失败')}finally{pending.current=false}}
 useEffect(()=>{alive.current=true;const c=new AbortController();void refresh();Promise.all([api<Catalog>('/qoder/models',{signal:c.signal}),api<{model:string}>('/qoder/preferences',{signal:c.signal})]).then(([m,p])=>{if(!c.signal.aborted){setCatalog(m);setSaved(p.model);setDraft(p.model)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>{alive.current=false;c.abort()}},[])
 useEffect(()=>{if(!waiting)return;const t=window.setInterval(()=>void refresh(),2000);return()=>window.clearInterval(t)},[waiting])
 async function action(key:string,fn:()=>Promise<void>){if(busy)return;setBusy(key);setError('');setMessage('');try{await fn()}catch(e){setError(e instanceof Error?e.message:'操作失败')}finally{setBusy('')}}
 async function authorize(kind:'start'|'cancel'){await action(kind,async()=>{await api('/qoder/login/'+kind,{method:'POST'});await refresh()})}
 async function discover(){await action('models',async()=>{const r=await api<Catalog>('/qoder/models/refresh',{method:'POST'});setCatalog(r);setMessage('模型清单已更新');if(!r.models.some(m=>m.id===draft))setDraft(r.models[0]?.id??'')})}
 async function save(e:FormEvent){e.preventDefault();await action('save',async()=>{const r=await api<{model:string}>('/qoder/preferences',{method:'PUT',body:JSON.stringify({model:draft})});setSaved(r.model);setEditing(false);setMessage('模型设置已保存')})}
 async function run(text:string,verify=false){await action(verify?'verify':'test',async()=>{if(!verify)setAnswer('');try{const r=await api<{answer:string}>('/qoder/test',{method:'POST',body:JSON.stringify({model:saved,prompt:text})});if(verify)setMessage('模型连接验证成功');else setAnswer(r.answer)}finally{await refresh()}})}
 function send(e:FormEvent){e.preventDefault();void run(prompt)}
 const disabled=Boolean(busy||waiting||!status?.available)
 return <div className="model-center">
  <div className="page-heading"><h1>AI 账号与模型</h1><p className="muted">统一授权、模型配置与连接测试</p></div>
  <nav className="model-tabs" aria-label="模型管理功能">{([{id:'accounts',label:'账号授权'},{id:'models',label:'模型配置'},{id:'test',label:'连接测试'}] as const).map(t=><button key={t.id} aria-pressed={tab===t.id} onClick={()=>{setTab(t.id);setMessage('');setError('')}}>{t.label}</button>)}</nav>
  {error&&<div className="model-feedback inline-error" role="alert">{error}</div>}{message&&<div className="model-feedback" role="status">{message}</div>}
  {tab==='accounts'&&<>
   <div className="model-account-grid">
    <section className="panel provider-card"><div className="provider-head"><span className="provider-icon" style={{background:'var(--ink)',color:'var(--surface)'}}>Q</span><strong>Qoder CN</strong><span className={'provider-state '+(status?.verified_at?'is-verified':'')}>{connected}</span></div><dl><div><dt>用途</dt><dd>AI 教研与智能录入</dd></div><div><dt>授权方式</dt><dd>阿里云 / 官方浏览器授权</dd></div><div><dt>执行服务</dt><dd>{status?.detail??'正在检测'}</dd></div><div><dt>最近验证</dt><dd>{status?.verified_at?date(status.verified_at):'—'}</dd></div></dl>
     {status?.available&&!status.model_discovery&&<p className="muted">独立执行服务需要升级，以支持动态模型探测。</p>}
     {status?.login&&status.login.state!=='idle'&&<p className="muted">{status.login.detail}</p>}
     {waiting&&<div className="provider-authorization"><strong>1. 获取官方授权链接</strong>{status?.login?.url?<><a className="auth-url" href={status.login.url} target="_blank" rel="noopener noreferrer">{status.login.url}</a><div className="button-row"><button onClick={()=>void navigator.clipboard.writeText(status.login!.url).catch(()=>setError('复制失败，请直接打开链接'))}>复制授权链接</button><a className="button-link primary" href={status.login.url} target="_blank" rel="noopener noreferrer">打开授权页</a></div></>:<p className="muted">正在等待 CLI 输出授权地址…</p>}<strong>2. 完成授权后验证连接</strong><button disabled={Boolean(busy)} onClick={()=>void authorize('cancel')}>取消本次授权</button></div>}
     <div className="provider-actions"><button className="primary" disabled={disabled||!status?.auth_ui} onClick={()=>void authorize('start')}>{busy==='start'?'正在启动…':status?.verified_at?'重新授权':'登录账号'}</button><button disabled={Boolean(busy)} onClick={()=>void refresh()}>刷新状态</button></div><button disabled={disabled||!selected} onClick={()=>void run('请直接回答：1+1等于多少？',true)}>{busy==='verify'?'验证中…':'验证模型连接'}</button>
    </section>

   </div>
   <section className="panel model-summary"><span>当前已验证平台：{status?.verified_at?'1':'0'} / 1</span><span>可用模型：{catalog?.source==='cli'?options.length:'待探测'}</span><span>当前模型：{saved}</span></section>
   <section className="panel model-quota"><h2>用量与积分</h2><p className="muted">当前未接入已验证的积分接口，不显示估算余额。可在官方 Qoder CN 账户中查看真实用量。</p><a className="text-link" href="https://qoder.com.cn/" target="_blank" rel="noopener noreferrer">打开 Qoder CN 官网 <Icon name="arrow" size={15}/></a></section>
  </>}
  {tab==='models'&&<section className="panel model-config"><div className="panel-heading"><div><h2>教研默认模型</h2><p>模型清单来源：{catalog?.source==='cli'?'CLI 实际探测':'兼容档位（尚未探测）'}</p></div><button disabled={disabled||!status?.model_discovery} onClick={()=>void discover()}>{busy==='models'?'正在探测…':'刷新模型'}</button></div>
   {catalog?.updated_at&&<p className="muted">上次探测：{date(catalog.updated_at)}</p>}
   {!selected&&catalog&&<p className="inline-error">当前保存的模型已不在清单中，请重新选择。</p>}
   <form className="model-config-form resource-form" onSubmit={save}><label>平台<input value="Qoder CN" readOnly/></label><label>模型<select value={editing?draft:saved} disabled={!editing||Boolean(busy)} onChange={e=>setDraft(e.target.value)}>{!options.some(m=>m.id===(editing?draft:saved))&&<option value={editing?draft:saved}>{editing?draft:saved}（待确认）</option>}{options.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</select></label><label>推理强度<input value="模型默认" readOnly/></label><div className="button-row">{editing?<><button type="button" onClick={()=>{setDraft(saved);setEditing(false)}}>取消</button><button className="primary" disabled={Boolean(busy)||!options.some(m=>m.id===draft)}>保存</button></>:<button type="button" disabled={Boolean(busy)||!options.length} onClick={()=>{setDraft(saved);setEditing(true)}}>修改</button>}</div></form><p className="muted">模型选择保存在服务器。推理强度仅在当前 CLI 能可靠报告该模型支持的档位后开放。</p>
  </section>}
  {tab==='test'&&<><form className="panel resource-form" onSubmit={send}><div className="panel-heading"><h2>模型连接测试</h2><span className="provider-state">{saved}</span></div><label>数学题目或教研要求<textarea rows={6} required maxLength={12000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="输入一道数学题，观察 Qoder CN 的回答质量"/></label><button className="primary" disabled={disabled||!selected}>{busy==='test'?'调用中…':'发送测试'}</button><p className="muted">本页面仅进行单轮测试，不执行模型生成的代码。日常数学教研请使用首页 AI 助手。</p></form>{answer&&<section className="panel"><h2>模型回答</h2><MathText content={answer}/></section>}</>}
 </div>
}
