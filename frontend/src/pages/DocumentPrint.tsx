import {useWorkspaceBack} from '../components/WorkspaceNavigation'
import {MathText} from '../components/MathText'
import {useEffect,useState,useRef,useMemo,Fragment} from 'react'
import PagedPreview from './PagedPreview'
import BlockStyleEditor from './BlockStyleEditor'
import SectionPageEditor from './SectionPageEditor'
import PdfJobs from './PdfJobs'
import type {CSSProperties} from 'react'
import {defaults,builtins,dimensions,layoutError,sanitizeLayout,readLocal,writeLocal,readTemplates,templateLayout,sanitizeRule} from './documentLayout'
import type {Layout,LayoutTemplate,BlockStyle,Role} from './documentLayout'
import './document-layout.css'
import {useParams,useSearchParams,Link,useNavigate} from 'react-router-dom'
import {api} from '../auth'
import ChatText from './ChatText'
type Content={title:string;content:string;answer:string;solution:string;analysis:string;proof:string;kind:string;question_type?:string;unit_type?:string;question_data?:{stem:string;options?:{label:string;content:string}[];blanks?:unknown[]}|null}
type Block=Content&{original_question_number?:string;resource_id?:string|null;heading_level?:1|2|null;uid:string;score?:number;subquestion_scores?:number[];local_fields?:('title'|'content'|'answer'|'solution'|'analysis'|'proof')[];hidden_fields?:('answer'|'solution'|'analysis'|'proof')[];file_id:string|null;width:number;snapshot?:Content}
type SourceDraft={export_token:string;selected_uids?:string[]|null;overrides:Record<string,Partial<Content>>;stem:boolean;answerOnly:boolean;filename:string}
type Saved<T>={revision:number;value:T;history:{revision:number;value:T}[]}
export type PrintDoc={export_token?:string;export_chapter_uid?:string;parent_document_id?:string|null;chaptered?:boolean;title:string;subject:string;kind:string;blocks:Block[];source_export?:boolean;has_source_content?:boolean;batch_count?:number}

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
 const [filename,setFilename]=useState(''),[picked,setPicked]=useState('')
 const [applyMode,setApplyMode]=useState<'keep'|'replace'|'partial'>('keep'),[applyParts,setApplyParts]=useState(['page','body','special','header','types'])
 const [layoutHistory,setLayoutHistory]=useState<Saved<Layout|null>['history']>([]),[templateHistory,setTemplateHistory]=useState<Saved<LayoutTemplate[]>['history']>([])
 const [cloudRevision,setCloudRevision]=useState<number|null>(null),[templateRevision,setTemplateRevision]=useState<number|null>(null),[cloudBusy,setCloudBusy]=useState(false),[cloudLayout,setCloudLayout]=useState<Layout|null>(null)
 const [hasDraft,setHasDraft]=useState(false),[draftRevision,setDraftRevision]=useState<number|null>(null),[localRecovery,setLocalRecovery]=useState<Layout|null>(null)
 const routeRef=useRef('')
 const storageKey='wg-layout-v1:'+String(source?'source':'doc')+':'+id+':'+(chapterUid??'all')
 const draftPath='/settings/source-layout-draft/'+encodeURIComponent(id??'')
 const layoutPath='/settings/document-layout/'+(source?'source':'doc')+'/'+encodeURIComponent(id??'')
 routeRef.current=storageKey
 const back=source?'/sources':(doc?.kind==='paper'?'/papers':doc?.kind==='handout'?'/handouts':doc?.kind==='textbook'?'/textbooks':'/intake')+'?doc='+id
 useWorkspaceBack(()=>{if(!doc&&!source)return false;navigate(back);return true})
 useEffect(()=>{
  const c=new AbortController();setDoc(undefined);setError('');setConfirmed(false);setReady(false);setLoadedKey('');setEditing(!source);setControls(true);setCloudRevision(null);setTemplateRevision(null);setCloudLayout(null);setHasDraft(false);setCloudBusy(false);setMessage('');setScope([]);setScopeMode('all');setOverrides({});setEditUid('');setFilename('');setPageCount(0);setPicked('');setLayoutHistory([]);setTemplateHistory([]);setDraftRevision(null);setLocalRecovery(null)
  api<PrintDoc>((source?'/documents/source-export/':'/documents/')+encodeURIComponent(id??'')+(source?'':'/export'+(chapterUid?'?chapter='+encodeURIComponent(chapterUid):'')),{signal:c.signal}).then(async data=>{
   if(c.signal.aborted)return
   if(chapterUid&&data.export_chapter_uid!==chapterUid){
    if(source||!['textbook','handout'].includes(data.kind))throw Error('仅讲义和教材支持按章导出')
    const start=data.blocks.findIndex(b=>b.uid===chapterUid&&b.kind==='heading'&&b.heading_level===1)
    if(start<0)throw Error('未找到指定章节，请返回教材目录重新选择')
    let end=data.blocks.findIndex((b,i)=>i>start&&b.kind==='heading'&&b.heading_level===1);if(end<0)end=data.blocks.length
    data={...data,blocks:data.blocks.slice(start,end)}
   }
   const base=builtins.find(t=>t.kind===data.kind)??builtins[builtins.length-1]
   const stored=readLocal<unknown>(storageKey,null)
   const local=stored&&typeof stored==='object'&&'value' in stored?stored as {value:unknown;baseRevision:number|null}:null
   const [remote,library,draft]=await Promise.allSettled([chapterUid?Promise.resolve(null):api<Saved<Layout|null>>(layoutPath,{signal:c.signal}),api<Saved<LayoutTemplate[]>>('/settings/document-templates',{signal:c.signal}),source&&data.export_token?api<Saved<SourceDraft|null>>(draftPath,{signal:c.signal}):Promise.resolve(null)])
   if(c.signal.aborted)return
   const saved=remote.status==='fulfilled'?remote.value:null
   const lib=library.status==='fulfilled'?library.value:null
   if(saved&&Number.isInteger(saved.revision)){setCloudRevision(saved.revision);setCloudLayout(saved.value?sanitizeLayout(saved.value):null);setLayoutHistory(saved.history??[])}
   if(lib&&Number.isInteger(lib.revision)&&Array.isArray(lib.value)){setTemplateRevision(lib.revision);setTemplateHistory(lib.history??[]);if(lib.revision>0){const list=lib.value.map(t=>({...t,layout:templateLayout(sanitizeLayout(t.layout))}));setTemplates(list);writeLocal('wg-layout-templates-v1',list)}}
   const defaultTemplate=lib?.value?.find(t=>t.isDefault&&t.kind===data.kind)??lib?.value?.find(t=>t.isDefault&&t.kind==='all')??base
   const localValue=local?.value??stored
   const sameRevision=!!local&&local.baseRevision===(saved?.revision??null)
   const current=sameRevision?localValue:saved?.value??localValue
   if(local&&saved?.value&&!sameRevision&&JSON.stringify(sanitizeLayout(local.value))!==JSON.stringify(sanitizeLayout(saved.value))){setLocalRecovery(sanitizeLayout(local.value));setMessage('服务器版本已更新，保留了本地排版恢复副本。')}
   const remoteDraft=draft.status==='fulfilled'?draft.value:null
   if(remoteDraft&&Number.isInteger(remoteDraft.revision))setDraftRevision(remoteDraft.revision)
   const localDraft=readLocal<{baseRevision:number|null;value:SourceDraft} | null>(storageKey+':source-draft',null)
   const draftValue=localDraft&&localDraft.baseRevision===(remoteDraft?.revision??null)?localDraft.value:remoteDraft?.value??localDraft?.value
   if(source&&draftValue&&draftValue.export_token===data.export_token){setScopeMode(draftValue.selected_uids==null?'all':'selected');setScope(draftValue.selected_uids??[]);setOverrides(draftValue.overrides??{});setStem(draftValue.stem);setAnswerOnly(draftValue.answerOnly);setFilename(draftValue.filename||data.title)}
   else if(draftValue)setMessage('来源内容已更新，旧内容草稿不会自动应用。')
   setHasDraft(Boolean(current));setTemplateId(defaultTemplate.id);setLayout(current?sanitizeLayout(current):{...sanitizeLayout(defaultTemplate.layout),originalNumbers:source});setDoc(data);if(!source||!draftValue||draftValue.export_token!==data.export_token)setFilename(data.title);setLoadedKey(storageKey)
  }).catch(e=>{if(!c.signal.aborted)setError(e.message)})
  return()=>c.abort()
 },[id,source,chapterUid,storageKey,layoutPath,draftPath])
 useEffect(()=>{
  if(!doc||loadedKey!==storageKey||layoutError(layout))return
  if(!writeLocal(storageKey,{value:layout,baseRevision:cloudRevision}))setMessage('浏览器无法保存排版设置，请保持当前页面。')
 },[doc,layout,loadedKey,storageKey,cloudRevision])
 const draftValue:SourceDraft|undefined=source&&doc?.export_token?{export_token:doc.export_token,selected_uids:scopeMode==='all'?null:scope,overrides,stem,answerOnly,filename}:undefined
 useEffect(()=>{if(draftValue&&loadedKey===storageKey&&editing&&!writeLocal(storageKey+':source-draft',{baseRevision:draftRevision,value:draftValue}))setMessage('浏览器无法保存内容草稿，请保存到服务器。')},[doc,scope,scopeMode,overrides,stem,answerOnly,filename,loadedKey,storageKey,draftRevision,editing])
 const scopeSet=useMemo(()=>new Set(scope),[scope])
 const viewDoc=useMemo(()=>doc?{...doc,blocks:doc.blocks.filter(b=>scopeMode==='all'||scopeSet.has(b.uid)).map(b=>{
  const edit=overrides[b.uid];if(!edit)return b
  return {...b,...edit,local_fields:Array.from(new Set([...(b.local_fields??[]),...Object.keys(edit)])) as Block['local_fields']}
 })}:undefined,[doc,scopeMode,scopeSet,overrides])
 const renderVersion=useMemo(()=>({viewDoc,stem,answerOnly}),[viewDoc,stem,answerOnly])
 const activeEdit=doc?.blocks.find(b=>b.uid===editUid)
 function invalidate(){setConfirmed(false);setReady(false)}
 const patch=(values:Partial<Layout>)=>{setConfirmed(false);setReady(false);setLayout(old=>({...old,...values}))}
 const compatible=[...builtins,...templates].filter(t=>t.kind==='all'||t.kind===doc?.kind)
 const selected=compatible.find(t=>t.id===templateId)
 function apply(){
  if(!selected)return
  const next=templateLayout(sanitizeLayout(selected.layout))
  if(source)next.originalNumbers=layout.originalNumbers
  if(applyMode==='partial'){
   const groups:Record<string,(keyof Layout)[]>={page:['paper','width','height','landscape','top','bottom','left','right','columns','gap','mirrorMargins','chapterNewPage'],body:['font','size','lineHeight','paragraphGap','titleSize','headingSize','keepQuestions','equationNumbering'],special:['subtitle','examTime','showScore','typeHeadings','numbering','optionColumns','blankWidth','answerSpace','originalNumbers'],header:['header','footer','toc','tocDepth'],types:['typeStyles']}
   const chosen=new Set(applyParts.flatMap(part=>groups[part]??[]))
   for(const key of Object.keys(next) as (keyof Layout)[])if(!chosen.has(key))Object.assign(next,{[key]:layout[key]})
  }
  if(applyMode!=='replace'){next.blockStyles=layout.blockStyles;next.chapterStyles=layout.chapterStyles;next.sectionPages=layout.sectionPages}
  setLayout(next);setConfirmed(false);setReady(false);setEditing(true);setMessage('已应用模板，原始教学内容保持不变。')
 }
 async function saveCloud(){
  if(cloudRevision===null||cloudBusy||layoutError(layout))return
  const key=storageKey;setCloudBusy(true)
  try{const saved=await api<Saved<Layout>>(layoutPath,{method:'PUT',body:JSON.stringify({revision:cloudRevision,value:layout})});if(routeRef.current!==key)return;setCloudRevision(saved.revision);setCloudLayout(sanitizeLayout(saved.value));setLayoutHistory(saved.history??[]);
   if(draftValue&&draftRevision!==null){const draft=await api<Saved<SourceDraft>>(draftPath,{method:'PUT',body:JSON.stringify({revision:draftRevision,value:draftValue})});if(routeRef.current!==key)return;setDraftRevision(draft.revision)}
   setMessage('排版配置已保存到服务器，可跨设备读取。')}
  catch(e){if(routeRef.current===key)setMessage(e instanceof Error?e.message:'服务器保存失败，当前浏览器草稿仍保留。')}
  finally{if(routeRef.current===key)setCloudBusy(false)}
 }
 async function clearDraft(){
  if(!source||cloudBusy||!window.confirm('清除来源导出草稿？原资料不会改变。'))return
  const key=storageKey;setCloudBusy(true)
  try{if(draftRevision!==null){await api(draftPath+'?revision='+draftRevision,{method:'DELETE'});if(routeRef.current!==key)return;setDraftRevision(0)}
   localStorage.removeItem(storageKey+':source-draft');setOverrides({});setScope([]);setScopeMode('all');setStem(false);setAnswerOnly(false);setFilename(doc?.title??'');invalidate();setMessage('内容草稿已清除。')
  }catch(e){if(routeRef.current===key)setMessage(e instanceof Error?e.message:'草稿清除失败')}
  finally{if(routeRef.current===key)setCloudBusy(false)}
 }
 async function persistTemplates(list:LayoutTemplate[],messageText:string,choose?:string){
  if(cloudBusy||list.length>100)return
  const key=storageKey;setCloudBusy(true)
  try{
   if(templateRevision!==null){
    const result=await api<Saved<LayoutTemplate[]>>('/settings/document-templates',{method:'PUT',body:JSON.stringify({revision:templateRevision,value:list})})
    if(routeRef.current!==key)return
    setTemplateRevision(result.revision);setTemplateHistory(result.history??[])
   }
   setTemplates(list)
   const cached=writeLocal('wg-layout-templates-v1',list)
   if(choose)setTemplateId(choose)
   setTemplateName('');setMessage(messageText+(templateRevision===null?(cached?'（保存在本浏览器）':'（本地保存失败）'):'到服务器。'))
  }catch(e){if(routeRef.current===key)setMessage(e instanceof Error?e.message:'模板保存失败')}
  finally{if(routeRef.current===key)setCloudBusy(false)}
 }
 async function saveTemplate(){
  if(!templateName.trim()||layoutError(layout))return
  const kind:LayoutTemplate['kind']=doc?.kind==='paper'||doc?.kind==='handout'||doc?.kind==='textbook'?doc.kind:'all'
  if(templates.length>=100){setMessage('个人模板已达到 100 个，请先删除不用的模板。');return}
  const item:LayoutTemplate={id:crypto.randomUUID(),name:templateName.trim().slice(0,80),kind,layout:templateLayout(layout)}
  await persistTemplates([...templates,item],'模板已保存',item.id)
 }
 async function removeTemplate(){
  if(!templates.some(t=>t.id===templateId))return
  await persistTemplates(templates.filter(t=>t.id!==templateId),'模板已删除',builtins.find(t=>t.kind===doc?.kind)?.id??'general')
 }
 async function updateTemplate(mode:'rename'|'replace'|'default'|'copy'){
  const item=selected
  if(!item)return
  const own=templates.some(t=>t.id===item.id)
  if(mode==='copy'){
   if(templates.length>=100){setMessage('个人模板最多100个。');return}
   const copied={...item,id:crypto.randomUUID(),name:(templateName.trim()||item.name+' 副本').slice(0,80),isDefault:false,layout:templateLayout(item.layout)}
   await persistTemplates([...templates,copied],'模板已复制',copied.id);return
  }
  if(!own)return
  if(mode==='rename'&&!templateName.trim())return
  if(mode==='replace'&&layoutError(layout))return
  const list=templates.map(t=>mode==='default'&&t.kind===item.kind?{...t,isDefault:t.id===item.id}:t.id!==item.id?t:mode==='rename'?{...t,name:templateName.trim().slice(0,80)}:mode==='replace'?{...t,layout:templateLayout(layout)}:t)
  await persistTemplates(list,mode==='default'?'默认模板已保存':'模板已更新',item.id)
 }
 function exportTemplate(){
  if(!selected)return
  const data={version:1,template:{...selected,layout:templateLayout(selected.layout),isDefault:false}}
  const href=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}))
  const a=document.createElement('a');a.href=href;a.download=selected.name+'.json';a.click();window.setTimeout(()=>URL.revokeObjectURL(href),1000)
 }
 async function importTemplate(file:File|undefined){
  if(!file||cloudBusy)return
  try{
   if(file.size>1_000_000||templates.length>=100)throw Error('模板文件过大或个人模板已满。')
   const parsed=JSON.parse(await file.text()),item=parsed.template
   if(parsed.version!==1||!item||typeof item.name!=='string'||!item.name.trim()||!['paper','handout','textbook','all'].includes(item.kind)||!item.layout||typeof item.layout!=='object')throw Error('不支持的模板格式')
   const imported:LayoutTemplate={id:crypto.randomUUID(),name:item.name.trim().slice(0,80),kind:item.kind,layout:templateLayout(sanitizeLayout(item.layout)),isDefault:false}
   if(layoutError(imported.layout))throw Error(layoutError(imported.layout))
   await persistTemplates([...templates,imported],'模板已导入',imported.id)
  }catch(e){setMessage(e instanceof Error?e.message:'模板导入失败')}
 }
 const [w,h]=dimensions(layout),invalid=layoutError(layout)
 const style={'--layout-width':w+'mm','--layout-height':h+'mm','--layout-top':layout.top+'mm','--layout-bottom':layout.bottom+'mm','--layout-left':layout.left+'mm','--layout-right':layout.right+'mm','--layout-columns':layout.columns,'--layout-gap':layout.gap+'mm','--layout-size':layout.size+'pt','--layout-line':layout.lineHeight,'--layout-paragraph':layout.paragraphGap+'pt','--layout-font':layout.font==='sans'?'"Noto Sans CJK SC","Microsoft YaHei",sans-serif':'"Noto Serif CJK SC",SimSun,serif'} as CSSProperties
 const num=(label:string,key:'width'|'height'|'top'|'bottom'|'left'|'right'|'gap'|'size'|'lineHeight'|'paragraphGap'|'answerSpace'|'titleSize'|'headingSize'|'blankWidth',min:number,max:number,step=1)=><label>{label}<input type="number" min={min} max={max} step={step} value={layout[key]} onChange={e=>{const value=e.currentTarget.valueAsNumber;if(Number.isFinite(value))patch({[key]:Math.max(min,Math.min(max,value))})}}/></label>
 return <div className="print-work layout-work" style={style}>
  <style>{'@page{size:'+w+'mm '+h+'mm;margin:0}'}</style>
  <header className="print-controls layout-toolbar">
   <Link className="button-link" to={back}>{source?'返回来源库':'返回编辑'}</Link>
   <strong>文档排版</strong>
   {editing&&<><button type="button" aria-pressed={controls} onClick={()=>setControls(true)}>排版设置</button><button type="button" aria-pressed={!controls} onClick={()=>setControls(false)}>预览</button></>}
  </header>
  {error&&<p role="alert">{error}</p>}
  {doc&&<div className="print-controls layout-template-panel">
   <label>选择排版模板<select aria-label="选择排版模板" value={templateId} onChange={e=>setTemplateId(e.target.value)}>{compatible.map(t=><option key={t.id} value={t.id}>{t.name}{t.isDefault?'（默认）':''}</option>)}</select></label>
   <button className={editing?'':'primary'} type="button" disabled={!selected} onClick={apply}>{editing?'应用模板':'进入排版工作台'}</button>
   {!editing&&hasDraft&&<button type="button" onClick={()=>setEditing(true)}>继续上次排版</button>}{editing&&<><button type="button" disabled={cloudBusy||cloudRevision===null||!!invalid} onClick={()=>void saveCloud()}>保存排版到服务器</button><label>新模板名称<input value={templateName} maxLength={80} onChange={e=>setTemplateName(e.target.value)} placeholder="保存当前排版"/></label><button type="button" disabled={cloudBusy||!templateName.trim()||!!invalid} onClick={()=>void saveTemplate()}>保存为模板</button><button type="button" disabled={cloudBusy||!templates.some(t=>t.id===templateId)} onClick={()=>void removeTemplate()}>删除个人模板</button></>}
   {editing&&controls&&<details><summary>模板管理与应用方式</summary><div className="layout-fields">
    <label>应用方式<select value={applyMode} onChange={e=>setApplyMode(e.target.value as typeof applyMode)}><option value="keep">保留局部修改</option><option value="replace">完全替换排版</option><option value="partial">仅应用指定设置</option></select></label>
    {applyMode==='partial'&&[['page','页面与分栏'],['body','字体与段落'],['special','文档专项规则'],['header','目录及页眉页脚'],['types','同类内容样式']].map(([v,t])=><label key={v} className="layout-check"><input type="checkbox" checked={applyParts.includes(v)} onChange={e=>setApplyParts(old=>e.target.checked?[...old,v]:old.filter(x=>x!==v))}/>{t}</label>)}
    <button type="button" disabled={!selected||cloudBusy} onClick={()=>void updateTemplate('copy')}>复制模板</button>
    <button type="button" disabled={!templates.some(t=>t.id===templateId)||cloudBusy||!templateName.trim()} onClick={()=>void updateTemplate('rename')}>重命名</button>
    <button type="button" disabled={!templates.some(t=>t.id===templateId)||cloudBusy||!!invalid} onClick={()=>void updateTemplate('replace')}>更新所选模板</button>
    <button type="button" disabled={!templates.some(t=>t.id===templateId)||cloudBusy} onClick={()=>void updateTemplate('default')}>设为同类默认模板</button>
    <button type="button" disabled={!selected} onClick={exportTemplate}>导出模板 JSON</button>
    <label>导入模板 JSON<input type="file" accept=".json,application/json" disabled={cloudBusy} onChange={e=>{const file=e.currentTarget.files?.[0];e.currentTarget.value='';void importTemplate(file)}}/></label>
    {templateHistory.map(v=><button key={v.revision} disabled={cloudBusy} onClick={()=>{if(window.confirm('恢复模板历史版本 '+v.revision+'？'))void persistTemplates(v.value.map(t=>({...t,layout:templateLayout(sanitizeLayout(t.layout))})),'模板历史已恢复','general')}}>恢复模板版本 {v.revision}</button>)}
    {layoutHistory.filter(v=>v.value).map(v=><button key={v.revision} onClick={()=>{if(window.confirm('恢复排版版本 '+v.revision+'？')){invalidate();setLayout(sanitizeLayout(v.value));setMessage('已载入历史排版，请保存确认。')}}}>载入排版版本 {v.revision}</button>)}
   </div></details>}
   {localRecovery&&<button onClick={()=>{setLayout(localRecovery);setLocalRecovery(null);invalidate();setMessage('本地排版已恢复，请检查并保存。')}}>恢复未同步的本地排版</button>}
   {message&&<p role="status">{message}</p>}
   <small className="muted">{cloudRevision===null?'排版草稿自动保存在当前浏览器。':cloudLayout&&JSON.stringify(cloudLayout)===JSON.stringify(layout)?'排版已同步至服务器。':'本地草稿自动保存，点击保存排版到服务器后可跨设备使用。'} 不修改题库或来源。</small>
  </div>}
  {source&&doc&&<p className="print-controls muted">{doc.has_source_content?'仅导出已入库批次及其他正式关联资源，不包含未入库草稿。':'此来源尚无已录入的关联内容，仅显示来源登记信息。'}</p>}
  {chapterUid&&doc&&<p className="print-controls muted">当前仅导出所选章节内容。</p>}
  {doc&&editing&&<>
   {controls&&source&&<section className="print-controls layout-settings"><details><summary>来源导出范围与局部内容</summary>
    <label>导出范围<select value={scopeMode} onChange={e=>{invalidate();setScopeMode(e.target.value as 'all'|'selected');if(e.target.value==='selected'&&!scope.length)setScope(doc.blocks.map(b=>b.uid))}}><option value="all">全部已入库内容</option><option value="selected">自由选择内容</option></select></label>
    {scopeMode==='selected'&&<div className="layout-selection"><button onClick={()=>{invalidate();setScope(doc.blocks.map(b=>b.uid))}}>全选</button><button onClick={()=>{invalidate();setScope([])}}>清空</button>{doc.blocks.map((b,i)=><label key={b.uid}><input type="checkbox" checked={scopeSet.has(b.uid)} onChange={e=>{invalidate();setScope(old=>e.target.checked?[...old,b.uid]:old.filter(x=>x!==b.uid))}}/>{i+1}. <MathText compact content={(b.snapshot??b).title||(b.snapshot??b).content.slice(0,100)}/></label>)}</div>}
    <label>仅修改当前导出副本<select value={editUid} onChange={e=>setEditUid(e.target.value)}><option value="">选择内容</option>{doc.blocks.map((b,i)=><option key={b.uid} value={b.uid}>{i+1}. {(b.snapshot??b).title||b.kind}</option>)}</select></label>
    {activeEdit&&(['title','content','answer','solution','analysis','proof'] as const).map(field=><label key={field}>{({title:'标题',content:'正文',answer:'答案',solution:'解析',analysis:'思路',proof:'证明'})[field]}<textarea rows={3} value={overrides[editUid]?.[field]??(activeEdit.local_fields?.includes(field)?activeEdit[field]:(activeEdit.snapshot??activeEdit)[field])??''} onChange={e=>{invalidate();setOverrides(old=>({...old,[editUid]:{...old[editUid],[field]:e.target.value}}))}}/></label>)}
    {activeEdit&&<button onClick={()=>{invalidate();setOverrides(old=>Object.fromEntries(Object.entries(old).filter(([k])=>k!==editUid)))}}>恢复该条原内容</button>}
    <button disabled={cloudBusy} onClick={()=>void clearDraft()}>清除来源内容草稿</button><small>仅影响本次导出副本，不写回来源库或题库；保存排版到服务器时同步保存内容草稿。</small>
   </details></section>}
   {controls&&<section className="print-controls layout-settings">
    <details open><summary>页面与分栏</summary><div className="layout-fields">
     <label>纸张<select aria-label="纸张" value={layout.paper} onChange={e=>patch({paper:e.target.value as Layout['paper']})}>{['A4','A3','A5','B5','A6','custom'].map(p=><option key={p} value={p}>{p==='custom'?'自定义':p}</option>)}</select></label>
     <label>方向<select value={layout.landscape?'landscape':'portrait'} onChange={e=>patch({landscape:e.target.value==='landscape'})}><option value="portrait">纵向</option><option value="landscape">横向</option></select></label>
     {layout.paper==='custom'&&<>{num('宽度 (mm)','width',50,1000)}{num('高度 (mm)','height',50,1000)}</>}
     {num('上边距 (mm)','top',0,100)}{num('下边距 (mm)','bottom',0,100)}{num('左边距 (mm)','left',0,100)}{num('右边距 (mm)','right',0,100)}
     <label>分栏<select value={layout.columns} onChange={e=>patch({columns:Number(e.target.value) as Layout['columns']})}><option value={1}>单栏</option><option value={2}>双栏</option><option value={3}>三栏</option></select></label>
     {layout.columns>1&&num('栏间距 (mm)','gap',3,30)}
    </div></details>
    <details><summary>正文与数学排版</summary><div className="layout-fields">
     <label>正文字体<select value={layout.font} onChange={e=>patch({font:e.target.value as Layout['font']})}><option value="serif">宋体类</option><option value="sans">黑体类</option></select></label>
     {num('字号 (pt)','size',6,36,.5)}{num('主标题字号 (pt)','titleSize',8,36,.5)}{num('章节标题字号 (pt)','headingSize',8,36,.5)}{num('行距','lineHeight',1,3,.1)}{num('段后间距 (pt)','paragraphGap',0,50)}
     <label>独立公式编号<select aria-label="独立公式编号" value={layout.equationNumbering} onChange={e=>patch({equationNumbering:e.target.value as Layout['equationNumbering']})}><option value="off">不自动编号</option><option value="continuous">全文连续编号</option><option value="chapter">按章编号</option></select></label>
     <label className="layout-check"><input type="checkbox" checked={layout.keepQuestions} onChange={e=>patch({keepQuestions:e.target.checked})}/>尽量保持题目完整</label>
     <label className="layout-check"><input type="checkbox" checked={layout.originalNumbers} onChange={e=>patch({originalNumbers:e.target.checked})}/>保留已有原题号</label>
     {doc.kind==='paper'&&num('每题答题留白 (mm)','answerSpace',0,180,5)}
    </div></details>
    <details><summary>文档专项排版</summary><div className="layout-fields">
     <label>副标题<input value={layout.subtitle} maxLength={200} onChange={e=>patch({subtitle:e.target.value})}/></label>
     {doc.kind==='paper'&&<><label>考试时间<input value={layout.examTime} maxLength={200} placeholder="例如 180 分钟" onChange={e=>patch({examTime:e.target.value})}/></label>
     <label className="layout-check"><input type="checkbox" checked={layout.showScore} onChange={e=>patch({showScore:e.target.checked})}/>显示分值与总分</label>
     <label className="layout-check"><input type="checkbox" checked={layout.typeHeadings} onChange={e=>patch({typeHeadings:e.target.checked})}/>按已有题型自动生成分组标题</label>
     <label>选择题选项排列<select value={layout.optionColumns} onChange={e=>patch({optionColumns:e.target.value==='auto'?'auto':Number(e.target.value) as 1|2|4})}><option value="auto">自动</option><option value="1">竖排</option><option value="2">双列</option><option value="4">四列</option></select></label>
     {num('填空横线长度 (mm，0 保留原样)','blankWidth',0,100)}</>}
     <label>题号规则<select value={layout.numbering} onChange={e=>patch({numbering:e.target.value as Layout['numbering']})}><option value="continuous">连续编号</option><option value="section">按章或题型重新编号</option></select></label>
    </div></details>
    <SectionPageEditor doc={doc} layout={layout} onChange={patch}/>
    <BlockStyleEditor doc={doc} layout={layout} onChange={patch} picked={picked}/>
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
    <label><input type="checkbox" checked={stem} onChange={e=>{setStem(e.target.checked);if(e.target.checked)setAnswerOnly(false);setConfirmed(false);setReady(false)}}/> {doc.kind==='paper'?'仅题目':'学生版（隐藏答案与解析）'}</label>
    {!stem&&<label><input type="checkbox" checked={answerOnly} onChange={e=>{setAnswerOnly(e.target.checked);setConfirmed(false);setReady(false)}}/> 仅答案（不含解析）</label>}
    <label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} disabled={!ready||!!invalid}/> 已检查预览，确认无问题</label>
    <button className="primary" disabled={!ready||!confirmed||!!invalid} onClick={async()=>{await document.fonts.ready;window.print()}}>打印 / 保存为 PDF</button>
    <label>文件名<input value={filename} onChange={e=>setFilename(e.target.value)} maxLength={200}/></label><small className="muted">{pageCount?`共 ${pageCount} 页`:"正在计算页数"} · 当前分页预览使用实际纸张尺寸。</small>
   </div>
   {doc.export_token&&<PdfJobs path={'/document-pdf/'+(source?'source':'doc')+'/'+encodeURIComponent(id??'')} canExport={ready&&confirmed&&!invalid&&!!filename.trim()} pageCount={pageCount} request={{export_token:doc.export_token,layout,stem,answerOnly,selected_uids:scopeMode==='all'?null:scope,overrides,chapter_uid:chapterUid,filename,confirmed:true}}/>}
   {invalid&&<p role="alert">{invalid}</p>}{previewError&&<p role="alert" className="print-controls">{previewError}</p>}
   {!invalid&&viewDoc&&viewDoc.blocks.length>0&&<div className="print-preview-content layout-preview" onClick={e=>{const target=e.target as HTMLElement;if(target.closest("a"))return;const uid=target.closest<HTMLElement>(".layout-pages [data-layout-uid]")?.dataset.layoutUid;if(uid&&doc.blocks.some(b=>b.uid===uid)){setPicked(uid);setControls(true)}}}><PagedPreview layout={layout} title={viewDoc.title} subject={viewDoc.subject??''} version={renderVersion} onResult={result=>{setPageCount(result.pages);setPreviewError(result.error);setReady(Boolean(result.pages)&&!result.error);setConfirmed(false)}}><PrintableDocument doc={viewDoc} stem={stem} answerOnly={answerOnly} source={source} layout={layout}/></PagedPreview></div>}
   {viewDoc&&!viewDoc.blocks.length&&<p role="alert">请选择至少一个内容条目。</p>}
  </>}
 </div>
}

const roleNames:Record<Role,string>={normal:'',knowledge:'知识点',definition:'定义',theorem:'定理',lemma:'引理',corollary:'推论',proof:'证明',example:'例',exercise:'练习',method:'方法',warning:'易错点',summary:'小结'}
function effective(b:Block):Content{
 const v={...(b.snapshot??b)}
 for(const field of b.local_fields??[])v[field]=b[field]
 for(const field of b.hidden_fields??[])v[field]=''
 return v
}
function blockCss(rule:BlockStyle):CSSProperties{
 return {fontSize:rule.size===undefined?undefined:rule.size+'pt',lineHeight:rule.lineHeight,marginBottom:rule.paragraphGap===undefined?undefined:rule.paragraphGap+'pt',textAlign:rule.align,fontWeight:rule.bold===undefined?undefined:rule.bold?700:400}
}
function RichPrint({content,labels,blankWidth=0}:{content:string;labels:Map<string,string>;blankWidth?:number}){
 const raw=blankWidth>0?content.replaceAll('\\underline{\\qquad}','\\underline{\\hspace{'+blankWidth+'mm}}'):content
 if(!raw.includes('[[ref:'))return <ChatText content={raw}/>
 return <div className="layout-rich-reference">{raw.split(/(\[\[ref:[A-Za-z0-9_-]{1,100}\]\])/g).filter(Boolean).map((part,i)=>{
  const m=part.match(/^\[\[ref:([A-Za-z0-9_-]{1,100})\]\]$/)
  return m?(labels.has(m[1])?<a key={i} href={'#layout-block-'+m[1]} className="layout-cross-ref">{labels.get(m[1])}</a>:<span key={i} data-layout-reference-error="true">[失效引用：{m[1]}]</span>):<MathText key={i} compact content={part}/>
 })}</div>
}
export function PrintableDocument({doc,stem=false,answerOnly=false,source=false,sourceId,layout}:{doc:PrintDoc;stem?:boolean;answerOnly?:boolean;source?:boolean;sourceId?:string;layout?:Layout}){
 let n=0,chapter='',type='',group=0
 const counts:Record<string,number>={},labels=new Map<string,string>()
 const hasHeadings=doc.blocks.some(b=>b.kind==='heading')
 const rows=doc.blocks.map(b=>{
  const v=effective(b),question=v.kind==='question',kind=question?'question':b.kind==='heading'?'heading':v.kind
  if(b.kind==='heading'&&b.heading_level===1){chapter=b.uid;if(layout?.numbering==='section')n=0}
  const generic={...layout?.typeStyles[kind],...(v.question_type?layout?.typeStyles[v.question_type]:{})}
  const specific={...layout?.chapterStyles[chapter],...layout?.blockStyles[b.uid]}
  const role=specific.role??generic.role??'normal'
  const rule:BlockStyle={...generic,...layout?.typeStyles['role:'+role],...specific}
  const qtype=v.question_type||'其他题型'
  const section=Boolean(question&&doc.kind==='paper'&&layout?.typeHeadings&&!hasHeadings&&qtype!==type)
  if(section){type=qtype;group++;if(layout?.numbering==='section')n=0}
  if(question)n++
  const roleNumber=role!=='normal'?(counts[role]=(counts[role]??0)+1):0
  const number=layout?.originalNumbers&&b.original_question_number?b.original_question_number:String(n)
  const label=role!=='normal'?roleNames[role]+(role==='proof'||role==='warning'||role==='summary'?'':' '+roleNumber):question?'第 '+number+' 题':v.title||v.content.slice(0,60)
  labels.set(b.uid,label)
  return {b,v,question,role,roleNumber,rule,number,section,group,qtype}
 })
 const score=doc.blocks.reduce((sum,b)=>sum+(b.score??0),0)
 const groups=new Map<number,{count:number;score:number}>()
 for(const row of rows)if(row.question){const g=groups.get(row.group)??{count:0,score:0};g.count++;g.score+=row.b.score??0;groups.set(row.group,g)}
 const chinese=['','一','二','三','四','五','六','七','八','九','十']
 return <article className={"print-document"+(layout?" configured-print":"")}>
  <h1><MathText compact content={doc.title}/></h1>
  <div className="print-subtitle"><MathText compact content={layout?.subtitle??''}/>{layout?.subtitle&&<br/>}{doc.subject}{doc.kind==='paper'&&(!source||score>0)&&layout?.showScore!==false&&' · 总分 '+score}{layout?.examTime&&' · 考试时间：'+layout.examTime}</div>
  <div className="layout-body">{rows.map(({b,v,question,role,roleNumber,rule,number,section,group,qtype})=>{
   if(b.kind==='pagebreak')return <div key={b.uid} className="print-break"/>
   const common={style:blockCss(rule),'data-layout-uid':b.uid,'data-layout-break':rule.pageBreak}
   const frame=rule.frame?' layout-frame-'+rule.frame:''
   if(b.kind==='image')return <figure key={b.uid} {...common}><img src={'/api/files/'+b.file_id+'/preview'} alt={b.title} style={{width:b.width+'%'}}/><figcaption><MathText compact content={b.title}/></figcaption></figure>
   if(b.kind==='heading'){
    const level=rule.headingLevel??b.heading_level??2
    const Heading= ('h'+Math.min(6,level+1)) as 'h2'|'h3'|'h4'|'h5'|'h6'
    return <section className={'print-block print-heading-level-'+level+frame} key={b.uid} {...common} data-layout-level={level}><Heading><MathText compact content={v.title||v.content}/></Heading>{v.title&&v.content&&<RichPrint content={v.content} labels={labels}/>}</section>
   }
   const structured=v.question_data,options=structured?.options??[]
   const canUseOptions=!!layout&&question&&options.length>0&&[structured?.stem??'',...options.map(o=>o.label+'. '+o.content)].join('\n').trim()===v.content.trim()
   const space=rule.answerSpace??layout?.answerSpace??0
   if(answerOnly&&!question)return null
   return <Fragment key={b.uid}>
    {section&&<section className="print-block layout-type-heading" data-layout-level="2" data-layout-uid={'type-'+group}><h2>{chinese[group]??group}、{qtype}</h2><small>共 {groups.get(group)?.count??0} 题{(groups.get(group)?.score??0)>0&&layout?.showScore!==false?'，共 '+groups.get(group)?.score+' 分':''}</small></section>}
    <section className={"print-block"+(question&&layout?.keepQuestions?" layout-keep":"")+frame} {...common}>
     {source&&sourceId&&b.resource_id&&<Link className="print-controls source-edit-link" to={'/resource-edit/'+encodeURIComponent(b.resource_id)+'?return_source='+encodeURIComponent(sourceId)}>编辑{question?'题目':'知识单元'}</Link>}
     {question?<p className="print-question-number">{role!=='normal'?roleNames[role]+' '+roleNumber:number+'.'} {b.score&&layout?.showScore!==false?'（本题满分 '+b.score+' 分）':''}</p>:role!=='normal'||v.title?<h2>{role!=='normal'&&roleNames[role]+(role==='proof'||role==='warning'||role==='summary'?'：':' '+roleNumber+'　')}<MathText compact content={v.title}/></h2>:null}
     {!answerOnly&&(canUseOptions?<><RichPrint content={structured?.stem??''} labels={labels}/><div className="layout-options" data-option-layout={String(rule.optionColumns??layout?.optionColumns??'auto')}>{options.map(o=><div className="layout-option" key={o.label}><span>{o.label}. </span><MathText compact content={o.content}/></div>)}</div></>:<RichPrint content={v.content} labels={labels} blankWidth={layout?.blankWidth}/>)}
     {!answerOnly&&question&&!!b.subquestion_scores?.length&&layout?.showScore!==false&&<p className="print-question-number">{b.subquestion_scores.map((value,i)=>'（'+(i+1)+'）'+value+'分').join('　')}</p>}
     {stem&&question&&space>0&&<div className="layout-answer-space" style={{height:space+'mm'}}/>}
     {!stem&&<>{v.answer&&<div>答案：<RichPrint content={v.answer} labels={labels}/></div>}{!answerOnly&&v.analysis&&<div>思路：<RichPrint content={v.analysis} labels={labels}/></div>}{!answerOnly&&v.solution&&<div>解析：<RichPrint content={v.solution} labels={labels}/></div>}{!answerOnly&&v.proof&&<div>证明：<RichPrint content={v.proof} labels={labels}/></div>}</>}
    </section>
   </Fragment>
  })}</div>
 </article>
}
