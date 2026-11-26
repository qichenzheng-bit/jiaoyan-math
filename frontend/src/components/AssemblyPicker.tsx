import {useEffect,useState} from 'react'
import {api} from '../auth'
import ChatText from '../pages/ChatText'
import {MathText} from './MathText'
import type {R} from '../pages/DocWork'
import './ManualWordWork.css'

type Kind='paper'|'handout'|'textbook'
const size=20
const names={paper:'试卷',handout:'讲义',textbook:'教材'}
export default function AssemblyPicker({kind,subjects,existing,append,busy,onConfirm,onCancel}:{kind:Kind;subjects:string[];existing:string[];append:boolean;busy:boolean;onConfirm:(items:R[],title:string)=>void;onCancel?:()=>void}){
 const [bank,setBank]=useState<'question'|'knowledge'>('question'),[q,setQ]=useState(''),[subject,setSubject]=useState(''),[type,setType]=useState(''),[difficulty,setDifficulty]=useState(''),[chapter,setChapter]=useState(''),[page,setPage]=useState(0),[items,setItems]=useState<R[]>([]),[total,setTotal]=useState(0),[cart,setCart]=useState<R[]>([]),[title,setTitle]=useState(''),[loading,setLoading]=useState(false),[error,setError]=useState('')
 const available=Math.max(0,200-existing.length)
 const selected=new Set(cart.map(r=>r.id)),included=new Set(existing)
 useEffect(()=>{
  const ctl=new AbortController();setLoading(true);setError('');setItems([])
  const query=new URLSearchParams({kind:bank,q,subject,chapter,limit:String(size),offset:String(page*size)})
  if(bank==='question'&&type)query.set('question_type',type)
  // Difficulty is not a server-side filter on the existing library listing; do not fake full-library filtering.
  const timer=window.setTimeout(()=>api<{items:R[];total:number}>('/resources?'+query,{signal:ctl.signal}).then(r=>{if(!ctl.signal.aborted){setItems(r.items);setTotal(r.total)}}).catch(e=>{if(!ctl.signal.aborted)setError(e.message||'题库读取失败')}).finally(()=>{if(!ctl.signal.aborted)setLoading(false)}),180)
  return()=>{window.clearTimeout(timer);ctl.abort()}
 },[bank,q,subject,type,chapter,page])
 const toggle=(r:R)=>setCart(prev=>prev.some(x=>x.id===r.id)?prev.filter(x=>x.id!==r.id):included.has(r.id)||prev.length>=available?prev:[...prev,r])
 const visible=items.filter(r=>!difficulty||r.difficulty===difficulty)
 return <section className="assembly-picker">
  <header className="manual-word-toolbar"><strong>{append?'补充选题':'新建'+names[kind]+' · 选题'}</strong><span className="muted">{cart.length} 项已选</span>{onCancel&&<button type="button" disabled={busy} onClick={onCancel}>返回编排</button>}</header>
  <div className="assembly-grid"><div className="assembly-library">
   <div className="assembly-filters">
    <div className="button-row"><button type="button" aria-pressed={bank==='question'} onClick={()=>{setBank('question');setPage(0)}}>题库</button>{kind!=='paper'&&<button type="button" aria-pressed={bank==='knowledge'} onClick={()=>{setBank('knowledge');setPage(0);setDifficulty('')}}>知识库</button>}</div>
    <input aria-label="搜索题库" placeholder="编号、标题、题干" value={q} onChange={e=>{setQ(e.target.value);setPage(0)}}/>
    <select aria-label="筛选科目" value={subject} onChange={e=>{setSubject(e.target.value);setPage(0)}}><option value="">全部科目</option>{subjects.map(s=><option key={s}>{s}</option>)}</select>
    <input aria-label="筛选章节" placeholder="章节" value={chapter} onChange={e=>{setChapter(e.target.value);setPage(0)}}/>
    {bank==='question'&&<><select aria-label="筛选题型" value={type} onChange={e=>{setType(e.target.value);setPage(0)}}><option value="">全部题型</option>{['选择题','单选题','多选题','填空题','综合题'].map(t=><option key={t}>{t}</option>)}</select><select aria-label="本页难度" value={difficulty} onChange={e=>setDifficulty(e.target.value)}><option value="">本页全部难度</option>{['简单','中等','困难'].map(t=><option key={t}>{t}</option>)}</select></>}
   </div>
   <div className="manual-word-side-head"><small>{loading?'正在读取…':'共 '+total+' 项'}</small><button type="button" disabled={busy||loading||!visible.some(r=>!included.has(r.id)&&!selected.has(r.id))||cart.length>=available} onClick={()=>setCart(prev=>[...prev,...visible.filter(r=>!included.has(r.id)&&!prev.some(x=>x.id===r.id)).slice(0,Math.max(0,available-prev.length))])}>加入本页</button></div>
   {error&&<p role="alert">{error}</p>}
   {!loading&&!visible.length&&<p className="muted">没有匹配的资源。</p>}
   {visible.map(r=><article key={r.id} className="assembly-result"><div className="manual-word-side-head"><small>{r.code} · {r.subject||'未分类'} · {r.kind==='question'?r.question_type||'题目':'知识单元'}{r.difficulty?' · '+r.difficulty:''}</small><button type="button" aria-pressed={selected.has(r.id)} disabled={busy||included.has(r.id)||(!selected.has(r.id)&&cart.length>=available)} onClick={()=>toggle(r)}>{included.has(r.id)?'已在文档':selected.has(r.id)?'移出清单':'＋ 选入'}</button></div><strong><MathText compact content={r.title}/></strong><ChatText content={r.content}/><details><summary>查看答案、解析与证明</summary>{r.answer&&<ChatText content={r.answer}/>}{r.solution&&<ChatText content={r.solution}/>}{r.proof&&<ChatText content={r.proof}/>}</details></article>)}
   <div className="button-row"><button type="button" disabled={page===0||loading} onClick={()=>setPage(p=>p-1)}>上一页</button><small>{page+1}/{Math.max(1,Math.ceil(total/size))}</small><button type="button" disabled={(page+1)*size>=total||loading} onClick={()=>setPage(p=>p+1)}>下一页</button></div>
  </div><aside className="assembly-cart"><div className="manual-word-side-head"><strong>选题清单（{cart.length}）</strong><button type="button" disabled={busy||!cart.length} onClick={()=>setCart([])}>清空</button></div>
   {!append&&<label>文档名称<input aria-label="文档名称" placeholder={'未命名'+names[kind]} value={title} maxLength={200} onChange={e=>setTitle(e.target.value)}/></label>}
   {!cart.length&&<p className="muted">从左侧选入题目，跨页保留选择。</p>}
   {cart.map((r,i)=><div key={r.id} className="assembly-cart-item"><div><small>{i+1}. {r.code}</small><MathText compact content={r.title||r.content.slice(0,80)}/></div><button type="button" disabled={busy} aria-label={'移除 '+r.code} onClick={()=>toggle(r)}>×</button></div>)}
   <button type="button" className="primary" disabled={busy||!cart.length} onClick={()=>onConfirm(cart,title.trim()||'未命名'+names[kind])}>{busy?'处理中…':append?'加入 Word 工作台':'进入 Word 工作台'}</button>
   <small className="muted">最多 200 个文档块；题库原题不会被修改。</small>
  </aside></div>
 </section>
}
