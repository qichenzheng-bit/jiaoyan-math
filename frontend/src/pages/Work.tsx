import {useEffect,useRef,useState,type FormEvent} from 'react'
import {useNavigate,useLocation,useSearchParams} from 'react-router-dom'
import {WorkspaceLink as Link,useWorkspaceGuard} from '../components/WorkspaceNavigation'
import {confirmAction} from '../components/WorkspaceConfirm'
import IntakeReview from './Intelligence'
import SourcePicker from '../components/SourcePicker'
import {validModelChoice,type ModelCatalog,type ModelPreferences} from '../components/ReasoningEffort'
import ComposerInference from '../components/ComposerInference'
import {api} from '../auth'
import {getModelCatalog,modelChoice,rememberModelChoice} from '../components/modelCatalog'
import {Icon} from '../components/Icon'
import {MathText} from '../components/MathText'
import type {ImportedMaterial} from '../components/MaterialImport'
type Job={id:string;title:string;state:string}
type Cap={text:boolean;docx:boolean;pdf_text:boolean;pdf_ocr:boolean;image_ocr:boolean}
type FileInfo={id:string;name:string;media_type:string}
const statusNames:Record<string,string>={running:'提取中',review:'待审核',converted:'已生成文档',failed:'失败',stopped:'已停止'}
export default function Work(){const location=useLocation(),[params]=useSearchParams();return params.has('job')||params.has('history')?<IntakeReview key={location.pathname+location.search}/>:<WorkComposer key={location.key}/>}
function WorkComposer(){
 const location=useLocation(),[params]=useSearchParams()
 const navigate=useNavigate(),input=useRef<HTMLInputElement>(null),area=useRef<HTMLTextAreaElement>(null),form=useRef<HTMLFormElement>(null)
 const transferred=(location.state as {intakeDraft?:{text?:string;origin?:string}}|null)?.intakeDraft
 const [draft,setDraft]=useState(transferred?.text??''),[file,setFile]=useState<File>(),[stored,setStored]=useState<FileInfo>(),[imported,setImported]=useState<ImportedMaterial>(),[reviewed,setReviewed]=useState(false)
 const [first,setFirst]=useState(1),[last,setLast]=useState(1),[ocr,setOcr]=useState(false),[tools,setTools]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[jobs,setJobs]=useState<Job[]>([]),[caps,setCaps]=useState<Cap>()
 const [model,setModel]=useState('Auto'),[models,setModels]=useState<ModelCatalog['models']>([]),[catalog,setCatalog]=useState<ModelCatalog>(),[effort,setEffort]=useState('default'),[intent,setIntent]=useState('mixed'),[subject,setSubject]=useState(''),[ready,setReady]=useState(false)
 const [materialSource,setMaterialSource]=useState(params.get('source')??''),[source,setSource]=useState<{message_id:string;session_id:string;role:string;text:string;title:string;has_attachments:boolean}>(),[sourceLoading,setSourceLoading]=useState(Boolean(params.get('from')))
 useEffect(()=>{const id=params.get('from');if(!id)return;const c=new AbortController();const wanted=params.get('intent');if(wanted&&['mixed','question','knowledge','document'].includes(wanted))setIntent(wanted);api<NonNullable<typeof source>>('/intelligence/chat-source/'+encodeURIComponent(id),{signal:c.signal}).then(s=>{if(!c.signal.aborted){setSource(s);setDraft(s.text)}}).catch(e=>{if(!c.signal.aborted)setError(e.message)}).finally(()=>{if(!c.signal.aborted)setSourceLoading(false)});return()=>c.abort()},[params])
 const pdf=Boolean(file?.name.toLowerCase().endsWith('.pdf')),word=Boolean(file?.name.toLowerCase().endsWith('.docx')),image=Boolean(file&&/\.(png|jpe?g|webp|gif)$/i.test(file.name))
 const supported=Boolean(caps&&(image?caps.image_ocr:pdf?(ocr?caps.pdf_ocr:caps.pdf_text):word?caps.docx:caps.text))
 const end=ocr||image?first:pdf||word?last:1
 const validRange=Number.isInteger(first)&&Number.isInteger(end)&&first>=1&&end>=first&&end<=10000&&end-first<(word?100:10)
 useEffect(()=>{const c=new AbortController();api<Job[]>('/intelligence/jobs',{signal:c.signal}).then(j=>setJobs(j.slice(0,3))).catch(()=>{});api<Cap>('/intelligence/import/capabilities',{signal:c.signal}).then(setCaps).catch(e=>setError(e.message));Promise.all([api<ModelPreferences>('/qoder/preferences',{signal:c.signal}),getModelCatalog()]).then(([p,m])=>{if(c.signal.aborted)return;const saved=modelChoice('work',p.model,p.effort??'default');setModel(saved.model);setModels(m.models);setCatalog(m);setEffort(saved.effort);setReady(true)}).catch(e=>{if(!c.signal.aborted)setError(e.message)});return()=>c.abort()},[])
 useEffect(()=>{const el=area.current;if(el){el.style.height='0px';el.style.height=Math.min(Math.max(el.scrollHeight,30),144)+'px'}},[draft])
 useEffect(()=>{if(!tools)return;const close=(e:PointerEvent)=>{if(!form.current?.contains(e.target as Node))setTools(false)};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close)},[tools])
 useWorkspaceGuard({busy,dirty:Boolean(draft.trim()||file||imported),message:'当前资料尚未提交，确认离开？'})
 function clearFile(){setFile(undefined);setStored(undefined);setImported(undefined);setReviewed(false);setFirst(1);setLast(1);setOcr(false)}
 function choose(f:File){clearFile();setSource(undefined);setError('');setFile(f);setLast(f.name.toLowerCase().endsWith('.docx')?100:1);setOcr(/\.(png|jpe?g|webp|gif)$/i.test(f.name));setTools(false)}
 async function submit(e:FormEvent){
   e.preventDefault();if(busy)return;setError('');setBusy(true);setTools(false)
   try{
     if(file&&!imported){
       if(!supported||!validRange)throw new Error('识别组件未就绪或页码范围无效')
       let info=stored
       if(!info){const r=await fetch('/api/files?name='+encodeURIComponent(file.name),{method:'POST',body:file,credentials:'same-origin'});if(!r.ok){const j=await r.json().catch(()=>({}));throw new Error(j.detail||'上传失败')}info=await r.json() as FileInfo;setStored(info)}
       const result=await api<ImportedMaterial>('/intelligence/import',{method:'POST',body:JSON.stringify({file_id:info.id,mode:ocr||image?'ocr':'text',start:pdf||word?first:1,end:pdf||word?end:1})})
       setImported(result);setReviewed(false);setDraft(result.text+(draft.trim()?'\n\n'+draft.trim():''));return
     }
     if(sourceLoading||(!file&&params.has('from')&&!source)||!draft.trim()||!ready||!validModelChoice(catalog,model,effort))throw new Error('请输入资料并选择可用模型')
     if(imported?.warnings.length&&!reviewed)throw new Error('请先对照原始文件核对识别内容')
     if(draft.length>24000)throw new Error('每批最多24000字，请拆分资料')
     const j=await api<Job>('/intelligence/jobs',{method:'POST',body:JSON.stringify({title:(file?.name||draft.trim().split('\n')[0]).slice(0,200),subject,text:draft,model,effort,intent,import_id:imported?.import_id??null,import_reviewed:reviewed,source_id:materialSource||null,source_message_id:imported?null:source?.message_id??null,input_origin:transferred?.origin==='draft'?'chat_draft':'manual'})})
     if(!j.id)throw new Error('未取得录入任务编号')
     navigate('/work?job='+encodeURIComponent(j.id))
   }catch(e){setError(e instanceof Error?e.message:'录入失败')}finally{setBusy(false)}
 }
 const canSend=!sourceLoading&&(!params.has('from')||Boolean(source)||Boolean(file))&&(file&&!imported?supported&&validRange:ready&&Boolean(draft.trim())&&validModelChoice(catalog,model,effort)&&(!imported?.warnings.length||reviewed))
 return <section data-chat-layout="v3" className="chat-workbench clean-chat chat-main-area chat-empty work-chat" aria-label="资料录入">
   {error&&<p className="chat-warning inline-error" role="alert">{error}</p>}{busy&&<p className="muted work-busy-state" role="status">{file&&!imported?"正在上传并提取文件原文…":"正在提交资料整理请求…"}</p>}
   <div className="chat-scroll">{sourceLoading?<p className="muted">正在读取聊天原文…</p>:source||transferred?<div className="work-review-preview"><strong>{source?.role==='assistant'||transferred?.origin==='assistant'?'来自 AI 回复的待核对草稿':'已带入聊天正文'}</strong><p className="muted">请核对正文后发送，附件和题库引用不会自动转入。</p></div>:null}{imported?<div className="work-review-preview"><strong>已识别：{imported.file_name}</strong><p className="muted">请核对下方原文；确认后再次发送，AI 将整理为待审核草稿。</p>{imported.warnings.map(w=><p key={w} className="muted">{w}</p>)}<div className="work-original-preview"><MathText content={draft}/></div>{Boolean(imported.warnings.length)&&<label><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)}/> 已对照原文件核对识别内容</label>}</div>:<div className="chat-home-recent" aria-label="最近录入"><div className="chat-home-heading"><h1>今天要整理什么资料？</h1><p>输入原文或上传图片、PDF、Word，整理后人工审核。</p></div><div className="chat-home-links"><button type="button" disabled={busy} onClick={()=>{setIntent("question");area.current?.focus()}}><Icon name="resources" size={17}/> 题目录入</button><button type="button" disabled={busy} onClick={()=>{setIntent("knowledge");area.current?.focus()}}><Icon name="book" size={17}/> 知识点录入</button><button type="button" disabled={busy||Boolean(file)} onClick={()=>{setIntent("document");input.current?.click()}}><Icon name="files" size={17}/> 整套资料</button></div><Link to="/work?history=1"><Icon name="intake" size={21}/><span>查看录入记录与审核草稿</span></Link>{jobs.map(j=><Link key={j.id} to={'/work?job='+encodeURIComponent(j.id)}><Icon name="clock" size={21}/><span><MathText compact content={j.title}/> · {statusNames[j.state]??j.state}</span></Link>)}</div>}</div>
   <form className="chat-composer compact-composer" ref={form} onSubmit={submit}>
    {file&&<div className="chat-attachments work-file"><span>{file.name}<button type="button" disabled={busy} aria-label="移除资料" onClick={async()=>{if(imported&&!await confirmAction('清空已提取正文？'))return;if(imported)setDraft('');clearFile()}}>×</button></span>{!imported&&(pdf||word)&&<div className="work-file-range">{pdf&&<label><input type="checkbox" checked={ocr} disabled={busy} onChange={e=>{setOcr(e.target.checked);setLast(first)}}/>扫描页 OCR</label>}<label>从<input type="number" min={1} max={10000} value={first} disabled={busy} onChange={e=>{setFirst(Number(e.target.value));setLast(Number(e.target.value))}}/></label>{!ocr&&<label>至<input type="number" min={first} max={Math.min(10000,first+(word?99:9))} value={last} disabled={busy} onChange={e=>setLast(Number(e.target.value))}/></label>}</div>}{!imported&&caps&&!supported&&<p className="muted">服务器缺少所选识别组件，暂不能识别此文件。</p>}</div>}
    <textarea ref={area} aria-label="输入录入资料" rows={1} maxLength={24000} placeholder={file&&!imported?'可补充原文':'发送图片、PDF 或输入资料'} value={draft} disabled={busy} onChange={e=>{setDraft(e.target.value);if(imported)setReviewed(false)}}/>
    <div className="chat-compose-tools compact-tools"><input ref={input} aria-label="选择录入文件" type="file" hidden accept=".pdf,.docx,.txt,.tex,.md,.csv,.png,.jpg,.jpeg,.webp,.gif" onChange={e=>{const f=e.target.files?.[0];if(f)choose(f);e.target.value=''}}/><button type="button" className="composer-plus" aria-label="添加录入资料" aria-expanded={tools} disabled={busy} onClick={()=>setTools(v=>!v)}><Icon name="plus" size={25}/></button>{tools&&<div className="composer-popover" role="group" aria-label="录入工具"><button type="button" disabled={Boolean(file)||sourceLoading} onClick={()=>{setTools(false);input.current?.click()}}><Icon name="upload" size={18}/> 上传图片、PDF 或 Word</button><label className="composer-model">科目提示<input aria-label="科目提示" placeholder="自动逐题识别" value={subject} maxLength={40} onChange={e=>setSubject(e.target.value)}/></label><label className="composer-model">录入目标<select aria-label="录入目标" value={intent} onChange={e=>setIntent(e.target.value)}><option value="mixed">自动识别</option><option value="question">题目</option><option value="knowledge">知识点</option><option value="document">整套资料</option></select></label><SourcePicker value={materialSource} disabled={busy||sourceLoading} subject={subject} onChange={id=>setMaterialSource(id)}/><Link to="/work?history=1"><Icon name="clock" size={18}/> 录入记录</Link></div>}<ComposerInference models={models} catalog={catalog} model={model} effort={effort} onModel={v=>{if(v!==model){setModel(v);setEffort('default');rememberModelChoice('work',v,'default')}}} onEffort={v=>{setEffort(v);rememberModelChoice('work',model,v)}} onCatalog={m=>{setCatalog(m);setModels(m.models)}} disabled={busy} effortDisabled={!ready} onOpen={()=>setTools(false)}/><button className="primary composer-send" aria-label="发送资料" disabled={busy||!canSend}><Icon name={busy?'clock':'send-up'} size={21}/></button></div>
   </form>
 </section>
}
