import {Link,useParams} from 'react-router-dom'
import {Icon} from '../components/Icon'
import {workspaceGroups,modules} from '../navigation'
const intro:Record<string,string>={teaching:'录入资料、管理教学资源与制作教学内容。',publishing:'管理封面、发布记录和运营数据。',sales:'管理课程与资料商品、订单和交付。'}
export default function ProjectHub(){
 const {id}=useParams(),group=workspaceGroups.find(g=>g.id===id)
 if(!group)return <section className="panel"><h1>项目不存在</h1><Link to="/">返回首页</Link></section>
 return <div className="project-hub">
   <header className="project-hub-heading"><span className="project-hub-icon"><Icon name={group.icon} size={30}/></span><h1>{group.name}</h1><p className="muted">{intro[group.id]}</p></header>
   {group.sections.map(section=><section className="project-section" key={section.id}><h2>{section.name}</h2><div className="project-links">{section.entries.map(entry=>{const mod=modules.find(m=>m.path===entry.path.split('?')[0]);return <Link to={entry.path} key={entry.path} className="project-link" aria-label={entry.name}><Icon name={entry.icon} size={21}/><span><strong>{entry.name}</strong>{mod&&<small>{mod.desc}</small>}</span><Icon name="chevron" size={15}/></Link>})}</div></section>)}
   {group.id==='sales'&&<section className="project-section"><h2>待接入功能</h2><p className="muted">课程商品、资料商品、定价、上架、订单与收入统计尚未接入。</p></section>}
 </div>
}
