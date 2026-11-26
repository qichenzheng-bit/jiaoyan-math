import {useEffect,useState} from 'react'
import {api} from '../auth'
import {Link,useParams} from 'react-router-dom'
import {Icon} from '../components/Icon'
import {workspaceGroups,modules} from '../navigation'
const intro:Record<string,string>={intake:'AI 整理或手动录入来源；在卡片工作台编辑题目与知识单元。',teaching:'管理数学教学资源、知识体系及自编资料。',creation:'制作视频、组卷、组讲义和组教材，完成后导出。',publishing:'设计并导出教学内容封面。',sales:'管理课程与资料商品、订单和交付。'}
export default function ProjectHub(){
 const {id}=useParams(),group=workspaceGroups.find(g=>g.id===id),[counts,setCounts]=useState<Record<string,string>>({})
 useEffect(()=>{if(id!=='teaching')return;const c=new AbortController();const pairs=[['/resources','/resources?kind=question&limit=1','道题'],['/knowledge-library','/resources?kind=knowledge&limit=1','个知识单元'],['/sources','/resources?kind=source&limit=1','份来源'],['/graph','/knowledge/points?limit=1','个知识点']];void Promise.all(pairs.map(async ([key,url,unit])=>{try{const v=await api<{total:number}>(url,{signal:c.signal});if(!c.signal.aborted&&typeof v.total==='number')setCounts(old=>({...old,[key]:v.total+' '+unit}))}catch{}}));return()=>c.abort()},[id])
 if(!group)return <section className="panel"><h1>项目不存在</h1><Link to="/">返回首页</Link></section>
 return <div className={"project-hub project-"+group.id}>
   <header className="project-hub-heading"><span className="project-hub-icon"><Icon name={group.icon} size={30}/></span><h1>{group.name}</h1><p className="muted">{intro[group.id]}</p></header>
   {group.sections.map(section=><section className="project-section" key={section.id}><h2>{section.name}</h2><div className="project-links">{section.entries.map(entry=>{const mod=modules.find(m=>m.path===entry.path.split('?')[0]);return <Link to={entry.path} key={entry.path} className="project-link" aria-label={entry.name}><Icon name={entry.icon} size={21}/><span><strong>{entry.name}</strong>{mod&&<small>{mod.desc}</small>}{counts[entry.path]&&<small>{counts[entry.path]}</small>}</span><Icon name="chevron" size={15}/></Link>})}</div></section>)}
   {group.id==='sales'&&<section className="project-section"><h2>待接入功能</h2><p className="muted">课程商品、资料商品、定价、上架、订单与收入统计尚未接入。</p></section>}
 </div>
}
