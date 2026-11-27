import {useEffect,useState} from 'react'
import {useSearchParams} from 'react-router-dom'
import {api} from '../auth'
import {MathText} from '../components/MathText'
import {WorkspaceLink as Link} from '../components/WorkspaceNavigation'
import {confirmAction} from '../components/WorkspaceConfirm'
import './TeachingWorks.css'
type Item={id:string;title:string;kind:string;version:number|null;project_id?:string;assets:{role:string;filename:string}[]}
type Draft={id:string;purpose:string;items:Item[];created_at:number}
export default function WorkHandoffs({purpose}:{purpose:'publish'|'product'}){
 const [params,setParams]=useSearchParams(),[rows,setRows]=useState<Draft[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(true),[reload,setReload]=useState(0)
 const selected=params.get('handoff')
 useEffect(()=>{const c=new AbortController();setError('');setLoading(true);api<Draft[]>('/teaching-works/handoffs/list?purpose='+purpose,{signal:c.signal}).then(v=>{if(!c.signal.aborted){setRows(v);setLoading(false)}}).catch(e=>{if(!c.signal.aborted){setError(e.message);setLoading(false)}});return()=>c.abort()},[purpose,reload])
 async function remove(id:string){if(!await confirmAction('解除准备单引用？原教学作品不变。','删除准备单','确认删除'))return;setBusy(true);try{await api('/teaching-works/handoffs/'+encodeURIComponent(id),{method:'DELETE'});setParams({});setReload(n=>n+1)}catch(e){setError(e instanceof Error?e.message:'删除失败')}finally{setBusy(false)}}
 return <div className="finished-works"><header className="finished-heading"><div><h1>{purpose==='publish'?'发布准备':'商品准备'}</h1><p className="muted">已选成品引用。实际发布、商品上架、支付及订单功能尚未接入。</p></div><Link className="button-link" to="/works">选择作品</Link></header>{error&&<p role="alert">{error}</p>}
 {loading?<p className="muted">正在读取准备单…</p>:rows.length===0&&!error&&<section className="panel"><p className="muted">暂无准备单，请从作品中心选择成品。</p></section>}
 {rows.map(d=><section className="panel finished-files" key={d.id}><div className="finished-heading"><h2>{d.items.length} 个作品 · {new Date(d.created_at*1000).toLocaleDateString('zh-CN')}</h2><button onClick={()=>setParams(selected===d.id?{}:{handoff:d.id})}>{selected===d.id?'收起':'查看'}</button></div>{selected===d.id&&<>{d.items.map(i=><article className="finished-version" key={i.id}><MathText compact content={i.title}/><small>{i.version===null?'已审核视频 · 引擎管理':'锁定版本 V'+i.version}</small>{i.assets.map(a=><a key={a.role} className="button-link" href={'/api/teaching-works/handoffs/'+encodeURIComponent(d.id)+'/files/'+encodeURIComponent(i.id)+'/'+encodeURIComponent(a.role)}>{a.filename}</a>)}{i.project_id&&<Link to={'/videos?project='+encodeURIComponent(i.project_id)}>原视频项目</Link>}</article>)}<div className="finished-actions"><button disabled={busy} onClick={()=>void remove(d.id)}>删除准备单</button></div></>}</section>)}
 </div>
}
