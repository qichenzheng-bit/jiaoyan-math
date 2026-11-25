import { useState, type FormEvent } from 'react'
import { BrandMark,Icon } from './components/Icon'

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api' + path, {
    ...options, credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请求失败')
  return data as T
}

export function Login({ onLogin }: { onLogin: (username: string) => void }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      const data = await api<{ username: string }>('/auth/login', { method: 'POST', body: JSON.stringify({username, password}) })
      setPassword('')
      onLogin(data.username)
    } catch (e) { setError(e instanceof Error ? e.message : '登录失败') }
    finally { setBusy(false) }
  }
  return <div className="login-page"><div className="login-layout"><div className="login-editorial"><div className="login-brand"><BrandMark onDark/></div><div><div className="eyebrow">WEIGUANG MATH</div><h1>让每一道数学题，<br/>都能讲给人听。</h1><p>数学教研、教学资源与内容创作，在同一个工作空间中完成。</p><ul className="login-features">{['题目与知识单元录入 · 题库查询','讲义排版 · 组卷出卷','教学内容创作与资料管理','AI 辅助教研'].map((f,i)=><li key={f}><span>{String(i+1).padStart(2,'0')}</span>{f}</li>)}</ul></div><div className="login-note"><Icon name="shield" size={17}/> 个人工作空间 · 安全访问</div></div><form className="login-card login-form" onSubmit={submit}><div className="login-mobile-brand"><BrandMark/></div><h1>登录工作台</h1><p className="muted">使用管理员账号继续。</p>
    <label>用户名<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required maxLength={80}/></label>
    <label>密码<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={128}/></label>
    {error && <p role="alert">{error}</p>}
    <button disabled={busy} type="submit">{busy ? '登录中…' : '登录'}</button>
  </form></div></div>
}

export function PasswordSettings() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setMessage('')
    try {
      await api('/auth/password', { method:'POST', body:JSON.stringify({current_password:current,new_password:next}) })
      setCurrent(''); setNext(''); setMessage('密码已更新，旧会话已失效。')
    } catch(e) { setMessage(e instanceof Error ? e.message : '修改失败') }
    finally { setBusy(false) }
  }
  return <form className="login-card" onSubmit={submit}><h2>修改密码</h2>
    <label>当前密码<input type="password" autoComplete="current-password" required maxLength={128} value={current} onChange={e=>setCurrent(e.target.value)}/></label>
    <label>新密码<input type="password" autoComplete="new-password" required minLength={12} maxLength={128} value={next} onChange={e=>setNext(e.target.value)}/></label>
    <button type="submit" disabled={busy}>保存</button>{message && <p role="status">{message}</p>}
  </form>
}
