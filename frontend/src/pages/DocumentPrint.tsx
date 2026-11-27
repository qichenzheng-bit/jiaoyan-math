import {useWorkspaceBack} from '../components/WorkspaceNavigation'
import {MathText} from '../components/MathText'
import {useEffect,useState,useRef,useMemo} from 'react'
import PagedPreview from './PagedPreview'
import PdfJobs from './PdfJobs'
import type {CSSProperties} from 'react'
import {defaults,builtins,dimensions,layoutError,sanitizeLayout,readLocal,writeLocal,readTemplates} from './documentLayout'
import type {Layout,LayoutTemplate} from './documentLayout'
import './document-layout.css'
import {useParams,useSearchParams,Link,useNavigate} from 'react-router-dom'
import {api} from '../auth'
import ChatText from './ChatText'
type Content={title:string;content:string;answer:string;solution:string;analysis:string;proof:string;kind:string}
type Block=Content&{original_question_number?:string;resource_id?:string|null;heading_level?:1|2|null;uid:string;score?:number;subquestion_scores?:number[];local_fields?:('title'|'content'|'answer'|'solution'|'analysis'|'proof')[];hidden_fields?:('answer'|'solution'|'analysis'|'proof')[];file_id:string|null;width:number;snapshot?:Content}
type Saved<T>={revision:number;value:T;history:{revision:number;value:T}[]}
export type PrintDoc={export_token?:string;parent_document_id?:string|null;chaptered?:boolean;title:string;subject:string;kind:string;blocks:Block[];source_export?:boolean;has_source_content?:boolean;batch_count?:number}

export default function DocumentPrint({source=false}:{source?:boolean}){
 const {id}=useParams(),navigate=useNavigate(),[params]=useSearchParams(),chapterUid=params.get('chapter')
 const [doc,setDoc]=useState<PrintDoc>(),[stem,setStem]=useState(params.get('stem')==='1'),[answerOnly,setAnswerOnly]=useState(params.get('answer')==='1')
 const [error,setError]=useState(''),[confirmed,setConfirmed]=useState(false),[ready,setReady]=useState(false),[previewError,setPreviewError]=useState('')
 const [layout,setLayout]=useState<Layout>({...defaults}),[templates,setTemplates]=useState<LayoutTemplate[]>(readTemplates)
 const [templateId,setTemplateId]=useState('general'),[templateName,setTemplateName]=useState(''),[message,setMessage]=useState('')
 const [editing,setEditing]=useState(!source),[controls,setControls]=useState(true),[loadedKey,setLoadedKey]=useState('')
 const [pageCount,setPageCount]=useState(0)
 const [scope,setScope]=useState<string[]>([]),[scopeMode,setScopeMode]=useState<'all'|'selected'>('all')
 const [editUid,setEditUid]=useState(''),[overrides,setOverrides]=useState<Record<string,Partial<Content>>>({})
 const [filename,setFilename]=useState('')
 const [cloudRevision,setCloudRevision]=useState<number|null>(null),[templateRevision,setTemplateRevision]=useState<number|null>(null),[cloudBusy,setCloudBusy]=useState(false),[cloudLayout,setCloudLayout]=useState<Layout|null>(null)
 const [hasDraft,setHasDraft]=useState(false)
 const routeRef=useRef('')
 const storageKey='wg-layout-v1:'+String(source?'source':'doc')+':'+id+':'+(chapterUid??'all')
 const layoutPath='/settings/document-layout/'+(source?'source':'doc')+'/'+encodeURIComponent(id??'')
 routeRef.current=storageKey
 const back=source?'/sources':(doc?.kind==='paper'?'/papers':doc?.kind==='handout'?'/handouts':doc?.kind==='textbook'?'/textbooks':'/intake')+'?doc='+id
 useWorkspaceBack(()=>{if(!doc&&!source)return false;navigate(back);return true})
 useEffect(()=>{
  const c=new AbortController();setDoc(undefined);setError('');setConfirmed(false);setReady(false);setLoadedKey('');setEditing(!source);setControls(true);setCloudRevision(null);setTemplateRevision(null);setCloudLayout(null);setHasDraft(false);setCloudBusy(false);setMessage('');setScope([]);setScopeMode('all');setOverrides({});setEditUid('');setFilename('');setPageCount(0)
  api<PrintDoc>((source?'/documents/source-export/':'/documents/')+encodeURIComponent(id??'')+(source?'':'/export'),{signal:c.signal}).then(async data=>{
   if(c.signal.aborted)return
   if(chapterUid){
    if(source||!['textbook','handout'].includes(data.kind))throw Error('仅讲义和教材支持按章导出')
    const start=data.blocks.findIndex(b=>b.uid===chapterUid&&b.kind==='heading'&&b.heading_level===1)
    if(start<0)throw Error('未找到指定章节，请返回教材目录重新选择')
    let end=data.blocks.findIndex((b,i)=>i>start&&b.kind==='heading'&&b.heading_level===1);if(end<0)end=data.blocks.length
    data={...data,blocks:data.blocks.slice(start,end)}
   }
   const base=builtins.find(t=>t.kind===data.kind)??builtins[builtins.length-1]
   const stored=readLocal<unknown>(storageKey,null)
   const [remote,library]=await Promise.allSettled([chapterUid?Promise.resolve(null):api<Saved<Layout|null>>(layoutPath,{signal:c.signal}),api<Saved<LayoutTemplate[]>>('/settings/document-templates',{signal:c.signal})])
   if(c.signal.aborted)return
   const saved=remote.status==='fulfilled'?remote.value:null
   const lib=library.status==='fulfilled'?library.value:null
   if(saved&&Number.isInteger(saved.revision)){setCloudRevision(saved.revision);setCloudLayout(saved.value?sanitizeLayout(saved.value):null)}
   if(lib&&Number.isInteger(lib.revision)&&Array.isArray(lib.value)){setTemplateRevision(lib.revision);if(lib.revision>0){setTemplates(lib.value);writeLocal('wg-layout-templates-v1',lib.value)}}
   const current=saved?.value??stored
   setHasDraft(Boolean(current));setTemplateId(base.id);setLayout(current?sanitizeLayout(current):{...base.layout,originalNumbers:source});setDoc(data);setFilename(data.title);setLoadedKey(storageKey)
  }).catch(e=>{if(!c.signal.aborted)setError(e.message)})
  return()=>c.abort()
 },[id,source,chapterUid,storageKey,layoutPath])
 useEffect(()=>{
  if(!doc||loadedKey!==storageKey||layoutError(layout))return
  if(!writeLocal(storageKey,layout))setMessage('浏览器无法保存排版设置，请保持当前页面。')
 },[doc,layout,loadedKey,storageKey])
 const viewDoc=useMemo(()=>doc?{...doc,blocks:doc.blocks.filter(b=>scopeMode==='all'||scope.includes(b.uid)).map(b=>{
  const edit=overrides[b.uid];if(!edit)return b
  return {...b,...edit,local_fields:Array.from(new Set([...(b.local_fields??[]),...Object.keys(edit)])) as Block['local_fields']}
 })}:undefined,[doc,scopeMode,scope,overrides])
 const renderVersion=useMemo(()=>({viewDoc,stem,answerOnly}),[viewDoc,stem,answerOnly])
 const activeEdit=doc?.blocks.find(b=>b.uid===editUid)
 function invalidate(){setConfirmed(false);setReady(false)}
 const patch=(values:Partial<Layout>)=>{setConfirmed(false);setReady(false);setLayout(old=>({...old,...values}))}
 const compatible=[...builtins,...templates].filter(t=>t.kind==='all'||t.kind===doc?.kind)
 const selected=compatible.find(t=>t.id===templateId)
 function apply(){
  if(!selected)return
  const next={...selected.layout}
  if(source)next.originalNumbers=true
  setLayout(next);setConfirmed(false);setReady(false);setEditing(true);setMessage('已应用模板，原始教学内容保持不变。')
 }
 async function saveCloud(){
  if(cloudRevision===null||cloudBusy||layoutError(layout))return
  const key=storageKey;setCloudBusy(true)
  try{const saved=await api<Saved<Layout>>(layoutPath,{method:'PUT',body:JSON.stringify({revision:cloudRevision,value:layout})});if(routeRef.current!==key)return;setCloudRevision(saved.revision);setCloudLayout(saved.value);setMessage('排版配置已保存到服务器，可跨设备读取。')}
  catch(e){if(routeRef.current===key)setMessage(e instanceof Error?e.message:'服务器保存失败，当前浏览器草稿仍保留。')}
  finally{if(routeRef.current===key)setCloudBusy(false)}
 }
 async function saveTemplate(){
  if(!templateName.trim()||layoutError(layout))return
  const kind:LayoutTemplate['kind']=doc?.kind==='paper'||doc?.kind==='handout'||doc?.kind==='textbook'?doc.kind:'all'
  if(templates.length>=100){setMessage('个人模板已达到 100 个，请先删除不用的模板。');return}
  const item:LayoutTemplate={id:crypto.randomUUID(),name:templateName.trim().slice(0,80),kind,layout:{...layout}}
  const list=[...templates,item]
  const key=storageKey;setCloudBusy(true)
  try{if(templateRevision!==null){const result=await api<Saved<LayoutTemplate[]>>('/settings/document-templates',{method:'PUT',body:JSON.stringify({revision:templateRevision,value:list})});if(routeRef.current!==key)return;setTemplateRevision(result.revision)}
   else if(!writeLocal('wg-layout-templates-v1',list))throw Error('模板保存失败。')
   setTemplates(list);writeLocal('wg-layout-templates-v1',list);setTemplateId(item.id);setTemplateName('');setMessage(templateRevision!==null?'模板已保存到服务器。':'服务器不可用，模板仅保存在当前浏览器。')
  }catch(e){if(routeRef.current===key)setMessage(e instanceof Error?e.message:'模板保存失败')}
  finally{if(routeRef.current===key)setCloudBusy(false)}
 }
 async function removeTemplate(){
  if(!templates.some(t=>t.id===templateId))return
  const list=templates.filter(t=>t.id!==templateId)
  const key=storageKey;setCloudBusy(true)
  try{if(templateRevision!==null){const result=await api<Saved<LayoutTemplate[]>>('/settings/document-templates',{method:'PUT',body:JSON.stringify({revision:templateRevision,value:list})});if(routeRef.current!==key)return;setTemplateRevision(result.revision)}
   else if(!writeLocal('wg-layout-templates-v1',list))throw Error('删除失败。')
   setTemplates(list);writeLocal('wg-layout-templates-v1',list);setTemplateId(compatible.find(t=>t.kind===doc?.kind&&builtins.includes(t))?.id??'general')
  }catch(e){if(routeRef.current===key)setMessage(e instanceof Error?e.message:'删除失败')}
  finally{if(routeRef.current===key)setCloudBusy(false)}
 }
 const [w,h]=dimensions(layout),invalid=layoutError(layout)
 const style={'--layout-width':w+'mm','--layout-height':h+'mm','--layout-top':layout.top+'mm','--layout-bottom':layout.bottom+'mm','--layout-left':layout.left+'mm','--layout-right':layout.right+'mm','--layout-columns':layout.columns,'--layout-gap':layout.gap+'mm','--layout-size':layout.size+'pt','--layout-line':layout.lineHeight,'--layout-paragraph':layout.paragraphGap+'pt','--layout-font':layout.font==='sans'?'"Noto Sans CJK SC","Microsoft YaHei",sans-serif':'"Noto Serif CJK SC",SimSun,serif'} as CSSProperties
 const num=(label:string,key:'width'|'height'|'top'|'bottom'|'left'|'right'|'gap'|'size'|'lineHeight'|'paragraphGap'|'answerSpace'|'titleSize'|'headingSize',min:number,max:number,step=1)=><label>{label}<input type="number" min={min} max={max} step={step} value={layout[key]} onChange={e=>{const value=e.currentTarget.valueAsNumber;if(Number.isFinite(value))patch({[key]:Math.max(min,Math.min(max,value))})}}/></label>
 return <div className="print-work layout-work" style={style}>
  <style>{'@page{size:'+w+'mm '+h+'mm;margin:0}'}</style>
  <header className="print-controls layout-toolbar">
   <Link className="button-link" to={back}>{source?'返回来源库':'返回编辑'}</Link>
   <strong>文档排版</strong>
   {editing&&<><button type="button" aria-pressed={controls} onClick={()=>setControls(true)}>排版设置</button><button type="button" aria-pressed={!controls} onClick={()=>setControls(false)}>预览</button></>}
  </header>
  {error&&<p role="alert">{error}</p>}
  {doc&&<div className="print-controls layout-template-panel">
   <label>选择排版模板<select value={templateId} onChange={e=>setTemplateId(e.target.value)}>{compatible.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
   <button className={editing?'':'primary'} type="button" disabled={!selected} onClick={apply}>{editing?'应用模板':'进入排版工作台'}</button>
   {!editing&&hasDraft&&<button type="button" onClick={()=>setEditing(true)}>继续上次排版</button>}{editing&&<><button type="button" disabled={cloudBusy||cloudRevision===null||!!invalid} onClick={()=>void saveCloud()}>保存排版到服务器</button><label>新模板名称<input value={templateName} maxLength={80} onChange={e=>setTemplateName(e.target.value)} placeholder="保存当前排版"/></label><button type="button" disabled={cloudBusy||!templateName.trim()||!!invalid} onClick={()=>void saveTemplate()}>保存为模板</button><button type="button" disabled={cloudBusy||!templates.some(t=>t.id===templateId)} onClick={()=>void removeTemplate()}>删除个人模板</button></>}
   {message&&<p role="status">{message}</p>}
   <small className="muted">{cloudRevision===null?'排版草稿自动保存在当前浏览器。':cloudLayout&&JSON.stringify(cloudLayout)===JSON.stringify(layout)?'排版已同步至服务器。':'本地草稿自动保存，点击保存排版到服务器后可跨设备使用。'} 不修改题库或来源。</small>
  </div>}
  {source&&doc&&<p className="print-controls muted">{doc.has_source_content?'仅导出已入库批次及其他正式关联资源，不包含未入库草稿。':'此来源尚无已录入的关联内容，仅显示来源登记信息。'}</p>}
  {chapterUid&&doc&&<p className="print-controls muted">当前仅导出所选章节内容。</p>}
  {doc&&editing&&<>
   {controls&&source&&<section className="print-controls layout-settings"><details><summary>来源导出范围与局部内容</summary>
    <label>导出范围<select value={scopeMode} onChange={e=>{invalidate();setScopeMode(e.target.value as 'all'|'selected');if(e.target.value==='selected'&&!scope.length)setScope(doc.blocks.map(b=>b.uid))}}><option value="all">全部已入库内容</option><option value="selected">自由选择内容</option></select></label>
    {scopeMode==='selected'&&<div className="layout-selection"><button onClick={()=>{invalidate();setScope(doc.blocks.map(b=>b.uid))}}>全选</button><button onClick={()=>{invalidate();setScope([])}}>清空</button>{doc.blocks.map((b,i)=><label key={b.uid}><input type="checkbox" checked={scope.includes(b.uid)} onChange={e=>{invalidate();setScope(old=>e.target.checked?[...old,b.uid]:old.filter(x=>x!==b.uid))}}/>{i+1}. <MathText compact content={(b.snapshot??b).title||(b.snapshot??b).content.slice(0,100)}/></label>)}</div>}
    <label>仅修改当前导出副本<select value={editUid} onChange={e=>setEditUid(e.target.value)}><option value="">选择内容</option>{doc.blocks.map((b,i)=><option key={b.uid} value={b.uid}>{i+1}. {(b.snapshot??b).title||b.kind}</option>)}</select></label>
    {activeEdit&&(['title','content','answer','solution','analysis','proof'] as const).map(field=><label key={field}>{({title:'标题',content:'正文',answer:'答案',solution:'解析',analysis:'思路',proof:'证明'})[field]}<textarea rows={3} value={overrides[editUid]?.[field]??(activeEdit.local_fields?.includes(field)?activeEdit[field]:(activeEdit.snapshot??activeEdit)[field])??''} onChange={e=>{invalidate();setOverrides(old=>({...old,[editUid]:{...old[editUid],[field]:e.target.value}}))}}/></label>)}
    {activeEdit&&<button onClick={()=>{invalidate();setOverrides(old=>Object.fromEntries(Object.entries(old).filter(([k])=>k!==editUid)))}}>恢复该条原内容</button>}
    <small>仅影响本次导出副本，不写回来源库或题库。</small>
   </details></section>}
   {controls&&<section className="print-controls layout-settings">
    <details open><summary>页面与分栏</summary><div className="layout-fields">
     <label>纸张<select value={layout.paper} onChange={e=>patch({paper:e.target.value as Layout['paper']})}>{['A4','A3','A5','B5','A6','custom'].map(p=><option key={p} value={p}>{p==='custom'?'自定义':p}</option>)}</select></label>
     <label>方向<select value={layout.landscape?'landscape':'portrait'} onChange={e=>patch({landscape:e.target.value==='landscape'})}><option value="portrait">纵向</option><option value="landscape">横向</option></select></label>
     {layout.paper==='custom'&&<>{num('宽度 (mm)','width',50,1000)}{num('高度 (mm)','height',50,1000)}</>}
     {num('上边距 (mm)','top',0,100)}{num('下边距 (mm)','bottom',0,100)}{num('左边距 (mm)','left',0,100)}{num('右边距 (mm)','right',0,100)}
     <label>分栏<select value={layout.columns} onChange={e=>patch({columns:Number(e.target.value) as Layout['columns']})}><option value={1}>单栏</option><option value={2}>双栏</option><option value={3}>三栏</option></select></label>
     {layout.columns>1&&num('栏间距 (mm)','gap',3,30)}
    </div></details>
    <details><summary>正文与数学排版</summary><div className="layout-fields">
     <label>正文字体<select value={layout.font} onChange={e=>patch({font:e.target.value as Layout['font']})}><option value="serif">宋体类</option><option value="sans">黑体类</option></select></label>
     {num('字号 (pt)','size',6,36,.5)}{num('主标题字号 (pt)','titleSize',8,36,.5)}{num('章节标题字号 (pt)','headingSize',8,36,.5)}{num('行距','lineHeight',1,3,.1)}{num('段后间距 (pt)','paragraphGap',0,50)}
     <label className="layout-check"><input type="checkbox" checked={layout.keepQuestions} onChange={e=>patch({keepQuestions:e.target.checked})}/>尽量保持题目完整</label>
     <label className="layout-check"><input type="checkbox" checked={layout.originalNumbers} onChange={e=>patch({originalNumbers:e.target.checked})}/>保留已有原题号</label>
     {doc.kind==='paper'&&num('每题答题留白 (mm)','answerSpace',0,180,5)}
    </div></details>
    <details><summary>分页、目录与页眉页脚</summary><div className="layout-fields">
     <label>页眉<input maxLength={200} value={layout.header} onChange={e=>patch({header:e.target.value})}/></label>
     <label>页脚<input maxLength={200} value={layout.footer} onChange={e=>patch({footer:e.target.value})}/></label>
     <small>支持文档名称、科目、当前章名、当前页码、总页数占位符。</small>
     <label className="layout-check"><input type="checkbox" checked={layout.toc} onChange={e=>patch({toc:e.target.checked})}/>生成目录</label>
     {layout.toc&&<label>目录层级<select value={layout.tocDepth} onChange={e=>patch({tocDepth:Number(e.target.value) as Layout['tocDepth']})}>{[1,2,3,4,5,6].map(n=><option key={n}>{n}</option>)}</select></label>}
     <label className="layout-check"><input type="checkbox" checked={layout.chapterNewPage} onChange={e=>patch({chapterNewPage:e.target.checked})}/>章标题另起一页</label>
     <label className="layout-check"><input type="checkbox" checked={layout.mirrorMargins} onChange={e=>patch({mirrorMargins:e.target.checked})}/>奇偶页镜像边距</label>
    </div></details>
   </section>}
   <div className="print-controls layout-output">
    <label><input type="checkbox" checked={stem} onChange={e=>{setStem(e.target.checked);setConfirmed(false);setReady(false)}}/> {doc.kind==='paper'?'仅题目':'学生版（隐藏答案与解析）'}</label>
    {doc.kind==='paper'&&!stem&&<label><input type="checkbox" checked={answerOnly} onChange={e=>{setAnswerOnly(e.target.checked);setConfirmed(false);setReady(false)}}/> 仅答案（不含解析）</label>}
    <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} disabled={!ready||!!invalid}/> 已检查预览，确认无问题</label>
    <button className="primary" disabled={!ready||!confirmed||!!invalid} onClick={async()=>{await document.fonts.ready;window.print()}}>打印 / 保存为 PDF</button>
    <label>文件名<input value={filename} onChange={e=>setFilename(e.target.value)} maxLength={200}/></label><small className="muted">{pageCount?`共 ${pageCount} 页`:"正在计算页数"} · 当前分页预览使用实际纸张尺寸。</small>
   </div>
   {doc.export_token&&<PdfJobs path={'/document-pdf/'+(source?'source':'doc')+'/'+encodeURIComponent(id??'')} canExport={ready&&confirmed&&!invalid&&!!filename.trim()} pageCount={pageCount} request={{export_token:doc.export_token,layout,stem,answerOnly,selected_uids:scopeMode==='all'?null:scope,overrides,chapter_uid:chapterUid,filename,confirmed:true}}/>}
   {invalid&&<p role="alert">{invalid}</p>}{previewError&&<p role="alert" className="print-controls">{previewError}</p>}
   {!invalid&&viewDoc&&viewDoc.blocks.length>0&&<div className="print-preview-content layout-preview"><PagedPreview layout={layout} title={viewDoc.title} subject={viewDoc.subject??''} version={renderVersion} onResult={result=>{setPageCount(result.pages);setPreviewError(result.error);setReady(Boolean(result.pages)&&!result.error);setConfirmed(false)}}><PrintableDocument doc={viewDoc} stem={stem} answerOnly={answerOnly} source={source} layout={layout}/></PagedPreview></div>}
   {viewDoc&&!viewDoc.blocks.length&&<p role="alert">请选择至少一个内容条目。</p>}
  </>}
 </div>
}
export function PrintableDocument({doc,stem=false,answerOnly=false,source=false,sourceId,layout}:{doc:PrintDoc;stem?:boolean;answerOnly?:boolean;source?:boolean;sourceId?:string;layout?:Layout}){let n=0;return <article className={"print-document"+(layout?" configured-print":"")}>{layout?.header&&<div className="layout-document-header"><MathText compact content={layout.header.replaceAll('{{文档名称}}',doc.title).replaceAll('{{科目}}',doc.subject??'')}/></div>}<h1><MathText compact content={doc.title}/></h1><div className="print-subtitle">{doc.subject}{doc.kind==='paper'&&!source&&' · 总分 '+doc.blocks.reduce((s,b)=>s+(b.score??0),0)}</div><div className="layout-body">{doc.blocks.map(b=>{const v={...(b.snapshot??b)};for(const field of b.local_fields??[])v[field]=b[field];for(const field of b.hidden_fields??[])v[field]='';if(b.kind==='pagebreak')return <div key={b.uid} className="print-break"/>;if(b.kind==='image')return <figure key={b.uid} data-layout-uid={b.uid}><img src={'/api/files/'+b.file_id+'/preview'} alt={b.title} style={{width:b.width+'%'}}/><figcaption><MathText compact content={b.title}/></figcaption></figure>;if(b.kind==='heading'&&b.heading_level){const Heading=b.heading_level===2?'h3':'h2';return <section className={'print-block print-heading-level-'+b.heading_level} key={b.uid} data-layout-uid={b.uid} data-layout-level={b.heading_level}><Heading><MathText compact content={v.title||v.content}/></Heading>{v.title&&v.content&&<ChatText content={v.content}/>}</section>}const question=v.kind==='question';if(question)n++;return <section className={"print-block"+(question&&layout?.keepQuestions?" layout-keep":"")} key={b.uid} data-layout-uid={b.uid}>{source&&sourceId&&b.resource_id&&<Link className="print-controls source-edit-link" to={'/resource-edit/'+encodeURIComponent(b.resource_id)+(sourceId?'?return_source='+encodeURIComponent(sourceId):'')}>编辑{question?'题目':'知识单元'}</Link>}{question?<p className="print-question-number">{layout?.originalNumbers&&b.original_question_number?b.original_question_number:n}. {b.score?'（本题满分 '+b.score+' 分）':''}</p>:v.title&&<h2><MathText compact content={v.title}/></h2>}<ChatText content={v.content}/>{question&&!!b.subquestion_scores?.length&&<p className="print-question-number">{b.subquestion_scores.map((s,i)=>'（'+(i+1)+'）'+s+'分').join('　')}</p>}{stem&&question&&layout&&layout.answerSpace>0&&<div className="layout-answer-space" style={{height:layout.answerSpace+'mm'}}/>}{!stem&&<>{v.answer&&<div>答案：<ChatText content={v.answer}/></div>}{!answerOnly&&v.analysis&&<div>思路：<ChatText content={v.analysis}/></div>}{!answerOnly&&v.solution&&<div>解析：<ChatText content={v.solution}/></div>}{!answerOnly&&v.proof&&<div>证明：<ChatText content={v.proof}/></div>}</>}</section>})}</div>{layout?.footer&&<div className="layout-document-footer"><MathText compact content={layout.footer.replaceAll('{{文档名称}}',doc.title).replaceAll('{{科目}}',doc.subject??'')}/></div>}</article>}
