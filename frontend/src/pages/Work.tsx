import {useEffect,useRef,useState,type FormEvent} from 'react'
import {useNavigate,useLocation,useSearchParams} from 'react-router-dom'
import {useWorkspaceGuard} from '../components/WorkspaceNavigation'
import {confirmAction} from '../components/WorkspaceConfirm'
import IntakeReview from './Intelligence'
import PersistentWork from './PersistentWork'
import {AttachmentDialog,AttachmentMenu,AttachmentStrip,ResourceAttachmentPicker,type AttachmentItem} from '../components/ComposerAttachments'
import {OriginalPicker,type OriginalFile} from '../components/OriginalPicker'
import SourcePicker from '../components/SourcePicker'
import {validModelChoice,type ModelCatalog,type ModelPreferences} from '../components/ReasoningEffort'
import ComposerInference from '../components/ComposerInference'
import {api} from '../auth'
import {getModelCatalog,modelChoice,rememberModelChoice} from '../components/modelCatalog'
import {Icon} from '../components/Icon'
import {MathText} from '../components/MathText'
import {AiHomeHeading,AiHomeShortcuts} from '../components/AiHome'
import {readModeDraft,useModeDraft} from '../components/modeDrafts'
import type {ImportedMaterial} from '../components/MaterialImport'
type Job={id:string;title:string;state:string}
type Cap={text:boolean;docx:boolean;pdf_text:boolean;pdf_ocr:boolean;image_ocr:boolean;image_ocr_missing?:string[];pdf_ocr_missing?:string[];pdf_text_missing?:string[];repair_command?:string}
type FileInfo={id:string;name:string;media_type:string}
type ChatSource={message_id:string;session_id:string;role:string;text:string;title:string;has_attachments:boolean}
type Transfer={text?:string;origin?:string}
type WorkDraft={additional?:File[];library?:OriginalFile[];draft:string;file?:File;stored?:FileInfo;imported?:ImportedMaterial;reviewed:boolean;first:number;last:number;ocr:boolean;intent:string;subject:string;materialSource:string;source?:ChatSource;transferred?:Transfer}
export default function Work(){const location=useLocation(),[params]=useSearchParams();return params.has('workspace')?<PersistentWork key={params.get('workspace')} id={params.get('workspace')!}/>:params.has('job')||params.has('history')?<IntakeReview key={location.pathname+location.search}/>:<WorkComposer key={location.key}/>}
function WorkComposer(){
 const location=useLocation(),[params]=useSearchParams()
 const navigate=useNavigate(),input=useRef<HTMLInputElement>(null),area=useRef<HTMLTextAreaElement>(null),form=useRef<HTMLFormElement>(null)
 const route=location.pathname+location.search
 const [restored]=useState(()=>readModeDraft<WorkDraft>('work',route,location.state))
 const transferred=restored?.transferred??(location.state as {intakeDraft?:Transfer}|null)?.intakeDraft
 const [draft,setDraft]=useState(restored?.draft??transferred?.text??(location.state as {workInstruction?:string}|null)?.workInstruction??''),[file,setFile]=useState<File|undefined>(restored?.file),[stored,setStored]=useState<FileInfo|undefined>(restored?.stored),[imported,setImported]=useState<ImportedMaterial|undefined>(restored?.imported),[reviewed,setReviewed]=useState(restored?.reviewed??false)
 const [additional,setAdditional]=useState<File[]>(restored?.additional??[]),[library,setLibrary]=useState<OriginalFile[]>(restored?.library??[]),[resourcePicker,setResourcePicker]=useState<'question'|'knowledge'>(),plus=useRef<HTMLButtonElement>(null)
 const [first,setFirst]=useState(restored?.first??1),[last,setLast]=useState(restored?.last??1),[ocr,setOcr]=useState(restored?.ocr??false),[tools,setTools]=useState(false),[libraryPicker,setLibraryPicker]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[caps,setCaps]=useState<Cap>()
 const [model,setModel]=useState('Auto'),[models,setModels]=useState<ModelCatalog['models']>([]),[catalog,setCatalog]=useState<ModelCatalog>(),[effort,setEffort]=useState('default'),[intent,setIntent]=useState(restored?.intent??'mixed'),[subject,setSubject]=useState(restored?.subject??''),[ready,setReady]=useState(false)
 const [materialSource,setMaterialSource]=useState(restored?.materialSource??params.get('source')??''),[source,setSource]=useState<ChatSource|undefined>(restored?.source),[sourceLoading,setSourceLoading]=useState(Boolean(params.get('from')&&!restored?.source&&!restored?.file))
 useEffect(()=>{const id=params.get('from');if(!id||restored?.source||restored?.file)return;const c=new AbortController();const wanted=params.get('intent');if(wanted&&['mixed','question','knowledge','document'].includes(wanted))setIntent(wanted);api<NonNullable<typeof source>>('/intelligence/chat-source/'+encodeURIComponent(id),{signal:c.signal}).then(s=>{if(!c.signal.aborted){setSource(s);setDraft(s.text)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)}).finally(()=>{if(!c.signal.aborted)setSourceLoading(false)});return()=>c.abort()},[params])
 const pdf=Boolean(file?.name.toLowerCase().endsWith('.pdf')),word=Boolean(file?.name.toLowerCase().endsWith('.docx')),image=Boolean(file&&/\.(png|jpe?g|webp|gif)$/i.test(file.name))
 const supported=Boolean(caps&&(image||pdf?true:word?caps.docx:caps.text))
 const recognitionMissing=caps?(image||pdf?[]:[]):undefined
 const end=pdf||image?first:word?last:1
 const autonomous=!source&&!transferred&&!params.has('from')&&intent==='mixed'&&!imported&&!params.has('source')&&!params.has('manual')
 const validRange=Number.isInteger(first)&&Number.isInteger(end)&&first>=1&&end>=first&&end<=10000&&end-first<(word?100:10)
 useEffect(()=>{const c=new AbortController();api<Cap>('/intelligence/import/capabilities',{signal:c.signal}).then(setCaps).catch(e=>setError(e.message));Promise.all([api<ModelPreferences>('/qoder/preferences',{signal:c.signal}),getModelCatalog()]).then(([p,m])=>{if(c.signal.aborted)return;const saved=modelChoice('work',p.model,p.effort??'default');setModel(saved.model);setModels(m.models);setCatalog(m);setEffort(saved.effort);setReady(true)}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[])
 useEffect(()=>{const el=area.current;if(el){el.style.height='0px';el.style.height=Math.min(Math.max(el.scrollHeight,30),144)+'px'}},[draft])
 useEffect(()=>{if(tools)area.current?.blur()},[tools])
 useModeDraft('work',route,{draft,file,additional,library,stored,imported,reviewed,first,last,ocr,intent,subject,materialSource,source,transferred})
 useWorkspaceGuard({busy:busy||sourceLoading,preserveOnModeSwitch:true,dirty:Boolean(draft.trim()||file||imported||additional.length||library.length),message:'当前资料尚未提交，确认离开？'})
 function clearFile(){setAdditional([]);setFile(undefined);setStored(undefined);setImported(undefined);setReviewed(false);setFirst(1);setLast(1);setOcr(false)}
 function choose(f:File){clearFile();setSource(undefined);setError('');setFile(f);setLast(f.name.toLowerCase().endsWith('.docx')?100:1);setOcr(/\.(png|jpe?g|webp|gif)$/i.test(f.name));setTools(false)}
 function addFiles(list:FileList|null){const fs=Array.from(list??[]);if(!fs.length)return;setError('');if(fs.some(f=>!/\.(pdf|docx|txt|tex|md|csv|png|jpe?g|webp|gif)$/i.test(f.name))){setError('不支持的文件格式，请选择 PDF、Word、文本或 JPG/PNG/WebP/GIF 图片');return}if(fs.some(f=>f.size>200*1024*1024)){setError('单文件不能超过200 MB');return}if(!autonomous){if(file||fs.length!==1){setError('当前核对流程一次只支持一份资料');return}choose(fs[0]);return}if((file?1:0)+additional.length+library.length+fs.length>20){setError('一次最多20份资料');return}if(file)setAdditional(v=>[...v,...fs]);else{choose(fs[0]);setAdditional(fs.slice(1))}}
 function chooseLibrary(_ids:string[],rows:OriginalFile[]){const next=[...library,...rows.filter(r=>!library.some(x=>x.id===r.id))];if(next.length+additional.length+(file?1:0)>20){setError('一次最多20份资料');return}setLibrary(next);setLibraryPicker(false)}
 async function removeAttachment(key:string){if(key==='local-0'){if(imported&&!await confirmAction('清空已提取正文？'))return;if(imported)setDraft('');const rest=additional;clearFile();if(rest.length){setFile(rest[0]);setAdditional(rest.slice(1));setOcr(/\.(png|jpe?g|webp|gif)$/i.test(rest[0].name))}}else if(key.startsWith('local-'))setAdditional(v=>v.filter((_,i)=>i!==Number(key.slice(6))-1));else setLibrary(v=>v.filter(x=>x.id!==key))}
 const items:AttachmentItem[]=[...(file?[file,...additional]:[]).map((f,i)=>({key:'local-'+i,name:f.name,file:f})),...library.map(f=>({key:f.id,id:f.id,name:f.name,media_type:f.media_type}))]
 async function submit(e:FormEvent){
   e.preventDefault();if(busy)return;setError('');setBusy(true);setTools(false)
   try{
     if(autonomous){
       if(!ready||!validModelChoice(catalog,model,effort)||(!draft.trim()&&!file&&!library.length))throw Error('请输入工作要求并选择可用模型')
       const files=[...(file?[file]:[]),...additional]
       const instruction=draft.trim()||('识别 '+[...files,...library].map(f=>f.name).join('、')+' 的原文，PDF 每份先识别最多10页，并进入录入流程')
       if(instruction.length>2000)throw Error('工作指令最多2000字；长原文请作为附件上传')
       const s=await api<{id:string}>('/workspaces',{method:'POST',body:JSON.stringify({title:instruction.split('\n')[0].slice(0,200)})})
       const base='/workspaces/'+encodeURIComponent(s.id)
       let selected_id:string|undefined
       if(files.length||library.length){const ids:string[]=library.map(f=>f.id);for(const f of files){
         const result=await fetch('/api/files?name='+encodeURIComponent(f.name),{method:'POST',body:f,credentials:'same-origin'})
         if(!result.ok)throw Error(f.name+' 上传失败：'+result.status)
         ids.push((await result.json()).id)
       }const attached=await api<{sequence_material_id?:string;materials:{id:string;file:{id:string}}[]}>(base+'/materials',{method:'POST',body:JSON.stringify({file_ids:ids,image_sequence:ids.length>1&&[...files,...library].every(f=>/\.(png|jpe?g|webp|gif)$/i.test(f.name))})});selected_id=attached.sequence_material_id??(ids.length===1?attached.materials.find(m=>m.file.id===ids[0])?.id:undefined)}
       await api(base+'/agent',{method:'POST',body:JSON.stringify({instruction,model,effort,selected_id,single_review:true,chat_session_id:params.get('chatSession')})})
       window.dispatchEvent(new Event('wg-recent-changed'));navigate('/work?workspace='+encodeURIComponent(s.id));return
     }
     if(file&&!imported){
       if(!supported||!validRange)throw new Error('识别组件未就绪或页码范围无效')
       let info=stored
       if(!info){const r=await fetch('/api/files?name='+encodeURIComponent(file.name),{method:'POST',body:file,credentials:'same-origin'});if(!r.ok){const j=await r.json().catch(()=>({}));throw new Error(j.detail||'上传失败')}info=await r.json() as FileInfo;setStored(info)}
       const result=await api<ImportedMaterial>('/intelligence/import',{method:'POST',body:JSON.stringify({file_id:info.id,mode:pdf||image?'vision':'text',model,effort,start:pdf||word?first:1,end:pdf||word?end:1})})
       setImported(result);setReviewed(false);setDraft(result.text+(draft.trim()?'\n\n'+draft.trim():''));return
     }
     if(sourceLoading||(!file&&params.has('from')&&!source)||!draft.trim()||!ready||!validModelChoice(catalog,model,effort))throw new Error('请输入资料并选择可用模型')
     if(imported?.warnings.length&&!reviewed)throw new Error('请先对照原始文件核对识别内容')
     if(draft.length>24000)throw new Error('每批最多24000字，请拆分资料')
     const j=await api<Job>('/intelligence/jobs',{method:'POST',body:JSON.stringify({title:(file?.name||draft.trim().split('\n')[0]).slice(0,200),subject,text:draft,model,effort,intent,import_id:imported?.import_id??null,import_reviewed:reviewed,source_id:materialSource||null,source_message_id:imported?null:source?.message_id??null,input_origin:transferred?.origin==='draft'?'chat_draft':'manual'})})
     if(!j.id)throw new Error('未取得录入任务编号')
     window.dispatchEvent(new Event('wg-recent-changed'));navigate('/work?job='+encodeURIComponent(j.id))
   }catch(e){setError(e instanceof Error?e.message:'录入失败')}finally{setBusy(false)}
 }
 const home=!sourceLoading&&!source&&!transferred&&!imported&&!params.has('manual')
 const canSend=autonomous?ready&&validModelChoice(catalog,model,effort)&&Boolean(draft.trim()||file||library.length):!sourceLoading&&(!params.has('from')||Boolean(source)||Boolean(file))&&(file&&!imported?supported&&validRange:ready&&Boolean(draft.trim())&&validModelChoice(catalog,model,effort)&&(!imported?.warnings.length||reviewed))
 return <section data-chat-layout="v3" className={"chat-workbench clean-chat chat-main-area work-chat"+(home?" chat-empty ai-home":"")} aria-label="资料录入">
   {error&&<p className="chat-warning inline-error" role="alert">{error}</p>}{busy&&<p className="muted work-busy-state" role="status">{file&&!imported?"正在上传并提取文件原文…":"正在提交资料整理请求…"}</p>}
   <div className="chat-scroll">{params.get('chatSession')&&<div className="work-review-preview"><strong>已关联聊天上下文</strong><p className="muted">输入本次要执行的要求，AI 将参考该对话中的已完成消息、附件和题库引用。</p></div>}{sourceLoading?<p className="muted">正在读取聊天原文…</p>:source||transferred?<div className="work-review-preview"><strong>{source?.role==='assistant'||transferred?.origin==='assistant'?'来自 AI 回复的待核对草稿':'已带入聊天正文'}</strong><p className="muted">请核对正文后发送，附件和题库引用不会自动转入。</p></div>:null}{imported?<div className="work-review-preview"><strong>已识别：{imported.file_name}</strong><p className="muted">请核对下方原文；确认后再次发送，AI 将整理为待审核草稿。</p>{imported.warnings.map(w=><p key={w} className="muted">{w}</p>)}<div className="work-original-preview"><MathText content={draft}/></div>{Boolean(imported.warnings.length)&&<label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> 已对照原文件核对识别内容</label>}</div>:home?<AiHomeHeading mode="work"/>:null}</div>
   <form className="chat-composer compact-composer" ref={form} onSubmit={submit}>
    <AttachmentStrip items={items} disabled={busy} onRemove={key=>void removeAttachment(key)}/>
    {!autonomous&&file&&<div className="work-file">{!imported&&(pdf||word)&&<div className="work-file-range"><label>从<input type="number" min={1} max={10000} value={first} disabled={busy} onChange={e=>{setFirst(Number(e.target.value));setLast(Number(e.target.value))}}/></label>{word&&<label>至<input type="number" min={first} max={Math.min(10000,first+(word?99:9))} value={last} disabled={busy} onChange={e=>setLast(Number(e.target.value))}/></label>}</div>}{!autonomous&&!imported&&caps&&!supported&&<div className="ocr-capability-warning" role="alert"><strong>服务器识别环境未就绪</strong><p>{recognitionMissing?.length?'缺少：'+recognitionMissing.join('、'):'所需识别组件未就绪'}</p>{caps.repair_command&&<small>服务器管理员可执行：{caps.repair_command}</small>}</div>}</div>}
    {!autonomous&&<details className="work-manual-config"><summary>录入配置</summary><label>科目提示<input aria-label="科目提示" placeholder="自动逐题识别" value={subject} maxLength={40} onChange={e=>setSubject(e.target.value)}/></label><label>录入目标<select aria-label="录入目标" value={intent} onChange={e=>setIntent(e.target.value)}><option value="mixed">自动识别</option><option value="question">题目</option><option value="knowledge">知识点</option><option value="document">整套资料</option></select></label><SourcePicker value={materialSource} disabled={busy||sourceLoading} subject={subject} onChange={id=>setMaterialSource(id)}/></details>}
    <textarea ref={area} aria-label="输入录入资料" rows={1} maxLength={24000} placeholder={autonomous?'告诉 AI 要完成什么工作…':file&&!imported?'可补充原文':'发送图片、PDF 或输入资料'} value={draft} disabled={busy} onChange={e=>{setDraft(e.target.value);if(imported)setReviewed(false)}}/>
    <div className="chat-compose-tools compact-tools"><input ref={input} aria-label="选择录入文件" type="file" multiple={autonomous} hidden accept=".pdf,.docx,.txt,.tex,.md,.csv,.png,.jpg,.jpeg,.webp,.gif" onChange={e=>{addFiles(e.target.files);e.target.value=''}}/><button ref={plus} type="button" className="composer-plus" aria-label="添加录入资料" aria-expanded={tools} disabled={busy} onClick={()=>setTools(v=>!v)}><Icon name="plus" size={25}/></button>{tools&&<AttachmentMenu anchor={plus.current} onClose={()=>setTools(false)} onFiles={addFiles} onLibrary={autonomous?()=>setLibraryPicker(true):undefined} onQuestions={autonomous?()=>setResourcePicker('question'):undefined} onKnowledge={autonomous?()=>setResourcePicker('knowledge'):undefined} disabled={busy||sourceLoading}/>} <ComposerInference models={models} catalog={catalog} model={model} effort={effort} onModel={v=>{if(v!==model){setModel(v);setEffort('default');rememberModelChoice('work',v,'default')}}} onEffort={v=>{setEffort(v);rememberModelChoice('work',model,v)}} onCatalog={m=>{setCatalog(m);setModels(m.models)}} disabled={busy} effortDisabled={!ready} onOpen={()=>setTools(false)}/><button className="primary composer-send" aria-label="发送资料" disabled={busy||!canSend}><Icon name={busy?'clock':'send-up'} size={21}/></button></div>
   </form>
   {libraryPicker&&<AttachmentDialog title="资料库" onClose={()=>setLibraryPicker(false)}><OriginalPicker disabled={busy} onCancel={()=>setLibraryPicker(false)} onChoose={chooseLibrary}/></AttachmentDialog>}{resourcePicker&&<ResourceAttachmentPicker kind={resourcePicker} onClose={()=>setResourcePicker(undefined)} onChoose={refs=>{setDraft(v=>[v,'引用'+(resourcePicker==='question'?'题目':'知识点')+'（请按编号查询）：'+refs.map(r=>r.code+' '+r.title).join('；')].filter(Boolean).join('\n'));setResourcePicker(undefined)}}/>}
   {home&&!draft.trim()&&!items.length&&<AiHomeShortcuts><button type="button" disabled={busy} onClick={()=>{setDraft('识别资料中的题目，整理后进入录入审核。');area.current?.focus()}}><Icon name="resources" size={17}/> 题目录入</button><button type="button" disabled={busy} onClick={()=>{setDraft('识别资料中的知识点，整理后进入录入审核。');area.current?.focus()}}><Icon name="book" size={17}/> 知识点录入</button><button type="button" disabled={busy} onClick={()=>setLibraryPicker(true)}><Icon name="files" size={17}/> 继续资料工作</button><button type="button" disabled={busy} onClick={()=>{setDraft('在题库中查找');area.current?.focus()}}><Icon name="search" size={17}/> 题库检索</button></AiHomeShortcuts>}

 </section>
}
