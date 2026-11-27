import {useEffect,useRef,useState} from 'react'
import {useLocation,useSearchParams} from 'react-router-dom'
import {api} from '../auth'
import {Icon} from '../components/Icon'
import FinishedMediaPreview from '../components/FinishedMediaPreview'
import {confirmAction} from '../components/WorkspaceConfirm'
import {MathText} from '../components/MathText'
import {WorkspaceLink as Link,useWorkspaceBack} from '../components/WorkspaceNavigation'
import './TeachingWorks.css'

type Work={id:string;title:string;kind:string;subject:string;origin_scope:string;origin_id:string;current_version:number|null;created_at:number;updated_at:number}
type Asset={role:string;filename:string;pages:number;size_bytes:number;media_type:string}
type Version={number:number;created_at:number;files:Asset[]}
type EditContext={origin_scope:string;origin_id:string;kind:string;version:number;edition:{chapter?:string|null;stem?:boolean;answerOnly?:boolean}}
type Detail=Work&{versions:Version[];pending_cover:{filename:string;created_at:number}|null;video?:{project_id:string;cover_file_id:string|null;resource_id:string}}
type Question={uid:string;title:string;content:string;answer:string;solution:string;analysis:string;proof:string;chapter:string}
type Related={items:Question[];total:number;question_count:number;knowledge_points:string[];knowledge_tags:string[];source_count:number;partial_pages:boolean}
const kinds=[['','全部'],['paper','试卷'],['handout','讲义'],['textbook','教材'],['video','视频'],['source','来源文档']]
const label=(kind:string)=>kinds.find(x=>x[0]===kind)?.[1]??'教学文档'
const day=(t:number)=>new Date(t*1000).toLocaleDateString('zh-CN')
const size=(n:number)=>n>=1048576?(n/1048576).toFixed(1)+' MB':Math.max(1,Math.round(n/1024))+' KB'
const fileUrl=(id:string,number:number,role:string)=>'/api/teaching-works/'+encodeURIComponent(id)+'/versions/'+number+'/files/'+encodeURIComponent(role)
const pendingUrl=(id:string)=>'/api/teaching-works/'+encodeURIComponent(id)+'/pending-cover/file'
const errorText=(e:unknown)=>e instanceof Error?e.message:'读取失败'
const pageSize=20

export default function TeachingWorks(){
 const [params,setParams]=useSearchParams(),location=useLocation(),id=params.get('work')??''
 const [q,setQ]=useState(params.get('q')??''),[kind,setKind]=useState(params.get('kind')??''),[subject,setSubject]=useState(''),[scope,setScope]=useState(''),[sort,setSort]=useState('recent')
 const [from,setFrom]=useState(''),[to,setTo]=useState(''),[advanced,setAdvanced]=useState(false),[page,setPage]=useState(0)
 const [rows,setRows]=useState<Work[]>([]),[total,setTotal]=useState(0),[subjects,setSubjects]=useState<string[]>([]),[busy,setBusy]=useState(true),[error,setError]=useState(''),[reload,setReload]=useState(0)
 const [detail,setDetail]=useState<Detail>(),[detailError,setDetailError]=useState(''),[version,setVersion]=useState<number>(),[tab,setTab]=useState('files')
 const [related,setRelated]=useState<Related>(),[relatedError,setRelatedError]=useState(''),[questionPage,setQuestionPage]=useState(0),[questionQuery,setQuestionQuery]=useState('')
 const [menu,setMenu]=useState(''),[preview,setPreview]=useState<{url:string;name:string;video?:boolean;pages?:number;pageUrl?:string}>()
 const [actionBusy,setActionBusy]=useState(false),[actionMessage,setActionMessage]=useState(''),[edit,setEdit]=useState<EditContext>()
 const scroll=useRef(0),returnScroll=useRef(false)
 const activeVersion=(tab==='related'?detail?.versions.find(v=>v.number===version):detail?.versions.find(v=>v.number===detail.current_version))??detail?.versions[0]
 const detailReady=detail?.id===id
 useEffect(()=>{const c=new AbortController();api<string[]>('/teaching-works/subjects',{signal:c.signal}).then(v=>{if(!c.signal.aborted)setSubjects(v)}).catch(()=>{});return()=>c.abort()},[reload])
 useEffect(()=>{
  if(id)return
  const c=new AbortController();setBusy(true);setError('')
  const filters=new URLSearchParams({q,kind,subject,scope,sort,offset:String(page*pageSize),limit:String(pageSize)})
  if(from)filters.set('created_from',String(Math.floor(new Date(from+'T00:00:00').getTime()/1000)))
  if(to){const d=new Date(to+'T00:00:00');d.setDate(d.getDate()+1);filters.set('created_to',String(Math.floor(d.getTime()/1000)))}
  const timer=window.setTimeout(()=>api<{items:Work[];total:number}>('/teaching-works?'+filters,{signal:c.signal}).then(v=>{if(!c.signal.aborted){setRows(v.items);setTotal(v.total);setBusy(false)}}).catch(e=>{if(!c.signal.aborted){setError(errorText(e));setBusy(false)}}),180)
  return()=>{c.abort();window.clearTimeout(timer)}
 },[id,q,kind,subject,scope,sort,from,to,page,reload])
 useEffect(()=>{
  if(id||busy||!returnScroll.current)return
  returnScroll.current=false;requestAnimationFrame(()=>document.querySelector('.main-content')?.scrollTo(0,scroll.current))
 },[id,busy])
 useEffect(()=>{
  setDetail(undefined);setDetailError('');setVersion(undefined);setTab('files');setPreview(undefined);setRelated(undefined);setMenu('');setEdit(undefined);setActionMessage('')
  if(!id)return
  const c=new AbortController()
  api<Detail>('/teaching-works/'+encodeURIComponent(id),{signal:c.signal}).then(v=>{if(!c.signal.aborted){setDetail(v);setVersion(v.current_version??undefined)}}).catch(e=>{if(!c.signal.aborted)setDetailError(errorText(e))})
  return()=>c.abort()
 },[id,reload])
 useEffect(()=>{setQuestionPage(0);setQuestionQuery('');setRelated(undefined);setRelatedError('')},[id,version])
 useEffect(()=>{
  if(!detailReady||tab!=='related'||!activeVersion||!detail)return
  const c=new AbortController();setRelatedError('')
  const query=new URLSearchParams({q:questionQuery,offset:String(questionPage*pageSize),limit:String(pageSize)})
  api<Related>('/teaching-works/'+encodeURIComponent(detail.id)+'/versions/'+activeVersion.number+'/questions?'+query,{signal:c.signal}).then(v=>{if(!c.signal.aborted)setRelated(v)}).catch(e=>{if(!c.signal.aborted)setRelatedError(errorText(e))})
  return()=>c.abort()
 },[detailReady,detail?.id,activeVersion?.number,tab,questionPage,questionQuery])
 function openWork(w:Work){scroll.current=document.querySelector('.main-content')?.scrollTop??0;setMenu('');const p=new URLSearchParams(location.search);p.set('work',w.id);setParams(p)}
 function closeWork(){returnScroll.current=true;const p=new URLSearchParams(location.search);p.delete('work');setParams(p)}
 useWorkspaceBack(()=>{if(preview){setPreview(undefined);return true}if(id){closeWork();return true}return false},20)
 function filter(fn:()=>void){fn();setPage(0);setMenu('')}
 function clear(){filter(()=>{setQ('');setKind('');setSubject('');setScope('');setSort('recent');setFrom('');setTo('')})}
 function openFile(f:Asset,v:Version){if(detail){const url=fileUrl(detail.id,v.number,f.role);setPreview({url,name:f.filename,pages:f.pages,pageUrl:url+'/pages'})}}
 async function restore(v:Version){if(!detail||!detail.current_version||actionBusy)return;if(!await confirmAction('将 V'+v.number+' 恢复为新的正式版本？原制作草稿与已发布内容不变。','恢复历史版本','确认恢复'))return;setActionBusy(true);setActionMessage('');try{await api('/teaching-works/'+encodeURIComponent(detail.id)+'/versions/'+v.number+'/restore',{method:'POST',body:JSON.stringify({expected_version:detail.current_version})});setReload(n=>n+1)}catch(e){setActionMessage(errorText(e))}finally{setActionBusy(false)}}
 async function openEdit(){if(!detail||actionBusy)return;setActionBusy(true);setActionMessage('');try{setEdit(await api<EditContext>('/teaching-works/'+encodeURIComponent(detail.id)+'/edit-context'))}catch(e){setActionMessage(errorText(e))}finally{setActionBusy(false)}}
 const editQuery=edit?new URLSearchParams({from_work:id,...(edit.edition.chapter?{chapter:edit.edition.chapter}:{}),...(edit.edition.stem?{stem:'1'}:{}),...(edit.edition.answerOnly?{answer:'1'}:{})}).toString():''
 if(id)return <div className="finished-works">
  <header className="finished-heading"><button type="button" className="finished-back" onClick={()=>preview?setPreview(undefined):closeWork()}><Icon name="back" size={18}/> {preview?'返回详情':'返回作品列表'}</button><button type="button" onClick={()=>setReload(x=>x+1)}>刷新</button></header>
  {detailError?<p className="inline-error" role="alert">{detailError}</p>:!detailReady||!detail?<p className="muted">正在读取作品…</p>:<>
   <h1><MathText compact content={detail.title}/></h1>
   <p className="muted">{label(detail.kind)} · {detail.kind==='video'?'引擎已归档':detail.current_version?'V'+detail.current_version:'待匹配正文'} · {day(detail.updated_at)}</p>
   {actionMessage&&<p className="inline-error" role="alert">{actionMessage}</p>}
   {preview?<FinishedMediaPreview key={preview.url} file={preview} onClose={()=>setPreview(undefined)}/>:<>
    {detail.video?<section className="panel finished-video">
      {detail.video.cover_file_id&&<img src={'/api/files/'+encodeURIComponent(detail.video.cover_file_id)+'/preview'} alt="视频封面" loading="lazy"/>}
      <div className="finished-actions"><button className="primary" onClick={()=>setPreview({url:'/api/video/projects/'+encodeURIComponent(detail.video!.project_id)+'/media',name:detail.title,video:true})}>播放视频</button><a className="button-link" href={'/api/video/projects/'+encodeURIComponent(detail.video.project_id)+'/media?download=true'}>下载视频</a><Link className="button-link" to={'/videos?project='+encodeURIComponent(detail.video.project_id)}>原视频项目</Link></div><p className="muted">视频文件及成片版本由原视频引擎管理。</p>
    </section>:<>
     <div className="finished-actions"><button className="primary" disabled={actionBusy||!detail.current_version} onClick={()=>void openEdit()}>修改作品</button></div>{edit&&<section className="panel finished-info"><h2>返回原工作台</h2><p className="muted">正式成品不变。可在原排版工作台主动应用 V{edit.version} 的配置，不覆盖当前草稿内容。</p><div className="finished-actions"><Link className="button-link" to={(edit.origin_scope==='source'?'/source-print/':'/print/')+encodeURIComponent(edit.origin_id)+'?'+editQuery}>修改排版</Link>{edit.origin_scope==='doc'&&['paper','handout','textbook'].includes(edit.kind)&&<Link className="button-link" to={(edit.kind==='paper'?'/papers':edit.kind==='handout'?'/handouts':'/textbooks')+'?doc='+encodeURIComponent(edit.origin_id)}>修改内容</Link>}<button onClick={()=>setEdit(undefined)}>取消</button></div></section>}
     <div className="finished-detail-tabs" role="group" aria-label="作品详情分类">{[['files','作品文件'],['info','基本信息'],['related','关联信息'],['versions','历史版本']].map(([v,n])=><button key={v} aria-pressed={tab===v} onClick={()=>setTab(v)}>{n}</button>)}</div>
     {tab==='files'&&<section className="panel finished-files"><h2>当前成品</h2>{activeVersion&&activeVersion.files.map(f=><article className="finished-file" key={f.role}><Icon name="works" size={23}/><div className="finished-name"><strong><MathText compact content={f.filename}/></strong><small>{f.role==='cover'?'印刷书衣':'正文'} · {f.pages} 页 · {size(f.size_bytes)} · V{activeVersion.number}</small></div><div className="finished-actions"><button onClick={()=>openFile(f,activeVersion)}>预览</button><a className="button-link" href={fileUrl(detail.id,activeVersion.number,f.role)+'?download=true'}>下载</a></div></article>)}{!activeVersion&&<p className="muted">尚无匹配的正文成品。</p>}
      {detail.pending_cover&&<article className="finished-file"><Icon name="book" size={23}/><div className="finished-name"><strong><MathText compact content={detail.pending_cover.filename}/></strong><small>待匹配正文的书衣 · {day(detail.pending_cover.created_at)}</small></div><div className="finished-actions"><button onClick={()=>setPreview({url:pendingUrl(detail.id),name:detail.pending_cover!.filename,pages:1,pageUrl:'/api/teaching-works/'+encodeURIComponent(detail.id)+'/pending-cover/pages'})}>预览</button><a className="button-link" href={pendingUrl(detail.id)+'?download=true'}>下载</a></div></article>}
     </section>}
     {tab==='info'&&<section className="panel finished-info"><h2>基本信息</h2><dl>{[['作品名称',detail.title],['类型',label(detail.kind)],['科目',detail.subject||'未记录'],['来源',detail.origin_scope==='source'?'来源库':'教学制作'],['创建时间',day(detail.created_at)],['最近更新',day(detail.updated_at)]].map(([k,v])=><div key={k}><dt>{k}</dt><dd><MathText compact content={v}/></dd></div>)}</dl><Link className="button-link" to={(detail.origin_scope==='source'?'/source-print/':'/print/')+encodeURIComponent(detail.origin_id)}>打开原排版工作台</Link></section>}
     {tab==='versions'&&<section className="panel finished-files"><h2>历史版本</h2><p className="muted">仅保留最近两个正式版本。</p>{detail.versions.map(v=><article key={v.number} className="finished-version"><div className="finished-actions"><strong>V{v.number}{v.number===detail.current_version?' · 当前版本':''}</strong><small>{day(v.created_at)}</small></div>{v.files.map(f=><div className="finished-file" key={f.role}><div className="finished-name"><MathText compact content={f.filename}/><small>{f.pages} 页 · {size(f.size_bytes)}</small></div><button onClick={()=>openFile(f,v)}>预览</button><a className="button-link" href={fileUrl(detail.id,v.number,f.role)+'?download=true'}>下载</a></div>)}<div className="finished-actions"><button onClick={()=>{setVersion(v.number);setTab('related')}}>查看版本关联信息</button>{v.number!==detail.current_version&&<button disabled={actionBusy} onClick={()=>void restore(v)}>恢复版本</button>}</div></article>)}</section>}
     {tab==='related'&&<section className="panel finished-related"><h2>关联信息 {activeVersion&&'· V'+activeVersion.number}</h2>{!activeVersion?<p className="muted">暂无正式正文版本。</p>:relatedError?<p role="alert">{relatedError}</p>:!related?<p className="muted">正在读取版本快照…</p>:<>
       <p className="muted">{related.question_count} 道题 · {related.source_count} 个直接来源</p>{related.partial_pages&&<p className="muted">此为选页文件，关联题目按排版内容快照统计，不代表实际选中页面内的题目。</p>}
       <details><summary>知识点（{related.knowledge_points.length}）</summary><div className="finished-tags">{related.knowledge_points.map(t=><span key={t}><MathText compact content={t}/></span>)}</div></details>
       <details><summary>知识标签（{related.knowledge_tags.length}）</summary><div className="finished-tags">{related.knowledge_tags.map(t=><span key={t}><MathText compact content={t}/></span>)}</div></details>
       <input aria-label="搜索关联题目" placeholder="搜索关联题目" maxLength={200} value={questionQuery} onChange={e=>{setQuestionQuery(e.target.value);setQuestionPage(0)}}/>
       {related.items.map((item,i)=><article className="finished-question" key={item.uid||i}><small>{item.chapter}</small><MathText content={item.title}/><MathText content={item.content}/>{(item.answer||item.solution||item.analysis||item.proof)&&<details><summary>答案与解析</summary>{[item.answer,item.solution,item.analysis,item.proof].filter(Boolean).map((s,j)=><MathText key={j} content={s}/>)}</details>}</article>)}
       <div className="finished-actions"><button disabled={!questionPage} onClick={()=>setQuestionPage(x=>x-1)}>上一页</button><small>{related.total} 道</small><button disabled={(questionPage+1)*pageSize>=related.total} onClick={()=>setQuestionPage(x=>x+1)}>下一页</button></div>
     </>}</section>}
    </>}
   </>}
  </>}
 </div>
 return <div className="finished-works">
  <header className="finished-heading"><div><h1>教学作品</h1><p className="muted">管理已导出文档及已归档视频</p></div><button type="button" onClick={()=>setReload(x=>x+1)}><Icon name="refresh" size={16}/> 刷新</button></header>
  <div className="finished-search"><div className="finished-search-field"><Icon name="search"/><input aria-label="搜索作品名称" placeholder="搜索作品名称" value={q} maxLength={200} onChange={e=>filter(()=>setQ(e.target.value))}/></div><button type="button" aria-expanded={advanced} onClick={()=>setAdvanced(x=>!x)}>筛选 <Icon name="chevron-down" size={15}/></button></div>
  <div className="finished-tabs" role="group" aria-label="作品类型">{kinds.map(([v,n])=><button key={v} aria-pressed={kind===v} onClick={()=>filter(()=>setKind(v))}>{n}</button>)}</div>
  {advanced&&<section className="panel finished-filters"><label>科目<select value={subject} onChange={e=>filter(()=>setSubject(e.target.value))}><option value="">全部科目</option>{subjects.map(s=><option key={s}>{s}</option>)}</select></label><label>制作来源<select value={scope} onChange={e=>filter(()=>setScope(e.target.value))}><option value="">全部</option><option value="doc">自编教学资料</option><option value="source">来源库</option><option value="video">视频引擎</option></select></label><label>创建起始<input type="date" value={from} onChange={e=>filter(()=>setFrom(e.target.value))}/></label><label>创建截止<input type="date" value={to} onChange={e=>filter(()=>setTo(e.target.value))}/></label><button onClick={clear}>重置筛选</button></section>}
  <div className="finished-meta"><small>{busy?'正在读取…':'共 '+total+' 个作品'}</small><select aria-label="作品排序" value={sort} onChange={e=>filter(()=>setSort(e.target.value))}><option value="recent">最近更新</option><option value="old">最早创建</option><option value="name">名称排序</option></select></div>
  {error?<p className="inline-error" role="alert">{error}</p>:<section className="panel finished-list" aria-busy={busy}>
   {!busy&&!rows.length&&<p className="muted finished-empty">没有符合条件的作品。正式导出的 PDF 或已归档视频将在这里显示。</p>}
   {!busy&&rows.map(w=><article className="finished-row" key={w.id}><button className="finished-open" type="button" onClick={()=>openWork(w)}><span className="finished-icon"><Icon name={w.kind==='video'?'film':w.kind==='textbook'?'book':'works'} size={24}/></span><span className="finished-name"><strong><MathText compact content={w.title}/></strong><small>{label(w.kind)} · {w.kind==='video'?'MP4': 'PDF'} · {w.subject||'未记录科目'}</small></span><span className="finished-status">{w.kind==='video'?'已归档':w.current_version?'V'+w.current_version:'待正文'}</span><span className="finished-date">{day(w.updated_at)}</span></button><button className="finished-more" aria-label={'操作 '+w.title} aria-expanded={menu===w.id} onClick={()=>setMenu(x=>x===w.id?'':w.id)}><Icon name="more"/></button>{menu===w.id&&<div className="finished-menu"><button onClick={()=>openWork(w)}>作品详情</button>{w.kind==='video'?<Link to={'/videos?project='+encodeURIComponent(w.origin_id)}>原视频项目</Link>:<Link to={(w.origin_scope==='source'?'/source-print/':'/print/')+encodeURIComponent(w.origin_id)}>打开排版</Link>}</div>}</article>)}
  </section>}
  <div className="finished-actions finished-pagination"><button disabled={busy||page===0} onClick={()=>setPage(x=>x-1)}>上一页</button><small>第 {page+1} 页</small><button disabled={busy||(page+1)*pageSize>=total} onClick={()=>setPage(x=>x+1)}>下一页</button></div>
  <details className="finished-legacy"><summary>旧版作品记录</summary><p className="muted">此前手工登记的非成品记录仍保留在原工作台，未自动复制到成品库。</p><Link to="/works?legacy=1">打开旧版作品记录</Link></details>
 </div>
}
