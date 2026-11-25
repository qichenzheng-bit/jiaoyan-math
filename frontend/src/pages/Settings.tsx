import { useEffect,useState,type FormEvent } from 'react'
import { api,PasswordSettings } from '../auth'
import {Link} from 'react-router-dom'
export type Preferences={display_name:string;theme:'light'|'dark'|'system'}
export const defaults:Preferences={display_name:'微光数学',theme:'light'}
type Status={version:string;release:string;disk:{total:number;free:number}|null}
type Audit={id:number;action:string;created_at:number}
export default function Settings({preferences,onChange}:{preferences:Preferences;onChange:(p:Preferences)=>void}){
  const [draft,setDraft]=useState(preferences)
  const [status,setStatus]=useState<Status>()
  const [logs,setLogs]=useState<Audit[]>([])
  const [message,setMessage]=useState('')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{setDraft(preferences)},[preferences])
  useEffect(()=>{const c=new AbortController();Promise.all([api<Status>('/settings/status',{signal:c.signal}),api<Audit[]>('/settings/audit',{signal:c.signal})]).then(([s,a])=>{setStatus(s);setLogs(a)}).catch(e=>{if(!c.signal.aborted)setMessage(e.message)});return()=>c.abort()},[])
  async function save(e:FormEvent){e.preventDefault();setBusy(true);setMessage('')
    try{const p=await api<Preferences>('/settings',{method:'PUT',body:JSON.stringify(draft)});onChange(p);setMessage('已保存')}
    catch(e){setMessage(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}
  }
  return <div className="settings-grid">
    <form className="login-card" onSubmit={save}><h2>常规设置</h2>
      <label>系统名称<input required maxLength={60} value={draft.display_name} onChange={e=>setDraft({...draft,display_name:e.target.value})}/></label>
      <label>主题<select value={draft.theme} onChange={e=>setDraft({...draft,theme:e.target.value as Preferences['theme']})}><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label>
      <button disabled={busy}>保存设置</button>{message&&<p role="status">{message}</p>}
    </form>
    <PasswordSettings/>
    <section className="login-card"><h2>系统信息</h2><p>版本：{status?.version??'读取中'}</p><p>提交：{status?.release.slice(0,12)??'—'}</p><p>磁盘剩余：{status?.disk?(status.disk.free/1073741824).toFixed(1)+' GiB':'未配置'}</p><p>备份与恢复由服务器管理员执行。</p></section>
    <section className="login-card"><h2>模型设置</h2><p>管理 Qoder CN 账号授权与模型连接。</p><Link className="button-link" to="/qoder">AI 账号与模型</Link></section>
    <section className="login-card"><h2>最近操作</h2>{logs.length===0?<p>暂无记录</p>:<ul className="audit-list">{logs.map(l=><li key={l.id}>{new Date(l.created_at*1000).toLocaleString()} · {l.action}</li>)}</ul>}</section>
  </div>
}
