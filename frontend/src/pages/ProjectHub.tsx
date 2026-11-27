import {useEffect,useState} from 'react'
import {api} from '../auth'
import {Link,useParams} from 'react-router-dom'
import {Icon} from '../components/Icon'
import {workspaceGroups,modules} from '../navigation'
type RecentDoc={id:string;kind:'paper'|'handout'|'textbook';title:string;updated_at:number;revision:number}
const recentKinds=['paper','handout','textbook'] as const
const recentRoutes={paper:'/papers',handout:'/handouts',textbook:'/textbooks'}
const recentNames={paper:'试卷',handout:'讲义',textbook:'教材'}
const intro:Record<string,string>={intake:'AI 整理或手动录入来源；在卡片工作台编辑题目与知识点。',teaching:'管理数学教学资源、知识体系及自编资料。',creation:'制作视频、组卷、组讲义和组教材，完成后导出。',publishing:'管理教学作品，设计并导出教学内容封面。',sales:'管理课程与资料商品、订单和交付。'}
export default function ProjectHub(){
 const {id}=useParams(),group=workspaceGroups.find(g=>g.id===id),[counts,setCounts]=useState<Record<string,string>>({})
 useEffect(()=>{if(id!=='teaching')return;const c=new AbortController();const pairs=[['/resources','/resources?kind=question&limit=1','道题'],['/knowledge-library','/resources?kind=knowledge&limit=1','个知识点'],['/sources','/resources?kind=source&limit=1','份来源'],['/graph','/knowledge/points?limit=1','个知识标签']];void Promise.all(pairs.map(async ([key,url,unit])=>{try{const v=await api<{total:number}>(url,{signal:c.signal});if(!c.signal.aborted&&typeof v.total==='number')setCounts(old=>({...old,[key]:v.total+' '+unit}))}catch{}}));return()=>c.abort()},[id])
 const [recent,setRecent]=useState<RecentDoc[]>([]),[cartCount,setCartCount]=useState<number>(),[recentState,setRecentState]=useState('正在读取…')
 useEffect(()=>{if(id!=='creation')return;const c=new AbortController();setRecent([]);setCartCount(undefined);setRecentState('正在读取…');api<{ids:string[]}>('/bank/cart',{signal:c.signal}).then(v=>{if(!c.signal.aborted)setCartCount(v.ids.length)}).catch(()=>{});Promise.all(recentKinds.map(kind=>api<{items:RecentDoc[]}>('/documents?kind='+kind+'&limit=5',{signal:c.signal}))).then(rs=>{if(!c.signal.aborted){setRecent(rs.flatMap(r=>r.items).sort((a,b)=>b.updated_at-a.updated_at).slice(0,5));setRecentState('暂无教学资料')}}).catch(()=>{if(!c.signal.aborted)setRecentState('最近编辑读取失败，请打开教学资料库')});return()=>c.abort()},[id])
 if(group?.id==='creation')return <div className="project-hub project-creation production-home">
  <header className="production-heading"><h1>教学制作</h1><p className="muted">从题库与知识库制作教学内容</p><Link className="button-link" to="/selection">选题清单{cartCount===undefined?'':' · '+cartCount+' 项'}</Link></header>
  <div className="production-grid">
    <Link to="/videos" className="project-link production-video" aria-label="视频制作"><span className="production-symbol"><Icon name="film" size={30}/></span><div className="production-info"><strong>视频制作</strong><small>将题库中的题目制作成教学视频</small><span className="production-flow">选题 · 生成 · 渲染 · 微调</span></div><span className="production-cta">进入视频制作 <Icon name="arrow" size={15}/></span></Link>
    {[{path:'/papers',name:'组卷',icon:'works',desc:'选择题目，设置题型与分值'},{path:'/handouts',name:'组讲义',icon:'files',desc:'编排知识点、例题与练习'},{path:'/textbooks',name:'组教材',icon:'book',desc:'按章节组织知识与题目'}].map(item=><Link key={item.path} to={item.path} className="project-link production-document" aria-label={item.name}><span className="production-symbol"><Icon name={item.icon} size={24}/></span><div className="production-info"><strong>{item.name}</strong><small>{item.desc}</small></div><span className="production-doc-cta">开始编写 <Icon name="chevron" size={15}/></span></Link>)}
  </div>
  <section className="panel"><div className="button-row"><h2>最近编辑</h2><Link to="/teaching-library">全部教学资料 ›</Link></div>{recent.length?recent.map(d=><Link key={d.id} className="production-library" to={recentRoutes[d.kind]+'?doc='+encodeURIComponent(d.id)}><Icon name="files" size={20}/><span><strong>{d.title}</strong><small>{recentNames[d.kind]} · 版本 {d.revision}</small></span><Icon name="chevron" size={16}/></Link>):<p className="muted">{recentState}</p>}</section>
  <Link className="production-library" to="/teaching-library"><Icon name="files" size={20}/><span><strong>我的教学资料</strong><small>查看已保存的试卷、讲义和教材</small></span><Icon name="chevron" size={16}/></Link>
 </div>
 if(!group)return <section className="panel"><h1>项目不存在</h1><Link to="/">返回首页</Link></section>
 return <div className={"project-hub project-"+group.id}>
   <header className="project-hub-heading"><span className="project-hub-icon"><Icon name={group.icon} size={30}/></span><h1>{group.name}</h1><p className="muted">{intro[group.id]}</p></header>
   {group.sections.map(section=><section className="project-section" key={section.id}><h2>{section.name}</h2><div className="project-links">{section.entries.map(entry=>{const mod=modules.find(m=>m.path===entry.path.split('?')[0]);return <Link to={entry.path} key={entry.path} className="project-link" aria-label={entry.name}><Icon name={entry.icon} size={21}/><span><strong>{entry.name}</strong>{mod&&<small>{mod.desc}</small>}{counts[entry.path]&&<small>{counts[entry.path]}</small>}</span><Icon name="chevron" size={15}/></Link>})}</div></section>)}
   {group.id==='sales'&&<section className="project-section"><h2>待接入功能</h2><p className="muted">课程商品、资料商品、定价、上架、订单与收入统计尚未接入。</p></section>}
 </div>
}
