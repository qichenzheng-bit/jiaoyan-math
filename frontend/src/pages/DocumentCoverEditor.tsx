import {useEffect,useState} from 'react'
import {api} from '../auth'
import type {Layout} from './documentLayout'
import {Link} from 'react-router-dom'
import {MathText} from '../components/MathText'

type Cover={id:string;title:string;data:{file_id?:string}}
export default function DocumentCoverEditor({layout,onChange}:{layout:Layout;onChange:(v:Partial<Layout>)=>void}){
 const [open,setOpen]=useState(false),[items,setItems]=useState<Cover[]>([]),[query,setQuery]=useState(''),[offset,setOffset]=useState(0),[total,setTotal]=useState(0),[target,setTarget]=useState<'coverFileId'|'backCoverFileId'>('coverFileId'),[error,setError]=useState('')
 useEffect(()=>{
  if(!open)return
  const c=new AbortController();setError('')
  api<{items:Cover[];total:number}>('/studio?'+new URLSearchParams({kind:'work',category:'cover',archived:'false',q:query,limit:'20',offset:String(offset)}),{signal:c.signal}).then(data=>{if(!c.signal.aborted){setItems(data.items.filter(x=>!!x.data?.file_id));setTotal(data.total)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)})
  return()=>c.abort()
 },[open,query,offset])
 return <details onToggle={e=>setOpen(e.currentTarget.open)}><summary>封面与封底</summary>
 <div className="layout-fields">
 {(['coverFileId','backCoverFileId'] as const).map(key=><div key={key}><strong>{key==='coverFileId'?'封面':'封底'}</strong>{layout[key]&&<img className="layout-cover-thumbnail" src={'/api/files/'+layout[key]+'/preview'} alt={key==='coverFileId'?'已选封面':'已选封底'}/>}<button type="button" onClick={()=>setTarget(key)} aria-pressed={target===key}>选择{key==='coverFileId'?'封面':'封底'}</button>{layout[key]&&<button type="button" onClick={()=>onChange({[key]:''})}>移除</button>}</div>)}
 </div>
 {open&&<><p className="muted">从已有封面作品选择图片；按纸张比例完整显示，不拉伸、不裁剪。</p><Link to="/covers">打开现有封面制作工具</Link><input aria-label="搜索封面作品" placeholder="搜索已有封面" value={query} onChange={e=>{setQuery(e.target.value);setOffset(0)}}/>
 {error&&<p role="alert">{error}</p>}
 <div className="layout-cover-list">{items.map(item=><button type="button" key={item.id} onClick={()=>onChange({[target]:item.data.file_id})}><img className="layout-cover-thumbnail" src={'/api/files/'+item.data.file_id+'/preview'} alt=""/><MathText compact content={item.title}/></button>)}</div>
 <div className="button-row"><button disabled={offset===0} onClick={()=>setOffset(x=>Math.max(0,x-20))}>上一页</button><button disabled={offset+20>=total} onClick={()=>setOffset(x=>x+20)}>下一页</button></div></>}
 </details>
}
