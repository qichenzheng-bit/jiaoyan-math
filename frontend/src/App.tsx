import { useEffect, useState } from 'react'
import { NavLink, Route, Routes, Link } from 'react-router-dom'

const modules = [
  { path: '/', name: '工作台首页', desc: '教研与创作入口' },
  { path: '/intake', name: '资源录入', desc: '手动录入、AI辅助录入及批量导入' },
  { path: '/resources', name: '教学资源', desc: '统一教学资源库及关联体系' },
  { path: '/research', name: '教研创作', desc: '资源调用、数学编辑器及教研任务' },
  { path: '/media', name: '多媒体制作', desc: '图文、绘图、文档、文章与课件' },
  { path: '/works', name: '教学作品', desc: '作品归档及版本管理' },
  { path: '/publishing', name: '自媒体运营', desc: '平台适配、发布管理及运营数据' },
  { path: '/settings', name: '系统设置', desc: '账号、模型、存储及系统信息' },
] as const

function Home() {
  return <><h1>教研工作台</h1><p className="muted">管理教学资源与创作任务。</p>
    <section className="notice">当前为基础工程测试版。登录、数据存储及业务功能尚未开放。</section>
    <div className="tiles">{modules.slice(1).map(m => <Link className="tile" key={m.path} to={m.path}><strong>{m.name}</strong><span>{m.desc}</span><small>待开发</small></Link>)}</div>
  </>
}

export default function App() {
  const [menu, setMenu] = useState(false)
  const [assistant, setAssistant] = useState(false)
  const [health, setHealth] = useState('检查中')
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/health', {signal: controller.signal})
      .then(async r => {
        if (!r.ok) throw new Error('health')
        const data = await r.json()
        setHealth(data.status === 'ok' ? '后端已连接' : '后端异常')
      })
      .catch(() => { if (!controller.signal.aborted) setHealth('后端未连接') })
    return () => controller.abort()
  }, [])
  return <div className="shell">
    <header><button className="menu" aria-label="切换导航" aria-expanded={menu} onClick={() => setMenu(!menu)}>菜单</button>
      <Link className="brand" to="/">微光数学 <small>教研工作台</small></Link>
      <span className="health" role="status">{health}</span>
      <button aria-expanded={assistant} onClick={() => setAssistant(!assistant)}>AI 助手</button>
    </header>
    <nav className={menu ? 'nav open' : 'nav'} aria-label="主导航">
      {modules.map(m => <NavLink end={m.path === '/'} key={m.path} to={m.path} onClick={() => setMenu(false)}>{m.name}</NavLink>)}
    </nav>
    <main><Routes>
      <Route path="/" element={<Home/>}/>
      {modules.slice(1).map(m => <Route key={m.path} path={m.path} element={<><h1>{m.name}</h1><p>{m.desc}</p><section className="notice">此模块将在对应开发阶段开放。</section></>}/>)}
      <Route path="*" element={<><h1>页面不存在</h1><Link to="/">返回首页</Link></>}/>
    </Routes></main>
    {assistant && <aside aria-label="AI 助手"><h2>AI 助手</h2><p>模型接入将在后续阶段完成。</p><button onClick={() => setAssistant(false)}>关闭</button></aside>}
  </div>
}
