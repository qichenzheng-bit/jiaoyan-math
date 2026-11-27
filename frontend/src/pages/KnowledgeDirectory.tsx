import {useMemo,useState} from 'react'
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
export default function KnowledgeDirectory({subjects,chapters,subject,chapter,onSelect}:{subjects:string[];chapters:Chapter[];subject:string;chapter:string;onSelect:(s:string,c:string)=>void}){
 const trees=useMemo(()=>Object.fromEntries(subjects.map(s=>[s,build(chapters.filter(c=>c.subject===s))])),[subjects,chapters])
 const [expanded,setExpanded]=useState<Record<string,boolean>>({})
 function branch(s:string,n:Node,depth:number){
  const key=JSON.stringify([s,n.path]),open=expanded[key]??(s===subject&&(chapter===n.path||chapter.startsWith(n.path+'/')))
  return <div key={key}><div className="knowledge-directory-node" style={{paddingInlineStart:Math.min(depth,8)*10+'px'}}>
    {n.children.length>0&&<button type="button" className="knowledge-directory-toggle" aria-label={(open?'折叠 ':'展开 ')+n.name} aria-expanded={open} onClick={()=>setExpanded(v=>({...v,[key]:!open}))}>{open?'▾':'▸'}</button>}
    <button type="button" className="bank-chapter" aria-pressed={s===subject&&n.path===chapter} onClick={()=>onSelect(s,n.path)}>{n.name} <small>{n.count}</small></button>
   </div>{open&&n.children.map(child=>branch(s,child,depth+1))}</div>
 }
 return <>{subjects.map(s=>{const key=JSON.stringify([s]),open=expanded[key]??(!subject||subject===s);return <div key={s}><div className="knowledge-directory-node"><button type="button" className="knowledge-directory-toggle" aria-label={(open?'折叠 ':'展开 ')+s} aria-expanded={open} onClick={()=>setExpanded(v=>({...v,[key]:!open}))}>{open?'▾':'▸'}</button><button type="button" aria-pressed={s===subject&&!chapter} onClick={()=>{setExpanded(v=>({...v,[key]:true}));onSelect(s,'')}}>{s}</button></div>{open&&trees[s]?.map(n=>branch(s,n,1))}</div>})}</>
}
