import {useMemo,useState} from 'react'
import {api} from '../auth'
import {MathText} from '../components/MathText'
type Chapter={subject:string;chapter:string;count:number}
type Node={name:string;path:string;count:number;children:Node[]}
function build(rows:Chapter[]):Node[]{
 const roots:Node[]=[]
 for(const row of rows){
  if(!row.chapter)continue
  const parts=row.chapter.split('/')
  let children=roots
  for(let i=0;i<parts.length;i++){
   const path=parts.slice(0,i+1).join('/')
   let node=children.find(n=>n.path===path)
   if(!node){node={name:parts[i]||'未命名层级',path,count:0,children:[]};children.push(node)}
   node.count+=row.count;children=node.children
  }
 }
 return roots
}
export default function KnowledgeDirectory({subjects,chapters,subject,chapter,onSelect,onChanged}:{subjects:string[];chapters:Chapter[];subject:string;chapter:string;onSelect:(s:string,c:string)=>void;onChanged:()=>void}){
 const trees=useMemo(()=>Object.fromEntries(subjects.map(s=>[s,build(chapters.filter(c=>c.subject===s))])),[subjects,chapters])
 const [expanded,setExpanded]=useState<Record<string,boolean>>({})
 const [operation,setOperation]=useState<'create'|'move'|''>(''),[editSubject,setEditSubject]=useState(''),[path,setPath]=useState(''),[target,setTarget]=useState('')
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[preview,setPreview]=useState<{total:number;archived:number;directories:number;preview_token:string;sample:{id:string;before:string;after:string}[]}>()
 function begin(mode:'create'|'move'){setOperation(mode);setEditSubject(subject||subjects[0]||'');setPath(mode==='move'?chapter:'');setTarget('');setPreview(undefined);setError('');setNotice('')}
 async function save(commit=false){
  if(busy||!editSubject.trim()||!path.trim()||(operation==='move'&&!target.trim()))return
  setBusy(true);setError('');setNotice('')
  try{
   if(operation==='create'){const state=await api<{revision:number}>('/resources/knowledge-directories');await api('/resources/knowledge-directories',{method:'POST',body:JSON.stringify({subject:editSubject,path,revision:state.revision})});setNotice('目录已创建');onChanged();onSelect(editSubject.trim(),path.trim());setOperation('')}
   else if(commit){const result=await api<{updated:number}>('/resources/knowledge-directories/move',{method:'POST',body:JSON.stringify({subject:editSubject,path,target,preview_token:preview?.preview_token})});setNotice('迁移完成，更新 '+result.updated+' 个知识单元');setOperation('');setPreview(undefined);onChanged();onSelect(editSubject.trim(),target.trim())}
   else setPreview(await api<NonNullable<typeof preview>>('/resources/knowledge-directories/move-preview',{method:'POST',body:JSON.stringify({subject:editSubject,path,target})}))
  }catch(e){setError(e instanceof Error?e.message:'目录操作失败');setPreview(undefined)}finally{setBusy(false)}
 }
 function branch(s:string,n:Node,depth:number){
  const key=JSON.stringify([s,n.path]),open=expanded[key]??(s===subject&&(chapter===n.path||chapter.startsWith(n.path+'/')))
  return <div key={key}><div className="knowledge-directory-node" style={{paddingInlineStart:Math.min(depth,8)*10+'px'}}>
    {n.children.length>0&&<button type="button" className="knowledge-directory-toggle" aria-label={(open?'折叠 ':'展开 ')+n.name} aria-expanded={open} onClick={()=>setExpanded(v=>({...v,[key]:!open}))}>{open?'▾':'▸'}</button>}
    <button type="button" className="bank-chapter" aria-pressed={s===subject&&n.path===chapter} onClick={()=>onSelect(s,n.path)}>{n.name} <small>{n.count}</small></button>
   </div>{open&&n.children.map(child=>branch(s,child,depth+1))}</div>
 }
 return <><div className="button-row"><button type="button" disabled={busy} onClick={()=>begin('create')}>新建目录</button><button type="button" disabled={busy||!chapter||!subject} onClick={()=>begin('move')}>重命名/迁移</button></div>
 {notice&&<p role="status">{notice}</p>}{error&&<p role="alert">{error}</p>}
 {operation&&<section className="bank-section resource-form"><h3>{operation==='create'?'新建目录':'迁移或重命名目录'}</h3><label>学科<input disabled={busy||operation==='move'} maxLength={40} value={editSubject} onChange={e=>{setEditSubject(e.target.value);setPreview(undefined)}}/></label><label>{operation==='create'?'新目录完整路径':'原目录'}<input disabled={busy||operation==='move'} maxLength={120} value={path} placeholder="函数/极限" onChange={e=>{setPath(e.target.value);setPreview(undefined)}}/></label>
 {operation==='move'&&<><label>目标完整路径<input disabled={busy} maxLength={120} value={target} onChange={e=>{setTarget(e.target.value);setPreview(undefined)}}/></label><small className="muted">仅迁移同学科知识库目录及其知识单元，不改动题目、来源、知识标签或历史快照。</small></>}
 <div className="button-row"><button type="button" disabled={busy} onClick={()=>{setOperation('');setPreview(undefined)}}>取消</button><button type="button" className="primary" disabled={busy||!editSubject.trim()||!path.trim()||(operation==='move'&&!target.trim())} onClick={()=>void save()}>{operation==='create'?'创建':'预览迁移'}</button></div>
 {preview&&<><p>影响 {preview.total} 个知识单元（含 {preview.archived} 个归档单元），{preview.directories} 个独立目录。</p>{preview.sample.map(x=><p key={x.id}><MathText content={x.before+' → '+x.after}/></p>)}<button className="primary" disabled={busy} onClick={()=>void save(true)}>确认迁移</button></>}</section>}
 {subjects.map(s=>{const key=JSON.stringify([s]),open=expanded[key]??(!subject||subject===s);return <div key={s}><div className="knowledge-directory-node"><button type="button" className="knowledge-directory-toggle" aria-label={(open?'折叠 ':'展开 ')+s} aria-expanded={open} onClick={()=>setExpanded(v=>({...v,[key]:!open}))}>{open?'▾':'▸'}</button><button type="button" aria-pressed={s===subject&&!chapter} onClick={()=>{setExpanded(v=>({...v,[key]:true}));onSelect(s,'')}}>{s}</button></div>{open&&trees[s]?.map(n=>branch(s,n,1))}</div>})}</>
}
