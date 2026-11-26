import {MathChoice} from '../components/MathText'
import {useEffect,useRef,useState} from 'react'
import {Link,useSearchParams} from 'react-router-dom'
import {api} from '../auth'
import ManualIntakeCards from '../components/ManualIntakeCards'
import AssemblyPicker from '../components/AssemblyPicker'
import type {CardPanel} from '../components/MobileDocWork'
export type Kind='heading'|'text'|'question'|'knowledge'|'reference'|'image'|'pagebreak'
export type R={id:string;code:string;kind:string;revision?:number;title:string;content:string;answer:string;solution:string;analysis:string;proof:string;chapter:string;subject?:string;question_type?:string;difficulty?:string;tags?:string[]}
export type Block={edit_reference_revision?:number|null;heading_level?:1|2|null;score?:number;uid:string;kind:Kind;title:string;content:string;answer:string;solution:string;analysis:string;proof:string;subject?:string|null;knowledge_tags?:string[];reuse_resource_id?:string|null;reuse_revision?:number|null;reuse_code?:string;fork_from_id?:string|null;chapter:string;question_type:string;difficulty?:string;unit_type:string;resource_id:string|null;file_id:string|null;width:number;snapshot?:R}
type Summary={id:string;title:string;kind:'intake'|'handout'|'paper'|'textbook';subject:string;source_id:string|null;revision:number;archived:boolean}
export type Doc=Summary&{blocks:Block[]}

type Composition='paper'|'handout'|'textbook'
const make=(kind:Kind):Block=>({uid:crypto.randomUUID(),kind,title:'',content:'',answer:'',solution:'',analysis:'',proof:'',chapter:'',question_type:'',unit_type:'',resource_id:null,file_id:null,width:100})
const recoveryKey=(id:string)=>'wg-doc-recovery:'+id
function removeRecovery(id:string){try{sessionStorage.removeItem(recoveryKey(id))}catch{}}
export default function DocWork({intake=false,docKind}:{intake?:boolean;docKind?:Composition}){
 const kind=docKind??'paper',queryKind=intake?'intake':kind
 const [params,setParams]=useSearchParams(),requested=params.get('doc')
 const [narrow,setNarrow]=useState(()=>window.matchMedia('(max-width: 900px)').matches),[layout,setLayout]=useState<'auto'|'cards'|'word'>('auto'),[cardPanel,setCardPanel]=useState<CardPanel>('card')
 const cardMode=intake&&(layout==='cards'||(layout==='auto'&&narrow))
 const [docs,setDocs]=useState<Summary[]>([]),[total,setTotal]=useState(0),[page,setPage]=useState(0),[doc,setDoc]=useState<Doc>(),[selected,setSelected]=useState(''),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[archived,setArchived]=useState(false),[subjects,setSubjects]=useState<string[]>([])
 const [picker,setPicker]=useState<'new'|'append'|null>(!intake&&!requested?'new':null)
 const running=useRef(false)
 const block=doc?.blocks.find(b=>b.uid===selected),locked=busy||Boolean(doc?.archived)
 const pending=!!doc?.blocks.some(b=>b.kind==='question'||b.kind==='knowledge'||b.edit_reference_revision)
 useEffect(()=>{const media=window.matchMedia('(max-width: 900px)');const change=()=>setNarrow(media.matches);change();media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[])
 useEffect(()=>{if(doc?.blocks.length&&!doc.blocks.some(b=>b.uid===selected))setSelected(doc.blocks[0].uid)},[doc?.blocks,selected])
 async function refresh(){const r=await api<{items:Summary[];total:number}>('/documents?'+new URLSearchParams({archived:String(archived),limit:'30',offset:String(page*30),kind:queryKind}));setDocs(r.items.filter(d=>d.kind===queryKind));setTotal(r.total)}
 useEffect(()=>{void refresh().catch(e=>setMessage(e.message))},[archived,page,queryKind])
 useEffect(()=>{const c=new AbortController();api<string[]>('/resources/subjects',{signal:c.signal}).then(setSubjects).catch(e=>{if(!c.signal.aborted)setMessage(e.message)});return()=>c.abort()},[])
 useEffect(()=>{if(requested&&requested!==doc?.id)void open(requested,false)},[requested])
 useEffect(()=>{if(!dirty||!doc)return;try{sessionStorage.setItem(recoveryKey(doc.id),JSON.stringify(doc))}catch{setMessage('浏览器草稿缓存空间不足，请立即保存到服务器。')}},[doc,dirty])
 useEffect(()=>{if(!dirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[dirty])
 function choose(uid:string){setCardPanel('card');setSelected(uid)}
 function update(p:Partial<Doc>){setDoc(d=>d&&({...d,...p}));setDirty(true)}
 function editBlock(p:Partial<Block>){if(!doc||!block||locked)return;setDoc(d=>d&&({...d,blocks:d.blocks.map(b=>b.uid===selected?{...b,...p}:b)}));setDirty(true)}
 function insert(b:Block){if(!doc||doc.archived)return;if(doc.blocks.length>=200){setMessage('文档已达到 200 个条目，请拆分。');return}const i=doc.blocks.findIndex(x=>x.uid===selected);const bs=[...doc.blocks];bs.splice(i<0?bs.length:i+1,0,b);update({blocks:bs});choose(b.uid)}
 function move(delta:number){if(!doc||!block||locked)return;const i=doc.blocks.indexOf(block),j=i+delta;if(j<0||j>=doc.blocks.length)return;const bs=[...doc.blocks];[bs[i],bs[j]]=[bs[j],bs[i]];update({blocks:bs})}
 function reorder(uid:string,target:string){if(!doc||locked||uid===target)return;const from=doc.blocks.findIndex(b=>b.uid===uid),to=doc.blocks.findIndex(b=>b.uid===target);if(from<0||to<0)return;const bs=[...doc.blocks];const [item]=bs.splice(from,1);bs.splice(to,0,item);update({blocks:bs});choose(uid)}
 function removeBlock(){if(!doc||!block||locked||!window.confirm('移除此条目？不会删除题库资源。'))return;const i=doc.blocks.indexOf(block),next=doc.blocks.filter(b=>b.uid!==block.uid);update({blocks:next});choose(next[Math.min(i,next.length-1)]?.uid??'')}
 async function act(fn:()=>Promise<void>){if(running.current)return;running.current=true;setBusy(true);setMessage('');try{await fn()}catch(e){setMessage(e instanceof Error?e.message:'操作失败')}finally{running.current=false;setBusy(false)}}
 function syncUrl(id:string){setParams({doc:id},{replace:true})}
 async function open(id:string,changeUrl=true){if(dirty&&!window.confirm('当前有未保存修改，切换后可在本标签页恢复草稿，确认切换？'))return;await act(async()=>{const r=await api<Doc>('/documents/'+encodeURIComponent(id));if(r.kind!==queryKind)throw Error('文档类型与当前工作台不一致');let recovered:Doc|undefined;try{const raw=sessionStorage.getItem(recoveryKey(id));if(raw){const candidate=JSON.parse(raw) as Doc;if(candidate.id===r.id&&candidate.kind===r.kind&&candidate.revision===r.revision&&!r.archived){if(window.confirm('发现本标签页未保存草稿，是否恢复？'))recovered=candidate;else removeRecovery(id)}else{setMessage('本地草稿版本已过期，未覆盖服务器。');if(window.confirm('下载恢复草稿 JSON，供手工核对？')){const url=URL.createObjectURL(new Blob([raw],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='document-recovery-'+id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}}}}catch{}setDoc(recovered??r);choose('');setDirty(Boolean(recovered));setPicker(null);if(changeUrl)syncUrl(id)})}
 function newComposition(){if(dirty&&!window.confirm('当前有未保存修改，确认先打开新建选题？'))return;setPicker('new');setMessage('')}
 async function confirmSelection(items:R[],title:string){
  await act(async()=>{if(intake||!picker)return
   const chosen=items.filter((r,i)=>['question','knowledge'].includes(r.kind)&&(kind!=='paper'||r.kind==='question')&&items.findIndex(v=>v.id===r.id)===i)
   if(!chosen.length)throw Error('请至少选入一项题库资源')
   if(picker==='append'){
    if(!doc||doc.archived)throw Error('请先打开可编辑文档')
    const known=new Set(doc.blocks.map(b=>b.resource_id))
    const blocks=chosen.filter(r=>!known.has(r.id)).map(r=>({...make('reference'),resource_id:r.id,snapshot:r}))
    if(!blocks.length)throw Error('所选资源已在文档中')
    if(doc.blocks.length+blocks.length>200)throw Error('文档最多 200 个条目，请拆分')
    update({blocks:[...doc.blocks,...blocks]});choose(blocks[0].uid);setPicker(null);return
   }
   if(chosen.length>200)throw Error('文档最多 200 个条目，请拆分')
   const blocks=chosen.map(r=>({...make('reference'),resource_id:r.id,snapshot:r}))
   const saved=await api<Doc>('/documents',{method:'POST',body:JSON.stringify({kind,title,subject:'',source_id:null,blocks})})
   if(saved.kind!==kind)throw Error('服务器返回的文档类型不正确')
   setDoc(saved);choose(saved.blocks[0]?.uid??'');setDirty(false);setPicker(null);syncUrl(saved.id);window.dispatchEvent(new Event('wg-recent-changed'));await refresh()
  })
 }
 async function save(){await act(async()=>{if(!doc)throw Error('请先打开文档');if(!dirty&&(!intake||!pending))return;const saved=await api<Doc>('/documents/'+doc.id+(intake?'/manual-save':''),{method:intake?'POST':'PUT',body:JSON.stringify(doc)});setDoc(saved);removeRecovery(saved.id);setDirty(false);setMessage(intake?'已保存并直接入库':'编排已保存到服务器');window.dispatchEvent(new Event('wg-recent-changed'));await refresh()})}
 useEffect(()=>{const handle=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'&&doc){e.preventDefault();if(!picker&&!busy&&!doc.archived&&(dirty||intake&&pending))void save()}};window.addEventListener('keydown',handle);return()=>window.removeEventListener('keydown',handle)},[doc,dirty,busy,picker,pending])
 async function image(file:File){if(!doc||locked)return;await act(async()=>{const r=await fetch('/api/files?name='+encodeURIComponent(file.name),{method:'POST',credentials:'same-origin',body:file});if(!r.ok)throw Error('图片上传失败');const f=await r.json() as {id:string;previewable:boolean};if(!f.previewable)throw Error('请选择支持的图片');insert({...make('image'),file_id:f.id,title:file.name})})}
 async function archiveDoc(){if(!doc||dirty)return;await act(async()=>{setDoc(await api<Doc>('/documents/'+doc.id+(doc.archived?'/restore':'/archive'),{method:'POST'}));await refresh()})}
 const title=intake?'录入工作台':kind==='paper'?'组卷':kind==='handout'?'组讲义':'组教材'
 return <div className={'doc-work '+(cardMode?'card-mode ':'')+(doc&&!picker?'doc-open ':'')+'density-标准'}>
  <header className="doc-work-heading"><div>{intake&&<Link className="text-link" to="/intake" onClick={e=>{if(dirty&&!window.confirm('尚有未保存修改，确认返回？'))e.preventDefault()}}>← 录入工作台</Link>}<h1>{title}</h1><p className="muted">{intake?'顺序整理 · 局部公式编辑 · 题库查重':picker?'题库选题 → Word 编排 → 预览保存':'Word 编排 · 顺序整理 · 预览保存'}</p></div>{intake&&<button className="doc-mode-switch" disabled={busy} onClick={()=>{setLayout(cardMode?'word':'cards');setCardPanel('card')}}>{cardMode?'切换 Word 版':'切换卡片版'}</button>}</header>
  <div className="doc-selector">{intake?<Link className="button-link primary" to="/intake?mode=document" onClick={e=>{if(dirty&&!window.confirm('有未保存修改，确认离开？'))e.preventDefault()}}>新建来源资料</Link>:<button className="primary" disabled={busy} onClick={newComposition}>新建{kind==='paper'?'试卷':kind==='handout'?'讲义':'教材'}</button>}<MathChoice label="打开文档" value={doc?.id??''} disabled={busy} onChange={v=>{if(v)void open(v)}} options={[...(doc&&!docs.some(d=>d.id===doc.id)?[{value:doc.id,label:doc.title}]:[]),...docs.map(d=>({value:d.id,label:d.title}))]} placeholder="打开已有文档"/><button disabled={page===0||busy} onClick={()=>setPage(p=>p-1)}>上一批</button><button disabled={(page+1)*30>=total||busy} onClick={()=>setPage(p=>p+1)}>下一批</button><label><input type="checkbox" checked={archived} onChange={e=>{setArchived(e.target.checked);setPage(0)}}/> 已归档</label></div>
  {message&&<p role="status" className="notice">{message}</p>}
  {!intake&&picker?<AssemblyPicker key={picker+'-'+(doc?.id??'')} kind={kind} subjects={subjects} existing={picker==='append'?(doc?.blocks??[]).flatMap(b=>b.resource_id?[b.resource_id]:[]):[]} occupied={picker==='append'?doc?.blocks.length??0:0} append={picker==='append'} busy={busy} onConfirm={(items,name)=>void confirmSelection(items,name)} onCancel={doc?()=>setPicker(null):undefined}/>:doc?<ManualIntakeCards key={doc.id} desktop={!cardMode} onPick={!intake?()=>setPicker('append'):undefined} onReorder={reorder} onTitle={name=>update({title:name})} onArchive={()=>void archiveDoc()} onImage={file=>void image(file)} doc={doc} selected={selected} panel={cardPanel} subjects={subjects} dirty={dirty} busy={busy} onPanel={setCardPanel} onSelect={choose} onEdit={editBlock} onAdd={(k,type,level)=>{if(!intake&&(k==='question'||k==='knowledge'))return;insert({...make(k),...(k==='heading'?{heading_level:level??1}:{}),subject:'',chapter:'',question_type:type??''})}} onRemove={removeBlock} onMove={move} onSave={()=>void save()}/>:<p className="muted">{busy?'正在打开文档…':'请选择已有文档或新建资料。'}</p>}
 </div>
}
