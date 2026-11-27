import {useEffect,useState,useRef} from 'react'
import {api} from '../auth'
import {MathText} from './MathText'
import {ResourceMultiSelect,ResourceExcerpt,ResourceSections,ResourcePagination,appendResourceFilters,type ResourceEntry} from './ResourceComponents'
import {Icon} from './Icon'
import {WorkspaceFeedback} from './WorkspaceFeedback'
import {confirmAction} from './WorkspaceConfirm'
import {useWorkspaceBack,useWorkspaceGuard} from './WorkspaceNavigation'
import type {R} from '../pages/DocWork'
import './ManualWordWork.css'
import './AssemblyPicker.css'
type Kind='paper'|'handout'|'textbook'
type Entry=ResourceEntry
type Item=R&{knowledge_points?:{id:string;name:string}[]}
const size=20,names={paper:'试卷',handout:'讲义',textbook:'教材'}
export default function AssemblyPicker({kind,subjects,existing,occupied,append,busy,onConfirm,onCancel}:{kind:Kind;subjects:string[];existing:string[];occupied:number;append:boolean;busy:boolean;onConfirm:(items:R[],title:string)=>void;onCancel?:()=>void}){
 const [bank,setBank]=useState<'question'|'knowledge'>('question'),[q,setQ]=useState(''),[subject,setSubject]=useState(''),[type,setType]=useState(''),[difficulty,setDifficulty]=useState(''),[chapter,setChapter]=useState(''),[origin,setOrigin]=useState(''),[originChapter,setOriginChapter]=useState(''),[sources,setSources]=useState<Entry[]>([]),[points,setPoints]=useState<Entry[]>([]),[related,setRelated]=useState(false),[video,setVideo]=useState(''),[usage,setUsage]=useState(''),[unit,setUnit]=useState(''),[advanced,setAdvanced]=useState(false),[chapters,setChapters]=useState<string[]>([]),[page,setPage]=useState(0),[items,setItems]=useState<Item[]>([]),[total,setTotal]=useState(0),[cart,setCart]=useState<Item[]>([]),[title,setTitle]=useState(''),[loading,setLoading]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0),[active,setActive]=useState<Item>(),[pinned,setPinned]=useState(false),[showCart,setShowCart]=useState(false),[sourceInfo,setSourceInfo]=useState<unknown[]>([]),[sourceError,setSourceError]=useState(''),[position,setPosition]=useState({left:0,top:0})
 const hoverTimer=useRef<number|undefined>(undefined),closeTimer=useRef<number|undefined>(undefined)
 const hasFilters=Boolean(q||subject||chapter||origin||originChapter||sources.length||points.length||usage||(bank==='question'?(type||difficulty||video):unit))
 const available=Math.max(0,200-occupied),selected=new Set(cart.map(r=>r.id)),included=new Set(existing)
 useEffect(()=>{const ctl=new AbortController();setLoading(true);setError('');setItems([]);setTotal(0);setActive(undefined);setPinned(false)
  const query=new URLSearchParams({kind:bank,q,subject,chapter,limit:String(size),offset:String(page*size)})
  if(bank==='question'){if(type)query.set('question_type',type);if(difficulty)query.set('difficulty',difficulty);if(video)query.set('video_state',video)}else if(unit)query.set('unit_type',unit)
  if(origin)query.set('origin_type',origin);if(originChapter)query.set('origin_chapter',originChapter);if(usage)query.set('usage_state',usage)
  appendResourceFilters(query,sources,points,related)
  const timer=window.setTimeout(()=>api<{items:Item[];total:number}>('/resources?'+query,{signal:ctl.signal}).then(r=>{if(!ctl.signal.aborted){setItems(r.items);setTotal(r.total)}}).catch(e=>{if(!ctl.signal.aborted)setError(e.message||'资源读取失败')}).finally(()=>{if(!ctl.signal.aborted)setLoading(false)}),180)
  return()=>{window.clearTimeout(timer);ctl.abort()}
 },[bank,q,subject,type,difficulty,chapter,origin,originChapter,sources,points,related,video,usage,unit,page,retry])
 useEffect(()=>{const c=new AbortController();api<{chapter:string}[]>('/resources/chapters?kind='+bank+'&subject='+encodeURIComponent(subject),{signal:c.signal}).then(r=>{if(!c.signal.aborted)setChapters(Array.isArray(r)?[...new Set(r.map(x=>x.chapter).filter(Boolean))]:[])}).catch(()=>{});return()=>c.abort()},[bank,subject])
 useEffect(()=>{if(!active)return;const c=new AbortController();setSourceInfo([]);setSourceError('');api<{items:unknown[]}>('/resources/'+active.id+'/sources',{signal:c.signal}).then(r=>{if(!c.signal.aborted)setSourceInfo(Array.isArray(r.items)?r.items:[])}).catch(e=>{if(!c.signal.aborted)setSourceError(e.message)});return()=>c.abort()},[active?.id])
 useEffect(()=>{const listener=(e:KeyboardEvent)=>{if(e.key==='Escape'){setActive(undefined);setPinned(false);setShowCart(false)}};window.addEventListener('keydown',listener);return()=>{window.removeEventListener('keydown',listener);window.clearTimeout(hoverTimer.current);window.clearTimeout(closeTimer.current)}},[])
 useWorkspaceGuard({busy,dirty:cart.length>0,message:'选题车尚未确认，离开将清空本次选取。确认离开？'})
 useWorkspaceBack(()=>{if(busy)return true;if(active){setActive(undefined);setPinned(false);return true}if(showCart){setShowCart(false);return true}if(advanced){setAdvanced(false);return true}if(append&&cart.length&&onCancel){void confirmAction('返回编排将清空本次补充选取，确认返回？','返回编排','返回').then(ok=>{if(ok)onCancel()});return true}return false},10)
 async function importCart(){try{const r=await api<{items:(Item&{archived?:boolean})[]}>('/bank/cart');setCart(prev=>[...prev,...r.items.filter(x=>!x.archived&&!included.has(x.id)&&!prev.some(p=>p.id===x.id)).slice(0,Math.max(0,available-prev.length))])}catch(e){setError(e instanceof Error?e.message:'读取清单失败')}}
 async function persistCart(){try{const c=await api<{revision:number;ids:string[]}>('/bank/cart');const ids=Array.from(new Set([...c.ids,...cart.filter(r=>r.kind==='question').map(r=>r.id)]));if(ids.length>200)throw Error('服务器选题清单最多200道');await api('/bank/cart',{method:'PUT',body:JSON.stringify({revision:c.revision,ids})});setError('题目已保存到服务器选题清单')}catch(e){setError(e instanceof Error?e.message:'保存清单失败')}}
 const toggle=(r:Item)=>setCart(prev=>prev.some(x=>x.id===r.id)?prev.filter(x=>x.id!==r.id):included.has(r.id)||prev.length>=available?prev:[...prev,r])
 function reveal(r:Item,el:HTMLElement,pin:boolean){window.clearTimeout(hoverTimer.current);window.clearTimeout(closeTimer.current);const rect=el.getBoundingClientRect();setPosition({left:Math.max(12,Math.min(rect.left+20,window.innerWidth-512)),top:Math.max(12,Math.min(rect.bottom+4,window.innerHeight-390))});setActive(r);setPinned(pin)}
 function leave(){window.clearTimeout(hoverTimer.current);if(!pinned)closeTimer.current=window.setTimeout(()=>setActive(undefined),200)}
 function choose(label:string,value:string,onChange:(v:string)=>void,options:{v:string;t:string}[]){return <select aria-label={label} value={value} onChange={e=>{onChange(e.target.value);setPage(0)}}><option value="">全部{label}</option>{options.map(o=><option key={o.v} value={o.v}>{o.t}</option>)}</select>}
 const opts=(a:string[])=>a.map(v=>({v,t:v}))
 function move(i:number,n:number){setCart(old=>{const a=[...old],j=i+n;if(j>=0&&j<a.length)[a[i],a[j]]=[a[j],a[i]];return a})}
 return <section className="assembly-picker compact-assembly">
 <header className="assembly-heading"><div><h2>{append?'补充资源':kind==='paper'?'选择试卷题目':'选择'+names[kind]+'资源'}</h2><small>确认选取后进入编排</small></div></header>
 <div className="assembly-grid"><div className="assembly-library">
 <div className="assembly-filters">{kind!=='paper'&&<div className="assembly-bank-tabs"><button aria-pressed={bank==='question'} onClick={()=>{setBank('question');setPage(0);setChapter('');setActive(undefined);setPinned(false)}}>题库</button><button aria-pressed={bank==='knowledge'} onClick={()=>{setBank('knowledge');setPage(0);setChapter('');setActive(undefined);setPinned(false)}}>知识库</button></div>}
 <div className="assembly-search-row"><div className="assembly-search"><Icon name="search" size={17}/><input aria-label="搜索题库" placeholder="搜索题目、知识标签或来源" value={q} onChange={e=>{setQ(e.target.value);setPage(0)}}/></div><button className="assembly-filter-toggle" aria-expanded={advanced} onClick={()=>setAdvanced(v=>!v)}><Icon name="settings" size={15}/> 筛选{[origin,originChapter,video,usage].filter(Boolean).length+sources.length+points.length||''}</button></div>
 <div className="assembly-common-filters">
 {choose('科目',subject,v=>{setSubject(v);setChapter('');setPoints([])},opts(subjects))}
 {choose('知识章节',chapter,setChapter,opts(chapters))}
 {bank==='question'?<>{choose('题型',type,setType,opts(['选择题','单选题','多选题','填空题','综合题']))}{choose('难度',difficulty,setDifficulty,opts(['简单','中等','困难']))}</>:choose('知识点类型',unit,setUnit,opts(['定义','定理','公式','性质','推论','方法']))}
 </div>
 {advanced&&<div className="assembly-advanced"><div className="assembly-advanced-heading"><strong>高级筛选</strong><button onClick={()=>setAdvanced(false)}>收起</button></div>
 {choose('来源类型',origin,v=>{setOrigin(v);setSources([])},[{v:'textbook',t:'教材'},{v:'handout',t:'讲义'},{v:'exam',t:'试卷'},{v:'other',t:'其他'}])}
 <ResourceMultiSelect label="具体来源" path={'/resources?kind=source&source_type='+origin} chosen={sources} setChosen={v=>{setSources(v);setPage(0)}}/>
 <input aria-label="来源章节" placeholder="原资料章节（精确名称）" value={originChapter} onChange={e=>{setOriginChapter(e.target.value);setPage(0)}}/>
 <ResourceMultiSelect label="知识标签" path={'/knowledge/points?subject='+encodeURIComponent(subject)} chosen={points} setChosen={v=>{setPoints(v);setPage(0)}}/>
 <label><input type="checkbox" checked={related} onChange={e=>{setRelated(e.target.checked);setPage(0)}}/>包含下级、相关及前置知识标签</label>
 {bank==='question'&&choose('视频状态',video,setVideo,[{v:'made',t:'已有确认成片'},{v:'unmade',t:'未有确认成片'}])}
 {choose('使用记录',usage,setUsage,[{v:'used',t:'已用于教学资料'},{v:'unused',t:'未使用'}])}
 <button onClick={()=>{setQ('');setSubject('');setChapter('');setType('');setDifficulty('');setOrigin('');setSources([]);setOriginChapter('');setPoints([]);setRelated(false);setVideo('');setUsage('');setUnit('');setPage(0)}}>重置筛选</button></div>}
 </div>
 <div className="assembly-results-head"><small>{loading?'正在读取…':error?'读取失败':'共 '+total+' 项'}</small>{!loading&&items.length>0&&<button disabled={busy||loading||!items.some(r=>!included.has(r.id)&&!selected.has(r.id))||cart.length>=available} onClick={()=>setCart(prev=>[...prev,...items.filter(r=>!included.has(r.id)&&!prev.some(x=>x.id===r.id)).slice(0,Math.max(0,available-prev.length))])}>加入本页</button>}</div>
 {!items.length&&<WorkspaceFeedback className="assembly-empty" state={loading?'loading':error?'error':'empty'} title={loading?'正在读取…':error?'资源读取失败':hasFilters?'暂无符合条件的资源':bank==='question'?'题库暂无题目':'知识库暂无知识点'} detail={error||(!loading?(hasFilters?'请调整搜索或筛选条件':'请先通过资料录入添加资源'):undefined)} onRetry={()=>setRetry(v=>v+1)}/>}
 {items.length>0&&<div className="compact-resource-list">{items.map(r=><article key={r.id} className="assembly-result compact-result" onPointerEnter={e=>{if(e.pointerType==='mouse'&&!pinned){const el=e.currentTarget;window.clearTimeout(closeTimer.current);hoverTimer.current=window.setTimeout(()=>reveal(r,el,false),220)}}} onPointerLeave={leave}><button className="compact-resource-main" onClick={e=>reveal(r,e.currentTarget,true)}><span className="compact-resource-summary"><ResourceExcerpt resource={r}/></span><small>{r.subject||'未分类'} · {r.kind==='question'?r.question_type||'题目':r.unit_type||'知识点'}{r.difficulty?' · '+r.difficulty:''}</small></button><button aria-pressed={selected.has(r.id)} disabled={busy||included.has(r.id)||(!selected.has(r.id)&&cart.length>=available)} onClick={()=>toggle(r)}>{included.has(r.id)?'已在文档':selected.has(r.id)?'✓ 已选':'＋ 选入'}</button></article>)}</div>}
 <ResourcePagination page={page} size={size} total={total} loading={loading} onPage={setPage} className="assembly-pages" showSingle={false}/></div>
 {showCart&&<div className="assembly-cart-backdrop" onClick={()=>setShowCart(false)}/>}
 <aside className={'assembly-cart '+(showCart?'cart-open':'')} aria-label="选题车"><div className="assembly-cart-heading"><strong>选题车（{cart.length}）</strong><button disabled={busy} onClick={()=>void importCart()}>导入选题清单</button><button disabled={busy||!cart.some(r=>r.kind==='question')} onClick={()=>void persistCart()}>保存选题清单</button><button disabled={busy||!cart.length} onClick={()=>setCart([])}>清空</button><button className="assembly-mobile-only" aria-label="关闭选题车" onClick={()=>setShowCart(false)}><Icon name="close" size={18}/></button></div>
 {!append&&<label>文档名称<input aria-label="文档名称" placeholder={'未命名'+names[kind]} value={title} maxLength={200} onChange={e=>setTitle(e.target.value)}/></label>}
 {!cart.length&&<div className="assembly-cart-empty"><Icon name="resources" size={28}/><small>尚未选择资源</small><span>选取后将在这里显示，跨页保留。</span></div>}
 {cart.map((r,i)=><div key={r.id} className="assembly-cart-item"><button className="compact-resource-main" onClick={e=>reveal(r,e.currentTarget,true)}><small>{i+1}. {r.code}</small><span className="compact-resource-summary"><ResourceExcerpt resource={r}/></span></button><button disabled={!i} onClick={()=>move(i,-1)} aria-label="上移">↑</button><button disabled={i===cart.length-1} onClick={()=>move(i,1)} aria-label="下移">↓</button><button disabled={busy} aria-label={'移除 '+r.code} onClick={()=>toggle(r)}>×</button></div>)}
 <button className="primary" disabled={busy||!cart.length} onClick={()=>onConfirm(cart,title.trim()||'未命名'+names[kind])}>{busy?'处理中…':append?'加入 Word 工作台':'进入 Word 工作台'}</button><small className="muted">最多 200 个文档块；原资源不会被修改。</small></aside></div>
 <div className="assembly-cart-bar assembly-mobile-only"><span><Icon name="works" size={19}/> 已选 <strong>{cart.length}</strong> 项</span><button className="primary assembly-cart-toggle" onClick={()=>setShowCart(true)}>查看选题车 <Icon name="chevron" size={14}/></button></div>
 {active&&<><div className={'assembly-preview-backdrop '+(pinned?'pinned':'')} onClick={()=>{setActive(undefined);setPinned(false)}}/><section key={active.id} role="dialog" aria-label="资源详情" className="assembly-preview" style={position} onPointerEnter={()=>window.clearTimeout(closeTimer.current)} onPointerLeave={leave}><header><strong>{active.kind==='question'?'题目详情':'知识点详情'}</strong><button aria-label="关闭详情" onClick={()=>{setActive(undefined);setPinned(false)}}>×</button></header><div className="assembly-preview-body"><ResourceSections resource={active} showKnowledge/><details><summary>题目来源</summary>{sourceError?<p>{sourceError}</p>:sourceInfo.length?sourceInfo.map((s,i)=>{const v=s as {source?:{title?:string};title?:string;source_title?:string;chapter?:string;original_question_number?:string};return <p key={i}><MathText compact content={v.source?.title||v.source_title||v.title||'关联来源'}/> {v.chapter} {v.original_question_number}</p>}):<p className="muted">暂无关联来源</p>}</details></div><footer><button className="primary" disabled={busy||included.has(active.id)||(!selected.has(active.id)&&cart.length>=available)} onClick={()=>toggle(active)}>{included.has(active.id)?'已在文档':selected.has(active.id)?'移出选题车':'加入选题车'}</button></footer></section></>}
 </section>
}
