import {Link} from 'react-router-dom'
import {Icon} from '../components/Icon'
import {modules,sectionFor} from '../navigation'
type Group={name:string;note:string;paths:string[]}
const sections:Record<string,{lead:string;action?:string;actionPath?:string;groups:Group[];pending:string[]}>={
 '/library':{lead:'所有教学内容从这里沉淀。按类型检索、关联、复用，再进入内容制作。',action:'AI 智能录入',actionPath:'/intelligence',groups:[{name:'核心资源库',note:'题目、知识与原始来源',paths:['/resources','/knowledge-library','/sources']},{name:'资源组织与素材',note:'关联教学内容与复用素材',paths:['/graph','/assets','/files']}],pending:[]},
 '/create':{lead:'从已有资源出发，制作教学视频、讲义和试卷。工具仅在需要时打开。',action:'开始制作视频',actionPath:'/videos',groups:[{name:'核心内容制作',note:'教学视频、可打印讲义与试卷',paths:['/videos','/handouts','/papers','/works']},{name:'创作工具',note:'排版、绘图与公式',paths:['/research','/drawing','/formulas']},{name:'其他内容形式',note:'目前仅支持草稿管理',paths:['/media','/slides']}],pending:['课程制作']},
 '/products':{lead:'集中管理课程、资料商品及交易。售卖功能尚未接入，当前不会产生商品、订单或收入记录。',groups:[],pending:['课程商品','资料商品','商品组合与定价','商品上架','订单与交付','收入统计']},
 '/operations':{lead:'记录发布文案、平台链接和真实反馈数据，集中管理运营工作。',action:'进入发布台账',actionPath:'/publishing',groups:[{name:'内容运营',note:'已接入的运营工具',paths:['/covers','/publishing','/analytics']}],pending:['运营计划']},
}
export default function ModuleHub({path}:{path:string}){
 const section=sectionFor(path),data=sections[path]
 if(!section||!data)return null
 return <div className="module-hub"><header className="hub-heading"><div><h1>{section.name}</h1><p className="muted">{data.lead}</p></div>{data.action&&data.actionPath&&<Link className="button-link primary" to={data.actionPath}>{data.action}<Icon name="arrow" size={16}/></Link>}</header>
 {data.groups.map(group=><section className="hub-group" key={group.name}><div className="home-panel-head"><h2>{group.name}</h2><span className="muted">{group.note}</span></div><div className="hub-grid">{group.paths.map(p=>{const m=modules.find(m=>m.path===p);return m?<Link className="hub-card clean-tool-row" key={p} to={p}><Icon name={m.icon} size={20}/><div><h3>{m.name}</h3><p className="muted">{m.desc}</p></div><span className="hub-card-arrow"><Icon name="arrow" size={17}/></span></Link>:null})}</div></section>)}
 {data.pending.length>0&&<details className="hub-planned" open={path==='/products'||undefined}><summary>尚未接入的功能</summary><p className="muted">尚未开发，当前不可操作。</p><div className="planned-list">{data.pending.map(name=><span key={name}>{name}</span>)}</div></details>}
 </div>
}
