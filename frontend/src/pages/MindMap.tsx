import {useMemo,useRef,useState} from 'react'
import {MathText} from '../components/MathText'
import type {Point} from './Graph'
type Edge={source_id:string;target_id:string;relation_type:'contains'|'prerequisite'|'related'}
type Node={id:string;name:string;point?:Point;children:Node[]}
type Pos={n:Node;x:number;y:number;w:number;color:number;depth:number;side:number;parent?:string}
const palette=['#6589AF','#6E998B','#B0966D','#9485B3','#B2807E','#6099A7']
const fills=['#DCE8F4','#DDEBE3','#F0E4D2','#E7E0F1','#F1E1DE','#DCEBED']
const ink=['#365D87','#426F60','#896A3C','#715D95','#925E5D','#487B87']
export default function MindMap({points,edges,subject,selected,focus,onSelect,onFocus,onReset}:{points:Point[];edges:Edge[];subject:string;selected:string;focus:string;onSelect:(id:string)=>void;onFocus:(id:string)=>void;onReset:()=>void}){
 const [fold,setFold]=useState<string[]>([]),[scale,setScale]=useState(1),[pan,setPan]=useState({x:0,y:0}),[relations,setRelations]=useState(false)
 const pointer=useRef<{id:number;x:number;y:number;px:number;py:number;unitX:number;unitY:number}|null>(null)
 const host=useRef<HTMLDivElement>(null)
 const layout=useMemo(()=>{
  const nodes=new Map(points.map(p=>[p.id,{id:p.id,name:p.name,point:p,children:[]} as Node]))
  const childIds=new Set<string>()
  for(const e of edges){if(e.relation_type!=='contains')continue;const a=nodes.get(e.source_id),b=nodes.get(e.target_id);if(a&&b&&!childIds.has(b.id)){a.children.push(b);childIds.add(b.id)}}
  const root:Node=nodes.get(focus)??{id:'root',name:subject||'全部知识标签',children:[]}
  if(!nodes.has(focus)){
   const chapters=new Map<string,Node>()
   for(const n of nodes.values()){if(childIds.has(n.id))continue;const name=subject?(n.point?.chapter||'未分类'):[n.point?.subject,n.point?.chapter].filter(Boolean).join(' / ')||'未分类';let ch=chapters.get(name);if(!ch){ch={id:'chapter:'+name,name,children:[]};chapters.set(name,ch);root.children.push(ch)}ch.children.push(n)}
  }
  const positions:Pos[]=[]
  const width=(n:Node,depth:number)=>Math.min(250,Math.max(depth===0?148:95,Array.from(n.name).length*15+26))
  const children=(n:Node)=>fold.includes(n.id)?[]:n.children
  function height(n:Node,depth=0):number{return depth>=40?52:Math.max(52,children(n).reduce((s,c)=>s+height(c,depth+1),0))}
  function place(n:Node,side:number,depth:number,y:number,color:number,parent?:string){const w=width(n,depth),x=side*depth*250-w/2;positions.push({n,x,y,w,color,depth,side,parent});if(depth>=40)return;const ch=children(n);let top=y-ch.reduce((s,c)=>s+height(c,depth+1),0)/2;for(const c of ch){const h=height(c,depth+1);place(c,side,depth+1,top+h/2,color,n.id);top+=h}}
  positions.push({n:root,x:-width(root,0)/2,y:0,w:width(root,0),color:0,depth:0,side:1})
  for(const side of [-1,1]){const branches=children(root).map((n,i)=>({n,i})).filter(x=>(x.i%2===0?-1:1)===side);let top=-branches.reduce((s,b)=>s+height(b.n)+38,0)/2;for(const {n,i} of branches){const h=height(n);place(n,side,1,top+h/2,i%palette.length,root.id);top+=h+38}}
  const x0=Math.min(-400,...positions.map(p=>p.x-30)),x1=Math.max(400,...positions.map(p=>p.x+p.w+30)),y0=Math.min(-260,...positions.map(p=>p.y-45)),y1=Math.max(260,...positions.map(p=>p.y+45))
  return {positions,x0,x1,y0,y1}
 },[points,edges,subject,focus,fold])
 const {positions,x0,x1,y0,y1}=layout, byId=new Map(positions.map(p=>[p.n.id,p])),w=x1-x0,h=y1-y0
 function fit(){setScale(1);setPan({x:0,y:0})}
 function toggle(id:string){setFold(v=>v.includes(id)?v.filter(x=>x!==id):[...v,id])}
 return <section className="panel galaxy-panel mindmap-panel" ref={host}><div className="panel-heading mindmap-tools"><div className="button-row"><button onClick={()=>setFold([])}>展开全部</button><button onClick={()=>setFold(positions.filter(p=>p.depth===1).map(p=>p.n.id))}>折叠分支</button><button aria-pressed={relations} onClick={()=>setRelations(v=>!v)}>关系显示</button>{focus&&<button onClick={()=>{onReset();fit()}}>返回总览</button>}</div></div><div className="mindmap-canvas"><svg aria-label="知识标签思维导图" viewBox={[(x0+x1)/2-w/scale/2+pan.x,(y0+y1)/2-h/scale/2+pan.y,w/scale,h/scale].join(' ')} onPointerDown={e=>{if((e.target as Element).closest('[data-mind-node]'))return;const b=e.currentTarget.getBoundingClientRect();pointer.current={id:e.pointerId,x:e.clientX,y:e.clientY,px:pan.x,py:pan.y,unitX:w/scale/b.width,unitY:h/scale/b.height};e.currentTarget.setPointerCapture(e.pointerId);if(e.target===e.currentTarget)onSelect('')}} onPointerMove={e=>{const p=pointer.current;if(p?.id===e.pointerId)setPan({x:p.px-(e.clientX-p.x)*p.unitX,y:p.py-(e.clientY-p.y)*p.unitY})}} onPointerUp={()=>{pointer.current=null}} onPointerCancel={()=>{pointer.current=null}} onWheel={e=>{if(e.ctrlKey||e.metaKey)setScale(v=>Math.max(.4,Math.min(4,v*(e.deltaY>0?.9:1.1))))}}>
 {positions.map(p=>{const a=p.parent?byId.get(p.parent):undefined;if(!a)return null;const start=p.side===1?a.x+a.w:a.x,end=p.side===1?p.x:p.x+p.w,mid=(start+end)/2;return <path key={'line:'+p.n.id} d={'M'+start+' '+a.y+' C'+mid+' '+a.y+' '+mid+' '+p.y+' '+end+' '+p.y} stroke={palette[p.color]} strokeWidth={p.depth===1?3.5:1.8} fill="none" strokeLinecap="round"/>})}
 {relations&&edges.filter(e=>e.relation_type!=='contains').map(e=>{const a=byId.get(e.source_id),b=byId.get(e.target_id);return a&&b?<path key={e.source_id+e.target_id+e.relation_type} d={'M'+(a.x+a.w/2)+' '+a.y+' Q0 '+((a.y+b.y)/2-35)+' '+(b.x+b.w/2)+' '+b.y} stroke={e.relation_type==='related'?'#9584B4':'#B0966D'} strokeWidth="1.5" strokeDasharray="5 5" fill="none"/>:null})}
 {positions.map(p=><g key={p.n.id} data-mind-node="" role="button" tabIndex={0} aria-label={p.n.name} onClick={()=>p.n.point?onSelect(p.n.id):toggle(p.n.id)} onDoubleClick={()=>{if(p.n.point){onFocus(p.n.id);fit()}}} onKeyDown={e=>{if(e.key==='Enter')p.n.point?onSelect(p.n.id):toggle(p.n.id)}}><rect x={p.x} y={p.y-19} width={p.w} height="38" rx={p.depth===0?12:7} fill={p.depth===0?'#2F4A6B':p.depth===1?fills[p.color]:'var(--surface)'} stroke={p.n.id===selected?'var(--highlight)':p.depth===0?'#2F4A6B':'transparent'} strokeWidth="2"/>{p.depth>1&&<path d={'M'+p.x+' '+(p.y+18)+'h'+p.w} stroke={palette[p.color]} strokeWidth="1.5"/>}<foreignObject x={p.x+7} y={p.y-17} width={p.w-14} height="34"><div className="mindmap-label" style={{color:p.depth===0?'#fff':ink[p.color],fontWeight:p.depth<2?600:400,fontSize:p.depth===0?17:13}}><MathText compact content={p.n.name}/></div></foreignObject><title>{p.n.name}</title>{p.n.children.length>0&&p.depth>0&&<g role="button" tabIndex={0} aria-label={(fold.includes(p.n.id)?'展开 ':'折叠 ')+p.n.name} onClick={e=>{e.stopPropagation();toggle(p.n.id)}} onKeyDown={e=>{if(e.key==='Enter'){e.stopPropagation();toggle(p.n.id)}}}><circle cx={p.side===1?p.x+p.w+9:p.x-9} cy={p.y} r="7" fill="var(--surface)" stroke={palette[p.color]}/><text x={p.side===1?p.x+p.w+9:p.x-9} y={p.y+4} textAnchor="middle" fontSize="12" fill={palette[p.color]}>{fold.includes(p.n.id)?'+':'−'}</text></g>}</g>)}
 </svg>{!points.length&&<p className="graph-empty">暂无知识标签，请新建或录入知识标签。</p>}</div><div className="button-row mindmap-bottom"><button aria-label="缩小图谱" onClick={()=>setScale(v=>Math.max(.4,v-.2))}>−</button><small>{Math.round(scale*100)}%</small><button aria-label="放大图谱" onClick={()=>setScale(v=>Math.min(4,v+.2))}>＋</button><button onClick={fit}>适应画布</button><button onClick={()=>{if(document.fullscreenElement)void document.exitFullscreen();else void host.current?.requestFullscreen?.()}}>全屏查看</button></div></section>
}
