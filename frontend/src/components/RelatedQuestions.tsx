import {useEffect,useState} from 'react'
import {api} from '../auth'
import {MathText} from './MathText'
import {WorkspaceLink as Link} from './WorkspaceNavigation'
type Props={content:string;solution:string;subject?:string|null;tags?:string[];excludeId?:string}
type Candidate={resource:{id:string;code:string;title:string;content:string;answer:string;solution:string};reason:string}
export default function RelatedQuestions({content,solution,subject,tags=[],excludeId}:Props){
 const [open,setOpen]=useState(false),[items,setItems]=useState<Candidate[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState('')
 const tagKey=JSON.stringify(tags)
 useEffect(()=>{if(!open||!content.trim())return;const c=new AbortController();setLoading(true);setError('');setItems([]);api<{items:Candidate[]}>('/documents/related-questions',{method:'POST',body:JSON.stringify({content,solution,subject:subject??'',tags:JSON.parse(tagKey),exclude_id:excludeId}),signal:c.signal}).then(r=>{if(!c.signal.aborted)setItems(r.items)}).catch(e=>{if(!c.signal.aborted)setError(e.message)}).finally(()=>{if(!c.signal.aborted)setLoading(false)});return()=>c.abort()},[open,content,solution,subject,tagKey,excludeId])
 return <details className="bank-section" onToggle={e=>setOpen(e.currentTarget.open)}><summary>同类题目 · 教研参考</summary><small className="muted">按已有知识点和明确的解法名称推荐，不属于重复题，不影响入库。</small>{loading&&<p role="status">正在查找相关题目…</p>}{error&&<p role="alert">{error}</p>}{open&&!loading&&!error&&!items.length&&<p className="muted">暂无相关建议，可先填写知识点或解法。</p>}{items.map(x=><details className="manual-match" key={x.resource.id}><summary><MathText compact content={x.resource.code+' '+x.resource.title}/></summary><small>{x.reason}</small><MathText content={x.resource.content}/><details><summary>答案与解析</summary><MathText content={x.resource.answer}/><MathText content={x.resource.solution}/></details><Link to={'/resource-edit/'+encodeURIComponent(x.resource.id)}>查看完整题目</Link></details>)}</details>
}
