import { useState, type FormEvent } from 'react'

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
  return <div className="login-page"><form className="login-card" onSubmit={submit}>
    <h1>微光数学</h1><p>个人教研工作台</p>
    <label>用户名<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required maxLength={80}/></label>
    <label>密码<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required maxLength={128}/></label>
    {error && <p role="alert">{error}</p>}
    <button disabled={busy} type="submit">{busy ? '登录中…' : '登录'}</button>
  </form></div>
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
