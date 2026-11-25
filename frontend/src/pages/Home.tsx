import {MathText} from '../components/MathText'
import {useEffect,useState} from 'react'
import {Link} from 'react-router-dom'
import {api} from '../auth'
import {taskLink} from '../task-links'
import {Icon} from '../components/Icon'
type Resource={id:string;code:string;title:string;kind:string;subject:string;updated_at:number}
type ResourceList={items:Resource[];total:number}
type Audit={id:number;action:string;created_at:number}
type FileStats={count:number;bytes:number;max_file_bytes:number}
type Task={id:string;kind:string;title:string;state:string;session_id:string|null;document_id?:string;document_kind?:string}
type VideoStatus={available:boolean;detail:string}
type QoderStatus={available:boolean;verified_at?:number|null}
type VideoProject={id:string;work_id:string|null;engine_id:string|null;source_snapshot:{title:string}}
const steps=[{no:'01',name:'智能录入',desc:'识别资料、整理题目与知识',path:'/intake',icon:'spark'},{no:'02',name:'教学资源',desc:'积累、检索、关联教学内容',path:'/library',icon:'resources'},{no:'03',name:'内容创作',desc:'视频、讲义、试卷制作',path:'/create',icon:'research'},{no:'04',name:'作品归档',desc:'管理已完成的教学作品',path:'/products',icon:'works'},{no:'05',name:'运营发布',desc:'发布台账与运营数据',path:'/operations',icon:'publishing'}]
const actions:Record<string,string>={'auth.login':'登录系统','auth.logout':'退出登录','auth.password_change':'修改密码','file.upload':'上传文件','file.archive':'归档文件','file.restore':'恢复文件','settings.update':'更新设置','admin.create':'创建管理员','resource.create':'录入资源','resource.update':'修改资源','resource.archive':'归档资源','resource.restore':'恢复资源'}
const labels:Record<string,string>={question:'题目',knowledge:'知识单元',source:'来源资料'}
function date(stamp:number){if(!Number.isFinite(stamp))return '—';return new Date(stamp*1000).toLocaleString(undefined,{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}
export default function Home(){
 const [counts,setCounts]=useState<Record<string,number>>({})
 const [recent,setRecent]=useState<Resource[]>(),[audit,setAudit]=useState<Audit[]>(),[stats,setStats]=useState<FileStats>()
 const [tasks,setTasks]=useState<Task[]>(),[video,setVideo]=useState<VideoStatus>(),[qoder,setQoder]=useState<QoderStatus>(),[projects,setProjects]=useState<VideoProject[]>()
 const [errors,setErrors]=useState<string[]>([]),[tab,setTab]=useState<'recent'|'audit'>('recent'),[retry,setRetry]=useState(0)
 useEffect(()=>{const c=new AbortController();setErrors([]);setCounts({});setRecent(undefined);setAudit(undefined);setStats(undefined);setTasks(undefined);setVideo(undefined);setQoder(undefined);setProjects(undefined)
  function fail(name:string){if(!c.signal.aborted)setErrors(prev=>[...prev,name])}
  for(const kind of ['question','knowledge','source']) api<ResourceList>('/resources?kind='+kind+'&limit=1',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setCounts(prev=>({...prev,[kind]:r.total}))}).catch(()=>fail(labels[kind]))
  Promise.all(['handout','paper'].map(kind=>api<{total:number}>('/documents?kind='+kind+'&limit=1',{signal:c.signal}))).then(rows=>{if(!c.signal.aborted)setCounts(prev=>({...prev,documents:rows.reduce((n,r)=>n+r.total,0)}))}).catch(()=>fail('讲义试卷'))
  api<ResourceList>('/resources?limit=6',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setRecent(r.items)}).catch(()=>fail('最近资源'))
  api<Audit[]>('/settings/audit',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setAudit(r.slice(0,8))}).catch(()=>fail('操作记录'))
  api<FileStats>('/files/stats',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setStats(r)}).catch(()=>fail('文件统计'))
  api<Task[]>('/tasks',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setTasks(r)}).catch(()=>fail('任务记录'))
  api<VideoStatus>('/video/status',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setVideo(r)}).catch(()=>fail('视频服务'))
  api<QoderStatus>('/qoder/status',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setQoder(r)}).catch(()=>fail('AI 服务'))
  api<VideoProject[]>('/video/projects',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setProjects(r)}).catch(()=>fail('视频项目'))
  api<{total:number}>('/studio?kind=work&limit=1',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setCounts(prev=>({...prev,works:r.total}))}).catch(()=>fail('作品数量'))
  return()=>c.abort()
 },[retry])
 const metrics=[{name:'题库题目',value:counts.question,icon:'resources',path:'/resources',hint:'当前题库资源'},{name:'知识单元',value:counts.knowledge,icon:'book',path:'/knowledge-library',hint:'定义、定理与方法'},{name:'来源资料',value:counts.source,icon:'files',path:'/sources',hint:'已录入的来源资料'},{name:'讲义 / 试卷',value:counts.documents,icon:'book',path:'/handouts',hint:'已保存文档'},{name:'视频项目',value:projects?.length,icon:'media',path:'/videos',hint:'项目记录'},{name:'教学作品',value:counts.works,icon:'works',path:'/works',hint:'已保存作品'}]
 return <div className="home-page">
  <div className="home-heading"><div><p className="workspace-kicker">微光数学 · 教研空间</p><h1>教研工作台</h1><p className="muted">从教学素材到内容产出，在同一个工作空间完成。</p></div><Link to="/chat" className="button-link primary"><Icon name="spark" size={18}/> 打开 AI 助手</Link></div>
  {errors.length>0&&<div className="home-error" role="status"><span>部分数据读取失败：{errors.join('、')}</span><button onClick={()=>setRetry(n=>n+1)}>重试</button></div>}
  <section className="workflow-board panel"><div className="home-panel-head"><div><h2>教研工作流程</h2><p className="muted">录入 → 资源沉淀 → 内容制作 → 作品 → 发布</p></div><Link className="text-link" to="/tasks">任务中心 <Icon name="arrow" size={15}/></Link></div><div className="workflow-steps">{steps.map(s=><Link to={s.path} key={s.no} className="workflow-step"><div><span className="step-index">{s.no}</span><Icon name={s.icon} size={22}/></div><strong>{s.name}</strong><small>{s.desc}</small><Icon name="arrow" size={15}/></Link>)}</div></section>
  <section className="home-quick"><div className="home-panel-head"><h2>开始创作</h2><Link to="/create" className="text-link">全部创作工具 <Icon name="chevron" size={14}/></Link></div><div className="quick-grid">{[{name:'制作视频',path:'/videos',icon:'media',desc:'题目讲解与微调'},{name:'制作讲义',path:'/handouts',icon:'book',desc:'知识编排与文档'},{name:'制作试卷',path:'/papers',icon:'works',desc:'题库组卷与导出'},{name:'新建资源',path:'/intake',icon:'plus',desc:'试卷、教材、讲义'}].map(m=><Link className="quick-link" to={m.path} key={m.path}><span className="soft-icon"><Icon name={m.icon} size={20}/></span><span><strong>{m.name}</strong><small>{m.desc}</small></span><Icon name="chevron" size={15}/></Link>)}</div></section>
  <div className="home-panel-head home-metrics-heading"><h2>资源与作品</h2><Link className="text-link" to="/library">教学资源 <Icon name="chevron" size={14}/></Link></div>
  <div className="home-stat-grid">{metrics.map(m=><Link className="home-stat" key={m.name} to={m.path}><div><span>{m.name}</span><Icon name={m.icon} size={18}/></div><strong>{m.value??'—'}</strong><small>{m.hint}</small></Link>)}</div>
  <div className="home-columns">
   <section className="panel home-activity"><div className="home-panel-head"><h2>工作动态</h2><div className="home-tabs"><button aria-pressed={tab==='recent'} onClick={()=>setTab('recent')}>最近资源</button><button aria-pressed={tab==='audit'} onClick={()=>setTab('audit')}>操作记录</button></div></div>
    {tab==='recent'?recent?.length?recent.map(r=><Link key={r.id} className="recent-row" to={(r.kind==='source'?'/sources':r.kind==='knowledge'?'/knowledge-library':'/resources')+'?q='+encodeURIComponent(r.code)}><span className="soft-icon"><Icon name={r.kind==='knowledge'?'book':'resources'} size={18}/></span><span className="recent-name"><strong><MathText compact content={r.title}/></strong><small>{labels[r.kind]??r.kind} · {r.subject||'未分类'}</small></span><small className="muted">{date(r.updated_at)}</small></Link>):<div className="empty-state"><Icon name="resources" size={28}/><strong>{recent?'暂无最近资源':errors.includes('最近资源')?'资源读取失败':'正在读取资源…'}</strong><Link to="/intake" className="text-link">录入教学资源</Link></div>:audit?.length?audit.map(a=><div key={a.id} className="recent-row"><span className="soft-icon"><Icon name="clock" size={18}/></span><span className="recent-name"><strong>{actions[a.action]??a.action}</strong><small>{date(a.created_at)}</small></span></div>):<div className="empty-state">{audit?'暂无操作记录':errors.includes('操作记录')?'读取失败':'正在读取…'}</div>}
   </section>
   <div className="home-right"><section className="panel home-resume"><div className="home-panel-head"><h2>继续工作</h2><Link className="text-link" to="/tasks">查看任务 <Icon name="chevron" size={14}/></Link></div>{tasks?.filter(t=>['running','review','failed'].includes(t.state)).slice(0,3).map(t=><Link className="resume-row" key={t.id} to={taskLink(t)}><Icon name="clock" size={17}/><span><MathText compact content={t.title}/><small>{({running:'执行中',review:'待审核',failed:'执行失败'} as Record<string,string>)[t.state]??t.state}</small></span><Icon name="chevron" size={14}/></Link>)}{projects?.filter(p=>!p.work_id).slice(0,2).map(p=><Link className="resume-row" key={p.id} to={'/videos?project='+encodeURIComponent(p.id)}><Icon name="media" size={17}/><span><MathText compact content={p.source_snapshot.title}/><small>{p.engine_id?'未归档视频项目':'待绑定引擎'}</small></span><Icon name="chevron" size={14}/></Link>)}{tasks&&projects&&!tasks.some(t=>['running','review','failed'].includes(t.state))&&!projects.some(p=>!p.work_id)&&<p className="muted">暂无待处理的录入或视频项目。</p>}{(!tasks||!projects)&&<p className="muted">任务或项目数据尚未读取。</p>}</section><section className="panel home-side"><div className="home-panel-head"><h2>工作空间</h2><Link className="text-link" to="/files">文件管理 <Icon name="chevron" size={14}/></Link></div><dl className="home-details"><div><dt>文件数量</dt><dd>{stats?.count??'—'}</dd></div><div><dt>内容占用</dt><dd>{stats?(stats.bytes/1048576).toFixed(1)+' MB':'—'}</dd></div><div><dt>单文件上限</dt><dd>{stats?(stats.max_file_bytes/1048576).toFixed(0)+' MB':'—'}</dd></div></dl><div className="home-services"><Link to="/qoder" className="service-row"><Icon name="spark" size={19}/><span><strong>Qoder CN</strong><small>{qoder?.available?(qoder.verified_at?'已验证连接':'执行服务可用，授权待验证'):qoder?'执行服务未就绪':'状态未读取'}</small></span><Icon name="chevron" size={14}/></Link><Link to="/videos" className="service-row"><Icon name="media" size={19}/><span><strong>视频引擎</strong><small>{video?.available?'接口已连接':video?'接口未就绪':'状态未读取'}</small></span><Icon name="chevron" size={14}/></Link></div></section></div>
  </div>
 </div>
}
