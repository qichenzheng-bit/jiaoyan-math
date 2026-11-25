import {Link} from 'react-router-dom'
import {Icon} from '../components/Icon'
import {modules,sectionFor} from '../navigation'
const pending:Record<string,string[]>={
 '/create':['课程制作'],
 '/products':['课程商品','资料商品','商品组合与定价'],
 '/operations':['商品上架','订单与交付','收入统计','运营计划'],
}
export default function ModuleHub({path}:{path:string}){
 const section=sectionFor(path)
 if(!section)return null
 const info=modules.find(m=>m.path===path)
 return <div className="module-hub"><header className="page-heading"><h1>{section.name}</h1><p className="muted">{info?.desc}</p></header><div className="hub-grid">
 {section.children.map(p=>{const m=modules.find(x=>x.path===p);return m?<Link className="panel hub-card" key={p} to={p}><span className="soft-icon"><Icon name={m.icon} size={24}/></span><h2>{m.name}</h2><p className="muted">{m.desc}</p><span className="text-link">{m.ready?'进入工作台':'打开草稿（待完善）'} <Icon name="chevron" size={15}/></span></Link>:null})}
 {(pending[path]??[]).map(name=><section className="panel hub-card hub-pending" key={name}><span className="soft-icon"><Icon name="clock" size={23}/></span><h2>{name}</h2><p className="muted">尚未开发，当前不可使用。</p></section>)}
 </div></div>
}
