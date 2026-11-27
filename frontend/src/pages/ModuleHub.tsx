import {modules} from '../navigation'
import WorkHandoffs from './WorkHandoffs'

const pending=['课程商品','资料商品','商品组合与定价','商品上架','订单与交付','收入统计']
export default function ModuleHub({path}:{path:string}){
 const module=modules.find(m=>m.path===path)
 if(path!=='/products'||!module)return null
 return <div className="module-hub"><WorkHandoffs purpose="product"/><header className="hub-heading"><div><h1>{module.name}</h1><p className="muted">集中管理课程、资料商品及交易。售卖功能尚未接入，当前不会产生商品、订单或收入记录。</p></div></header>
 <details className="hub-planned" open><summary>尚未接入的功能</summary><p className="muted">尚未开发，当前不可操作。</p><div className="planned-list">{pending.map(name=><span key={name}>{name}</span>)}</div></details>
 </div>
}
