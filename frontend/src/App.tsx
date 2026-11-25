import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, Link } from 'react-router-dom'
import { api, Login } from './auth'
import Settings, {defaults,type Preferences} from './pages/Settings'
import Files from './pages/Files'
import FormulaLab from './pages/FormulaLab'

const modules = [
  { path: '/', name: '工作台首页', desc: '教研与创作入口' },
  { path: '/intake', name: '资源录入', desc: '手动录入、AI辅助录入及批量导入' },
  { path: '/resources', name: '教学资源', desc: '统一教学资源库及关联体系' },
  { path: '/research', name: '教研创作', desc: '资源调用、数学编辑器及教研任务' },
  { path: '/media', name: '多媒体制作', desc: '图文、绘图、文档、文章与课件' },
  { path: '/works', name: '教学作品', desc: '作品归档及版本管理' },
  { path: '/publishing', name: '自媒体运营', desc: '平台适配、发布管理及运营数据' },
  { path: '/files', name: '文件管理', desc: '公共文件上传、预览与归档' },
  { path: '/formulas', name: '公式预览', desc: 'LaTeX 公式实时显示' },
  { path: '/settings', name: '系统设置', desc: '账号、模型、存储及系统信息' },
] as const

function Home() {
  return <><h1>教研工作台</h1><p className="muted">管理教学资源与创作任务。</p>
    <section className="notice">基础工程测试版。教研业务功能尚未开放。</section>
    <div className="tiles">{modules.slice(1).map(m => <Link className="tile" key={m.path} to={m.path}><strong>{m.name}</strong><span>{m.desc}</span><small>{['/settings','/files','/formulas'].includes(m.path) ? '基础功能' : '待开发'}</small></Link>)}</div>
  </>
}

export default function App() {
  const [preferences,setPreferences]=useState<Preferences>(defaults)
  const [menu, setMenu] = useState(false)
  const [assistant, setAssistant] = useState(false)
  const [health, setHealth] = useState('检查中')
  const [user, setUser] = useState<string | null | undefined>(undefined)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/auth/me', {signal:controller.signal}).then(async r => {
      if (r.status === 401) return setUser(null)
      if (!r.ok) throw new Error('无法连接认证服务')
      const data = await r.json(); setUser(data.username)
    }).catch(() => { if (!controller.signal.aborted) { setError('无法连接认证服务，请检查服务器配置'); setUser(null) } })
    fetch('/api/ready', {signal:controller.signal}).then(r=>setHealth(r.ok?'服务已连接':'服务未就绪')).catch(()=>{if(!controller.signal.aborted)setHealth('服务未连接')})
    return () => controller.abort()
  }, [])
  useEffect(()=>{
    if(!user)return
    const c=new AbortController()
    api<Preferences>('/settings',{signal:c.signal}).then(setPreferences).catch(()=>{})
    return()=>c.abort()
  },[user])
  useEffect(()=>{
    const media=window.matchMedia('(prefers-color-scheme: dark)')
    const apply=()=>{document.documentElement.dataset.theme=preferences.theme==='system'?(media.matches?'dark':'light'):preferences.theme}
    apply();media.addEventListener('change',apply)
    return()=>media.removeEventListener('change',apply)
  },[preferences.theme])
  async function logout() {
    try { await api('/auth/logout',{method:'POST'}); setUser(null); setPreferences(defaults); setAssistant(false); setMenu(false); setError('') }
    catch(e) { setError(e instanceof Error?e.message:'退出失败') }
  }
  if (user === undefined) return <div className="login-page"><p>正在检查登录状态…</p></div>
  if (user === null) return <><Login onLogin={name=>{setUser(name);setError('')}}/>{error && <p className="auth-error" role="alert">{error}</p>}</>
  return <div className="shell">
    <header><button className="menu" aria-label="切换导航" aria-expanded={menu} onClick={() => setMenu(!menu)}>菜单</button>
      <Link className="brand" to="/">{preferences.display_name} <small>教研工作台</small></Link>
      <span className="health" role="status">{health} · {user}</span>
      <button aria-expanded={assistant} onClick={() => setAssistant(!assistant)}>AI 助手</button>
      <button onClick={logout}>退出</button>
    </header>
    <nav className={menu ? 'nav open' : 'nav'} aria-label="主导航">
      {modules.map(m => <NavLink end={m.path === '/'} key={m.path} to={m.path} onClick={() => setMenu(false)}>{m.name}</NavLink>)}
    </nav>
    <main>{error && <p role="alert">{error}</p>}<Routes>
      <Route path="/" element={<Home/>}/>
      {modules.slice(1).map(m => <Route key={m.path} path={m.path} element={m.path==='/files'?<Files/>:m.path==='/formulas'?<FormulaLab/>:<><h1>{m.name}</h1><p>{m.desc}</p>{m.path==='/settings'?<Settings preferences={preferences} onChange={setPreferences}/>:<section className="notice">此模块将在对应开发阶段开放。</section>}</>}/>)}
      <Route path="*" element={<><h1>页面不存在</h1><Link to="/">返回首页</Link></>}/>
    </Routes></main>
    {assistant && <aside aria-label="AI 助手"><h2>AI 助手</h2><p>模型接入将在后续阶段完成。</p><button onClick={() => setAssistant(false)}>关闭</button></aside>}
  </div>
}
