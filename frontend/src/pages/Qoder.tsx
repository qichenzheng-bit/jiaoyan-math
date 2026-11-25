import {useEffect,useRef,useState,type FormEvent} from 'react'
import {api} from '../auth'
import {Icon} from '../components/Icon'
import {MathText} from '../components/MathText'
type Login={state:string;url:string;detail:string}
type Status={available:boolean;detail:string;verified_at?:number|null;login?:Login;auth_ui?:boolean;model_discovery?:boolean;worker_version?:number}
type Catalog={models:{id:string;label:string;efforts:string[]}[];source:string;updated_at?:number|null}
const date=(s:number)=>new Date(s*1000).toLocaleString()
function officialUrl(value?:string){try{const u=new URL(value??'');return u.protocol==='https:'&&!u.username&&!u.password&&['qoder.com.cn','qoder.com','aliyun.com','alibabacloud.com'].some(d=>u.hostname===d||u.hostname.endsWith('.'+d))?u.href:''}catch{return ''}}

export default function Qoder(){
 const [status,setStatus]=useState<Status>(),[catalog,setCatalog]=useState<Catalog>(),[saved,setSaved]=useState('Auto'),[draft,setDraft]=useState('Auto'),[editing,setEditing]=useState(false)
 const [prompt,setPrompt]=useState(''),[answer,setAnswer]=useState(''),[message,setMessage]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(''),[tab,setTab]=useState<'accounts'|'models'|'test'>('accounts')
 const alive=useRef(true), pending=useRef(false), loginRevision=useRef(0), autoDiscovered=useRef(false), authWindow=useRef<Window|null>(null)
 const authUrl=officialUrl(status?.login?.url)
 const waiting=status?.login?.state==='starting'||status?.login?.state==='waiting'
 const options=catalog?.models??[]
 const selected=options.find(m=>m.id===saved)
 const connected=status?.verified_at?'已验证':waiting?'等待授权':status?.login?.state==='finished'?'授权完成':status?.available?'尚未验证':status?'未连接':'检测中'
 async function refresh(){if(pending.current)return;pending.current=true;const revision=loginRevision.current;try{const r=await api<Status>('/qoder/status',{signal:AbortSignal.timeout(10000)});if(alive.current&&revision===loginRevision.current)setStatus(r)}catch(e){if(alive.current&&revision===loginRevision.current)setError(e instanceof Error?e.message:'连接失败')}finally{pending.current=false}}
 useEffect(()=>{alive.current=true;const c=new AbortController();const revision=loginRevision.current;void refresh();Promise.all([api<Catalog>('/qoder/models',{signal:c.signal}),api<{model:string}>('/qoder/preferences',{signal:c.signal})]).then(([m,p])=>{if(!c.signal.aborted){if(revision===loginRevision.current)setCatalog(m);setSaved(p.model);setDraft(p.model)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>{alive.current=false;c.abort();closePendingWindow()}},[])
 useEffect(()=>{if(!waiting)return;const t=window.setInterval(()=>void refresh(),2000);return()=>window.clearInterval(t)},[waiting])
 useEffect(()=>{
   if(busy||waiting)return
   let cancelled=false
   const sync=()=>{const revision=loginRevision.current;api<Catalog>('/qoder/models',{signal:AbortSignal.timeout(10000)}).then(m=>{if(!cancelled&&revision===loginRevision.current&&m.source==='cli')setCatalog(m)}).catch(()=>{})}
   const timer=window.setInterval(sync,60000)
   window.addEventListener('focus',sync)
   return()=>{cancelled=true;window.clearInterval(timer);window.removeEventListener('focus',sync)}
 },[busy,waiting])
 function closePendingWindow(){const w=authWindow.current;authWindow.current=null;try{w?.close()}catch{/* browser may already have closed it */}}
 useEffect(()=>{
   if(authUrl&&waiting&&authWindow.current){const w=authWindow.current;authWindow.current=null;try{if(!w.closed){w.location.replace(authUrl);setMessage('已打开官方授权页，请完成登录后返回此页面。')}}catch{setMessage('请点击下方打开授权页。')}}
   if(status?.login&&!waiting)closePendingWindow()
 },[authUrl,waiting,status?.login?.state])
 async function action(key:string,fn:()=>Promise<void>){if(busy)return;setBusy(key);setError('');setMessage('');try{await fn()}catch(e){setError(e instanceof Error?e.message:'操作失败')}finally{setBusy('')}}
 async function authorize(kind:'start'|'cancel'){
  if(busy)return
  if(kind==='start'){
    if(!status){setError('正在检测 Qoder CN 执行服务，请刷新状态后重试。');void refresh();return}
    if(!status.available){setError('Qoder CN 暂不可用：'+status.detail+'。请检查服务器独立执行服务和 CLI 是否已安装、启动。');void refresh();return}
    if(!status.auth_ui){setError('服务器 Qoder CN 执行服务版本过旧，尚不支持网页授权，请升级并重启独立执行服务。');return}
    try{const w=window.open('about:blank','_blank');if(w){authWindow.current=w;w.opener=null;w.document.title='正在获取 Qoder CN 授权链接';w.document.body.textContent='正在获取官方授权链接，请稍候；如未跳转，请返回微光数学查看授权状态。'}}catch{/* Explicit link remains available if the browser blocks a new tab. */}
  }
  await action(kind,async()=>{
    loginRevision.current++
    if(kind==='start')autoDiscovered.current=false
    setMessage(kind==='start'?'正在发起官方授权，请稍候…':'正在取消授权…')
    try{
      const login=await api<Login>('/qoder/login/'+kind,{method:'POST',signal:AbortSignal.timeout(15000)})
      if(!login||typeof login.state!=='string')throw new Error('授权接口未返回有效状态，请检查服务器执行服务。')
      if(kind==='start')setCatalog({models:[],source:'pending'})
      setStatus(prev=>prev?{...prev,login,verified_at:kind==='start'?null:prev.verified_at}:prev)
      setMessage(kind==='cancel'?'已取消本次授权':login.detail||'已发起授权，正在获取链接')
      if(kind==='cancel'||!['starting','waiting'].includes(login.state))closePendingWindow()
      await refresh()
    }catch(e){closePendingWindow();setMessage('');throw e}
  })
 }
 async function discover(automatic=false){await action('models',async()=>{
   setMessage(automatic?'授权完成，正在拉取最新模型…':'正在拉取最新模型…')
   try{
     const r=await api<Catalog>('/qoder/models/refresh',{method:'POST',signal:AbortSignal.timeout(55000)})
     if(r.source!=='cli'||!Array.isArray(r.models))throw new Error('未取得 CLI 实际模型清单')
     setCatalog(r)
     if(!r.models.some(m=>m.id===draft))setDraft(r.models[0]?.id??'')
     setMessage(r.models.length?'最新模型清单已更新（'+r.models.length+' 个）'+(r.models.some(m=>m.id===saved)?'':'，原默认模型已不可用，请重新选择。'):'授权完成，但 CLI 当前未返回可用模型。')
   }catch(e){setMessage('');throw new Error((automatic?'授权已完成，自动拉取模型失败：':'拉取模型失败：')+(e instanceof Error?e.message:'未知错误')+'。可点击刷新模型重试。')}
 })}
 useEffect(()=>{
   // The worker clears its catalog on each new login. On return to this page,
   // also recover a completed authorization whose catalog was not yet fetched.
   if(!busy&&status?.available&&status.model_discovery&&status.login?.state==='finished'&&catalog&&catalog.source!=='cli'&&!autoDiscovered.current){
     autoDiscovered.current=true
     void discover(true)
   }
 },[busy,status?.available,status?.model_discovery,status?.login?.state,catalog])
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
     {status&&!status.available&&<p className="inline-error" role="status">Qoder CN 暂不可用：{status.detail}。点击登录账号可查看处理提示。</p>}{status?.available&&!status.auth_ui&&<p className="inline-error" role="status">服务器执行服务版本过旧，不支持网页授权。</p>}{status?.login&&status.login.state!=='idle'&&<p role="status" className={['failed','expired'].includes(status.login.state)?'inline-error':'muted'}>{status.login.detail}</p>}
     {waiting&&<div className="provider-authorization"><strong>1. 获取官方授权链接</strong>{authUrl?<><a className="auth-url" href={authUrl} target="_blank" rel="noopener noreferrer">{authUrl}</a><div className="button-row"><button onClick={()=>{if(!navigator.clipboard){setError('当前浏览器不支持复制，请直接打开链接');return}void navigator.clipboard.writeText(authUrl).catch(()=>setError('复制失败，请直接打开链接'))}}>复制授权链接</button><a className="button-link primary" href={authUrl} target="_blank" rel="noopener noreferrer">打开授权页</a></div></>:<p className="muted">正在等待 CLI 输出授权地址… 如未自动跳转，链接出现后可手动打开。</p>}<strong>2. 完成授权后自动拉取最新模型</strong><button disabled={Boolean(busy)} onClick={()=>void authorize('cancel')}>取消本次授权</button></div>}
     <div className="provider-actions"><button className="primary" disabled={Boolean(busy||waiting)} onClick={()=>void authorize('start')}>{busy==='start'?'正在启动…':status?.verified_at?'重新授权':'登录账号'}</button><button disabled={Boolean(busy)} onClick={()=>void refresh()}>刷新状态</button>{status?.login?.state==='finished'&&<button disabled={disabled||!status.model_discovery} onClick={()=>void discover()}>{busy==='models'?'正在拉取…':'刷新模型'}</button>}</div>{status?.login?.state==='finished'&&catalog?.source==='cli'&&<p className="muted">已获取 {options.length} 个实际模型。<button type="button" onClick={()=>setTab('models')}>选择模型</button></p>}<button disabled={disabled||!selected} onClick={()=>void run('请直接回答：1+1等于多少？',true)}>{busy==='verify'?'验证中…':'验证模型连接'}</button>
    </section>

   </div>
   <section className="panel model-summary"><span>当前已验证平台：{status?.verified_at?'1':'0'} / 1</span><span>可用模型：{catalog?.source==='cli'?options.length:'待探测'}</span><span>当前模型：{saved}</span><span>自动更新：每 24 小时</span><span>上次成功更新：{catalog?.source==='cli'&&catalog.updated_at?date(catalog.updated_at):'尚未更新'}</span></section>
   <section className="panel model-quota"><h2>用量与积分</h2><p className="muted">当前未接入已验证的积分接口，不显示估算余额。可在官方 Qoder CN 账户中查看真实用量。</p><a className="text-link" href="https://qoder.com.cn/" target="_blank" rel="noopener noreferrer">打开 Qoder CN 官网 <Icon name="arrow" size={15}/></a></section>
  </>}
  {tab==='models'&&<section className="panel model-config"><div className="panel-heading"><div><h2>教研默认模型</h2><p>模型清单来源：{catalog?.source==='cli'?'CLI 实际探测':catalog?.source==='pending'?'等待授权后探测':'兼容档位（尚未探测）'}</p></div><button disabled={disabled||!status?.model_discovery} onClick={()=>void discover()}>{busy==='models'?'正在探测…':'刷新模型'}</button></div>
   {catalog?.updated_at&&<p className="muted">上次成功更新：{date(catalog.updated_at)}</p>}
   {!selected&&catalog&&<p className="inline-error">当前保存的模型已不在清单中，请重新选择。</p>}
   <form className="model-config-form resource-form" onSubmit={save}><label>平台<input value="Qoder CN" readOnly/></label><label>模型<select value={editing?draft:saved} disabled={!editing||Boolean(busy)} onChange={e=>setDraft(e.target.value)}>{!options.some(m=>m.id===(editing?draft:saved))&&<option value={editing?draft:saved}>{editing?draft:saved}（待确认）</option>}{options.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</select></label><label>推理强度<input value="模型默认" readOnly/></label><div className="button-row">{editing?<><button type="button" onClick={()=>{setDraft(saved);setEditing(false)}}>取消</button><button className="primary" disabled={Boolean(busy)||!options.some(m=>m.id===draft)}>保存</button></>:<button type="button" disabled={Boolean(busy)||!options.length} onClick={()=>{setDraft(saved);setEditing(true)}}>修改</button>}</div></form><p className="muted">模型选择保存在服务器。推理强度仅在当前 CLI 能可靠报告该模型支持的档位后开放。</p>
  </section>}
  {tab==='test'&&<><form className="panel resource-form" onSubmit={send}><div className="panel-heading"><h2>模型连接测试</h2><span className="provider-state">{saved}</span></div><label>数学题目或教研要求<textarea rows={6} required maxLength={12000} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="输入一道数学题，观察 Qoder CN 的回答质量"/></label><button className="primary" disabled={disabled||!selected}>{busy==='test'?'调用中…':'发送测试'}</button><p className="muted">本页面仅进行单轮测试，不执行模型生成的代码。日常数学教研请使用首页 AI 助手。</p></form>{answer&&<section className="panel"><h2>模型回答</h2><MathText content={answer}/></section>}</>}
 </div>
}
