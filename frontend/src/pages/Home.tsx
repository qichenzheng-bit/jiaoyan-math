import {MathText} from '../components/MathText'
import {useEffect,useState} from 'react'
import {Link} from 'react-router-dom'
import {api} from '../auth'
import {Icon} from '../components/Icon'
type Resource={id:string;code:string;title:string;kind:string;subject:string;updated_at:number}
type ResourceList={items:Resource[];total:number}
type Audit={id:number;action:string;created_at:number}
type FileStats={count:number;bytes:number;max_file_bytes:number}
const actions:Record<string,string>={'auth.login':'登录系统','auth.logout':'退出登录','auth.password_change':'修改密码','file.upload':'上传文件','file.archive':'归档文件','file.restore':'恢复文件','settings.update':'更新设置','admin.create':'创建管理员','resource.create':'录入资源','resource.update':'修改资源','resource.archive':'归档资源','resource.restore':'恢复资源'}
const labels:Record<string,string>={question:'题目',knowledge:'知识单元',source:'来源资料'}
function date(stamp:number){return new Date(stamp*1000).toLocaleString(undefined,{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}
export default function Home(){
 const [counts,setCounts]=useState<Record<string,number>>({})
 const [recent,setRecent]=useState<Resource[]>(),[audit,setAudit]=useState<Audit[]>(),[stats,setStats]=useState<FileStats>()
 const [errors,setErrors]=useState<string[]>([]),[tab,setTab]=useState<'recent'|'audit'>('recent'),[retry,setRetry]=useState(0)
 useEffect(()=>{const c=new AbortController();setErrors([]);setCounts({});setRecent(undefined);setAudit(undefined);setStats(undefined)
  function fail(name:string){if(!c.signal.aborted)setErrors(prev=>[...prev,name])}
  for(const kind of ['question','knowledge','source']) api<ResourceList>('/resources?kind='+kind+'&limit=1',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setCounts(prev=>({...prev,[kind]:r.total}))}).catch(()=>fail(labels[kind]))
  Promise.all(['handout','paper'].map(kind=>api<{total:number}>('/documents?kind='+kind+'&limit=1',{signal:c.signal}))).then(rows=>{if(!c.signal.aborted)setCounts(prev=>({...prev,documents:rows.reduce((n,r)=>n+r.total,0)}))}).catch(()=>fail('讲义试卷'))
  api<ResourceList>('/resources?limit=6',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setRecent(r.items)}).catch(()=>fail('最近资源'))
  api<Audit[]>('/settings/audit',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setAudit(r.slice(0,8))}).catch(()=>fail('操作记录'))
  api<FileStats>('/files/stats',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setStats(r)}).catch(()=>fail('文件统计'))
  return()=>c.abort()
 },[retry])
 const metrics=[{name:'题库题目',value:counts.question,icon:'resources',path:'/resources',hint:'当前题库资源'},{name:'知识单元',value:counts.knowledge,icon:'book',path:'/resources',hint:'定义、定理与方法'},{name:'来源资料',value:counts.source,icon:'files',path:'/sources',hint:'已录入的来源资料'},{name:'讲义文档 / 试卷',value:counts.documents,icon:'works',path:'/handouts',hint:'已保存讲义与试卷'}]
 return <div className="home-page">
  <div className="home-heading"><div><h1>首页</h1><p className="muted">你的数学教学与内容创作总览</p></div><Link to="/intake" className="button-link primary"><Icon name="plus" size={18}/> 新建资源</Link></div>
  {errors.length>0&&<div className="home-error" role="status"><span>部分数据读取失败：{errors.join('、')}</span><button onClick={()=>setRetry(n=>n+1)}>重试</button></div>}
  <div className="home-stat-grid">{metrics.map(m=><Link className="home-stat" key={m.name} to={m.path}><div><span>{m.name}</span><Icon name={m.icon} size={18}/></div><strong>{m.value??'—'}</strong><small>{m.hint}</small></Link>)}</div>
  <div className="home-columns">
   <section className="panel home-activity"><div className="home-panel-head"><h2>工作动态</h2><div className="home-tabs"><button aria-pressed={tab==='recent'} onClick={()=>setTab('recent')}>最近资源</button><button aria-pressed={tab==='audit'} onClick={()=>setTab('audit')}>操作记录</button></div></div>
    {tab==='recent'?recent?.length?recent.map(r=><Link key={r.id} className="recent-row" to={(r.kind==='source'?'/sources':'/resources')+'?q='+encodeURIComponent(r.code)}><span className="soft-icon"><Icon name={r.kind==='knowledge'?'book':'resources'} size={18}/></span><span className="recent-name"><strong><MathText compact content={r.title}/></strong><small>{labels[r.kind]??r.kind} · {r.subject||'未分类'}</small></span><small className="muted">{date(r.updated_at)}</small></Link>):<div className="empty-state"><Icon name="resources" size={28}/><strong>{recent?'暂无最近资源':errors.includes('最近资源')?'资源读取失败':'正在读取资源…'}</strong><Link to="/intake" className="text-link">录入教学资源</Link></div>:audit?.length?audit.map(a=><div key={a.id} className="recent-row"><span className="soft-icon"><Icon name="clock" size={18}/></span><span className="recent-name"><strong>{actions[a.action]??a.action}</strong><small>{date(a.created_at)}</small></span></div>):<div className="empty-state">{audit?'暂无操作记录':errors.includes('操作记录')?'读取失败':'正在读取…'}</div>}
   </section>
   <section className="panel home-side"><div className="home-panel-head"><h2>工作空间</h2><Link className="text-link" to="/files">文件管理 <Icon name="chevron" size={14}/></Link></div><dl className="home-details"><div><dt>文件数量</dt><dd>{stats?.count??'—'}</dd></div><div><dt>内容占用</dt><dd>{stats?(stats.bytes/1048576).toFixed(1)+' MB':'—'}</dd></div><div><dt>单文件上限</dt><dd>{stats?(stats.max_file_bytes/1048576).toFixed(0)+' MB':'—'}</dd></div></dl><div className="home-ai"><Icon name="spark" size={21}/><div><strong>Qoder CN</strong><p>管理模型账号与验证连接</p></div><Link className="button-link" to="/qoder">管理</Link></div></section>
  </div>
  <section className="home-quick"><h2>快速开始</h2><div>{[{name:'录入题目',path:'/intake',icon:'intake'},{name:'查询题库',path:'/resources',icon:'resources'},{name:'来源资料',path:'/sources',icon:'files'},{name:'数学公式',path:'/formulas',icon:'formulas'}].map(m=><Link className="quick-link" to={m.path} key={m.path}><Icon name={m.icon} size={20}/><span>{m.name}</span><Icon name="chevron" size={15}/></Link>)}</div></section>
 </div>
}
