import { useEffect,useState,type FormEvent } from 'react'
import { api,PasswordSettings } from '../auth'
import {Link} from 'react-router-dom'
export type Preferences={display_name:string;theme:'light'|'dark'|'system'}
export const defaults:Preferences={display_name:'微光数学',theme:'light'}
type Status={version:string;release:string;disk:{total:number;free:number}|null}
type BackupRecord={state?:string;at?:string;commit?:string;entries?:number;error?:string}
type BackupState={configured:boolean;timer_active:boolean;running:boolean;schedule:string;latest:BackupRecord|null;last_success:BackupRecord|null}
type Audit={id:number;action:string;created_at:number}
export default function Settings({preferences,onChange}:{preferences:Preferences;onChange:(p:Preferences)=>void}){
  const [draft,setDraft]=useState(preferences)
  const [status,setStatus]=useState<Status>()
  const [backup,setBackup]=useState<BackupState>()
  const [backupError,setBackupError]=useState('')
  const [backupBusy,setBackupBusy]=useState(false)
  const [backupRequested,setBackupRequested]=useState(false)
  const [logs,setLogs]=useState<Audit[]>([])
  const [message,setMessage]=useState('')
  const [busy,setBusy]=useState(false)
  useEffect(()=>{setDraft(preferences)},[preferences])
  useEffect(()=>{const c=new AbortController();Promise.all([api<Status>('/settings/status',{signal:c.signal}),api<Audit[]>('/settings/audit',{signal:c.signal})]).then(([s,a])=>{setStatus(s);setLogs(a)}).catch(e=>{if(!c.signal.aborted)setMessage(e.message)});return()=>c.abort()},[])
  useEffect(()=>{let alive=true,active=false;const c=new AbortController()
    const load=async()=>{if(active)return;active=true;try{const value=await api<BackupState>('/settings/backup',{signal:c.signal});if(alive){setBackup(value);setBackupError('')}}catch(e){if(alive)setBackupError(e instanceof Error?e.message:'读取备份状态失败')}finally{active=false}}
    void load();const timer=window.setInterval(()=>void load(),5000)
    return()=>{alive=false;c.abort();window.clearInterval(timer)}
  },[])
  async function requestBackup(){setBackupBusy(true);setBackupError('');setBackupRequested(false);try{await api('/settings/backup/run',{method:'POST'});setBackupRequested(true)}catch(e){setBackupError(e instanceof Error?e.message:'提交失败')}finally{setBackupBusy(false)}}
  async function save(e:FormEvent){e.preventDefault();setBusy(true);setMessage('')
    try{const p=await api<Preferences>('/settings',{method:'PUT',body:JSON.stringify(draft)});onChange(p);setMessage('已保存')}
    catch(e){setMessage(e instanceof Error?e.message:'保存失败')}finally{setBusy(false)}
  }
  return <div className="legacy-settings"><aside className="panel settings-side">{[['model','模型与 AI'],['appearance','外观与显示'],['account','账号安全'],['storage','数据与存储'],['audit','操作记录']].map(([id,t])=><a key={id} href={'#settings-'+id}>{t}</a>)}</aside><div className="settings-content">
    <section className="panel" id="settings-model"><h2>模型与 AI</h2><p className="muted">当前使用 Qoder CN，其他平台尚未接入。</p><Link className="button-link" to="/qoder">账号授权 / 刷新模型</Link></section><form id="settings-appearance" className="login-card" onSubmit={save}><h2>常规设置</h2>
      <label>系统名称<input required maxLength={60} value={draft.display_name} onChange={e=>setDraft({...draft,display_name:e.target.value})}/></label>
      <label>主题<select value={draft.theme} onChange={e=>setDraft({...draft,theme:e.target.value as Preferences['theme']})}><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label>
      <button disabled={busy}>保存设置</button>{message&&<p role="status">{message}</p>}
    </form>
    <div id="settings-account"><PasswordSettings/></div>
    <section className="login-card" id="settings-storage"><h2>系统信息</h2><p>版本：{status?.version??'读取中'}</p><p>提交：{status?.release.slice(0,12)??'—'}</p><p>磁盘剩余：{status?.disk?(status.disk.free/1073741824).toFixed(1)+' GiB':'未配置'}</p><h3>数据备份与恢复</h3><p>计划：每天北京时间 24:00</p><p>自动备份：{!backup?'读取中':backup.timer_active?'已启用':backup.configured?'尚未启用定时器':'等待服务器管理员配置'}</p><p>最近状态：{backup?.running?'正在备份':backup?.latest?.state==='failed'?'失败':backup?.latest?.state==='success'?'成功':backup?.latest?.state==='unchanged'?'无变化，已核验':backup?.latest?.state==='running'?'等待确认':'尚无记录'}</p><p>最近成功：{backup?.last_success?.at?new Date(backup.last_success.at).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'—'}</p>{backup?.last_success?.commit&&<p><a href={'https://github.com/qichenzheng-bit/jiaoyan-data/commit/'+backup.last_success.commit} target="_blank" rel="noreferrer">查看备份提交</a></p>}<button type="button" onClick={()=>void requestBackup()} disabled={!backup?.timer_active||backup.running||backupBusy}>立即备份</button>{backupRequested&&<p role="status">已提交，请查看最新备份状态。</p>}{(backupError||backup?.latest?.error)&&<p role="alert">{backupError||backup?.latest?.error}</p>}<p className="muted">数据恢复需在独立空数据库演练，由服务器管理员执行。</p></section>
    
    <section className="login-card" id="settings-audit"><h2>最近操作</h2>{logs.length===0?<p>暂无记录</p>:<ul className="audit-list">{logs.map(l=><li key={l.id}>{new Date(l.created_at*1000).toLocaleString()} · {l.action}</li>)}</ul>}</section>
  </div></div>
}
